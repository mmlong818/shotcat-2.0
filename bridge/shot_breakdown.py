#!/usr/bin/env python3
"""镜头级分镜：把剧本按【镜头】(不是场景)拆解——一个场景含多个镜头
(建立/特写/插入/反应/正反打…)。写进 shots + shot_details，并映射到场景实体。
时长由内容决定，不锁固定秒数。
用法：python shot_breakdown.py <project_id> [--model glm-4.6]
（会替换该项目章节内的现有镜头，先用 clear_shots 清旧镜头再跑）
"""
from __future__ import annotations
import argparse, json, re, time, urllib.error, urllib.request
from pathlib import Path
from glm import chat_json
from http_util import get_all

SHOTS = "ECU 大特写 / CU 特写 / MCU 中近景 / MS 中景 / MLS 中远景 / LS 远景 / ELS 大远景"
ANGLES = "EYE_LEVEL 平视 / HIGH_ANGLE 俯 / LOW_ANGLE 仰 / BIRD_EYE 鸟瞰 / DUTCH 荷兰式"
MOVES = "STATIC 固定 / PAN 横向取景 / TILT 纵向取景 / DOLLY_IN 紧构图 / DOLLY_OUT 宽构图 / TRACK 跟随关系 / CRANE 高角度 / HANDHELD 现场感 / STEADICAM 稳定取景 / ZOOM_IN 紧构图 / ZOOM_OUT 宽构图"

SYS = f"""你是拥有十年经验的网络动漫剧分镜师兼摄影指导。把单集剧本设计成一组彼此关联、可直接用于画面生成的镜头，而不是逐句配图。

【三阶段工作顺序】
1. 先划分镜头边界：识别场次、动作转折、台词、反应、情绪爆点和重要道具，不遗漏、不重复原文。
2. 再为每个场景建立空间方案：先写唯一且固定的 scene_geometry，再锁定人物左右站位、朝向、视线轴和移动触发点；同场景不得换一种说法重写空间结构。
3. 最后设计相邻镜头关系并派生镜头参数：先决定 transition_from_previous 的匹配点与转场意图，再选择景别、机位、焦距、构图和运动。禁止为“多样”而随机换机位。

【连续性铁律】
- 每进入新场景，先用 LS/ELS/MLS 建立空间，再按“主镜头/双人关系 → 正反打或反应 → 信息或情绪落点”推进；极短场景可以合并，但不得一场只剩一张无设计的说明图。
- 同一场景内，spatial_anchor 必须使用固定参照物描述位置。剧本未明确写走、跑、起身、坐下、转身等位移时，人物位置不得改变。
- character_states 必须把角色固定身份与本镜可变状态分开：只记录当前镜可见的位置、姿态、朝向、视线和可见程度；角色外貌仍以资产为准。只有剧本或 action 明确发生移动/转身/姿态变化时，下一镜才能更新对应状态。
- scene_geometry 是场景不变的门窗、通道、家具和关键道具相对位置；viewing_direction 是本镜从哪里看向哪里；visible_range 是本镜实际能看见的边界。三者不得互相替代。机位必须从 scene_geometry 中可成立，不得为了变化虚构另一套空间。
- screen_direction 必须明确人物在画面左/右、面对方向和视线落点；正反打始终守住 180 度轴线，换机位至少满足 30 度规则。
- continuity_from_previous 必须写出与前镜可见状态的连接：空间、姿态、视线、动作因果或构图重心；不得只写“承接上一镜”。
- transition_from_previous 必须写明相邻镜头采用的关系（动作匹配、视线匹配、视觉重心匹配、因果切换、反应切换、声音桥或直接切换）、具体匹配点和叙事意图；本场首镜写明入场方式。转场关系用于组织镜头，不得把动态转场过程写进静态 description。
- 对话不是连续拍说话者。先建立双方空间关系，再在说话者、受话者反应和必要双人镜头之间切换；一句有冲击力的台词可在下一镜切受话者反应。
- 相邻镜头的景别、角度和构图变化必须有叙事动机。情绪爆点/信息落点用 CU/ECU，关键物件才用插入特写，小景别目标占比不少于 40%。

【画面与资产】
- scene、characters、props 只能使用输入资产库里的名称。角色造型名带“·状态名”时必须按剧情选对状态，不得只写基础名。
- action 与 action_beats 只写摄影机可见的动作和状态；description 是当前镜头的一张代表性静态画面，必须与 viewing_direction、visible_range、character_states 一致，写清前中后景、主体位置、姿态、光线和情绪，不写剧情总结。
- 背对镜头或面部被遮挡时不得描述不可见表情；LS/ELS 等大景别不得依赖细微眼神、皮肤纹理等不可辨认信息表达剧情。characters 只列当前画面真实可见角色，character_states 与之逐一对应。
- 空镜 action 必须以“空镜：”开头。不得凭常识添加手机、书包、雨伞、杯子等随身物件。
- 不使用肩部遮挡或借肩构图；正反打采用干净单人镜头、平视轻侧面或双人关系镜头，并保持左右站位与视线。
- reference_relations 只说明本镜头实际引用的角色、场景、道具分别锁定什么。
- 项目大脑中的已确认规则是本项目的事实与创作约束，优先级高于一般场景常识；不得与其冲突，也不得把未确认候选当成事实。

【镜头参数】
- camera_shot 仅用 [{SHOTS}] 的英文代码，只输出 ECU/CU/MCU/MS/MLS/LS/ELS 之一，不得附加中文名。
- angle 仅用 [{ANGLES}] 的英文代码，只输出代码本身，不得附加中文名，不使用 OVER_SHOULDER。
- movement 仅用 [{MOVES}] 的英文代码，只输出代码本身，不得附加中文名。运动必须服务于揭示空间、跟随动作或强调信息；没有动机时可用 STATIC，不要靠随机运镜制造变化。
- focal_length 从 24mm广角 / 35mm标准广角 / 50mm标准 / 85mm人像 / 105mm中焦 / 135mm长焦中选择。
- composition 从 三分法 / 对角线 / 框架 / 引导线 / 对称 / 黄金比例中选择，禁止中心构图；仅当剧本明确要求黑屏、黑场或淡出结束时允许使用 黑场。
- duration 为 1-60 的整数；有对白时不少于对白净字数÷4再加动作或反应余量。
- sfx 只写环境、机械、自然或物体声音，不写说话、呼吸、哭笑、心跳、脚步等人类声音。

【对白】
- dialogues 是对白数组，text 必须逐字保留原文；不同人物说话必须拆成不同镜头。
- 每项包含 speaker、target、text、mode。mode 仅用 DIALOGUE / VOICE_OVER / OFF_SCREEN / PHONE。
- 画内人物 speaker/target 使用角色造型的完整名称；画外音或旁白可留空。

【每镜必填字段】
scene、time、space、title、script_content、camera_shot、angle、movement、focal_length、composition、action、action_beats、description、scene_geometry、viewing_direction、visible_range、spatial_anchor、screen_direction、character_states、continuity_from_previous、transition_from_previous、narrative_function、atmosphere、sfx、reference_relations、dialogues、duration、characters、props。

character_states 格式为数组：{{"name":"角色造型完整名称","location":"相对固定参照物的位置","posture":"当前静态姿态","facing":"身体朝向","gaze":"视线落点","visibility":"面部与身体实际可见程度"}}。黑场或空镜可为空数组。

script_content 必须从完整剧本按原顺序逐字复制；纯反应镜头或插入镜头可以为空，但不得重复占用前镜原文。所有镜头的 script_content 拼接后应覆盖完整剧本，无遗漏、无重复、无改写。输出只包含 JSON。"""

