#!/usr/bin/env python3
"""第一阶段·视觉词典：读项目全剧本 → GLM 生成锁定描述 → 回填角色状态/场景/道具造型库。
用法：python visual_dict.py <project_id> [--base http://localhost:8000] [--model glm-4.6]
"""
from __future__ import annotations
import argparse, json, urllib.error, urllib.request
from pathlib import Path
from glm import chat_json
from http_util import get_all

SYS = """你是微短剧AI视频制作的"视觉词典"专家，同时担任本项目的艺术指导 agent。通读完整剧本后，先在内部统一判断故事类型、时代背景、摄影风格、人物关系、角色气质和主要场景体系，再为给定的角色/场景/物件产出【可直接复制粘贴、供每次AIGC生成复用】的锁定描述。

艺术指导职责：
- 所有锁定描述必须像同一部影片的美术设定：摄影风格、年代质感、色彩基调、材质语言保持一致。
- 每一张角色造型卡都必须符合其年龄、身份、妆发、服装、身体状态、剧情关系和时代背景，不要写成随机人设模板。
- 场景 space_lock 和 lighting 必须符合剧情发生地点的空间逻辑、建筑体系、陈设语言和光影基调，只写可画出的环境细节。
- 物件 appearance_lock 必须符合角色会使用的年代、材质、磨损和叙事功能，不要添加脱离剧本的装饰。若实体描述中含“强关联参考”，照片、屏幕或画框内部的角色与场景内容必须严格保持一致。
- style_statement 由你作为艺术指导提炼，必须短、可复用、能约束后续所有画面风格。

要求（对每一项都写成连贯的一段话，视觉化、可被画出，禁用抽象词）：
- 角色 appearance_lock：性别年龄段、身高体态姿态、发型发色、至少5个面部细节(眉/眼/鼻/唇/颧骨/下颌/肤质/皱纹疤痕痣等)、整体轮廓。精度需让没见过的人能画出八成相似。
- 角色 performance：情绪底色 + 情绪弧线(起点→转折→终点) + 1-2个标志动作 + 声音特征。
- 角色 look_lock：这一张角色状态卡专属的可见信息，包括年龄/身份变化、发型、妆容、服装、鞋履、配饰、污损或伤痕等。服装只在这里写一次；不要写手持物、动作、情绪或剧情含义。**必须点明服装所属年代/款式年代**(如"九十年代末蓝白运动校服")。
- 场景 space_lock：类型(室内外)、空间性质推断、尺度感、布局陈设(用画面方位)、墙面地面材质颜色损耗、材质关键词、氛围关键词，**并带入年代线索**(陈设/建材/物品的年代特征)。
- 场景 lighting：按剧中时段(日/黄昏/夜等)分别写主光源方向色温、明暗分布、色彩基调。
- 物件 appearance_lock：尺寸、形状、颜色、材质、损耗、表面细节(刻痕/锈渍/文字)，**若是有年代感的物件要写明年代款式**。
- 物件 function：一句话叙事功能。
- era_note：**全剧年代感/时代背景**——推断故事所处年代与时代标志物；若存在不同时代/新旧对比(回忆 vs 现在、二十年前 vs 当下)，分别写明各自的年代视觉特征与对比关系。
- style_statement：一句可复制到每个镜头开头的风格声明(影调/对比/暗部亮部色偏/质感)，**并体现年代质感**(如怀旧胶片/年代褪色感，如适用)。

年代感是重点：从剧本线索(服装、物品、场景、台词提到的时间)推断并显式写出年代特征，不要写成无年代的通用画面。
剧本明确写的如实提取；视觉必要但未写的可合理补充。名称必须与给定实体名完全一致，用作 JSON 键。

【角色状态硬规则】
- 名称中“·”后的部分是一个独立角色状态。每个名称都必须单独输出，不得把同名角色的多个状态合并，也不得让不同状态共用一段 look_lock。
- appearance_lock 描述稳定容貌；look_lock 描述这张卡的状态差异。两者不得重复服装、发型等同一细节。
- 场景和物件也遵循“基础 + 状态”标准。每张状态卡保留同一空间结构或同一物件本体，只描述当前状态的光线、天气、陈设、损耗、污损或破损变化。

【场景锁定硬规则】
- 场景就是地点环境，不是剧情摘要。
- scene.space_lock 与 scene.lighting 只写空间、结构、陈设、材质、损耗、光线、天气、年代痕迹。
- 不写人物、角色身份、动作、对白、剧情事件、情绪意义、回忆、幻影或叙事功能。
- 如果场景来自人物动作，请只保留动作发生的地点，并把它转译为空场景环境。"""

