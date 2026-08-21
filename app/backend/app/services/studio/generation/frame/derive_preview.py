from __future__ import annotations

import re

from app.schemas.studio.shots import FrameGuidanceDecisionRead, RenderedShotFramePromptRead, ShotFramePromptMappingRead
from app.services.studio.generation.frame.build_base import FrameBaseDraft
from app.services.studio.generation.frame.build_context import FrameGenerationContext
from app.services.studio.generation.shared.types import GenerationDerivedPreview


def replace_reference_names_in_prompt(
    *,
    base_prompt: str,
    mappings: list[ShotFramePromptMappingRead],
) -> str:
    """保留实体原名，避免把可读提示词污染成“图1/图2”。"""
    return (base_prompt or "").strip()


def _score_frame_guidance_line(
    *,
    frame_type: str,
    category: str,
    text: str,
) -> int:
    """按帧类型和文本特征给图片 guidance 打分，控制最终 prompt 的收敛顺序。"""
    score_by_category = {
        "summary": 100,
        "continuity": 80,
        "frame": 70,
        "screen": 65,
        "composition": 60,
    }
    score = score_by_category.get(category, 0)

    if frame_type == "first" and category == "frame":
        score += 18
    if frame_type == "first" and category == "composition":
        score += 15
    if frame_type == "key" and category == "frame":
        score += 6
    if frame_type == "last" and category == "frame":
        score += 8
    if frame_type in {"key", "last"} and category == "screen":
        score += 10
    if frame_type == "last" and category == "continuity":
        score += 5

    if category == "frame" and any(keyword in text for keyword in ("触发瞬间", "初始反应", "尚未完成", "动作峰值", "情绪余韵", "收束")):
        score += 8
    if category == "screen" and any(keyword in text for keyword in ("视线", "对视", "左右", "朝向", "跳轴")):
        score += 10
    if category == "composition" and any(keyword in text for keyword in ("空间", "重心", "环境", "锚点", "站位")):
        score += 10
    if category == "continuity" and any(keyword in text for keyword in ("上一镜头", "下一镜头", "承接", "收束")):
        score += 5

    return score


def _build_frame_guidance_reason(
    *,
    frame_type: str,
    category: str,
    selected: bool,
) -> str:
    """生成 guidance 被保留或压缩的可解释原因。"""
    if selected:
        if category == "frame":
            if frame_type == "first":
                return "当前是首帧，系统优先保留触发瞬间与未完成态约束，避免画面直接跳到后续完成动作。"
            if frame_type == "key":
                return "当前是关键帧，系统保留帧职责 guidance 来强化动作峰值或情绪爆点。"
            if frame_type == "last":
                return "当前是尾帧，系统保留帧职责 guidance 来强化动作收束与情绪落点。"
        if frame_type == "first" and category == "composition":
            return "当前是首帧，系统优先稳住空间建立与主体站位，所以保留构图锚点。"
        if frame_type in {"key", "last"} and category == "screen":
            return "当前镜头更看重视线与左右轴线稳定，因此优先保留朝向与视线 guidance。"
        if category == "summary":
            return "导演主指令始终属于最高优先级约束，因此会优先保留。"
        if category == "continuity":
            return "连续性 guidance 直接影响镜头承接稳定性，因此被保留。"
        if category == "composition":
            return "这条 guidance 对画面空间重心更关键，因此被保留。"
        if category == "screen":
            return "这条 guidance 对视线、朝向或轴线更关键，因此被保留。"

    if category == "frame":
        if frame_type == "first":
            return "当前已有更高优先级的首帧约束进入最终 prompt，因此这条帧职责 guidance 被压缩。"
        if frame_type == "key":
            return "当前已有更高优先级的关键帧约束进入最终 prompt，因此这条帧职责 guidance 被压缩。"
        if frame_type == "last":
            return "当前已有更高优先级的尾帧约束进入最终 prompt，因此这条帧职责 guidance 被压缩。"
    if frame_type == "first" and category == "screen":
        return "当前是首帧，系统更优先保空间建立与站位关系，因此将朝向与视线 guidance 降为次级。"
    if frame_type in {"key", "last"} and category == "composition":
        return "当前镜头更优先保视线与左右轴线稳定，因此构图锚点 guidance 被压缩。"
    if category == "summary":
        return "当前已有更高分的导演主指令进入最终 prompt，这条摘要未继续保留。"
    if category == "continuity":
        return "当前已有更高优先级的镜头约束进入最终 prompt，因此这条连续性 guidance 被压缩。"
    if category == "composition":
        return "当前已有更高优先级的空间或朝向约束进入最终 prompt，因此这条构图 guidance 被压缩。"
    if category == "screen":
        return "当前已有更高优先级的空间或连续性约束进入最终 prompt，因此这条朝向/视线 guidance 被压缩。"
    return "当前已有更高优先级 guidance 进入最终 prompt，因此该条目未被保留。"