USER_TMPL = """【拆分模式】标准模式

【完整剧本】
{script}

【项目大脑已确认规则（高于一般场景常识，不得冲突）】
{brain}

【本项目场景（scene 字段须用这些名，并用描述建立空间锚点）】
{scenes}
【角色造型（名称必须原样用于 characters；每行含状态依据）】{chars}
【道具（名称必须原样使用）】
{props}

把全剧本拆成标准粒度的镜头级分镜。先在内部完成场景空间与镜头序列规划，再输出结果，不要输出分析过程。
输出 JSON：{{"shots":[{{"scene":"","time":"日","space":"内","title":"","script_content":"","camera_shot":"","angle":"","movement":"","focal_length":"","composition":"","action":"","action_beats":[],"description":"","scene_geometry":"","viewing_direction":"","visible_range":"","spatial_anchor":"","screen_direction":"","character_states":[{{"name":"","location":"","posture":"","facing":"","gaze":"","visibility":""}}],"continuity_from_previous":"","transition_from_previous":"","narrative_function":"","atmosphere":"","sfx":"","reference_relations":"","dialogues":[{{"speaker":"","target":"","text":"","mode":"DIALOGUE"}}],"duration":6,"characters":[],"props":[]}}]}}"""

REVIEW_SYS = f"""你是资深分镜质量控制导演。校验并直接修复输入的完整镜头表，返回修复后的 shots，不输出修改说明。

按以下优先级逐镜检查：
1. 原文完整性：script_content 按原顺序逐字覆盖剧本；台词不删改；不同人物台词不塞进同一镜。
2. 空间连续性：同场景固定空间锚点、人物左右站位、朝向、视线和 180 度轴线；只有原文明确位移才更新位置。
3. 镜头序列：建立空间后再进入关系镜头、正反打、反应和落点；相邻镜头必须存在动作因果、视线或构图重心的明确连接。
4. 状态与场景锚定：同场景 scene_geometry 必须逐字一致；逐角色检查 character_states，只有原文或动作明确移动、转身、起身、坐下时才更新位置、姿态或朝向；viewing_direction 与 visible_range 必须在固定空间中成立。
5. 镜头关系：transition_from_previous 必须写清相邻镜头的匹配点与叙事意图；动作匹配、视线匹配和视觉重心匹配必须能从前后两镜的可见状态中得到支持。
6. 镜头语言：景别和机位服务情绪与权力关系，换机位满足 30 度规则；小景别不少于 40%；避免连续三个相同景别和没有动机的随机运镜。
7. 画面可生成：description 是一张确定的静态画面；背面或遮挡人物不写不可见表情，大景别不靠细微表情传递信息。
8. 资产准确：scene/characters/props 只能原样使用输入资产；道具仅在真实可见或互动时引用。
9. 技术值：camera_shot 仅 [{SHOTS}]；angle 仅 [{ANGLES}] 且不用 OVER_SHOULDER；movement 仅 [{MOVES}]；构图禁用中心构图；剧本明确要求黑屏、黑场或淡出结束时，黑场是合法构图。
10. 项目事实：逐镜检查是否遵守项目大脑已确认规则；这些规则高于一般常识，不得为了修复其他问题而改写或绕过。

不要降低镜头数量来规避问题，不要添加原文没有的剧情。只输出 JSON：{{"shots":[...]}}。"""

REVIEW_USER_TMPL = """【完整剧本】
{script}

【项目大脑已确认规则（高于一般场景常识，不得冲突）】
{brain}

【场景资产】
{scenes}
【角色造型】
{chars}
【道具资产】
{props}

【程序初检问题】
{issues}

【待校验镜头表】
{draft}

修复全部问题并输出完整 shots。"""

BASE = "http://localhost:8000/api/v1"
REPAIR_EXIT_CODE = 42
REPAIR_MARKER = "SHOTCAT_REPAIR_REQUIRED:"

