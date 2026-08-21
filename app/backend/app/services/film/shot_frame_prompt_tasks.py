from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.chains.agents import (
    ShotFirstFramePromptAgent,
    ShotKeyFramePromptAgent,
    ShotLastFramePromptAgent,
)
from app.core.db import async_session_maker
from app.core.task_manager import SqlAlchemyTaskStore
from app.core.task_manager.types import TaskStatus
from app.models.studio import (
    Chapter,
    Character,
    ProjectPropLink,
    ProjectBrainEntry,
    ProjectSceneLink,
    Prop,
    Scene,
    Shot,
    ShotCharacterLink,
    ShotDetail,
)
from app.services.llm.runtime import build_default_text_llm_sync
from app.services.common import entity_not_found, invalid_choice
from app.services.studio.action_beats import infer_action_beat_sequence, pick_action_beat_for_frame
from app.services.studio.shot_status import recompute_shot_status
from app.services.worker.async_task_support import cancel_if_requested_async
from app.services.worker.task_logging import log_task_event, log_task_failure


def normalize_frame_type(frame_type: str) -> str:
    value = (frame_type or "").strip().lower()
    if value not in {"first", "last", "key"}:
        raise HTTPException(status_code=400, detail=invalid_choice("frame_type", ["first", "last", "key"]))
    return value


def relation_type_for_frame(frame_type: str) -> str:
    if frame_type == "first":
        return "shot_first_frame_prompt"
    if frame_type == "last":
        return "shot_last_frame_prompt"
    return "shot_key_frame_prompt"


def prompt_field_for_frame(frame_type: str) -> str:
    normalized = normalize_frame_type(frame_type)
    return {
        "first": "first_frame_prompt",
        "key": "key_frame_prompt",
        "last": "last_frame_prompt",
    }[normalized]


def _enum_value(value: object | None) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw or "")


def _compact_text(value: str | None) -> str:
    return str(value or "").strip()


def _build_project_brain_context(entries: list[ProjectBrainEntry]) -> str:
    """把已确认项目规则压缩成可审计的提示词约束，不注入 AI 待确认内容。"""

    lines: list[str] = []
    total_length = 0
    for entry in entries:
        category = _enum_value(entry.category)
        content = _compact_text(entry.content)[:500]
        if not content:
            continue
        line = f"[{category}] {entry.title}：{content}"
        if total_length + len(line) > 12000:
            break
        lines.append(line)
        total_length += len(line)
    return "\n".join(lines)


_SPECIAL_CLOTHING_TERMS = (
    "校服",
    "制服",
    "军装",
    "警服",
    "礼服",
    "婚纱",
    "戏服",
    "古装",
    "盔甲",
    "防护服",
    "雨衣",
    "白大褂",
    "病号服",
    "囚服",
    "工装",
    "工作服",
    "舞台服",
    "演出服",
    "宇航服",
    "潜水服",
)

_GENERIC_CLOTHING_TERMS = (
    "默认服装",
    "日常服装",
    "日常穿着",
    "普通衣服",
    "普通服装",
    "常规服装",
    "简洁日常服装",
    "简洁日常",
    "便装",
    "浅色上衣",
    "长裤",
    "长裙",
)


def _has_special_clothing(text: str) -> bool:
    return any(term in text for term in _SPECIAL_CLOTHING_TERMS)


def _strip_generic_clothing_text(text: str) -> str:
    """角色描述进入画面提示词前，去掉普通默认穿着；特殊服装保留。"""
    value = _compact_text(text)
    if not value:
        return ""
    parts = re.split(r"([；;，,。])", value)
    kept: list[str] = []
    for idx in range(0, len(parts), 2):
        piece = parts[idx].strip()
        sep = parts[idx + 1] if idx + 1 < len(parts) else ""
        if not piece:
            continue
        if any(term in piece for term in _GENERIC_CLOTHING_TERMS) and _has_special_clothing(piece):
            piece = _cleanup_default_clothing_mentions(piece).strip()
            if not piece:
                continue
        elif any(term in piece for term in _GENERIC_CLOTHING_TERMS):
            continue
        if re.search(r"(穿|身着|穿着|衣服|服装|上衣|裤|裙|外套|衬衫|T恤|针织|毛衣|风衣|夹克|鞋|靴|帽|围巾)", piece) and not _has_special_clothing(piece):
            continue
        kept.append(piece + sep)
    cleaned = "".join(kept).strip("；;，,。 ")
    return cleaned or value


def _join_context_lines(lines: list[str]) -> str:
    cleaned = [line for line in lines if line]
    return "\n".join(cleaned) if cleaned else "无"


def _build_character_context(characters: list[Character]) -> str:
    if not characters:
        # 空镜必须显式声明，否则图像模型会按场景常识脑补人物（如出租车内自动画出司机乘客）
        return "本镜为空镜：画面中不出现任何人物（也不要出现人影、剪影、倒影中的人、路人）。"
    lines: list[str] = []
    for character in characters:
        fragments: list[str] = []
        if _compact_text(character.description):
            desc = _strip_generic_clothing_text(_compact_text(character.description))
            if desc:
                fragments.append(desc)
        actor = getattr(character, "actor", None)
        if actor is not None and _compact_text(getattr(actor, "name", None)):
            actor_desc = f"演员形象：{_compact_text(getattr(actor, 'name', None))}"
            if _compact_text(getattr(actor, "description", None)):
                actor_desc += f"（{_compact_text(getattr(actor, 'description', None))}）"
            fragments.append(actor_desc)
        line = f"- {character.name}"
        if fragments:
            line += f"：{'；'.join(fragments)}"
        lines.append(line)
    return _join_context_lines(lines)


def _build_named_asset_context(assets: list[Scene] | list[Prop]) -> str:
    lines: list[str] = []
    for asset in assets:
        line = f"- {asset.name}"
        if _compact_text(getattr(asset, "description", None)):
            line += f"：{_compact_text(getattr(asset, 'description', None))}"
        lines.append(line)
    return _join_context_lines(lines)