def _build_frame_guidance_reason_tag(
    *,
    frame_type: str,
    category: str,
    selected: bool,
) -> str:
    """生成更适合前端快速阅读的短标签。"""
    if category == "summary":
        return "导演主指令"
    if category == "frame":
        if frame_type == "first":
            return "首帧保时序" if selected else "首帧降时序"
        if frame_type == "key":
            return "关键帧保峰值" if selected else "关键帧降峰值"
        if frame_type == "last":
            return "尾帧保收束" if selected else "尾帧降收束"
    if category == "continuity":
        return "连续性优先" if selected else "连续性降级"
    if frame_type == "first" and category == "composition":
        return "首帧保空间" if selected else "首帧降构图"
    if frame_type == "first" and category == "screen":
        return "首帧降轴线"
    if frame_type in {"key", "last"} and category == "screen":
        return "关键帧保轴线" if frame_type == "key" and selected else ("尾帧保轴线" if selected else "轴线降级")
    if frame_type in {"key", "last"} and category == "composition":
        return "关键帧降构图" if frame_type == "key" else "尾帧降构图"
    if category == "composition":
        return "构图优先" if selected else "构图降级"
    if category == "screen":
        return "轴线优先" if selected else "轴线降级"
    return "优先级调整"


def _collect_frame_guidance_lines(
    *,
    frame_type: str,
    replaced_prompt: str,
    director_command_summary: str,
    continuity_guidance: str,
    frame_specific_guidance: str,
    composition_anchor: str,
    screen_direction_guidance: str,
) -> tuple[list[str], list[str], list[FrameGuidanceDecisionRead], list[FrameGuidanceDecisionRead]]:
    """收集最终保留与被压缩掉的 guidance，供渲染与前端展示共用。"""
    text = (replaced_prompt or "").strip()
    candidates: list[tuple[int, int, str, str]] = []
    normalized_summary = (director_command_summary or "").strip()
    normalized_continuity = (continuity_guidance or "").strip()
    normalized_frame = (frame_specific_guidance or "").strip()
    normalized_composition = (composition_anchor or "").strip()
    normalized_screen = (screen_direction_guidance or "").strip()

    if normalized_summary and normalized_summary not in text:
        candidates.append(
            (
                _score_frame_guidance_line(frame_type=frame_type, category="summary", text=normalized_summary),
                0,
                "summary",
                f"高优先级导演指令：{normalized_summary}",
            )
        )
    if (
        normalized_continuity
        and normalized_continuity not in text
        and normalized_continuity not in normalized_summary
        and "连续性要求：" not in text
    ):
        candidates.append(
            (
                _score_frame_guidance_line(frame_type=frame_type, category="continuity", text=normalized_continuity),
                1,
                "continuity",
                f"连续性要求：{normalized_continuity}",
            )
        )
    if (
        normalized_frame
        and normalized_frame not in text
        and normalized_frame not in normalized_summary
        and "当前帧职责：" not in text
    ):
        candidates.append(
            (
                _score_frame_guidance_line(frame_type=frame_type, category="frame", text=normalized_frame),
                2,
                "frame",
                f"当前帧职责：{normalized_frame}",
            )
        )
    if (
        normalized_composition
        and normalized_composition not in text
        and "构图锚点：" not in text
    ):
        candidates.append(
            (
                _score_frame_guidance_line(frame_type=frame_type, category="composition", text=normalized_composition),
                4,
                "composition",
                f"构图锚点：{normalized_composition}",
            )
        )
    if (
        normalized_screen
        and normalized_screen not in text
        and "朝向与视线：" not in text
    ):
        candidates.append(
            (
                _score_frame_guidance_line(frame_type=frame_type, category="screen", text=normalized_screen),
                3,
                "screen",
                f"朝向与视线：{normalized_screen}",
            )
        )

    ranked = sorted(candidates, key=lambda item: (-item[0], item[1]))
    selected_rows = ranked[:3]
    dropped_rows = ranked[3:]
    selected = [line for _, _, _, line in selected_rows]
    dropped = [line for _, _, _, line in dropped_rows]
    selected_details = [
        FrameGuidanceDecisionRead(
            text=line,
            category=category,
            reason_tag=_build_frame_guidance_reason_tag(frame_type=frame_type, category=category, selected=True),
            reason=_build_frame_guidance_reason(frame_type=frame_type, category=category, selected=True),
        )
        for _, _, category, line in selected_rows
    ]
    dropped_details = [
        FrameGuidanceDecisionRead(
            text=line,
            category=category,
            reason_tag=_build_frame_guidance_reason_tag(frame_type=frame_type, category=category, selected=False),
            reason=_build_frame_guidance_reason(frame_type=frame_type, category=category, selected=False),
        )
        for _, _, category, line in dropped_rows
    ]
    return selected, dropped, selected_details, dropped_details


