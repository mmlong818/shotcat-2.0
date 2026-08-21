#!/usr/bin/env python3
"""剧本贯通桥：读取一份结构化故事圣经 JSON，
把它灌进 Jellyfish 底座：建项目 → 建场景/道具/服装/角色实体 → 每集建章节并切分镜。

只依赖标准库（urllib）。用法：
    python import_to_jellyfish.py <story_bible.json> [--base http://localhost:8000] [--async]

设计取舍：
- 实体 id 直接沿用故事圣经里的 char_001/scene_001（与 Jellyfish EntityMerger 同构），
  故本桥不做 id 重映射，保证一致性契约贯穿始终。
- 默认用同步 /divide 便于即时看到分镜结果；--async 走任务队列（Celery）。
- 幂等性：当前不做，重复导入会因唯一约束报错，测试请对空库/新项目 id 运行。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from http_util import get_all

# 视觉表现：故事圣经枚举 → Jellyfish 中文枚举
VISUAL_STYLE_MAP = {"live_action": "现实", "anime": "动漫"}
VALID_STYLES = {"真人都市", "真人科幻", "真人古装", "动漫科幻", "动漫3D", "国漫", "水墨画"}
DEFAULT_STYLE = "真人都市"


class Api:
    """极简 Jellyfish API 客户端。"""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def _call(self, method: str, path: str, body: dict | None = None, timeout: int = 180):
        """返回 (http_status, payload_dict)；HTTP 错误也返回而非抛出，交由上层判定。"""
        url = f"{self.base}/api/v1{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"message": raw[:500]}

    def post(self, path: str, body: dict, timeout: int = 180) -> dict:
        code, payload = self._call("POST", path, body, timeout)
        if code >= 400:
            raise SystemExit(f"[HTTP {code}] POST {path}\n  {payload.get('message')}")
        return payload

    def put(self, path: str, body: dict) -> dict:
        code, payload = self._call("PUT", path, body)
        if code >= 400:
            raise SystemExit(f"[HTTP {code}] PUT {path}\n  {payload.get('message')}")
        return payload

    def create_idempotent(self, path: str, body: dict) -> str:
        """幂等创建：'已存在'视为跳过。返回 'created' / 'exists'。"""
        code, payload = self._call("POST", path, body)
        if code < 400:
            return "created"
        msg = str(payload.get("message", ""))
        if "already exists" in msg or "已存在" in msg:
            return "exists"
        raise SystemExit(f"[HTTP {code}] POST {path}\n  {msg}")

    def wait_get(self, path: str, *, tries: int = 30) -> None:
        """轮询 GET 直到 200，跨越 Jellyfish commit-after-yield 的时序缝隙。
        每次间隔 0.5s（30 次≈15s 窗口）。"""
        for _ in range(tries):
            code, _payload = self._call("GET", path, None, timeout=10)
            if code == 200:
                return
            time.sleep(0.5)
        raise SystemExit(f"依赖对象未就绪（超时）：GET {path}")

    def poll_shots(self, chapter_id: str, task_id: str | None = None, *, tries: int = 120) -> int:
        """轮询章节 shots 直到 worker 写入（异步 divide 完成）。返回分镜全量数；
        若给了 task_id 则同时查 divide 任务状态，任务 failed 立即抛错停止等待；
        超时返回 -1（哨兵，交由上层判失败，避免谎报成功）。"""
        for _ in range(tries):
            if task_id:
                tc, tp = self._call("GET", f"/film/tasks/{task_id}/status", None, timeout=10)
                if tc == 200 and (tp.get("data") or {}).get("status") == "failed":
                    raise SystemExit(f"divide 任务 {task_id} 报告失败，停止等待（章节 {chapter_id}）")
            code, payload = self._call("GET", f"/studio/shots?chapter_id={chapter_id}&page_size=100", None, timeout=15)
            if code == 200 and payload.get("data", {}).get("items"):
                # 有分镜后按分页信封拉全量，避免单页 100 截断
                return len(get_all(f"{self.base}/api/v1", f"/studio/shots?chapter_id={chapter_id}"))
            time.sleep(3)
        return -1


def build_style(project: dict) -> tuple[str, str]:
    """从故事圣经 project 段解析 (style, visual_style)，非法值回退默认。"""
    style = project.get("style") or DEFAULT_STYLE
    if style not in VALID_STYLES:
        print(f"  ! style {style!r} 非 Jellyfish 合法枚举，回退 {DEFAULT_STYLE}")
        style = DEFAULT_STYLE
    visual = VISUAL_STYLE_MAP.get(project.get("visual_style", "live_action"), "现实")
    return style, visual


def run(bible_path: str, base: str, use_async: bool) -> None:
    bible = json.load(open(bible_path, encoding="utf-8"))
    api = Api(base)
    project = bible["project"]
    sb = bible["story_bible"]
    style, visual = build_style(project)
    pid = project.get("id", "project_001")
    # 实体 id 加项目前缀：id 是全局主键，跨项目必须唯一（否则两项目的 char_001 冲突）
    def pfx(raw: str) -> str:
        return f"{pid}__{raw}"

    # 1) 项目（建后轮询直到可见，跨越 commit-after-yield 时序缝隙）
    st = api.create_idempotent("/studio/projects", {
        "id": pid, "name": project["title"], "style": style, "visual_style": visual,
        "description": project.get("logline", ""),
    })
    api.wait_get(f"/studio/projects/{pid}")
    print(f"[项目] {pid} 《{project['title']}》 style={style}/{visual} ({st})")

    def create_asset(entity_type: str, eid: str, name: str, desc: str) -> None:
        st = api.create_idempotent(f"/studio/entities/{entity_type}", {
            "id": eid, "name": name, "description": desc,
            "style": style, "visual_style": visual, "project_id": pid,
        })
        print(f"  [{entity_type}] {eid} {name} ({st})")

    # 2) 场景 / 道具（项目级资产）
    for sc in sb.get("scenes", []):
        create_asset("scene", pfx(sc["id"]), sc["name"], sc.get("visual_description", ""))
    for pr in sb.get("props", []):
        create_asset("prop", pfx(pr["id"]), pr["name"], pr.get("visual_description", ""))

    # 3) 角色：先按 default_costume 建服装，再建角色并绑定 costume_id
    for i, ch in enumerate(sb.get("characters", []), 1):
        costume_id = None
        if ch.get("default_costume"):
            costume_id = pfx(f"cos_{i:03d}")
            create_asset("costume", costume_id, f"{ch['name']}-默认服装", ch["default_costume"])
            api.wait_get(f"/studio/entities/costume/{costume_id}")  # 服装提交后再绑定到角色
        body = {
            "id": pfx(ch["id"]), "name": ch["name"],
            "description": ch.get("appearance", "") or ch.get("external_want", ""),
            "style": style, "visual_style": visual, "project_id": pid,
        }
        if costume_id:
            body["costume_id"] = costume_id
        st = api.create_idempotent("/studio/entities/character", body)
        print(f"  [character] {ch['id']} {ch['name']} ({ch.get('story_role','')})"
              + (f" +服装{costume_id}" if costume_id else "") + f" ({st})")

    # 4) 每集：建章节 → 切分镜
    #    默认走异步（Celery worker）：divide 不阻塞 web、不受 HTTP 超时限制；
    #    投递后轮询该章节的 shots 直到出现，确认 worker 已写库。
    episodes = bible.get("script", {}).get("episodes", [])
    total_shots = 0
    failed_eps = []  # 超时/任务失败的集，最后据此非零退出
    for ep in episodes:
        idx = ep["index"]
        cid = f"{pid}_ch{idx:02d}"
        ch_st = api.create_idempotent("/studio/chapters", {
            "id": cid, "project_id": pid, "index": idx,
            "title": ep.get("title", f"第{idx}集"), "raw_text": ep["body"],
        })
        api.wait_get(f"/studio/chapters/{cid}")  # 确保章节已提交再切分镜
        if ch_st == "exists":
            print(f"  [章节] {cid} 第{idx}集 章节已存在，跳过切镜（如需重切用 shot_breakdown.py）")
            continue
        path = "/script-processing/divide-async" if use_async else "/script-processing/divide"
        res = api.post(path, {"script_text": ep["body"], "write_to_db": True, "chapter_id": cid})
        if use_async:
            task = res["data"].get("task_id")
            print(f"  [章节] {cid} 第{idx}集 → divide 任务投递 task={task}，等待 worker 切分镜…")
            n = api.poll_shots(cid, task_id=task)
            if n < 0:
                print(f"           ✗ 第{idx}集 等待超时且未见分镜，记为失败")
                failed_eps.append(idx)
            else:
                total_shots += n
                print(f"           worker 完成 → {n} 个分镜")
        else:
            n = res["data"].get("total_shots", len(res["data"].get("shots", [])))
            total_shots += n
            print(f"  [章节] {cid} 第{idx}集 → 切出 {n} 个分镜")

    print("\n=== 导入完成 ===")
    print(f"项目 {pid} ｜ 场景 {len(sb.get('scenes',[]))} ｜ 道具 {len(sb.get('props',[]))} "
          f"｜ 角色 {len(sb.get('characters',[]))} ｜ 集 {len(episodes)} ｜ 分镜合计 {total_shots}")
    print(f"打开 http://localhost:7788 查看项目《{project['title']}》")
    if failed_eps:
        raise SystemExit(f"✗ 以下集未产出分镜(超时或任务失败)，请检查 worker/任务日志：{failed_eps}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bible")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--sync", dest="use_async", action="store_false",
                    help="强制同步 divide（会阻塞 web、受 HTTP 超时限制，不推荐）")
    ap.set_defaults(use_async=True)
    a = ap.parse_args()
    run(a.bible, a.base, a.use_async)