VALID_SHOT = {"ECU", "CU", "MCU", "MS", "MLS", "LS", "ELS"}
VALID_ANGLE = {"EYE_LEVEL", "HIGH_ANGLE", "LOW_ANGLE", "BIRD_EYE", "DUTCH", "OVER_SHOULDER"}
VALID_MOVE = {"STATIC", "PAN", "TILT", "DOLLY_IN", "DOLLY_OUT", "TRACK", "CRANE", "HANDHELD", "STEADICAM", "ZOOM_IN", "ZOOM_OUT"}
VALID_FOCAL_LENGTH = {"24mm广角", "35mm标准广角", "50mm标准", "85mm人像", "105mm中焦", "135mm长焦"}
VALID_COMPOSITION = {"三分法", "对角线", "框架", "引导线", "对称", "黄金比例", "黑场"}
SHOT_CODE_ALIASES = {
    "大特写": "ECU", "特写": "CU", "中近景": "MCU", "中景": "MS",
    "中远景": "MLS", "大远景": "ELS", "远景": "LS",
}
ANGLE_CODE_ALIASES = {
    "平视": "EYE_LEVEL", "俯拍": "HIGH_ANGLE", "俯视": "HIGH_ANGLE", "仰拍": "LOW_ANGLE",
    "仰视": "LOW_ANGLE", "鸟瞰": "BIRD_EYE", "荷兰角": "DUTCH", "荷兰式": "DUTCH",
}
MOVE_CODE_ALIASES = {
    "固定": "STATIC", "横摇": "PAN", "横向取景": "PAN", "纵摇": "TILT", "纵向取景": "TILT",
    "推镜": "DOLLY_IN", "紧构图": "DOLLY_IN", "拉镜": "DOLLY_OUT", "宽构图": "DOLLY_OUT",
    "跟拍": "TRACK", "跟随": "TRACK", "摇臂": "CRANE", "高角度": "CRANE", "手持": "HANDHELD",
    "稳定器": "STEADICAM", "变焦推": "ZOOM_IN", "变焦拉": "ZOOM_OUT",
}


def _norm(v, valid, default):
    v = (v or "").strip().upper()
    return v if v in valid else default


_DLG_PUNCT = re.compile(r"[「」『』“”\s，。！？；：、…—·,.!?;:]")


def _dlg_min_secs(dialogue):
    """对白朗读时间下限：常规语速每秒 4 字（去引号/标点后计字，向上取整）。"""
    n = len(_DLG_PUNCT.sub("", dialogue or ""))
    return (n + 3) // 4 if n else 0


def _duration(v, dialogue=None):
    """容错解析建议秒数：提取前导数字(如 '6秒' → 6)，缺省 5；
    有对白时下限抬到朗读时间(常规每秒4字)，夹到 1-60。"""
    if isinstance(v, (int, float)):
        n = int(v)
    else:
        m = re.match(r"\s*(\d+)", str(v or ""))
        n = int(m.group(1)) if m else 5
    return max(1, min(60, max(n, _dlg_min_secs(dialogue))))


def _text(value) -> str:
    """把模型返回值收敛为去首尾空白的字符串，避免 None 或数值污染后续校验。"""
    return str(value or "").strip()


def _text_list(value) -> list[str]:
    """读取模型返回的字符串数组，并保持原顺序去除空项。"""
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _enum_code(value, valid: set[str], aliases: dict[str, str]) -> str:
    """兼容模型输出的“英文代码 + 中文名”或纯中文名，并收敛为数据库枚举代码。"""
    raw = _text(value)
    upper = raw.upper()
    if upper in valid:
        return upper
    for token in re.findall(r"[A-Z]+(?:_[A-Z]+)*", upper):
        if token in valid:
            return token
    for label, code in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if label in raw:
            return code
    return upper


def _normalize_focal_length(value) -> str:
    """把带“镜头”等自然语言后缀的焦距输出归一为允许值。"""
    raw = _text(value).lower().replace(" ", "")
    for canonical in VALID_FOCAL_LENGTH:
        prefix = canonical.lower().split("mm", 1)[0] + "mm"
        if raw.startswith(prefix):
            return canonical
    return _text(value)


def _normalize_composition(value) -> str:
    """兼容“三分法构图”等常见模型表达，保留合法构图名称。"""
    raw = _text(value)
    if any(label in raw for label in ("黑屏", "黑场", "纯黑")):
        return "黑场"
    for canonical in sorted(VALID_COMPOSITION, key=len, reverse=True):
        if canonical in raw:
            return canonical
    return raw


def _normalize_time(value) -> str:
    """把“日景/夜晚”等表达归一为分镜时间枚举。"""
    raw = _text(value)
    for label, canonical in (("黄昏", "黄昏"), ("清晨", "晨"), ("早晨", "晨"), ("晨", "晨"), ("夜", "夜"), ("日", "日")):
        if label in raw:
            return canonical
    return raw


def _normalize_space(value) -> str:
    """把“室内/内景、室外/外景”等表达归一为内外景枚举。"""
    raw = _text(value)
    if "室内" in raw or "内景" in raw or raw == "内":
        return "内"
    if "室外" in raw or "外景" in raw or raw == "外":
        return "外"
    return raw


def _normalize_dialogues(shot: dict) -> list[dict]:
    """兼容旧的单 dialogue 字段，并统一为可落库的结构化对白数组。"""
    rows = shot.get("dialogues")
    if not isinstance(rows, list):
        rows = []
    normalized: list[dict] = []
    for row in rows:
        if not isinstance(row, dict) or not _text(row.get("text")):
            continue
        mode = _text(row.get("mode")).upper() or "DIALOGUE"
        if mode not in {"DIALOGUE", "VOICE_OVER", "OFF_SCREEN", "PHONE"}:
            mode = "DIALOGUE"
        normalized.append({
            "speaker": _text(row.get("speaker")),
            "target": _text(row.get("target")),
            "text": _text(row.get("text")),
            "mode": mode,
        })
    legacy = _text(shot.get("dialogue"))
    if legacy and not normalized:
        normalized.append({
            "speaker": _text(shot.get("dialogue_speaker")),
            "target": _text(shot.get("dialogue_target")),
            "text": legacy,
            "mode": "DIALOGUE",
        })
    return normalized


