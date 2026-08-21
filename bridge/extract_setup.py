#!/usr/bin/env python3
"""从剧本抽取设定：读项目全剧本 → GLM 抽取 角色/场景/道具 → 建实体(项目级)。
供"剧本页"一键使用；抽完可再跑 视觉词典(锁定细化) 与 AI拆镜头。
用法：python extract_setup.py <project_id> [--model glm-4.6]
"""
from __future__ import annotations
import argparse, json, re, time, urllib.error, urllib.request
from glm import chat_json
from http_util import get_all

SYS = """你是剧本设定抽取专家，同时担任本项目的艺术指导 agent。必须完整通读剧本后再输出，不得边读边列资产。

严格按以下三阶段在内部完成分析，最终只输出 JSON：
1. 全文分类：先建立角色身份、物理场景、可移动关键道具三份基础实体清单。此时不要拆年龄、服装、时间、天气、开合或损坏状态。
2. 全局去重：逐项回看全文，合并同一身份、同一物理空间、同一件物品。角色的本名、昵称、青年/老年称呼、幻象或回忆称呼若指向同一人，必须合并为一个角色并写入 aliases；同一地点的日/夜/持续/稍后必须先归为一个场景；同一道具的开合、内容物或磨损变化必须先归为一个道具。完成去重前禁止创建派生状态。
3. 派生拆分：只对去重后的每个基础实体检查是否确有值得单独生成参考图的视觉变化，再建立 looks/states。语义相同但措辞不同的状态必须合并，每个实体只保留一个基准状态。

输出前必须自检：基础实体无重复；aliases 不会再作为独立角色输出；同一物理地点不会因场次或时间重复；同一道具不会因状态重复；每个状态族恰好一个 is_base=true；同族 state_key 唯一且稳定。

艺术指导职责：
- 统筹所有抽取结果，让角色、场景、道具和服装符合同一个剧本、同一种年代质感、同一套摄影/美术风格。
- 角色描述必须符合角色年龄、身份、气质和剧情关系，不要写成随机美女/帅哥模板。
- 场景描述必须符合剧情发生地点的空间逻辑、时代痕迹和材质体系，不要把人物状态或剧情事件写进场景。
- 道具和服装必须服务角色身份、年代背景和剧情用途，不要添加脱离剧本的装饰性物品。

【强关联道具规则】
- 只有道具本身展示、记录或承载画面内容时才填写 visual_content，例如照片、毕业照、手机屏幕、监视器画面、画框、证件照、海报或带人物/地点图像的书页。
- visual_content.characters 和 visual_content.scenes 只能填写该道具内部画面中实际可见的角色与地点；普通手机、普通书本、纸条、钥匙等没有图像内容的道具必须留空，不能因为使用者或出现地点而强行关联。
- description 要说明道具内部画面应呈现什么，不重复道具本体材质；后续生成会将列出的角色与场景设定图作为强参考，必须与剧情一致。
【角色造型拆解硬规则】
- 一个角色不是一张“默认造型”。先识别剧本中所有可见且会影响生图一致性的状态组合，再分别输出到 looks。
- 每个状态必须由剧本证据支持，至少包含年龄/时期、身份、服装、发型或妆造、身体状态中的必要项；例如“少年学生时期·校服”“成年职场时期·通勤造型”“雨后淋湿状态”。
- 只在外观确实不同或剧情需要锁定时拆分。短暂情绪、单次动作、手持道具、镜头景别不能单独形成造型状态。
- 同一角色在不同年龄、时代、身份、特殊服装、明显妆发或受伤/污损状态下，必须拆成不同状态；状态名称短、具体且彼此不重复。
- base_appearance 只写稳定外貌；looks.description 只写该状态新增或需要锁定的可见信息。服装属于角色状态，不单独输出“默认服装”。
- 场景和道具遵循同一规则：空间/物件本体写在基础描述，时间、天气、使用痕迹、损坏或陈设变化等写在 states。只有视觉上确实不同的状态才拆分。
- 每个角色、场景、道具状态都必须指定且仅指定一个 is_base=true 的基准状态。其他状态必须以这张基准图为参考生成，保持同一张脸、同一空间结构或同一物件本体。

【是否拆分派生状态】
- 先判断“是否值得单独生成参考图”，而不是见到任何变化就拆资产。基础资产可被多个镜头复用；镜头自身的提示词负责修正本镜头的时段、光线、天气、情绪和动作。
- 角色：只有年龄/时代变化、身份转换、持续或剧情关键的服装妆发变化、明显伤病/污损、伪装等会改变识别或连续性的情况，才拆为派生状态。一次性的表情、姿势、轻微凌乱、普通日夜光线不拆。
- 场景：只有空间结构、年代、季节、核心陈设、长期损坏/改造、灾后状态等发生明显变化，或该状态会在多个镜头复用时，才拆为派生状态。仅一次出现的日夜、晨昏、轻微阴晴/雨雪、普通灯光开关，不拆新场景图，保留同一基础场景并由镜头提示词描述。
- 道具：只有本体外观、尺寸、内容物、可见损坏或关键文字发生持续且重要的变化时才拆。一次性的摆放方向、拿取动作、轻微反光不拆。
- 拆分不确定时默认复用基准资产；宁少拆、不要为一次性小差异生成孤立资产。每个输出 states 条目都必须是“需要单独参考图”的状态，不要列出由镜头提示词即可修正的微小变化。

抽取：
- 角色：所有有台词或明确动作的人物。
- 角色身份按“叙事中的同一个人”判断，而不是按剧本中的称呼判断。例如“周诚/小周”若是同一人的现在与过去，只输出一个角色，两个时期放进该角色的 looks。
- 场景：按独立物理地点分类；同地点的场次、持续、稍后和普通日夜变化仍是同一场景，只在空间结构或长期陈设确有显著变化时拆派生状态。
- 物件（道具）判据——三选一才算，其余不列：①能被角色拿起/携带/递出/操作的可移动物品；②被台词点名或成为镜头/情节焦点的物品；③承载象征意义、推动情节的物品。
  【明确排除】车辆/房屋/门/窗/百叶窗/桌椅/沙发/地毯/方向盘/仪表/计价器/家具/建筑构件等固定或场景固有物，一律归入场景描述，绝不单列为道具。宁缺毋滥，只保留真正影响剧情的关键道具（通常一集 2-4 个）。
名称一律用剧本原文；描述写视觉化简述（后续会锁定细化，不必很长）。
【场景描述硬规则】
- 场景就是地点环境，不是剧情摘要。
- 只写地点类型、空间结构、方位布局、建筑/地面/墙面/门窗/树木/陈设/材质、光线、天气、年代痕迹。
- 不写任何人物、角色身份、动作、对白、剧情事件、回忆、幻影、情绪意义或叙事功能。
- 如果剧本只提供人物动作，请只保留动作发生的地点名称，并把描述写成空场景环境。
只输出 JSON。"""