def _build_art_direction_context(
    *,
    project: object | None,
    characters: list[Character],
    scenes: list[Scene],
    props: list[Prop],
) -> str:
    """生成艺术指导统筹说明，统一约束画面提示词的剧情、风格和实体一致性。"""
    project_name = _compact_text(getattr(project, "name", None))
    project_desc = _compact_text(getattr(project, "description", None))
    visual_style = _enum_value(getattr(project, "visual_style", None))
    style = _enum_value(getattr(project, "style", None))
    lines = [
        "你是本项目的艺术指导，负责统筹画面提示词，而不是简单拼接字段。",
        "最终提示词必须同时符合剧情意图、项目风格、角色特征、场景质感和相邻镜头连续性。",
    ]
    project_parts = [part for part in [project_name, project_desc, visual_style, style] if part]
    if project_parts:
        lines.append(f"项目基调：{'；'.join(project_parts)}。")
    if characters:
        lines.append("角色一致性：保留已确认角色的年龄、气质、外貌和身份，不要改名、换脸或改造为不符合剧情的人设。")
    else:
        lines.append("空镜一致性：没有角色时，画面应以环境、道具或动作痕迹承担叙事，不要自动添加人物。")
    if scenes:
        scene_names = "、".join(scene.name for scene in scenes[:2])
        lines.append(f"场景一致性：以 {scene_names} 的空间结构、材质、光线和年代痕迹作为环境锚点。")
    if props:
        prop_names = "、".join(prop.name for prop in props[:3])
        lines.append(f"道具控制：{prop_names} 只在符合剧情动作或画面焦点时出现，不要喧宾夺主。")
    lines.append("生成时先判断当前帧真正要表达什么，再选择画面主体、空间重点、光线和情绪，不要平均罗列所有信息。")
    return "\n".join(lines)


def _build_subject_priority(
    *,
    characters: list[Character],
    scenes: list[Scene],
    props: list[Prop],
) -> str:
    parts: list[str] = []
    if characters:
        primary_names = "、".join(character.name for character in characters[:2])
        parts.append(f"优先以角色 {primary_names} 作为画面主体")
        if len(characters) > 2:
            support_names = "、".join(character.name for character in characters[2:])
            parts.append(f"其余角色 {support_names} 仅在能强化画面关系时再补充")
    else:
        parts.append("本镜为空镜（无任何人物），以动作拍点描述的物体/环境细节作为画面主体")
    if scenes:
        parts.append(f"优先建立场景 {scenes[0].name} 的环境信息")
    if props:
        prop_names = "、".join(prop.name for prop in props[:2])
        parts.append(f"道具 {prop_names} 仅在进入主动作或构图焦点时重点写入")
    return "；".join(parts) if parts else "优先根据镜头信息突出主角色和主场景，不必平均铺陈所有元素"