def _normalize_character_states(value) -> list[dict]:
    """规范化逐镜角色可变状态；身份外观继续由角色资产负责。"""
    if not isinstance(value, list):
        return []
    states: list[dict] = []
    for raw in value:
        if not isinstance(raw, dict) or not _text(raw.get("name")):
            continue
        states.append({
            key: _text(raw.get(key))
            for key in ("name", "location", "posture", "facing", "gaze", "visibility")
        })
    return states


def _normalize_shots(value) -> list[dict]:
    """规范化两轮模型输出，保证校验和落库读取同一组字段。"""
    if not isinstance(value, list):
        return []
    normalized: list[dict] = []
    text_fields = (
        "scene", "time", "space", "title", "script_content", "camera_shot", "angle", "movement",
        "focal_length", "composition", "action", "description", "scene_geometry", "viewing_direction",
        "visible_range", "spatial_anchor", "screen_direction", "continuity_from_previous",
        "transition_from_previous", "narrative_function", "atmosphere", "sfx", "reference_relations",
    )
    for raw in value:
        if not isinstance(raw, dict):
            continue
        shot = {field: _text(raw.get(field)) for field in text_fields}
        shot["camera_shot"] = _enum_code(shot["camera_shot"], VALID_SHOT, SHOT_CODE_ALIASES)
        shot["angle"] = _enum_code(shot["angle"], VALID_ANGLE, ANGLE_CODE_ALIASES)
        shot["movement"] = _enum_code(shot["movement"], VALID_MOVE, MOVE_CODE_ALIASES)
        shot["focal_length"] = _normalize_focal_length(shot["focal_length"])
        shot["composition"] = _normalize_composition(shot["composition"])
        shot["time"] = _normalize_time(shot["time"])
        shot["space"] = _normalize_space(shot["space"])
        shot["characters"] = _text_list(raw.get("characters"))
        shot["props"] = _text_list(raw.get("props"))
        shot["action_beats"] = _text_list(raw.get("action_beats")) or ([shot["action"]] if shot["action"] else [])
        shot["character_states"] = _normalize_character_states(raw.get("character_states"))
        shot["dialogues"] = _normalize_dialogues(raw)
        shot["duration"] = raw.get("duration")
        normalized.append(shot)
    return normalized


def _compact_source(value: str) -> str:
    """去除排版空白后比较原文覆盖度，保留所有实际文字与标点。"""
    return re.sub(r"\s+", "", value or "")


_EXPLICIT_STATE_CHANGE = re.compile(
    r"走|跑|进入|离开|靠近|退后|上前|移到|来到|穿过|起身|站起|坐下|蹲下|跪下|躺下|转身|回头|转向|侧身"
)
_TRANSITION_RELATIONS = (
    "动作匹配", "视线匹配", "视觉重心匹配", "因果切换", "反应切换", "声音桥", "直接切换", "入场",
)


def _states_by_name(shot: dict) -> dict[str, dict]:
    return {
        _text(state.get("name")): state
        for state in shot.get("character_states") or []
        if _text(state.get("name"))
    }


def _has_explicit_state_change(shot: dict, *, character_name: str, known_names: set[str]) -> bool:
    source = " ".join([
        _text(shot.get("script_content")),
        _text(shot.get("action")),
        *(_text_list(shot.get("action_beats"))),
    ])
    if not _EXPLICIT_STATE_CHANGE.search(source):
        return False
    aliases = {character_name, character_name.split("·", 1)[0]}
    clauses = re.split(r"[。！？；，,\n]", source)
    if any(any(alias and alias in clause for alias in aliases) and _EXPLICIT_STATE_CHANGE.search(clause) for clause in clauses):
        return True
    known_aliases = {alias for name in known_names for alias in (name, name.split("·", 1)[0]) if alias}
    return not any(alias in source for alias in known_aliases)


def _stabilize_continuity_truth(shots: list[dict]) -> list[dict]:
    """把场景结构与无动作变更的角色状态收敛为代码维护的连续性真值。"""
    scene_geometry_by_name: dict[str, str] = {}
    previous_shot: dict | None = None
    for shot in shots:
        scene = _text(shot.get("scene"))
        geometry = _text(shot.get("scene_geometry"))
        if scene and scene not in scene_geometry_by_name and geometry:
            scene_geometry_by_name[scene] = geometry
        elif scene and scene in scene_geometry_by_name:
            shot["scene_geometry"] = scene_geometry_by_name[scene]

        previous = previous_shot if previous_shot is not None and previous_shot.get("scene") == scene else None
        if previous is not None:
            previous_states = _states_by_name(previous)
            current_states = _states_by_name(shot)
            known_names = set(previous_states) | set(current_states)
            for name in sorted(set(previous_states) & set(current_states)):
                if _has_explicit_state_change(shot, character_name=name, known_names=known_names):
                    continue
                for field in ("location", "posture", "facing"):
                    current_states[name][field] = _text(previous_states[name].get(field))
        previous_shot = shot
    return shots