USER_TMPL = """【完整剧本】
{script}

【本项目实体（名称必须原样用作键）】
角色：{chars}
场景：{scenes}
物件：{props}

输出 JSON：
{{
  "style_statement": "…",
  "era_note": "全剧年代背景与时代感，含新旧/回忆对比(如适用)",
  "characters": [{{"name":"", "appearance_lock":"", "look_lock":"", "performance":""}}],
  "scenes": [{{"name":"", "space_lock":"", "state_lock":"", "lighting":""}}],
  "props": [{{"name":"", "appearance_lock":"", "state_lock":"", "function":""}}]
}}"""

BASE = "http://localhost:8000/api/v1"


def clean_scene_text(value: str) -> str:
    return (value or "").strip()


def repair_legacy_description_line(value: str) -> str:
    """Recover legacy UTF-8 text that was mistakenly stored as Latin-1 once or twice."""
    repaired = value or ""
    if not any(marker in repaired for marker in ("Ã", "Â", "â", "ã")):
        return repaired
    for _ in range(2):
        try:
            decoded = repaired.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if not decoded or "\ufffd" in decoded or decoded == repaired:
            break
        repaired = decoded
        if any("\u4e00" <= char <= "\u9fff" or char in "【】" for char in repaired):
            break
    return repaired


def description_lines(description: str) -> list[str]:
    return [repair_legacy_description_line(line) for line in (description or "").splitlines()]