def enrich_frame_prompt_with_guidance(
    *,
    frame_type: str,
    replaced_prompt: str,
    director_command_summary: str,
    continuity_guidance: str,
    frame_specific_guidance: str,
    composition_anchor: str,
    screen_direction_guidance: str,
) -> str:
    """最终生图 prompt 只保留可画内容；内部导演约束留在结构化 metadata 中。"""
    return (replaced_prompt or "").strip()


def _reference_relation_lines(mappings: list[ShotFramePromptMappingRead]) -> list[str]:
    """把参考图关系压成可读短句，不使用图片编号。"""
    if not mappings:
        return []
    label_by_type = {
        "character": "角色参考",
        "scene": "场景参考",
        "prop": "道具参考",
    }
    use_by_type = {
        "character": "保持外貌、发型与身份一致",
        "scene": "保持空间结构、材质、陈设与光线一致",
        "prop": "保持外观、尺寸、材质与文字细节一致",
    }
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for mapping in mappings:
        name = (mapping.name or "").strip()
        if not name:
            continue
        key = (str(mapping.type), name)
        if key in seen:
            continue
        seen.add(key)
        label = label_by_type.get(str(mapping.type), "参考")
        use = use_by_type.get(str(mapping.type), "保持设定一致")
        lines.append(f"{label}：{name}，{use}。")
    return lines


def _strip_existing_reference_lines(prompt: str) -> str:
    lines = []
    for line in str(prompt or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(("角色参考：", "场景参考：", "道具参考：", "参考：")):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _strip_character_clothing_when_referenced(prompt: str) -> str:
    text = str(prompt or "").strip()
    if not text:
        return ""
    clothing_words = r"(校服|制服|礼服|雨衣|工作服|服装|衣服|衣物|上衣|裤|裙|外套|衬衫|T恤|毛衣|风衣|夹克|鞋|靴)"
    action_lookahead = r"(坐|站|走|蹲|背对|面对|回头|看|望|视线|手|拿|捏|压|拉|合|靠|位于|在|从|向|低垂|抬起|转向)"
    # 保留“少年女主……坐在窗边”这类姿态动作，只删除中间服装片段。
    text = re.sub(
        rf"(身着|穿着|身穿|穿)[^，,；;。]*?{clothing_words}[^，,；;。]*?(?={action_lookahead})",
        "",
        text,
    )
    # 如果一个短句只剩“某角色穿某衣服”，整句没有姿态动作，就删除这段服装短句。
    text = re.sub(
        rf"[，,；;。\s]*[\u4e00-\u9fffA-Za-z0-9_·（）()]*?(身着|穿着|身穿|穿)[^，,；;。]*?{clothing_words}[^，,；;。]*",
        "",
        text,
    )
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"^[，,；;。\s]+", "", text)
    text = re.sub(r"[，,；;]\s*([。])", r"\1", text)
    return text.strip()


_INCIDENTAL_CARRIED_OBJECT_GROUPS = {
    "bag": ("书包", "背包", "包带"),
}

_ACTIVE_OBJECT_VERBS = (
    "打开",
    "拉开",
    "合上",
    "翻",
    "掏",
    "取出",
    "拿出",
    "放进",
    "塞进",
    "塞入",
    "露出",
    "掉出",
    "压住",
    "抓住",
    "拎起",
)