def _storyboard_quality_issues(
    shots: list[dict],
    *,
    script: str,
    scene_names: set[str],
    character_names: set[str],
    prop_names: set[str],
) -> list[str]:
    """执行可确定的分镜初检；问题会交给质量控制模型做定向修复。"""
    if not shots:
        return ["[P0] 未输出任何镜头"]

    issues: list[str] = []
    required = (
        "scene", "title", "camera_shot", "angle", "movement", "action", "description",
        "scene_geometry", "viewing_direction", "visible_range", "spatial_anchor", "screen_direction",
        "composition", "continuity_from_previous", "transition_from_previous", "narrative_function",
    )
    for index, shot in enumerate(shots, 1):
        for field in required:
            if not _text(shot.get(field)):
                issues.append(f"[P0] 镜头{index:03d} 缺少 {field}")
        if shot.get("scene") not in scene_names:
            issues.append(f"[P0] 镜头{index:03d} 使用未知场景：{shot.get('scene') or '空'}")
        if shot.get("camera_shot") not in VALID_SHOT:
            issues.append(f"[P0] 镜头{index:03d} 景别代码无效：{shot.get('camera_shot') or '空'}")
        if shot.get("angle") not in VALID_ANGLE or shot.get("angle") == "OVER_SHOULDER":
            issues.append(f"[P0] 镜头{index:03d} 机位代码无效或使用了过肩：{shot.get('angle') or '空'}")
        if shot.get("movement") not in VALID_MOVE:
            issues.append(f"[P0] 镜头{index:03d} 运动代码无效：{shot.get('movement') or '空'}")
        if shot.get("focal_length") not in VALID_FOCAL_LENGTH:
            issues.append(f"[P0] 镜头{index:03d} 焦距无效：{shot.get('focal_length') or '空'}")
        if shot.get("composition") not in VALID_COMPOSITION:
            issues.append(f"[P0] 镜头{index:03d} 构图无效或使用了中心构图：{shot.get('composition') or '空'}")
        if shot.get("time") not in {"日", "夜", "晨", "黄昏"}:
            issues.append(f"[P0] 镜头{index:03d} 时间值无效：{shot.get('time') or '空'}")
        if shot.get("space") not in {"内", "外"}:
            issues.append(f"[P0] 镜头{index:03d} 内外景值无效：{shot.get('space') or '空'}")
        unknown_characters = sorted(set(shot.get("characters") or []) - character_names)
        if unknown_characters:
            issues.append(f"[P0] 镜头{index:03d} 使用未知角色造型：{'、'.join(unknown_characters)}")
        unknown_props = sorted(set(shot.get("props") or []) - prop_names)
        if unknown_props:
            issues.append(f"[P0] 镜头{index:03d} 使用未入库道具：{'、'.join(unknown_props)}")
        for dialogue in shot.get("dialogues") or []:
            speaker = _text(dialogue.get("speaker"))
            target = _text(dialogue.get("target"))
            if speaker and speaker not in character_names:
                issues.append(f"[P0] 镜头{index:03d} 对白说话者不是角色造型名：{speaker}")
            if target and target not in character_names:
                issues.append(f"[P0] 镜头{index:03d} 对白听者不是角色造型名：{target}")

        states = _states_by_name(shot)
        state_names = set(states)
        visible_characters = set(shot.get("characters") or [])
        unknown_state_names = sorted(state_names - character_names)
        if unknown_state_names:
            issues.append(f"[P0] 镜头{index:03d} 角色状态使用未知角色造型：{'、'.join(unknown_state_names)}")
        if shot.get("composition") != "黑场" and state_names != visible_characters:
            missing = sorted(visible_characters - state_names)
            extra = sorted(state_names - visible_characters)
            detail = "；".join(filter(None, [
                f"缺少 {'、'.join(missing)}" if missing else "",
                f"多出 {'、'.join(extra)}" if extra else "",
            ]))
            issues.append(f"[P0] 镜头{index:03d} character_states 未与可见角色逐一对应：{detail}")
        for name, state in states.items():
            for field in ("location", "posture", "facing", "gaze", "visibility"):
                if not _text(state.get(field)):
                    issues.append(f"[P0] 镜头{index:03d} 角色 {name} 缺少状态字段 {field}")
        transition = _text(shot.get("transition_from_previous"))
        if transition and not any(relation in transition for relation in _TRANSITION_RELATIONS):
            issues.append(f"[P0] 镜头{index:03d} 镜间关系未使用允许的关系类型：{transition}")

        previous = shots[index - 2] if index > 1 else None
        starts_scene = previous is None or previous.get("scene") != shot.get("scene")
        if starts_scene and shot.get("camera_shot") not in {"MLS", "LS", "ELS"}:
            issues.append(f"[P1] 镜头{index:03d} 是场景首镜但未建立空间")
        if not starts_scene and not _text(shot.get("continuity_from_previous")):
            issues.append(f"[P0] 镜头{index:03d} 与同场景前镜没有明确承接")
        if not starts_scene and _compact_source(_text(previous.get("scene_geometry"))) != _compact_source(_text(shot.get("scene_geometry"))):
            issues.append(f"[P0] 镜头{index:03d} 与同场景前镜的 scene_geometry 不一致")
        if not starts_scene:
            previous_states = _states_by_name(previous)
            for name in sorted(set(previous_states) & state_names):
                changed = [
                    field for field in ("location", "posture", "facing")
                    if _compact_source(_text(previous_states[name].get(field)))
                    != _compact_source(_text(states[name].get(field)))
                ]
                if changed and not _has_explicit_state_change(
                    shot,
                    character_name=name,
                    known_names=set(previous_states) | state_names,
                ):
                    issues.append(
                        f"[P0] 镜头{index:03d} 角色 {name} 未发生明确动作却改变状态：{'、'.join(changed)}"
                    )

    compact_script = _compact_source(script)
    compact_covered = "".join(_compact_source(_text(shot.get("script_content"))) for shot in shots)
    if compact_script != compact_covered:
        issues.append("[P0] 全部 script_content 拼接后未逐字覆盖完整剧本，存在遗漏、重复、改写或顺序错误")

    if len(shots) >= 3:
        tight_count = sum(shot.get("camera_shot") in {"ECU", "CU", "MCU"} for shot in shots)
        if tight_count / len(shots) < 0.4:
            issues.append(f"[P1] 小景别占比仅 {tight_count}/{len(shots)}，低于 40%")
        for index in range(2, len(shots)):
            if len({shots[index - 2].get("camera_shot"), shots[index - 1].get("camera_shot"), shots[index].get("camera_shot")}) == 1:
                issues.append(f"[P1] 镜头{index - 1:03d}-{index + 1:03d} 连续三个相同景别")
    return issues


def _blocking_issues(issues: list[str]) -> list[str]:
    """只保留会阻断任务完成的 P0 问题。"""
    return [item for item in issues if item.startswith("[P0]")]