def _truncate_for_prompt(value: str | None, *, limit: int = 80) -> str:
    text = _compact_text(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


_CONTINUITY_DESCRIPTION_LABELS = (
    "画面描述",
    "固定场景结构",
    "观看方向",
    "可视范围",
    "空间锚点",
    "人物调度与轴线",
    "角色当前状态",
)


def _build_continuity_state_summary(value: str | None) -> str:
    """从结构化镜头描述提取连续性真值，避免新增字段被固定长度截断。"""
    raw = str(value or "").strip()
    fields: dict[str, str] = {}
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if "：" not in line:
            continue
        label, content = line.split("：", 1)
        if label in _CONTINUITY_DESCRIPTION_LABELS and content.strip():
            fields[label] = _truncate_for_prompt(content, limit=240)
    if not fields:
        return _truncate_for_prompt(raw, limit=220)
    return "；".join(f"{label}：{fields[label]}" for label in _CONTINUITY_DESCRIPTION_LABELS if label in fields)


def _summarize_neighbor_shot(shot: Shot | None) -> tuple[str, str, str]:
    """生成相邻镜头的标题、摘录和状态摘要，供连续性提示词使用。"""
    if shot is None:
        return "", "", ""
    detail = getattr(shot, "detail", None)
    scene_name = _compact_text(getattr(getattr(detail, "scene", None), "name", None))
    camera_parts = [
        _enum_value(getattr(detail, "camera_shot", None)),
        _enum_value(getattr(detail, "angle", None)),
        _enum_value(getattr(detail, "movement", None)),
    ]
    camera_text = " / ".join(part for part in camera_parts if part)
    # 分镜拆解会把场景结构、观看方向、可视范围、角色状态和人物轴线写入 description；
    # 按字段抽取比截取开头更可靠，否则后部的角色状态会在相邻镜头链中消失。
    description = _build_continuity_state_summary(getattr(detail, "description", None))
    summary_parts = [
        f"场景：{scene_name}" if scene_name else "",
        f"镜头语言：{camera_text}" if camera_text else "",
        f"画面状态：{description}" if description else "",
    ]
    return (
        _compact_text(getattr(shot, "title", None)),
        _truncate_for_prompt(getattr(shot, "script_excerpt", None), limit=80),
        "；".join(part for part in summary_parts if part),
    )


def _build_continuity_guidance(
    *,
    previous_shot: Shot | None,
    current_shot: Shot,
    next_shot: Shot | None,
) -> str:
    """基于相邻镜头关系生成静态图片可用的空间一致性约束。"""
    guidance: list[str] = []
    current_detail = getattr(current_shot, "detail", None)
    current_scene_id = str(getattr(current_detail, "scene_id", "") or "")
    previous_detail = getattr(previous_shot, "detail", None) if previous_shot else None
    next_detail = getattr(next_shot, "detail", None) if next_shot else None
    previous_scene_id = str(getattr(previous_detail, "scene_id", "") or "")
    next_scene_id = str(getattr(next_detail, "scene_id", "") or "")

    if previous_shot is not None:
        guidance.append("仅参考上一镜头的可见空间方向、左右轴线、主体朝向和场景材质，不写动作承接")
        if current_scene_id and previous_scene_id and current_scene_id == previous_scene_id:
            guidance.append("上一镜头与当前镜头处于同一场景，只保持可见建筑方向、空间轴线、主体朝向、角色左右站位和前后距离稳定")

    if next_shot is not None:
        guidance.append("仅参考下一镜头的可见空间方向和视觉重心，不写未来动作、变化或衔接结果")
        if current_scene_id and next_scene_id and current_scene_id == next_scene_id:
            guidance.append("下一镜头与当前镜头处于同一场景，只保持画面内可见的空间关系、角色相对位置和材质体系一致")

    return "；".join(guidance)


def _build_composition_anchor(
    *,
    detail: ShotDetail,
    previous_shot: Shot | None,
    next_shot: Shot | None,
    characters: list[Character],
    scenes: list[Scene],
) -> str:
    """根据镜头语言和相邻镜头关系生成静态图片构图锚点建议。"""
    anchors: list[str] = []
    camera_shot = _enum_value(detail.camera_shot)
    movement = _enum_value(detail.movement)

    if camera_shot in {"ECU", "CU"}:
        anchors.append("可视范围集中在主角色面部、手部或关键对象的局部，背景只保留少量可见环境")
    elif camera_shot in {"MS", "FS"}:
        anchors.append("可视范围应同时包含主体全貌或半身与周围关键环境，交代人物和空间关系")
    else:
        anchors.append("可视范围应优先交代空间整体、入口/通道/建筑边界和主体所在位置")

    if movement in {"DOLLY_IN", "ZOOM_IN"}:
        anchors.append("按较紧的静态构图处理，让主体或关键对象位于画面视觉中心")
    elif movement in {"DOLLY_OUT", "ZOOM_OUT"}:
        anchors.append("按较宽的静态构图处理，保留更多前景、中景和背景空间，不描述拉远")
    elif movement in {"PAN", "TILT", "TRACK", "CRANE", "HANDHELD", "STEADICAM"}:
        anchors.append("只取该镜头语言对应的静态取景方向和画面边界，使用稳定静态构图")
    elif movement == "STATIC":
        anchors.append("保持静态构图稳定，明确主体在画面中的重心位置")

    if scenes:
        anchors.append(f"以场景 {scenes[0].name} 作为空间锚点，明确镜头朝向、可见区域边界和前中后景")
    if characters:
        anchors.append(f"优先锁定角色 {characters[0].name} 在画面内的朝向、视线和左右位置")

    if previous_shot is not None and str(getattr(getattr(previous_shot, 'detail', None), 'scene_id', '') or '') == str(detail.scene_id or ''):
        anchors.append("与上一镜头同场景时，只保持静态画面中的空间轴线和主体朝向")
    if next_shot is not None and str(getattr(getattr(next_shot, 'detail', None), 'scene_id', '') or '') == str(detail.scene_id or ''):
        anchors.append("与下一镜头同场景时，只保持静态画面中的视觉重心与空间方向")

    return "；".join(anchors)


def _build_screen_direction_guidance(
    *,
    detail: ShotDetail,
    previous_shot: Shot | None,
    next_shot: Shot | None,
    dialogue_summary: str,
    character_names: list[str],
) -> str:
    """生成人物朝向、视线与左右轴线建议。"""
    guidance: list[str] = []
    angle = _enum_value(detail.angle)

    if angle == "OVER_SHOULDER":
        guidance.append("原始机位为过肩时，改写为稳定平视或轻侧面双人关系；禁止写肩部、肩背或借肩遮挡；保持双方左右站位、前后距离、朝向和视线落点清楚")
    elif angle == "EYE_LEVEL":
        guidance.append("优先保持人物视线水平和对视方向稳定，避免无故翻转左右朝向")
    else:
        guidance.append("明确主体朝向和视线落点，避免人物突然改向或跳轴")

    if dialogue_summary.strip():
        guidance.append("存在对白时，优先保证说话者与受话者的视线关系连续")
    if len(character_names) >= 2:
        guidance.append(f"角色 {character_names[0]} 与 {character_names[1]} 的左右站位、前后距离、朝向和对视方向应保持一致")
    elif character_names:
        guidance.append(f"角色 {character_names[0]} 的朝向与视线落点应在相邻镜头中保持延续")

    current_scene_id = str(detail.scene_id or "")
    previous_scene_id = str(getattr(getattr(previous_shot, "detail", None), "scene_id", "") or "")
    next_scene_id = str(getattr(getattr(next_shot, "detail", None), "scene_id", "") or "")
    if previous_shot is not None and current_scene_id and current_scene_id == previous_scene_id:
        guidance.append("与上一镜头同场景时，不要无故翻转人物面向和左右轴线")
    if next_shot is not None and current_scene_id and current_scene_id == next_scene_id:
        guidance.append("与下一镜头同场景时，当前镜头结尾应保留可延续的视线方向")

    return "；".join(guidance)


_SEQUENTIAL_REACTION_KEYWORDS = (
    "听到",
    "闻声",
    "忽然",
    "突然",
    "下意识",
    "立刻",
    "随即",
    "紧接着",
    "随后",
    "脱手",
    "掉在地上",
    "捂住耳朵",
    "捂住",
    "蹲下",
    "跪下",
    "跌坐",
    "转身",
    "回头",
)


def _has_sequential_reaction_chain(*values: str | None) -> bool:
    """判断文本是否包含明显的连续反应链，供首帧时间切片加权使用。"""
    text = " ".join(_compact_text(value) for value in values if _compact_text(value))
    if not text:
        return False
    keyword_hits = sum(1 for keyword in _SEQUENTIAL_REACTION_KEYWORDS if keyword in text)
    punctuation_hits = text.count("，") + text.count("。") + text.count("；") + text.count("、")
    return keyword_hits >= 2 or (keyword_hits >= 1 and punctuation_hits >= 2)


def _build_frame_specific_guidance(
    *,
    frame_type: str,
    previous_shot: Shot | None,
    next_shot: Shot | None,
    detail: ShotDetail,
    script_excerpt: str,
    action_beats: list[str],
) -> str:
    """按首帧/关键帧/尾帧生成静态图片专项提示。"""
    guidance: list[str] = []
    if frame_type == "first":
        guidance.append("首帧应优先建立静态空间、主体初始站位、镜头朝向和第一眼可见范围")
        guidance.append("首帧只写当前图片内可见的主体状态和环境，不写后续动作、变化过程或结果")
        guidance.append("若剧本存在连续反应链，只截取可见的静态起始姿态，不描述动作链本身")
        if _has_sequential_reaction_chain(script_excerpt, detail.description):
            guidance.append("当前镜头存在明显连续反应链，首帧只保留画面内最早可见的姿态和空间关系，不写过程")
        if previous_shot is not None:
            guidance.append("首帧可参考上一镜头的可见空间轴线和主体朝向，但不得写上一镜头动作")
        if _enum_value(detail.camera_shot) in {"LS", "ELS", "MLS"}:
            guidance.append("当前景别较大时，优先写清环境可视范围、人物位置关系和镜头观看方向")
    elif frame_type == "last":
        guidance.append("尾帧应写成单张静态图片中的稳定主体姿态、视线停留点和可见环境")
        if next_shot is not None:
            guidance.append("尾帧可参考下一镜头的空间方向，但不得写下一镜头或未来动作")
        guidance.append("尾帧中的主体姿态应清晰稳定，只描述当前图片可见状态")
    else:
        guidance.append("关键帧应锁定镜头内最具代表性的单张静态画面，不要平均描述整个过程")
        guidance.append("优先选择构图最清楚、信息最集中、主体姿态最有代表性的静态状态")
        if _enum_value(detail.movement) in {"DOLLY_IN", "ZOOM_IN", "TRACK"}:
            guidance.append("若原镜头存在推进或跟拍，只转化为更紧凑的静态取景，不写推进、移动或运动过程")
    beat_item = pick_action_beat_for_frame(frame_type, action_beats)
    if beat_item is not None:
        phase_label = {
            "trigger": "触发阶段",
            "peak": "峰值阶段",
            "aftermath": "收束阶段",
        }.get(beat_item.phase, "当前阶段")
        guidance.append(f"当前帧只把动作拍点“{beat_item.text}”转化为当前图片内可见的静态姿态、对象位置和环境关系（{phase_label}），不写过程")
    return "；".join(guidance)


def _format_action_beat_phase_summary(action_beats: list[str]) -> str:
    """格式化动作拍点阶段摘要，供 agent 输入与调试预览复用。"""
    sequence = infer_action_beat_sequence(action_beats)
    phase_labels = {
        "trigger": "触发",
        "peak": "峰值",
        "aftermath": "收束",
    }
    return "；".join(
        f"{index + 1}. {phase_labels.get(item.phase, item.phase)} · {item.text}"
        for index, item in enumerate(sequence)
    )


def _same_scene(shot: Shot | None, current_scene_id: str) -> bool:
    """判断相邻镜头是否与当前镜头处于同一场景。"""
    return bool(
        shot is not None
        and current_scene_id
        and str(getattr(getattr(shot, "detail", None), "scene_id", "") or "") == current_scene_id
    )


def _score_director_guidance_item(
    *,
    category: str,
    text: str,
    frame_type: str,
    has_dialogue: bool,
    character_count: int,
    same_scene_with_previous: bool,
    same_scene_with_next: bool,
    movement: str,
) -> int:
    """为 guidance 句子打分，优先保留更能稳定镜头连续性的约束。"""
    score = 0
    if category == "frame":
        score += 10
        if frame_type == "first" and ("建立空间" in text or "起始状态" in text):
            score += 5
        if frame_type == "first" and ("触发瞬间" in text or "后续完成动作" in text or "尚未完成" in text):
            score += 6
        if frame_type == "first" and ("连续反应链" in text or "最早的可见瞬间" in text or "完成态" in text):
            score += 8
        if frame_type == "key" and ("动作峰值" in text or "戏剧张力" in text or "情绪爆点" in text):
            score += 5
        if frame_type == "last" and ("动作收束" in text or "情绪余韵" in text or "停留点" in text):
            score += 5
    elif category == "continuity":
        score += 8
        if "承接上一镜头" in text:
            score += 3
            if same_scene_with_previous:
                score += 4
        if "下一镜头" in text or "收束" in text:
            score += 3
            if same_scene_with_next:
                score += 4
        if "空间轴线" in text or "主体朝向稳定" in text or "视觉重心" in text:
            score += 3
    elif category == "composition":
        score += 7
        if frame_type == "first" and ("空间锚点" in text or "建立空间" in text):
            score += 5
        if frame_type == "key" and ("画面重心" in text or "推进" in text or "焦点" in text):
            score += 4
        if frame_type == "last" and ("视觉落点" in text or "空间方向" in text):
            score += 4
        if "锁定角色" in text or "重心位置" in text:
            score += 2
    elif category == "screen":
        score += 6
        if "不要无故翻转" in text or "跳轴" in text:
            score += 5
        if has_dialogue and ("视线关系连续" in text or "对视方向" in text):
            score += 5
        if character_count >= 2 and ("左右站位" in text or "对视方向" in text):
            score += 4
        if same_scene_with_previous or same_scene_with_next:
            if "同场景" in text or "视线方向" in text or "左右轴线" in text:
                score += 4
        if frame_type == "last" and "视线方向" in text:
            score += 2
    if movement in {"DOLLY_IN", "ZOOM_IN", "TRACK"} and category == "composition" and "推进" in text:
        score += 3
    return score


def _build_director_must_categories(
    *,
    frame_type: str,
    has_dialogue: bool,
    character_count: int,
    same_scene_with_previous: bool,
    same_scene_with_next: bool,
    movement: str,
) -> list[str]:
    """按镜头风险动态决定哪些 guidance 应提升为必须项。"""
    if frame_type == "first":
        must_categories = ["frame", "continuity", "composition"]
    elif frame_type == "key":
        must_categories = ["frame", "composition", "continuity"]
    else:
        must_categories = ["frame", "continuity", "screen"]

    if movement in {"DOLLY_IN", "ZOOM_IN", "TRACK"} and "composition" in must_categories:
        must_categories = ["composition" if item == "composition" else item for item in must_categories]
        must_categories.insert(0, must_categories.pop(must_categories.index("composition")))

    if has_dialogue or character_count >= 2 or same_scene_with_previous or same_scene_with_next:
        if "screen" not in must_categories:
            insert_at = 2 if frame_type == "key" else 1
            must_categories.insert(min(insert_at, len(must_categories)), "screen")
        elif frame_type == "last":
            must_categories.insert(1, must_categories.pop(must_categories.index("screen")))

    deduped: list[str] = []
    for category in must_categories:
        if category not in deduped:
            deduped.append(category)
    return deduped[:4]


def _build_director_command_summary(
    *,
    frame_type: str,
    frame_specific_guidance: str,
    continuity_guidance: str,
    composition_anchor: str,
    screen_direction_guidance: str,
    has_dialogue: bool,
    character_count: int,
    same_scene_with_previous: bool,
    same_scene_with_next: bool,
    movement: str,
) -> str:
    """将多类 guidance 压缩成高优先级导演指令摘要。"""
    seen: set[str] = set()

    def _split_bucket(category: str, block: str) -> list[str]:
        bucket: list[str] = []
        for piece in str(block or "").split("；"):
            text = piece.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            bucket.append(text)
        return sorted(
            bucket,
            key=lambda item: _score_director_guidance_item(
                category=category,
                text=item,
                frame_type=frame_type,
                has_dialogue=has_dialogue,
                character_count=character_count,
                same_scene_with_previous=same_scene_with_previous,
                same_scene_with_next=same_scene_with_next,
                movement=movement,
            ),
            reverse=True,
        )

    buckets = {
        "frame": _split_bucket("frame", frame_specific_guidance),
        "continuity": _split_bucket("continuity", continuity_guidance),
        "composition": _split_bucket("composition", composition_anchor),
        "screen": _split_bucket("screen", screen_direction_guidance),
    }
    must_categories = _build_director_must_categories(
        frame_type=frame_type,
        has_dialogue=has_dialogue,
        character_count=character_count,
        same_scene_with_previous=same_scene_with_previous,
        same_scene_with_next=same_scene_with_next,
        movement=movement,
    )

    must_items: list[str] = []
    prefer_items: list[str] = []
    consumed_must_items: set[str] = set()

    for category in must_categories:
        bucket = buckets.get(category) or []
        if bucket:
            must_items.append(bucket[0])
            consumed_must_items.add(bucket[0])

    frame_bucket = buckets.get("frame") or []
    if frame_type == "first" and len(frame_bucket) > 1:
        primary_frame_item = frame_bucket[0]
        if any(keyword in primary_frame_item for keyword in ("连续反应链", "触发瞬间", "尚未完成", "完成态")):
            secondary_frame_item = frame_bucket[1]
            if secondary_frame_item not in consumed_must_items:
                must_items.append(secondary_frame_item)
                consumed_must_items.add(secondary_frame_item)

    for category in ("frame", "continuity", "composition", "screen"):
        bucket = buckets.get(category) or []
        if category in must_categories and bucket:
            prefer_items.extend(item for item in bucket[1:] if item not in consumed_must_items)
            continue
        prefer_items.extend(item for item in bucket if item not in consumed_must_items)
        if category not in must_categories and bucket:
            head = bucket[0]
            if head not in consumed_must_items:
                prefer_items.insert(0, head)

    items = [*(f"必须：{item}" for item in must_items[:4]), *(f"优先：{item}" for item in prefer_items[:4])]
    if not items:
        return ""
    return "；".join(items[:8])


def _extract_context_names(context_text: str | None) -> list[str]:
    names: list[str] = []
    for raw_line in str(context_text or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        body = line[2:]
        name = body.split("：", 1)[0].strip()
        if name:
            names.append(name)
    return names


def _cleanup_generated_prompt(prompt: str) -> str:
    text = str(prompt or "").strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned: list[str] = []
    after_generation_heading = False
    for line in lines:
        if line == "## 生成内容":
            after_generation_heading = True
            cleaned = []
            continue
        if line == "## 图片内容说明" or re.fullmatch(r"图\d+\s*[:：].*", line):
            continue
        cleaned.append(line)
    if after_generation_heading and cleaned:
        return _cleanup_default_clothing_mentions("\n".join(cleaned).strip())
    return _cleanup_default_clothing_mentions("\n".join(cleaned).strip())


def _cleanup_default_clothing_mentions(prompt: str) -> str:
    """去掉无意义的默认服装描述；特殊服装词不处理。"""
    text = str(prompt or "").strip()
    if not text:
        return text
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
        r"[，,；;。\s]*(身着|穿着|穿|身穿)?简洁日常服装",
        r"[，,；;。\s]*(身着|穿着|穿|身穿)?简洁日常衣物",
        r"[，,；;。\s]*(身着|穿着|穿|身穿)?便装",
    )
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"^[，,；;。\s]+", "", text)
    text = re.sub(r"^[和及与、\s]+", "", text)
    text = re.sub(r"[和及与、\s]+([，,；;。])", r"\1", text)
    text = re.sub(r"[，,；;]\s*([。])", r"\1", text)
    text = text.replace("过肩视角", "平视轻侧面视角")
    text = text.replace("过肩镜头", "平视轻侧面构图")
    return text.strip()