USER_TMPL = """【完整剧本】
{script}

输出 JSON：
{{
  "characters": [{{"name":"全文统一后的角色本名", "aliases":["指向同一人的其他称呼"], "base_appearance":"角色不随状态改变的外貌基础（性别、五官、体态、稳定发型特征等；不要写服装或手持物）", "looks":[{{"state_key":"稳定、简短的语义键，如 youth_student / adult_return", "label":"造型状态名称（如少年学生时期·校服 / 成年职场时期·通勤造型）", "description":"这一状态下可见的年龄、身份、发型、妆容、服装、身体状态和年代细节", "is_base":true}}]}}],
  "scenes": [{{"name":"去掉日夜和场次后统一的物理地点名", "aliases":["同一地点的其他写法"], "base_description":"空场景的稳定空间结构、建筑/地面/墙面/陈设/材质与年代痕迹；不得含人物、动作、剧情", "states":[{{"state_key":"稳定、简短的语义键，如 base / damaged", "label":"场景状态名称（如基础状态 / 灾后损毁）", "description":"仅写值得单独生成参考图的结构、陈设或长期损耗变化；普通日夜光线不单独拆分", "is_base":true}}]}}],
  "props": [{{"name":"去掉开合和损坏状态后统一的道具名", "aliases":["同一道具的其他写法"], "base_description":"道具本体的稳定形态、尺寸、材质与年代特征", "states":[{{"state_key":"稳定、简短的语义键，如 closed / open_with_contents", "label":"物品状态名称（如闭合完好 / 打开露出内容物）", "description":"仅写值得单独生成参考图的污损、破损、内容物或表面变化", "is_base":true}}], "visual_content":{{"description":"仅当道具本身展示/记录/承载角色或场景内容时，写出其中可见内容；普通道具留空", "characters":["只填写该道具中实际可见的角色名"], "scenes":["只填写该道具中实际可见的场景名"]}}}}]
}}"""