def _issue_shot_indices(issues: list[str], shot_count: int) -> set[int]:
    """从 P0 文本提取问题镜头序号；无法定位到单镜的问题按整表修复处理。"""
    indices: set[int] = set()
    for issue in _blocking_issues(issues):
        matches = [int(value) for value in re.findall(r"镜头(\d+)", issue)]
        if not matches:
            return set(range(1, shot_count + 1))
        indices.update(index for index in matches if 1 <= index <= shot_count)
    return indices


def _build_shot_description(shot: dict) -> str:
    """把结构化导演设计写入 ShotDetail.description，供相邻镜头与关键帧链真实消费。"""
    parts = [
        ("画面描述", shot.get("description")),
        ("固定场景结构", shot.get("scene_geometry")),
        ("观看方向", shot.get("viewing_direction")),
        ("可视范围", shot.get("visible_range")),
        ("空间锚点", shot.get("spatial_anchor")),
        ("人物调度与轴线", shot.get("screen_direction")),
        ("角色当前状态", json.dumps(shot.get("character_states") or [], ensure_ascii=False)),
        ("前镜承接", shot.get("continuity_from_previous")),
        ("镜间关系", shot.get("transition_from_previous")),
        ("构图", "；".join(filter(None, [_text(shot.get("composition")), _text(shot.get("focal_length"))]))),
        ("叙事功能", shot.get("narrative_function")),
        ("参考图关系", shot.get("reference_relations")),
    ]
    return "\n".join(f"{label}：{_text(value)}" for label, value in parts if _text(value))


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


def items(path):
    return get_all(BASE, path)


def _generate_reviewed_shots(
    *,
    script: str,
    scene_context: str,
    character_context: str,
    prop_context: str,
    brain_context: str,
    scene_names: set[str],
    character_names: set[str],
    prop_names: set[str],
    model: str,
) -> tuple[list[dict], list[str]]:
    """执行分镜设计和导演复核两轮模型调用，返回镜头表与剩余质量问题。"""
    print("  第一轮：划分镜头并规划空间、轴线与叙事节奏…", flush=True)
    draft = chat_json(SYS, USER_TMPL.format(
        script=script,
        scenes=scene_context,
        chars=character_context,
        props=prop_context,
        brain=brain_context,
    ), model=model, temperature=0.45, timeout=300)
    shots = _stabilize_continuity_truth(_normalize_shots(draft.get("shots", [])))
    if not shots:
        raise SystemExit("模型未产出镜头")
    initial_issues = _storyboard_quality_issues(
        shots,
        script=script,
        scene_names=scene_names,
        character_names=character_names,
        prop_names=prop_names,
    )
    print(f"  第一轮产出 {len(shots)} 个镜头，进入导演校验（初检发现 {len(initial_issues)} 项）…", flush=True)
    reviewed = chat_json(REVIEW_SYS, REVIEW_USER_TMPL.format(
        script=script,
        scenes=scene_context,
        chars=character_context,
        props=prop_context,
        brain=brain_context,
        issues="\n".join(f"- {item}" for item in initial_issues) or "- 未发现程序可判定的问题；仍需做空间与镜头语言专业复核",
        draft=json.dumps({"shots": shots}, ensure_ascii=False),
    ), model=model, temperature=0.2, timeout=300)
    shots = _stabilize_continuity_truth(_normalize_shots(reviewed.get("shots", [])))
    final_issues = _storyboard_quality_issues(
        shots,
        script=script,
        scene_names=scene_names,
        character_names=character_names,
        prop_names=prop_names,
    )
    return shots, final_issues


def _repair_reviewed_shots(
    *,
    shots: list[dict],
    issues: list[str],
    script: str,
    scene_context: str,
    character_context: str,
    prop_context: str,
    brain_context: str,
    scene_names: set[str],
    character_names: set[str],
    prop_names: set[str],
    model: str,
) -> tuple[list[dict], list[str]]:
    """在用户确认后只接受问题镜头的改动，未命中的镜头保持原样。"""
    target_indices = _issue_shot_indices(issues, len(shots))
    if not target_indices:
        return shots, _storyboard_quality_issues(
            shots,
            script=script,
            scene_names=scene_names,
            character_names=character_names,
            prop_names=prop_names,
        )
    target_text = "、".join(f"{index:03d}" for index in sorted(target_indices))
    print(f"  用户已确认，开始定向修正镜头 {target_text}…", flush=True)
    repaired = chat_json(
        REVIEW_SYS + (
            f"\n这是用户确认后的定向修正轮次。只允许修改镜头 {target_text}；"
            "必须保持镜头总数、顺序和其他镜头内容完全不变。逐项消除程序初检问题，不能只改写措辞后原样返回。"
        ),
        REVIEW_USER_TMPL.format(
            script=script,
            scenes=scene_context,
            chars=character_context,
            props=prop_context,
            brain=brain_context,
            issues="\n".join(f"- {item}" for item in issues),
            draft=json.dumps({"shots": shots}, ensure_ascii=False),
        ),
        model=model,
        temperature=0.1,
        timeout=300,
    )
    normalized = _stabilize_continuity_truth(_normalize_shots(repaired.get("shots", [])))
    if len(normalized) != len(shots):
        final_issues = _storyboard_quality_issues(
            shots,
            script=script,
            scene_names=scene_names,
            character_names=character_names,
            prop_names=prop_names,
        )
        final_issues.append(
            f"[P0] 定向修正返回 {len(normalized)} 个镜头，与原 {len(shots)} 个不一致"
        )
        return shots, final_issues

    merged = _stabilize_continuity_truth([
        candidate if index in target_indices else original
        for index, (original, candidate) in enumerate(zip(shots, normalized), 1)
    ])
    final_issues = _storyboard_quality_issues(
        merged,
        script=script,
        scene_names=scene_names,
        character_names=character_names,
        prop_names=prop_names,
    )
    return merged, final_issues