def _validate_generated_prompt(prompt: str, input_dict: dict[str, object]) -> list[str]:
    issues: list[str] = []
    text = str(prompt or "").strip()
    if not text:
        return ["生成结果为空"]
    if "## 图片内容说明" in text or "## 生成内容" in text or re.search(r"(^|\n)\s*图\d+\s*[:：]", text):
        issues.append("结果混入了图片映射说明，应只保留基础提示词")
    video_terms = (
        "运镜",
        "推进",
        "拉远",
        "跟拍",
        "横摇",
        "缓缓",
        "逐渐",
        "逐步",
        "动作链",
        "运动过程",
        "变化过程",
        "后续",
        "下一镜头",
        "上一镜头",
        "镜头开始",
        "镜头结束",
        "画面外",
        "不可见区域",
        "看不见的",
    )
    hits = [term for term in video_terms if term in text]
    if hits:
        issues.append(f"结果混入视频化或不可见区域表达：{'、'.join(hits[:5])}；应改为单张静态生图提示词，只写画面内可见内容")
    if any(term in text for term in ("肩部", "肩背", "借肩", "前景肩")):
        issues.append("结果不应使用肩部/肩背/借肩遮挡构图；应改为横向构图、高角度构图、平视轻侧面或双人关系构图")
    if any(term in text for term in ("默认服装", "默认衣服", "默认穿着", "日常服装", "普通衣服", "普通服装", "便装")):
        issues.append("结果不应强调普通默认穿着；只有校服、制服、礼服、雨衣、工作服等特殊服装才需要写入")
    if "过肩" in text:
        issues.append("结果不应使用过肩视角；应改为稳定平视或轻侧面双人关系，避免前景肩背遮挡导致图像错乱")
    relation_terms = [term for term in ("动作匹配", "视线匹配", "视觉重心匹配", "转场", "承接前镜", "切到下一镜") if term in text]
    if relation_terms:
        issues.append(f"结果混入镜间关系说明：{'、'.join(relation_terms)}；应只呈现匹配后的静态构图与可见状态")
    shot_description = str(input_dict.get("shot_description") or "")
    face_not_visible = any(
        term in shot_description
        for term in ("背对镜头", "背面可见", "仅见背影", "面部不可见", "面部被遮挡", '"visibility": "背')
    )
    facial_detail_terms = tuple(
        term for term in ("眼神", "瞳孔", "眼角", "嘴角", "泪痕", "眉头", "面部表情", "脸上露出")
        if term in text
    )
    if face_not_visible and facial_detail_terms:
        issues.append(f"角色面部在本镜不可见，却描述了面部细节：{'、'.join(facial_detail_terms[:4])}")
    if str(input_dict.get("camera_shot") or "").upper() in {"LS", "ELS"}:
        fine_detail_terms = tuple(term for term in ("瞳孔", "眼角", "睫毛", "毛孔", "皮肤纹理", "泪痕", "嘴角细微") if term in text)
        if fine_detail_terms:
            issues.append(f"大景别无法可靠呈现这些细微信息：{'、'.join(fine_detail_terms[:4])}；应改用姿态、轮廓或空间关系表达")
    required_groups = {
        "景别或视角": ("景", "近景", "中景", "远景", "全景", "特写", "视角", "俯视", "仰视", "平视", "低机位", "高机位", "广角"),
        "主体外观或姿态": ("外貌", "发型", "姿态", "站", "坐", "侧身", "背影", "表情", "建筑", "空间", "陈设", "道具", "轮廓"),
        "场景环境": ("场景", "环境", "室内", "室外", "走廊", "教室", "街道", "房间", "建筑", "地面", "墙面", "门窗", "天空"),
        "光影": ("光", "阴影", "晨光", "夕阳", "逆光", "侧光", "自然光", "柔光", "明暗"),
        "色彩": ("色", "色调", "冷暖", "暖色", "冷色", "中性影调", "低饱和", "高饱和"),
        "构图或可视范围": ("构图", "前景", "中景", "背景", "画面", "左侧", "右侧", "中央", "纵深", "可见", "范围", "边界"),
        "质感": ("质感", "材质", "写实", "电影感", "胶片", "纹理", "颗粒", "细节", "实拍"),
    }
    missing_groups = [
        label
        for label, keywords in required_groups.items()
        if not any(keyword in text for keyword in keywords)
    ]
    if missing_groups:
        issues.append(f"完整画面 Prompt 缺少这些要素：{'、'.join(missing_groups[:4])}；应融合景别、视角、主体外貌与姿态、场景环境、光影、色彩、构图、质感")
    primary_characters = _extract_context_names(str(input_dict.get("character_context") or ""))
    if primary_characters:
        lead_names = primary_characters[:2]
        if not any(name in text for name in lead_names):
            issues.append(f"结果缺少主角色名称：{'、'.join(lead_names)}")
    return issues