BASE = "http://localhost:8000/api/v1"


def clean_scene_text(value: str) -> str:
    # Do not try to maintain an endless blocklist here. Scene descriptions
    # are generated upstream as environment-only text; if empty, callers fall
    # back to the scene name.
    return (value or "").strip()


def _req(m, p, b=None, t=40):
    data = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(BASE + p, data=data, headers={"Content-Type": "application/json"} if data else {}, method=m)
    try:
        with urllib.request.urlopen(r, timeout=t) as x:
            return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def items(p):
    return get_all(BASE, p)


def _identity_names(entry: dict) -> list[str]:
    """返回实体的统一名称和别名，用于跨称呼合并同一基础实体。"""
    aliases = entry.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    values = [entry.get("name"), *aliases]
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def _family_root(asset_name: str) -> str:
    """从平铺资产名中取出去重后的基础实体名称。"""
    return str(asset_name or "").split(" · ", 1)[0].strip()


def _ordered_variants(entry: dict, fallback_label: str) -> list[dict]:
    """规范状态顺序、state_key 和唯一基准状态。"""
    raw_variants = entry.get("states") or entry.get("looks") or []
    variants = [dict(item) for item in raw_variants if isinstance(item, dict) and str(item.get("label") or "").strip()]
    if not variants:
        variants = [{"state_key": "base", "label": fallback_label, "description": "", "is_base": True}]

    deduped: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(variants):
        label = str(item.get("label") or fallback_label).strip()
        state_key = str(item.get("state_key") or ("base" if item.get("is_base") else label)).strip().lower()
        normalized_key = re.sub(r"[^\w\u4e00-\u9fff]+", "", state_key)
        if not normalized_key:
            normalized_key = f"state{index + 1}"
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        item["state_key"] = state_key
        item["label"] = label
        deduped.append(item)

    base_index = next((index for index, item in enumerate(deduped) if item.get("is_base") is True), 0)
    for index, item in enumerate(deduped):
        item["is_base"] = index == base_index
    return [deduped[base_index], *deduped[:base_index], *deduped[base_index + 1:]]


def _merge_entity_entries(entries: list, *, fallback_label: str) -> list[dict]:
    """按统一名称和 aliases 合并模型仍可能重复输出的基础实体。"""
    groups: list[dict] = []
    group_names: list[set[str]] = []
    for raw in entries:
        if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
            continue
        entry = dict(raw)
        identities = set(_identity_names(entry))
        match_index = next((index for index, names in enumerate(group_names) if identities & names), None)
        if match_index is None:
            groups.append(entry)
            group_names.append(identities)
            continue
        group = groups[match_index]
        group_names[match_index].update(identities)
        group["aliases"] = [name for name in group_names[match_index] if name != group.get("name")]
        variants_key = "looks" if "looks" in group or "looks" in entry else "states"
        group[variants_key] = [*(group.get(variants_key) or []), *(entry.get(variants_key) or [])]
        for field in ("base_appearance", "base_description", "appearance", "description"):
            if len(str(entry.get(field) or "")) > len(str(group.get(field) or "")):
                group[field] = entry[field]

    for group, identities in zip(groups, group_names):
        group["aliases"] = [name for name in identities if name != group.get("name")]
        variants_key = "looks" if "looks" in group else "states"
        group[variants_key] = _ordered_variants(group, fallback_label)
    return groups


def create_idem(path, body):
    c, r = _req("POST", path, body)
    if c < 400:
        return "created"
    msg = str(r.get("message", ""))
    if "already exists" in msg or "已存在" in msg:
        return "exists"
    raise RuntimeError(f"{path} 保存失败：HTTP {c} {msg[:120]}")


def wait_get(path, tries=30):
    for _ in range(tries):
        if _req("GET", path)[0] == 200:
            return
        time.sleep(0.5)
    raise SystemExit(f"依赖未就绪 {path}")


