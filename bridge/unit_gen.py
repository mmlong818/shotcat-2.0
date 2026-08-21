#!/usr/bin/env python3
"""第二阶段·视听单元：为项目每个镜头生成自足的视听描述（内嵌视觉词典），
可喂图像/图生视频模型。单元按合理情节断点，时长由内容决定，不设 15s 硬顶。
依赖第一阶段产物 bridge/visual-dict-<pid>.json。
用法：python unit_gen.py <project_id> [--model glm-4.6]
"""
from __future__ import annotations
import argparse, json, urllib.error, urllib.request
from pathlib import Path
from glm import chat_json
from http_util import get_all

SYS = """你是微短剧AI视频制作的"视听单元"专家。为【一个镜头】产出可直接喂给图像/图生视频模型的自足视听描述。

规则：
- 单元边界依据合理情节的自然断点（情绪完成/信息落点/动作闭环/场景边界/节奏换气），不强调固定秒数。
- 时长由内容自然决定：给一个建议时长(秒)，并理解实际时长视所用视频模型上限而定，不强求15秒上限。
- av_description：一段按时间顺序的连贯文字（≤600字），不设独立区块、不分类罗列。第一句为风格声明（用给定 style_statement）。角色/物件首次出现时，把给定的锁定外貌+服装/外观原样内嵌。表演-台词-声音写在一起；镜头行为融入动作（不单独声明景别机位）；情绪用可见细节传达；色彩光照具体化（给具体色名/色温）。
- in_anchor/out_anchor：入帧、出帧的（角色位置/朝向/姿态/物件状态/表情/光照）。
- link_from/link_to：与上/下镜头的承接与递出。
输出 JSON。"""

USER_TMPL = """【风格声明】{style}
【年代感/时代背景（必须在画面中体现）】{era}

【本镜头】第{idx}镜：{title}
剧本摘录：{excerpt}
上一镜：{prev}
下一镜：{nxt}

【可复用的视觉词典（原样内嵌，不要改写）】
角色：
{chars}
场景：
{scenes}
物件：
{props}

输出 JSON：
{{"duration_hint": "建议时长(秒)+一句依据", "av_description": "…", "in_anchor": "…", "out_anchor": "…", "link_from": "…", "link_to": "…"}}"""

BASE = "http://localhost:8000/api/v1"


def _req(method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data,
                               headers={"Content-Type": "application/json"} if data else {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def items(path):
    return get_all(BASE, path)


def brief(arr, keys):
    """把词典项压成 '名称：字段…' 的文本块，供内嵌。"""
    out = []
    for x in arr:
        parts = [x.get("name", "")]
        for k in keys:
            if x.get(k):
                parts.append(x[k])
        out.append("- " + "｜".join(parts))
    return "\n".join(out) or "（无）"


def run(pid: str, model: str):
    vdf = Path(__file__).with_name(f"visual-dict-{pid}.json")
    if not vdf.exists():
        raise SystemExit(f"缺少视觉词典 {vdf.name}，请先跑 visual_dict.py {pid}")
    vd = json.loads(vdf.read_text(encoding="utf-8"))
    style = vd.get("style_statement", "")
    era = vd.get("era_note", "")
    chars_txt = brief(vd.get("characters", []), ["appearance_lock", "costume"])
    scenes_txt = brief(vd.get("scenes", []), ["space_lock", "lighting"])
    props_txt = brief(vd.get("props", []), ["appearance_lock"])

    chapters = sorted(items(f"/studio/chapters?project_id={pid}&page_size=100"), key=lambda c: c.get("index", 0))
    shots = []
    for ch in chapters:
        shots += sorted(items(f"/studio/shots?chapter_id={ch['id']}&page_size=100"), key=lambda s: s.get("index", 0))
    if not shots:
        raise SystemExit("项目无分镜")

    print(f"[视听单元] 项目 {pid}｜镜头 {len(shots)}｜模型 {model}（按情节断点，时长由内容定，不锁15s）")
    units = []
    for i, s in enumerate(shots):
        prev = shots[i - 1].get("title", "") if i > 0 else "（本镜为开场）"
        nxt = shots[i + 1].get("title", "") if i < len(shots) - 1 else "（本镜为结尾）"
        user = USER_TMPL.format(style=style, era=era or "(见剧本推断)", idx=s.get("index", i + 1), title=s.get("title", ""),
                                excerpt=s.get("script_excerpt", ""), prev=prev, nxt=nxt,
                                chars=chars_txt, scenes=scenes_txt, props=props_txt)
        try:
            u = chat_json(SYS, user, model=model, temperature=0.75, timeout=240)
        except Exception as e:
            print(f"    镜{s.get('index')} 生成失败：{str(e)[:60]}"); continue
        u["shot_id"] = s["id"]; u["index"] = s.get("index"); u["title"] = s.get("title")
        units.append(u)
        print(f"    镜{s.get('index')} 《{s.get('title','')[:16]}》 → {len(u.get('av_description',''))}字｜{u.get('duration_hint','')[:20]}")

    Path(__file__).with_name(f"units-{pid}.json").write_text(
        json.dumps({"style_statement": style, "units": units}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 完成 {len(units)}/{len(shots)} 个视听单元 → bridge/units-{pid}.json ===")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pid")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--model", default="glm-4.6")
    a = ap.parse_args()
    globals()["BASE"] = a.base.rstrip("/") + "/api/v1"
    run(a.pid, a.model)