def _build_retry_guidance(issues: list[str]) -> str:
    if not issues:
        return ""
    return "请严格修正以下问题后重新生成：\n- " + "\n- ".join(issues)


async def build_run_args(
    db: AsyncSession,
    *,
    shot_id: str,
    frame_type: str,
) -> dict:
    normalized_frame_type = normalize_frame_type(frame_type)
    shot_stmt = (
        select(Shot)
        .options(
            selectinload(Shot.detail).selectinload(ShotDetail.dialog_lines),
            selectinload(Shot.detail).selectinload(ShotDetail.scene),
            selectinload(Shot.chapter).selectinload(Chapter.project),
            selectinload(Shot.character_links)
            .selectinload(ShotCharacterLink.character)
            .selectinload(Character.actor),
            selectinload(Shot.scene_links).selectinload(ProjectSceneLink.scene),
            selectinload(Shot.prop_links).selectinload(ProjectPropLink.prop),
        )
        .where(Shot.id == shot_id)
    )
    shot = (await db.execute(shot_stmt)).scalar_one_or_none()
    if shot is None:
        raise HTTPException(status_code=404, detail=entity_not_found("Shot"))
    if shot.detail is None:
        raise HTTPException(status_code=404, detail=entity_not_found("ShotDetail"))

    detail = shot.detail
    neighbors_stmt = (
        select(Shot)
        .options(selectinload(Shot.detail).selectinload(ShotDetail.scene))
        .where(
            Shot.chapter_id == shot.chapter_id,
            Shot.index.in_([shot.index - 1, shot.index + 1]),
        )
    )
    neighbor_rows = (await db.execute(neighbors_stmt)).scalars().all()
    previous_shot = next((item for item in neighbor_rows if item.index == shot.index - 1), None)
    next_shot = next((item for item in neighbor_rows if item.index == shot.index + 1), None)
    previous_title, previous_excerpt, previous_state = _summarize_neighbor_shot(previous_shot)
    next_title, next_excerpt, next_goal = _summarize_neighbor_shot(next_shot)
    # 保留说话者与听者，正反打和反应镜头才能基于真实对话关系稳定视线轴。
    dialog_summary = "\n".join(
        "：".join(
            part
            for part in [
                _compact_text(getattr(line, "speaker_name", None)),
                _compact_text(getattr(line, "text", None)),
            ]
            if part
        )
        + (f" → {_compact_text(getattr(line, 'target_name', None))}" if _compact_text(getattr(line, "target_name", None)) else "")
        for line in (detail.dialog_lines or [])
        if _compact_text(getattr(line, "text", None))
    )
    project = getattr(getattr(shot, "chapter", None), "project", None)
    visual_style = _enum_value(getattr(project, "visual_style", None))
    style = _enum_value(getattr(project, "style", None))
    unify_style = bool(getattr(project, "unify_style", True)) if project is not None else True
    project_brain_context = ""
    if project is not None:
        brain_stmt = (
            select(ProjectBrainEntry)
            .where(
                ProjectBrainEntry.project_id == project.id,
                ProjectBrainEntry.status == "confirmed",
            )
            .order_by(ProjectBrainEntry.locked.desc(), ProjectBrainEntry.category, ProjectBrainEntry.title)
        )
        project_brain_context = _build_project_brain_context(
            list((await db.execute(brain_stmt)).scalars().all())
        )

    characters = [
        link.character
        for link in sorted(list(getattr(shot, "character_links", []) or []), key=lambda item: (item.index, item.id))
        if getattr(link, "character", None) is not None
    ]
    scenes_by_id: dict[str, Scene] = {}
    detail_scene = getattr(detail, "scene", None)
    if detail_scene is not None:
        scenes_by_id[str(detail_scene.id)] = detail_scene
    for link in list(getattr(shot, "scene_links", []) or []):
        scene = getattr(link, "scene", None)
        if scene is not None:
            scenes_by_id[str(scene.id)] = scene
    props = [
        link.prop
        for link in list(getattr(shot, "prop_links", []) or [])
        if getattr(link, "prop", None) is not None
    ]
    scenes = list(scenes_by_id.values())

    continuity_guidance = _build_continuity_guidance(
        previous_shot=previous_shot,
        current_shot=shot,
        next_shot=next_shot,
    )
    action_beats = [str(item).strip() for item in list(getattr(detail, "action_beats", []) or []) if str(item).strip()]
    selected_action_beat = pick_action_beat_for_frame(normalized_frame_type, action_beats)
    action_beat_phases = _format_action_beat_phase_summary(action_beats)
    composition_anchor = _build_composition_anchor(
        detail=detail,
        previous_shot=previous_shot,
        next_shot=next_shot,
        characters=characters,
        scenes=scenes,
    )
    screen_direction_guidance = _build_screen_direction_guidance(
        detail=detail,
        previous_shot=previous_shot,
        next_shot=next_shot,
        dialogue_summary=dialog_summary,
        character_names=[character.name for character in characters],
    )
    frame_specific_guidance = _build_frame_specific_guidance(
        frame_type=normalized_frame_type,
        previous_shot=previous_shot,
        next_shot=next_shot,
        detail=detail,
        script_excerpt=shot.script_excerpt or "",
        action_beats=action_beats,
    )
    return {
        "shot_id": shot_id,
        "frame_type": normalized_frame_type,
        "input": {
            "script_excerpt": shot.script_excerpt or "",
            "title": shot.title or "",
            "visual_style": visual_style,
            "style": style,
            "unify_style": unify_style,
            "project_brain_context": project_brain_context,
            "camera_shot": _enum_value(detail.camera_shot),
            "angle": _enum_value(detail.angle),
            "movement": _enum_value(detail.movement),
            "atmosphere": detail.atmosphere or "",
            "shot_description": detail.description or "",
            "mood_tags": detail.mood_tags or [],
            "vfx_type": _enum_value(detail.vfx_type),
            "vfx_note": detail.vfx_note or "",
            "duration": detail.duration,
            "scene_id": detail.scene_id,
            "dialog_summary": dialog_summary,
            "action_beats": action_beats,
            "action_beat_phases": action_beat_phases,
            "selected_action_beat_phase": getattr(selected_action_beat, "phase", ""),
            "selected_action_beat_text": getattr(selected_action_beat, "text", ""),
            "character_context": _build_character_context(characters),
            "scene_context": _build_named_asset_context(scenes),
            "prop_context": _build_named_asset_context(props),
            "art_direction": _build_art_direction_context(
                project=project,
                characters=characters,
                scenes=scenes,
                props=props,
            ),
            "subject_priority": _build_subject_priority(
                characters=characters,
                scenes=scenes,
                props=props,
            ),
            "previous_shot_title": previous_title,
            "previous_shot_script_excerpt": previous_excerpt,
            "previous_shot_end_state": previous_state,
            "next_shot_title": next_title,
            "next_shot_script_excerpt": next_excerpt,
            "next_shot_start_goal": next_goal,
            "continuity_guidance": continuity_guidance,
            "composition_anchor": composition_anchor,
            "screen_direction_guidance": screen_direction_guidance,
            "frame_specific_guidance": frame_specific_guidance,
            "director_command_summary": _build_director_command_summary(
                frame_type=normalized_frame_type,
                frame_specific_guidance=frame_specific_guidance,
                continuity_guidance=continuity_guidance,
                composition_anchor=composition_anchor,
                screen_direction_guidance=screen_direction_guidance,
                has_dialogue=bool(dialog_summary.strip()),
                character_count=len(characters),
                same_scene_with_previous=_same_scene(previous_shot, str(detail.scene_id or "")),
                same_scene_with_next=_same_scene(next_shot, str(detail.scene_id or "")),
                movement=_enum_value(detail.movement),
            ),
        },
    }