def run(pid: str, model: str):
    proj = _req("GET", f"/studio/projects/{pid}")[1].get("data") or {}
    if not proj:
        raise SystemExit(f"项目 {pid} 不存在")
    style = proj.get("style") or "真人都市"
    visual = proj.get("visual_style") or "现实"
    chapters = sorted(items(f"/studio/chapters?project_id={pid}&page_size=100"), key=lambda c: c.get("index", 0))
    script = "\n\n".join(c.get("raw_text", "") for c in chapters)
    if not script.strip():
        raise SystemExit("项目无剧本正文，请先在剧本页粘贴剧本")

    print(f"[抽取设定] 项目 {pid}｜剧本 {len(script)} 字｜模型 {model}")
    data = chat_json(SYS, USER_TMPL.format(script=script), model=model, temperature=0.5, timeout=420)

    def pfx(raw):
        return f"{pid}__{raw}"

    def asset(etype, eid, name, desc):
        return create_idem(f"/studio/entities/{etype}", {
            "id": eid, "name": name, "description": desc,
            "style": style, "visual_style": visual, "project_id": pid,
        })

    # 重跑稳定性：按“基础实体家族”同步现有记录，不再把模型换一种状态措辞
    # 当作新资产；新 id 只从现有最大序号之后分配。
    def alloc(etype, kw):
        """读取某类现有实体并初始化同步状态。"""
        existing = items(f"/studio/entities/{etype}?project_id={pid}&page_size=100")
        pat = re.compile(rf"^{re.escape(pid)}__{re.escape(kw)}_(\d+)$")
        mx = max((int(m.group(1)) for e in existing for m in [pat.match(e.get("id", ""))] if m), default=0)
        return {"existing": existing, "pattern": pat, "max": mx, "claimed": set(), "removed": set()}

    def next_id(state, kw):
        """为同步中新出现的状态分配下一个稳定 ID。"""
        state["max"] += 1
        return pfx(f"{kw}_{state['max']:03d}")

    sc = _merge_entity_entries(data.get("scenes", []), fallback_label="基础状态")
    pr = _merge_entity_entries(data.get("props", []), fallback_label="基础状态")
    ch = _merge_entity_entries(data.get("characters", []), fallback_label="剧本当前造型")
    sc_state = alloc("scene", "scene")
    pr_state = alloc("prop", "prop")
    ch_state = alloc("character", "char")

    def update_asset(entity_type, entity_id, name, description):
        """更新已匹配的资产；任一失败立即终止整步抽取。"""
        code, response = _req(
            "PATCH",
            f"/studio/entities/{entity_type}/{entity_id}",
            {"name": name, "description": description},
        )
        if code >= 400:
            raise RuntimeError(
                f"/studio/entities/{entity_type}/{entity_id} 更新失败：HTTP {code} "
                f"{str(response.get('message', ''))[:120]}"
            )

    def delete_asset(entity_type, entity):
        """删除不再属于最新全文分类结果的旧状态资产。"""
        entity_id = str(entity.get("id") or "")
        code, response = _req("DELETE", f"/studio/entities/{entity_type}/{entity_id}")
        if code >= 400:
            raise RuntimeError(
                f"/studio/entities/{entity_type}/{entity_id} 删除失败：HTTP {code} "
                f"{str(response.get('message', ''))[:120]}"
            )

    def stored_state_key(entity):
        """从已保存描述中读取稳定状态键，兼容没有该字段的旧记录。"""
        for line in str(entity.get("description") or "").splitlines():
            if line.startswith("【状态键】"):
                return line.removeprefix("【状态键】").strip().lower()
        return ""

    def delete_entities(entity_type, state, entities):
        """先删派生状态再删基准，避免旧引用链阻止清理。"""
        ordered = sorted(
            entities,
            key=lambda item: 0 if "【状态关系】派生自：" in str(item.get("description") or "") else 1,
        )
        for entity in ordered:
            entity_id = str(entity.get("id") or "")
            if not entity_id or entity_id in state["removed"]:
                continue
            delete_asset(entity_type, entity)
            state["removed"].add(entity_id)

    def store_state_family(entity_type, id_key, state, entries, *, base_field, legacy_field, title, fallback_label, extra_description=None):
        """按全文去重后的实体家族覆盖同步基准与派生状态。"""
        count = 0
        for entry in entries:
            base_name = (entry.get("name") or "").strip()
            if not base_name:
                continue
            variants = _ordered_variants(entry, fallback_label)
            if not str(variants[0].get("description") or "").strip():
                variants[0]["description"] = entry.get(legacy_field) or entry.get(base_field) or ""
            base_label = str(variants[0].get("label") or fallback_label).strip()
            base_asset_name = f"{base_name} · {base_label}"
            identity_names = set(_identity_names(entry))
            family = sorted(
                [
                    item for item in state["existing"]
                    if str(item.get("id") or "") not in state["claimed"]
                    and str(item.get("id") or "") not in state["removed"]
                    and _family_root(str(item.get("name") or "")) in identity_names
                ],
                key=lambda item: str(item.get("id") or ""),
            )
            used_ids: set[str] = set()
            plans: list[tuple[dict | None, str, str]] = []
            for variant in variants:
                label = str(variant.get("label") or fallback_label).strip()
                asset_name = f"{base_name} · {label}"
                base = (entry.get(base_field) or entry.get(legacy_field) or "").strip()
                detail = (variant.get("description") or "").strip()
                state_key = str(variant.get("state_key") or "base").strip().lower()
                relation = "【状态关系】基准" if variant.get("is_base") else f"【状态关系】派生自：{base_asset_name}"
                description = "\n".join(part for part in [
                    f"【{title}基础】{base}" if base else "",
                    f"【{title}状态】{detail}" if detail else "",
                    f"【状态键】{state_key}",
                    relation,
                    extra_description(entry) if extra_description else "",
                ] if part)
                available = [item for item in family if str(item.get("id") or "") not in used_ids]
                target = next((item for item in available if item.get("name") == asset_name), None)
                if target is None:
                    target = next((item for item in available if stored_state_key(item) == state_key), None)
                if target is None and variant.get("is_base"):
                    target = next(
                        (item for item in available if "【状态关系】基准" in str(item.get("description") or "")),
                        None,
                    )
                if target is None and available:
                    target = available[0]
                if target is not None:
                    used_ids.add(str(target.get("id") or ""))
                plans.append((target, asset_name, description))

            delete_entities(
                entity_type,
                state,
                [item for item in family if str(item.get("id") or "") not in used_ids],
            )
            for target, asset_name, description in plans:
                if target is None:
                    entity_id = next_id(state, id_key)
                    asset(entity_type, entity_id, asset_name, description)
                else:
                    entity_id = str(target.get("id") or "")
                    update_asset(entity_type, entity_id, asset_name, description)
                    state["claimed"].add(entity_id)
                count += 1

        stale = [
            item for item in state["existing"]
            if state["pattern"].match(str(item.get("id") or ""))
            and str(item.get("id") or "") not in state["claimed"]
            and str(item.get("id") or "") not in state["removed"]
        ]
        delete_entities(entity_type, state, stale)
        return count

    def base_asset_name(entry, fallback_label):
        """返回实体家族的基准资产名。"""
        variants = _ordered_variants(entry, fallback_label)
        label = str(variants[0].get("label") or fallback_label).strip()
        return f"{entry.get('name', '').strip()} · {label}" if entry.get("name") else ""

    character_base_names = {
        identity: base_asset_name(entry, "剧本当前造型")
        for entry in ch
        for identity in _identity_names(entry)
    }
    scene_base_names = {
        identity: base_asset_name(entry, "基础状态")
        for entry in sc
        for identity in _identity_names(entry)
    }

    def prop_visual_content(entry):
        visual_content = entry.get("visual_content") or {}
        if not isinstance(visual_content, dict):
            return ""
        content = str(visual_content.get("description") or "").strip()
        character_names = [character_base_names.get(name, "") for name in visual_content.get("characters", []) or []]
        scene_names = [scene_base_names.get(name, "") for name in visual_content.get("scenes", []) or []]
        character_names = list(dict.fromkeys(name for name in character_names if name))
        scene_names = list(dict.fromkeys(name for name in scene_names if name))
        if not content and not character_names and not scene_names:
            return ""
        return "【强关联参考】内容：%s；角色：%s；场景：%s" % (
            content or "无",
            "、".join(character_names) or "无",
            "、".join(scene_names) or "无",
        )

    scene_count = store_state_family("scene", "scene", sc_state, sc, base_field="base_description", legacy_field="description", title="场景", fallback_label="基础状态")
    prop_count = store_state_family("prop", "prop", pr_state, pr, base_field="base_description", legacy_field="description", title="道具", fallback_label="基础状态", extra_description=prop_visual_content)
    look_count = store_state_family("character", "char", ch_state, ch, base_field="base_appearance", legacy_field="appearance", title="角色", fallback_label="剧本当前造型")

    print(f"=== 抽取完成：角色造型 {look_count}｜场景状态 {scene_count}｜道具状态 {prop_count} ===")
    print("下一步：造型页「① 锁定视觉词典」细化 → 「② 生成缺失造型图」；分镜页「AI 拆镜头」")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pid")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--model", default="glm-4.6")
    a = ap.parse_args()
    globals()["BASE"] = a.base.rstrip("/") + "/api/v1"
    run(a.pid, a.model)