def _req(method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data,
                               headers={"Content-Type": "application/json"} if data else {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def get_items(path):
    return get_all(BASE, path)


def patch_desc(entity_type, eid, description):
    c, _ = _req("PATCH", f"/studio/entities/{entity_type}/{eid}", {"description": description})
    return c < 400


def state_relation(description: str) -> str:
    """保留抽取阶段写入的基准/派生关系，避免视觉词典回填后丢失引用链。"""
    for line in description_lines(description):
        if line.startswith("【状态关系】"):
            return line.strip()
    return "【状态关系】基准"


def strong_visual_relation(description: str) -> str:
    """Preserve strong prop relationships written by extraction for image-reference generation."""
    for line in description_lines(description):
        if line.startswith("【强关联参考】"):
            return line.strip()
    return ""


def entity_list(entries):
    return "\n".join(f"- {entry['name']}：{' '.join(description_lines(entry.get('description', '')))}" for entry in entries)


def run(pid: str, model: str):
    chapters = get_items(f"/studio/chapters?project_id={pid}&page_size=100")
    script = "\n\n".join(c.get("raw_text", "") for c in sorted(chapters, key=lambda x: x.get("index", 0)))
    if not script.strip():
        raise SystemExit("项目无剧本正文（chapters.raw_text 为空）")
    chars = get_items(f"/studio/entities/character?project_id={pid}&page_size=100")
    scenes = get_items(f"/studio/entities/scene?project_id={pid}&page_size=100")
    props = get_items(f"/studio/entities/prop?project_id={pid}&page_size=100")

    print(f"[视觉词典] 项目 {pid}｜剧本 {len(script)} 字｜角色 {len(chars)} 场景 {len(scenes)} 物件 {len(props)}｜模型 {model}")
    print("  调 GLM 生成锁定描述…（长上下文，约 30-90s）")
    user = USER_TMPL.format(
        script=script,
        chars=entity_list(chars),
        scenes=entity_list(scenes),
        props=entity_list(props),
    )
    vd = chat_json(SYS, user, model=model, temperature=0.7, timeout=420)

    Path(__file__).with_name(f"visual-dict-{pid}.json").write_text(
        json.dumps(vd, ensure_ascii=False, indent=2), encoding="utf-8")

    by = lambda arr: {x.get("name"): x for x in arr}
    vc, vs, vp = by(vd.get("characters", [])), by(vd.get("scenes", [])), by(vd.get("props", []))

    print("  回填造型库：")
    ok = fail = miss = 0
    for c in chars:
        d = vc.get(c["name"])
        if not d:
            print(f"    ! [角色] {c['name']} 在词典中无同名项(GLM 改写了名称?)，跳过回填")
            miss += 1
            continue
        # 静态造型图只读取稳定外貌和当前状态，表演基线留在词典 JSON 供后续视频链路使用。
        desc = "\n".join(part for part in [
            f"【角色基础】{(d.get('appearance_lock') or '').strip()}" if (d.get("appearance_lock") or "").strip() else "",
            f"【造型状态】{(d.get('look_lock') or '').strip()}" if (d.get("look_lock") or "").strip() else "",
            state_relation(c.get("description", "")),
        ] if part)
        if patch_desc("character", c["id"], desc):
            ok += 1
            print(f"    [角色造型] {c['name']} ← 外貌+状态锁定({len(desc)}字，表演基线不入生图)")
        else:
            fail += 1
            print(f"    ✗ [角色造型] {c['name']} 锁定描述回填失败(HTTP≥400)")
    for s in scenes:
        d = vs.get(s["name"])
        if not d:
            print(f"    ! [场景] {s['name']} 在词典中无同名项(GLM 改写了名称?)，跳过回填")
            miss += 1
            continue
        desc = "\n".join(part for part in [
            f"【场景基础】{clean_scene_text(d.get('space_lock', ''))}" if clean_scene_text(d.get("space_lock", "")) else "",
            f"【场景状态】{clean_scene_text(d.get('state_lock', ''))}" if clean_scene_text(d.get("state_lock", "")) else "",
        ] if part)
        if d.get("lighting"):
            lighting = clean_scene_text(d["lighting"])
            if lighting:
                desc += "\n\n【光照】" + lighting
        desc = "\n".join(part for part in [desc, state_relation(s.get("description", ""))] if part)
        if patch_desc("scene", s["id"], desc):
            ok += 1
            print(f"    [场景] {s['name']} ← 空间+光照锁定({len(desc)}字)")
        else:
            fail += 1
            print(f"    ✗ [场景] {s['name']} 回填失败(HTTP≥400)")
    for p in props:
        d = vp.get(p["name"])
        if not d:
            print(f"    ! [物件] {p['name']} 在词典中无同名项(GLM 改写了名称?)，跳过回填")
            miss += 1
            continue
        desc = "\n".join(part for part in [
            f"【道具基础】{(d.get('appearance_lock') or '').strip()}" if (d.get("appearance_lock") or "").strip() else "",
            f"【道具状态】{(d.get('state_lock') or '').strip()}" if (d.get("state_lock") or "").strip() else "",
        ] if part)
        if d.get("function"):
            desc += "\n\n【叙事功能】" + d["function"]
        desc = "\n".join(part for part in [
            desc,
            state_relation(p.get("description", "")),
            strong_visual_relation(p.get("description", "")),
        ] if part)
        if patch_desc("prop", p["id"], desc):
            ok += 1
            print(f"    [物件] {p['name']} ← 外观锁定({len(desc)}字)")
        else:
            fail += 1
            print(f"    ✗ [物件] {p['name']} 回填失败(HTTP≥400)")

    print(f"\n=== 完成：回填成功 {ok}｜失败 {fail}｜名称未匹配跳过 {miss} ===")
    print(f"风格声明：{vd.get('style_statement', '')}")
    print(f"年代感：{vd.get('era_note', '(未提取)')}")
    print(f"完整词典已存：bridge/visual-dict-{pid}.json（供第二阶段视听单元复用）")
    if fail:
        raise SystemExit(f"✗ 有 {fail} 项回填失败，请检查后端/实体 id 后重跑")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pid")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--model", default="glm-4.6")
    a = ap.parse_args()
    globals()["BASE"] = a.base.rstrip("/") + "/api/v1"
    run(a.pid, a.model)