def _has_term_near_active_verb(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        for match in re.finditer(re.escape(term), text):
            start = max(match.start() - 8, 0)
            end = min(match.end() + 8, len(text))
            window = text[start:end]
            if any(verb in window for verb in _ACTIVE_OBJECT_VERBS):
                return True
    return False


def _strip_incidental_carried_objects(
    prompt: str,
    *,
    context_text: str,
    prop_reference_names: list[str],
) -> str:
    text = str(prompt or "").strip()
    if not text:
        return ""
    context = str(context_text or "")
    prop_text = " ".join(prop_reference_names)
    for terms in _INCIDENTAL_CARRIED_OBJECT_GROUPS.values():
        has_story_evidence = any(term in context for term in terms)
        has_prop_reference = any(term in prop_text for term in terms)
        has_active_use = _has_term_near_active_verb(text, terms)
        if has_story_evidence or has_prop_reference or has_active_use:
            continue
        text = re.sub(r"(背着|背着一只|背着一个|背|挎着|拎着)(书包|背包)", "", text)
        text = re.sub(r"[，,；;。\s]*(书包|背包|包带)[^，,；;。]*(掠过|晃动|挂在|露在|背在|位于|出现在)[^，,；;。]*", "", text)
        text = re.sub(r"[，,；;。\s]*(书包|背包|包带)[^，,；;。]*", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"^[，,；;。\s]+", "", text)
    text = re.sub(r"[，,；;]\s*([。])", r"\1", text)
    return text.strip()


def _cleanup_static_image_language(prompt: str) -> str:
    text = str(prompt or "").strip()
    if not text:
        return ""
    # 先处理整句级风险表达，避免单词替换后留下“白色校服，的侧向位置关系”这类残句。
    sentence_replacements = (
        (
            r"镜头从[^，,；;。]{0,24}(学生们|同学们|人群|路人)[^，,；;。]{0,12}(肩后|肩背)[^，,；;。]{0,24}(推近|推进|移动|跟拍)[^，,；;。]*",
            "横向静态构图从教室前排课桌与过道建立空间层次",
        ),
        (
            r"从[^，,；;。]{0,24}(学生们|同学们|人群|路人)[^，,；;。]{0,12}(肩后|肩背)[^，,；;。]{0,24}(推近|推进|移动|跟拍)[^，,；;。]*",
            "横向静态构图保留教室前排课桌、过道与主体之间的空间关系",
        ),
        (
            r"[^，,；;。]{0,18}(肩后|肩背)[^，,；;。]{0,18}(推近|推进|移动|跟拍)[^，,；;。]*",
            "稳定平视轻侧面构图，画面层次清楚",
        ),
        (
            r"[^，,；;。]{0,18}(推近|推进|移动|跟拍)[^，,；;。]{0,18}(肩后|肩背)[^，,；;。]*",
            "稳定平视轻侧面构图，画面层次清楚",
        ),
        (
            r"[，,；;。\s]*镜头(向|沿|从|朝)[^，,；;。]{0,40}(缓慢|缓缓|逐渐|慢慢)?(推近|推进|移动|跟拍)[^，,；;。]*",
            "",
        ),
    )
    for pattern, replacement in sentence_replacements:
        text = re.sub(pattern, replacement, text)
    replacements = {
        "MCU过肩视角": "MCU中近景，稳定平视轻侧面构图",
        "过肩视角": "稳定平视轻侧面构图",
        "过肩镜头": "稳定平视轻侧面构图",
        "前景左侧是虚化的男主肩背": "左侧前景保留教室空间层次",
        "前景右侧是虚化的男主肩背": "右侧前景保留教室空间层次",
        "前景左侧是虚化的女主肩背": "左侧前景保留教室空间层次",
        "前景右侧是虚化的女主肩背": "右侧前景保留教室空间层次",
        "虚化的男主肩背": "男主的侧向位置关系",
        "虚化的女主肩背": "女主的侧向位置关系",
        "前景肩部": "前景空间层次",
        "肩背": "侧向位置关系",
        "肩部": "侧向位置关系",
        "镜头推进到": "静态取景朝向",
        "推进到": "静态取景朝向",
        "镜头推进": "画面构图更紧凑",
        "推进": "构图更紧凑",
        "推镜": "紧凑构图",
        "拉远": "宽一些的静态构图",
        "跟拍": "稳定静态取景",
        "横摇": "横向广角构图",
        "纵摇": "稳定静态构图",
        "移动": "静态",
        "运镜": "静态构图",
        "镜头运动": "静态构图",
        "缓慢": "",
        "缓缓": "",
        "逐渐": "",
        "正在变化": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"镜头像?从([^，,；;。]{1,24})构图更紧凑的关键瞬间", r"静态构图从\1建立可视范围", text)
    text = re.sub(r"(沿|向|朝)([^，,；;。]{1,24})构图更紧凑的关键瞬间", r"\1\2形成静态纵深构图", text)
    text = re.sub(r"[，,；;。\s]*为后续镜头[^，,；;。]*", "", text)
    text = re.sub(r"[，,；;。\s]*白色校服[，,；;。\s]*的侧向位置关系虚化?", "", text)
    text = re.sub(r"[，,；;。\s]*[^，,；;。]{0,12}的侧向位置关系虚化", "", text)
    text = re.sub(r"[，,；;。\s]*[^，,；;。]{0,12}侧向位置关系虚化", "", text)
    text = re.sub(r"(克制而紧绷|紧绷|安静|沉默|迟疑|犹豫)虚化", r"\1", text)
    # 删除仍然包含肩部遮挡的短句，避免图像模型把身体局部画错。
    text = re.sub(r"[，,；;。\s]*[^，,；;。]{0,18}(肩|肩背)[^，,；;。]{0,18}(遮挡|虚化|前景)[^，,；;。]*", "", text)
    text = re.sub(r"[，,；;。\s]*[^，,；;。]{0,18}(肩后|肩背|肩部|借肩)[^，,；;。]*", "", text)
    text = re.sub(r"[，,；;。\s]*[^，,；;。]*(DOLLY_IN|DOLLY_OUT|PAN|TILT|TRACK|HANDHELD|STEADICAM|ZOOM_IN|ZOOM_OUT)[^，,；;。]*", "", text)
    text = re.sub(r"[，,；;。\s]*(镜头)?(从|向|朝)[^，,；;。]{0,24}(推近|推进|移动|跟拍)[^，,；;。]*", "", text)
    text = re.sub(r"(缓慢|缓缓|逐渐|慢慢)(推近|推进|移动|靠近)", "静态取景", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"^[，,；;。\s]+", "", text)
    text = re.sub(r"[，,；;]\s*([。])", r"\1", text)
    text = re.sub(r"[，,；;]\s*([，,；;])", r"\1", text)
    return text.strip()


def _cleanup_rendered_prompt_surface(
    prompt: str,
    *,
    has_character_reference: bool = False,
    context_text: str = "",
    prop_reference_names: list[str] | None = None,
) -> str:
    text = str(prompt or "").strip()
    if not text:
        return ""
    name_part = r"[\u4e00-\u9fffA-Za-z0-9_·（）()]{1,30}?"
    text = re.sub(rf"(身着|穿着|身穿|穿){name_part}[-－_ ]默认服装[（(]([^）)]+)[）)]", r"\1\2", text)
    text = re.sub(rf"(?<![\u4e00-\u9fffA-Za-z0-9_·（）()]){name_part}[-－_ ]默认服装[（(]([^）)]+)[）)]", r"\1", text)
    text = re.sub(rf"(身着|穿着|身穿|穿){name_part}[-－_ ]默认服装", r"\1", text)
    text = re.sub(rf"(?<![\u4e00-\u9fffA-Za-z0-9_·（）()]){name_part}[-－_ ]默认服装", "", text)
    patterns = (
        r"[，,；;。\s]*(身着|穿着|穿|身穿)?默认服装",
        r"[，,；;。\s]*(身着|穿着|穿|身穿)?默认衣服",
        r"[，,；;。\s]*(身着|穿着|穿|身穿)?默认穿着",
        r"[，,；;。\s]*(身着|穿着|穿|身穿)?日常服装",
        r"[，,；;。\s]*(身着|穿着|穿|身穿)?普通服装",
        r"[，,；;。\s]*(身着|穿着|穿|身穿)?普通衣服",
        r"[，,；;。\s]*(身着|穿着|穿|身穿)?便装",
    )
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    text = text.replace("过肩视角", "平视轻侧面视角")
    text = text.replace("过肩镜头", "平视轻侧面构图")
    text = _cleanup_static_image_language(text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"^[，,；;。\s]+", "", text)
    text = re.sub(r"^[和及与、\s]+", "", text)
    text = re.sub(r"[和及与、\s]+([，,；;。])", r"\1", text)
    text = re.sub(r"[，,；;]\s*([。])", r"\1", text)
    if has_character_reference:
        text = _strip_character_clothing_when_referenced(text)
    text = _strip_incidental_carried_objects(
        text,
        context_text=context_text,
        prop_reference_names=prop_reference_names or [],
    )
    return text.strip()


def compose_shot_frame_rendered_prompt(
    *,
    replaced_prompt: str,
    mappings: list[ShotFramePromptMappingRead],
) -> str:
    """拼装最终提交给模型的关键帧提示词，避免暴露内部调度说明。"""
    has_character_reference = any(str(mapping.type) == "character" for mapping in mappings)
    prop_reference_names = [(mapping.name or "").strip() for mapping in mappings if str(mapping.type) == "prop"]
    lines = [
        _cleanup_rendered_prompt_surface(
            _strip_existing_reference_lines(replaced_prompt),
            has_character_reference=has_character_reference,
            context_text="",
            prop_reference_names=prop_reference_names,
        )
    ]
    lines.extend(_reference_relation_lines(mappings))
    return "\n".join(line for line in lines if line).strip()


class FrameDerivedPreview(GenerationDerivedPreview):
    """分镜帧图片生成的最终预览结果。"""

    kind: str = "frame"
    shot_id: str
    frame_type: str
    base_prompt: str
    rendered_prompt: str
    selected_guidance: list[str]
    dropped_guidance: list[str]
    selected_guidance_details: list[FrameGuidanceDecisionRead]
    dropped_guidance_details: list[FrameGuidanceDecisionRead]
    images: list[str]
    mappings: list[ShotFramePromptMappingRead]


def derive_frame_preview(
    *,
    base: FrameBaseDraft,
    context: FrameGenerationContext,
) -> FrameDerivedPreview:
    normalized_base_prompt = (base.prompt or "").strip()
    replaced_prompt = replace_reference_names_in_prompt(
        base_prompt=normalized_base_prompt,
        mappings=context.ordered_refs,
    )
    selected_guidance, dropped_guidance, selected_guidance_details, dropped_guidance_details = _collect_frame_guidance_lines(
        frame_type=base.frame_type.value if hasattr(base.frame_type, "value") else str(base.frame_type),
        replaced_prompt=replaced_prompt,
        director_command_summary=base.director_command_summary,
        continuity_guidance=base.continuity_guidance,
        frame_specific_guidance=base.frame_specific_guidance,
        composition_anchor=base.composition_anchor,
        screen_direction_guidance=base.screen_direction_guidance,
    )
    enriched_prompt = enrich_frame_prompt_with_guidance(
        frame_type=base.frame_type.value if hasattr(base.frame_type, "value") else str(base.frame_type),
        replaced_prompt=replaced_prompt,
        director_command_summary=base.director_command_summary,
        continuity_guidance=base.continuity_guidance,
        frame_specific_guidance=base.frame_specific_guidance,
        composition_anchor=base.composition_anchor,
        screen_direction_guidance=base.screen_direction_guidance,
    )
    rendered_prompt = compose_shot_frame_rendered_prompt(
        replaced_prompt=_cleanup_rendered_prompt_surface(
            enriched_prompt,
            has_character_reference=any(str(mapping.type) == "character" for mapping in context.ordered_refs),
            context_text="；".join(
                part
                for part in [
                    base.frame_specific_guidance,
                    base.director_command_summary,
                ]
                if part
            ),
            prop_reference_names=[(mapping.name or "").strip() for mapping in context.ordered_refs if str(mapping.type) == "prop"],
        ),
        mappings=context.ordered_refs,
    )
    return FrameDerivedPreview(
        shot_id=base.shot_id,
        frame_type=base.frame_type.value if hasattr(base.frame_type, "value") else str(base.frame_type),
        base_prompt=normalized_base_prompt,
        rendered_prompt=rendered_prompt,
        selected_guidance=selected_guidance,
        dropped_guidance=dropped_guidance,
        selected_guidance_details=selected_guidance_details,
        dropped_guidance_details=dropped_guidance_details,
        images=[mapping.file_id for mapping in context.ordered_refs],
        mappings=context.ordered_refs,
    )


def to_rendered_shot_frame_prompt_read(
    *,
    derived: FrameDerivedPreview,
) -> RenderedShotFramePromptRead:
    return RenderedShotFramePromptRead(
        base_prompt=derived.base_prompt,
        rendered_prompt=derived.rendered_prompt,
        selected_guidance=derived.selected_guidance,
        dropped_guidance=derived.dropped_guidance,
        selected_guidance_details=derived.selected_guidance_details,
        dropped_guidance_details=derived.dropped_guidance_details,
        images=derived.images,
        mappings=derived.mappings,
    )