def _pause_for_repair(pid: str, shots: list[dict], issues: list[str]) -> None:
    """保存待修正镜头并输出机器可读标记，让 Pipeline 进入等待用户确认状态。"""
    pending_path = Path(__file__).with_name(f"shots-repair-{pid}.json")
    pending_path.write_text(
        json.dumps({"shots": shots, "issues": issues}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    blocking = _blocking_issues(issues)
    payload = {"count": len(blocking), "issues": blocking[:12]}
    print("  导演校验仍发现关键问题，等待用户确认后继续定向修正。", flush=True)
    print(REPAIR_MARKER + json.dumps(payload, ensure_ascii=False), flush=True)
    raise SystemExit(REPAIR_EXIT_CODE)


def run(pid: str, model: str, *, repair: bool = False):
    chapters = sorted(items(f"/studio/chapters?project_id={pid}&page_size=100"), key=lambda c: c.get("index", 0))
    if not chapters:
        raise SystemExit("无章节")
    ch = chapters[0]  # 短片单章节；多集可扩展为逐章
    script = "\n\n".join(c.get("raw_text", "") for c in chapters)
    if not script.strip():
        raise SystemExit("项目无剧本正文，请先在剧本页粘贴剧本（避免空剧本白调 GLM）")
    scenes = items(f"/studio/entities/scene?project_id={pid}&page_size=100")
    chars = items(f"/studio/entities/character?project_id={pid}&page_size=100")
    props = items(f"/studio/entities/prop?project_id={pid}&page_size=100")
    brain_status, brain_response = _req("GET", f"/studio/projects/{pid}/brain?status=confirmed")
    brain_entries = brain_response.get("data", []) if brain_status < 400 else []
    scene_id_by_name = {s["name"]: s["id"] for s in scenes}
    char_id_by_name = {c["name"]: c["id"] for c in chars}
    prop_id_by_name = {p["name"]: p["id"] for p in props}

    scene_context = "\n".join(
        f"- {scene['name']}：{_text(scene.get('description')).replace(chr(10), ' ')}" for scene in scenes
    )
    character_context = "\n".join(
        f"- {character['name']}：{_text(character.get('description')).replace(chr(10), ' ')}" for character in chars
    )
    prop_context = "\n".join(
        f"- {prop['name']}：{_text(prop.get('description')).replace(chr(10), ' ')}" for prop in props
    ) or "（无已确认道具）"
    brain_context = "\n".join(
        f"- [{_text(entry.get('category')) or 'fact'}] {_text(entry.get('title'))}："
        f"{_text(entry.get('content')).replace(chr(10), ' ')}"
        for entry in brain_entries
        if isinstance(entry, dict) and _text(entry.get("content"))
    ) or "（暂无已确认项目规则）"

    print(
        f"[镜头级分镜] 项目 {pid}｜章节 {ch['id']}｜场景 {len(scenes)}｜"
        f"项目规则 {len(brain_entries)}｜模型 {model}"
    )
    pending_path = Path(__file__).with_name(f"shots-repair-{pid}.json")
    common_args = {
        "script": script,
        "scene_context": scene_context,
        "character_context": character_context,
        "prop_context": prop_context,
        "brain_context": brain_context,
        "scene_names": set(scene_id_by_name),
        "character_names": set(char_id_by_name),
        "prop_names": set(prop_id_by_name),
        "model": model,
    }
    if repair:
        if not pending_path.exists():
            raise SystemExit("待修正分镜不存在，请重新执行 AI 拆镜头")
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        pending_shots = _stabilize_continuity_truth(_normalize_shots(pending.get("shots", [])))
        pending_issues = [_text(item) for item in pending.get("issues", []) if _text(item)]
        current_issues = _storyboard_quality_issues(
            pending_shots,
            script=script,
            scene_names=set(scene_id_by_name),
            character_names=set(char_id_by_name),
            prop_names=set(prop_id_by_name),
        )
        repair_indices = _issue_shot_indices(pending_issues, len(pending_shots))
        if _blocking_issues(current_issues):
            repair_indices = _issue_shot_indices(current_issues, len(pending_shots))
            shots, final_issues = _repair_reviewed_shots(
                shots=pending_shots,
                issues=current_issues,
                **common_args,
            )
        else:
            shots, final_issues = pending_shots, current_issues
            print("  待修正镜头已符合当前规则，无需再次调用模型。", flush=True)
    else:
        shots, final_issues = _generate_reviewed_shots(**common_args)
        repair_indices = set(range(1, len(shots) + 1))

    if final_issues:
        print("  导演校验提示：" + "；".join(final_issues[:6]), flush=True)
    Path(__file__).with_name(f"shots-{pid}.json").write_text(
        json.dumps({"shots": shots, "quality_issues": final_issues}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  导演校验完成：{len(shots)} 个镜头（原场景数 {len(scenes)}）", flush=True)

    # 空镜前缀不依赖 GLM 遵守（实测遵守率低）：characters 为空且 action 未以"空镜"开头则后处理补上，
    # 供下游帧提示词识别为无人物镜头。
    for s in shots:
        act = (s.get("action") or "").strip()
        if not (s.get("characters") or []) and act and not act.startswith("空镜"):
            s["action"] = "空镜：" + act

    # 首轮先落地整份镜头草稿；修正轮只替换问题镜头。若发现旧草稿不完整，则整表恢复以避免缺镜。
    old = items(f"/studio/shots?chapter_id={ch['id']}")
    expected_indices = set(range(1, len(shots) + 1))
    old_indices = {int(item.get("index") or 0) for item in old}
    replace_all = not repair or old_indices != expected_indices
    persist_indices = expected_indices if replace_all else repair_indices
    delete_rows = old if replace_all else [item for item in old if int(item.get("index") or 0) in persist_indices]
    if repair and replace_all:
        print("  已落地草稿不完整，恢复整份待修正镜头表。", flush=True)
    for o in delete_rows:
        cd, _ = _req("DELETE", f"/studio/shot-details/{o['id']}")
        if cd >= 400 and cd != 404:
            raise SystemExit(f"删除旧镜头详情 {o['id']} 失败(HTTP {cd})，中止以免新旧数据混杂")
        cs, _ = _req("DELETE", f"/studio/shots/{o['id']}")
        if cs >= 400 and cs != 404:
            raise SystemExit(f"删除旧镜头 {o['id']} 失败(HTTP {cs})，中止以免新旧数据混杂")
    if delete_rows:
        print(f"  已替换旧镜头 {len(delete_rows)} 个")
    # 注：后端 shot-character-links 无 DELETE 接口(仅 GET/POST-upsert)，旧镜头的角色关联
    # 依赖删 shot 时的级联清理；新镜头 id 与旧镜头按 index 复用同名，POST 为 upsert 会覆盖。

    ok_shot = ok_detail = 0
    for i, s in enumerate(shots, 1):
        if i not in persist_indices:
            continue
        sid = f"{ch['id']}__shot_{i:03d}"
        c1, _ = _req("POST", "/studio/shots", {
            "id": sid, "chapter_id": ch["id"], "index": i,
            "title": s.get("title", f"镜头{i}"), "script_excerpt": s.get("script_content", ""), "status": "pending",
        })
        if c1 >= 400:
            raise SystemExit(f"镜{i} 落库失败(HTTP {c1})")
        ok_shot += 1
        dialogue_text = "".join(_text(row.get("text")) for row in s.get("dialogues", []))
        dialogue_beats = [f"「{_text(row.get('text'))}」" for row in s.get("dialogues", [])]
        detail = {
            "id": sid,
            "camera_shot": _norm(s.get("camera_shot"), VALID_SHOT, "MS"),
            "angle": _norm(s.get("angle"), VALID_ANGLE, "EYE_LEVEL"),
            "movement": _norm(s.get("movement"), VALID_MOVE, "STATIC"),
            "duration": _duration(s.get("duration"), dialogue_text),
            # 动作与对白同时保留在分镜表；结构化对白另写 dialog_lines，供镜头关系与提示词链读取说话者。
            "action_beats": [*s.get("action_beats", []), *dialogue_beats],
            "description": _build_shot_description(s),
            "atmosphere": s.get("atmosphere", ""),
            # 场次时间/内外景：ShotDetail 无专用字段，按 "时:X"/"景:X" 约定存 mood_tags
            # （mood_tags 会进帧提示词链，时间与内外景本身也是画面生成的关键信息）
            "mood_tags": [t for t in [
                f"时:{s.get('time')}" if s.get("time") in {"日", "夜", "晨", "黄昏"} else None,
                f"景:{s.get('space')}" if s.get("space") in {"内", "外"} else None,
            ] if t],
        }
        sid_scene = scene_id_by_name.get(s.get("scene", ""))
        if sid_scene:
            detail["scene_id"] = sid_scene
        # 仅在 400(父 shot 尚未提交的时序缝隙)重试；422 是校验错，不重试
        c2 = 400
        for _try in range(10):
            c2, r2 = _req("POST", "/studio/shot-details", detail)
            if c2 != 400:
                break
            time.sleep(1.2)
        if c2 < 400:
            ok_detail += 1
            for dialogue_index, dialogue in enumerate(s.get("dialogues", [])):
                speaker = _text(dialogue.get("speaker"))
                target = _text(dialogue.get("target"))
                dc, _ = _req("POST", "/studio/shot-dialog-lines", {
                    "shot_detail_id": sid,
                    "index": dialogue_index,
                    "text": _text(dialogue.get("text")),
                    "line_mode": dialogue.get("mode", "DIALOGUE"),
                    "speaker_character_id": char_id_by_name.get(speaker),
                    "target_character_id": char_id_by_name.get(target),
                    "speaker_name": speaker or None,
                    "target_name": target or None,
                })
                if dc >= 400:
                    print(f"      对白{dialogue_index + 1} 落库失败 HTTP {dc}", flush=True)
        else:
            raise SystemExit(f"镜{i} 详情落库失败(HTTP {c2})")
        # 关联出场角色(供画面提示词/参考图按对应角色生成)
        for k, nm in enumerate(s.get("characters", []) or []):
            cid = char_id_by_name.get(nm)
            if cid:
                for _t in range(6):
                    lc, _ = _req("POST", "/studio/shot-character-links", {"shot_id": sid, "character_id": cid, "index": k})
                    if lc != 400:
                        break
                    time.sleep(1.0)
        # 关联当前画面实际出现的关键道具，帧图生成据此带入道具设计图作为参考。
        for nm in dict.fromkeys(s.get("props", []) or []):
            prop_id = prop_id_by_name.get(nm)
            if not prop_id:
                continue
            for _t in range(6):
                lc, _ = _req("POST", "/studio/shot-links/prop", {
                    "project_id": pid,
                    "chapter_id": ch["id"],
                    "shot_id": sid,
                    "asset_id": prop_id,
                })
                if lc != 400:
                    break
                time.sleep(1.0)
        print(f"    镜{i:>2} [{s.get('camera_shot','?')}/{s.get('movement','?')}] {s.get('title','')[:16]}"
              + f" 角色{s.get('characters',[])} 道具{s.get('props',[])}" + (f"  (detail 失败 {c2})" if c2 >= 400 else ""))

    print(f"\n=== 已落地：{ok_shot} 镜头 / {ok_detail} 含景别机位详情，写入章节 {ch['id']} ===")
    if _blocking_issues(final_issues):
        _pause_for_repair(pid, shots, final_issues)
    pending_path.unlink(missing_ok=True)
    print("=== 导演校验通过，分镜任务完成 ===", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pid")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--model", default="glm-4.6")
    ap.add_argument("--repair", action="store_true", help="继续用户已确认的导演修正轮次")
    a = ap.parse_args()
    globals()["BASE"] = a.base.rstrip("/") + "/api/v1"
    run(a.pid, a.model, repair=a.repair)