async def resolve_batch_frame_prompt(
    db: AsyncSession,
    *,
    shot_id: str,
    frame_type: str,
) -> str:
    """为批量生图读取已保存提示词；没有时从镜头真值构造稳定的本地提示词。

    批量队列必须在未配置文本模型时仍可工作，因此这里不调用 LLM。图片任务的
    最终渲染阶段仍会补入角色、场景、道具与连续性约束。
    """

    normalized_frame_type = normalize_frame_type(frame_type)
    stmt = (
        select(Shot, ShotDetail)
        .join(ShotDetail, ShotDetail.id == Shot.id)
        .where(Shot.id == shot_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=entity_not_found("ShotDetail"))
    shot, detail = row

    prompt_field = prompt_field_for_frame(normalized_frame_type)
    saved_prompt = _compact_text(getattr(detail, prompt_field, ""))
    if saved_prompt:
        return saved_prompt

    parts: list[str] = []
    for value in (
        _enum_value(detail.camera_shot),
        _compact_text(shot.title),
        _compact_text(detail.description),
        _compact_text(shot.script_excerpt),
    ):
        if value and value not in parts:
            parts.append(value)
    prompt = "，".join(parts).strip("，")
    if not prompt:
        raise HTTPException(status_code=400, detail="No usable frame prompt source")
    return prompt[:1000]


async def read_saved_frame_prompt(
    db: AsyncSession,
    *,
    shot_id: str,
    frame_type: str,
) -> str:
    """读取镜头已保存的指定帧提示词，不生成临时内容。"""

    detail = await db.get(ShotDetail, shot_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=entity_not_found("ShotDetail"))
    return _compact_text(getattr(detail, prompt_field_for_frame(frame_type), ""))


async def persist_frame_prompt(
    db: AsyncSession,
    *,
    shot_id: str,
    frame_type: str,
    prompt: str,
) -> str:
    """保存批量流程实际使用的提示词，确保页面与图片任务来源一致。"""

    value = _compact_text(prompt)
    if not value:
        raise HTTPException(status_code=400, detail="frame prompt is required")
    detail = await db.get(ShotDetail, shot_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=entity_not_found("ShotDetail"))
    setattr(detail, prompt_field_for_frame(frame_type), value)
    await db.flush()
    return value


async def run_shot_frame_prompt_task(
    task_id: str,
    run_args: dict,
) -> None:
    async with async_session_maker() as session:
        try:
            store = SqlAlchemyTaskStore(session)
            await store.set_status(task_id, TaskStatus.running)
            await store.set_progress(task_id, 10)
            await session.commit()
            log_task_event("shot_frame_prompt", task_id, "running")
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("shot_frame_prompt", task_id, "cancelled", stage="before_execute")
                return

            frame_type = str(run_args.get("frame_type") or "")
            shot_id = str(run_args.get("shot_id") or "")
            input_dict = dict(run_args.get("input") or {})
            llm = await session.run_sync(lambda sync_db: build_default_text_llm_sync(sync_db, thinking=False))

            if frame_type == "first":
                agent = ShotFirstFramePromptAgent(llm)
            elif frame_type == "last":
                agent = ShotLastFramePromptAgent(llm)
            else:
                agent = ShotKeyFramePromptAgent(llm)
            input_dict.setdefault("retry_guidance", "")
            result = await agent.aextract(**input_dict)
            result.prompt = _cleanup_default_clothing_mentions(result.prompt)
            quality_issues = _validate_generated_prompt(result.prompt, input_dict)
            if quality_issues:
                retry_input = dict(input_dict)
                retry_input["retry_guidance"] = _build_retry_guidance(quality_issues)
                retry_result = await agent.aextract(**retry_input)
                retry_result.prompt = _cleanup_default_clothing_mentions(retry_result.prompt)
                retry_issues = _validate_generated_prompt(retry_result.prompt, retry_input)
                if not retry_issues:
                    input_dict = retry_input
                    result = retry_result
                    quality_issues = []
                else:
                    result.prompt = _cleanup_generated_prompt(retry_result.prompt) or _cleanup_generated_prompt(result.prompt) or result.prompt
                    input_dict = retry_input
                    quality_issues = retry_issues
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("shot_frame_prompt", task_id, "cancelled", stage="after_execute")
                return

            if not shot_id:
                raise RuntimeError("Missing shot_id in run args")
            shot_detail = await session.get(ShotDetail, shot_id)
            if shot_detail is None:
                raise RuntimeError("ShotDetail not found when persisting prompt")

            if frame_type == "first":
                shot_detail.first_frame_prompt = result.prompt
            elif frame_type == "last":
                shot_detail.last_frame_prompt = result.prompt
            else:
                shot_detail.key_frame_prompt = result.prompt

            result_payload = result.model_dump()
            result_payload["debug_context"] = dict(input_dict)
            result_payload["quality_checks"] = {
                "passed": not quality_issues,
                "issues": quality_issues,
            }
            await store.set_result(task_id, result_payload)
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("shot_frame_prompt", task_id, "cancelled", stage="after_persist")
                return
            await store.set_progress(task_id, 100)
            await store.set_status(task_id, TaskStatus.succeeded)
            await recompute_shot_status(session, shot_id=shot_id)
            await session.commit()
            log_task_event("shot_frame_prompt", task_id, "succeeded")
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            async with async_session_maker() as s2:
                store = SqlAlchemyTaskStore(s2)
                await store.set_error(task_id, str(exc))
                await store.set_status(task_id, TaskStatus.failed)
                shot_id = str(run_args.get("shot_id") or "")
                if shot_id:
                    await recompute_shot_status(s2, shot_id=shot_id)
                await s2.commit()
            log_task_failure("shot_frame_prompt", task_id, str(exc))
