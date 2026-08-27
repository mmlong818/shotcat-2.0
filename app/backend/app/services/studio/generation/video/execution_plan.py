from __future__ import annotations

from app.schemas.skills import CAMERA_ANGLE_ZH, CAMERA_MOVEMENT_ZH, SHOT_TYPE_ZH
from app.schemas.studio.shots import (
    ShotVideoPromptPackRead,
    VideoExecutionPlanRead,
    VideoReferenceBindingRead,
    VideoTimelineSegmentRead,
)


_MODE_PATHS: dict[str, tuple[str, str]] = {
    "text_only": ("text_to_video", "文字生成视频"),
    "first": ("single_frame_i2v", "首帧图生视频"),
    "last": ("single_frame_i2v", "尾帧约束视频"),
    "key": ("single_frame_i2v", "关键帧图生视频"),
    "first_last": ("first_last_i2v", "首尾帧图生视频"),
    "first_last_key": ("multi_reference_i2v", "多参考帧图生视频"),
}

_REFERENCE_ROLES: dict[str, tuple[str, str, str]] = {
    "first": ("start", "0 秒起始状态", "锁定视频开场的构图、人物位置、服装与动作起点。"),
    "last": ("end", "结束目标状态", "视频结束时自然抵达该构图与人物状态，不要在最后一刻跳变。"),
    "key": ("key_state", "关键动作锚点", "保持角色、场景与核心构图一致，用作镜头中段的视觉锚点。"),
}

_PHASE_PURPOSES = {
    "trigger": "建立与触发",
    "peak": "动作推进",
    "aftermath": "结果与落点",
}


def _compact(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _camera_text(pack: ShotVideoPromptPackRead) -> str:
    shot = SHOT_TYPE_ZH.get(pack.camera.camera_shot, pack.camera.camera_shot)
    angle = CAMERA_ANGLE_ZH.get(pack.camera.angle, pack.camera.angle)
    movement = CAMERA_MOVEMENT_ZH.get(pack.camera.movement, pack.camera.movement)
    parts = [item for item in (shot, angle, movement) if item]
    return " / ".join(parts) or "保持构图稳定，镜头运动服从主体动作"


def _timeline_beats(pack: ShotVideoPromptPackRead) -> list[tuple[str, str]]:
    phase_by_text = {item.text: item.phase for item in pack.action_beat_phases}
    beats = [(_compact(item), phase_by_text.get(item, "peak")) for item in pack.action_beats if _compact(item)]
    if beats:
        return beats[:4]
    fallback = _compact(pack.shot_description or pack.script_excerpt or pack.title)
    return [(fallback or "主体完成镜头规定动作并形成稳定落点", "peak")]


def _dialogue_lines(pack: ShotVideoPromptPackRead) -> list[str]:
    return [_compact(item) for item in pack.dialogue_summary.splitlines() if _compact(item)]


def _segment_audio(
    *,
    index: int,
    segment_count: int,
    dialogue_lines: list[str],
    sound_effects: str,
) -> str:
    parts: list[str] = []
    if dialogue_lines:
        if index < segment_count - 1 and index < len(dialogue_lines):
            parts.append(f"同期对白：{dialogue_lines[index]}")
        elif index == segment_count - 1 and index < len(dialogue_lines):
            remaining = dialogue_lines[index:]
            if remaining:
                parts.append(f"同期对白：{'；'.join(remaining)}")
    if sound_effects and index == 0:
        parts.append(f"声音设计：{sound_effects}")
    if not parts:
        parts.append("环境声与动作音效同期发生")
    return "；".join(parts)


def _build_references(reference_mode: str, images: list[str]) -> list[VideoReferenceBindingRead]:
    frame_types = {
        "first": ("first",),
        "last": ("last",),
        "key": ("key",),
        "first_last": ("first", "last"),
        "first_last_key": ("first", "last", "key"),
        "text_only": (),
    }[reference_mode]
    references: list[VideoReferenceBindingRead] = []
    for frame_type, file_id in zip(frame_types, images, strict=False):
        role, title, instruction = _REFERENCE_ROLES[frame_type]
        references.append(
            VideoReferenceBindingRead(
                file_id=file_id,
                frame_type=frame_type,
                role=role,
                title=title,
                instruction=instruction,
            )
        )
    return references


def _build_warnings(reference_mode: str) -> list[str]:
    if reference_mode == "text_only":
        return ["未使用画面参考，角色外观、场景空间与构图一致性完全依赖文字描述。"]
    if reference_mode == "key":
        return ["关键帧只是镜头中的视觉锚点，不应被模型误当作 0 秒首帧或结束帧。"]
    if reference_mode == "first":
        return ["只有起始状态约束，结束画面由动作计划与提示词控制。"]
    if reference_mode == "last":
        return ["只有结束状态约束，开场构图由动作计划与提示词控制。"]
    return []


def build_video_execution_plan(
    *,
    pack: ShotVideoPromptPackRead,
    reference_mode: str,
    images: list[str],
) -> VideoExecutionPlanRead:
    """从已落地的镜头数据推导一份可审阅、可重复的视频执行计划。"""
    duration = max(int(pack.camera.duration or 1), 1)
    beats = _timeline_beats(pack)
    dialogue_lines = _dialogue_lines(pack)
    camera = _camera_text(pack)
    sound_effects = _compact(pack.sound_effects)
    segment_count = len(beats)
    timeline: list[VideoTimelineSegmentRead] = []

    for index, (action, phase) in enumerate(beats):
        start_s = round(duration * index / segment_count, 2)
        end_s = duration if index == segment_count - 1 else round(duration * (index + 1) / segment_count, 2)
        purpose = _PHASE_PURPOSES.get(phase, "动作推进")
        if index == 0 and _compact(pack.narrative_function):
            purpose = f"{purpose}：{_compact(pack.narrative_function)}"
        timeline.append(
            VideoTimelineSegmentRead(
                start_s=start_s,
                end_s=end_s,
                purpose=purpose,
                action=action,
                camera=camera,
                audio=_segment_audio(
                    index=index,
                    segment_count=segment_count,
                    dialogue_lines=dialogue_lines,
                    sound_effects=sound_effects,
                ),
            )
        )

    start_action = beats[0][0]
    end_action = beats[-1][0]
    start_prefix = "严格承接首帧" if reference_mode in {"first", "first_last", "first_last_key"} else "承接上一镜头"
    end_prefix = "自然抵达尾帧" if reference_mode in {"last", "first_last", "first_last_key"} else "形成可剪辑的稳定落点"
    path, path_label = _MODE_PATHS[reference_mode]
    if dialogue_lines:
        audio_approach = "对白与人物口型、动作同期；保留必要环境声与动作音效"
    else:
        audio_approach = "以环境声和动作音效为主，不自动添加旁白"
    audio_approach += "；使用镜头已配置的背景音乐" if pack.has_bgm else "；不默认添加背景音乐"

    return VideoExecutionPlanRead(
        shot_id=pack.shot_id,
        target_duration_s=duration,
        reference_mode=reference_mode,
        generation_path=path,
        generation_path_label=path_label,
        start_state=f"{start_prefix}：{start_action}",
        end_state=f"{end_prefix}：{end_action}",
        audio_approach=audio_approach,
        references=_build_references(reference_mode, images),
        timeline=timeline,
        warnings=_build_warnings(reference_mode),
    )


def render_execution_plan(plan: VideoExecutionPlanRead) -> str:
    """把执行计划转成模型可直接执行的时间轴文本。"""
    lines = [
        f"视频执行计划（完整覆盖 {plan.target_duration_s} 秒）：",
        f"生成路径：{plan.generation_path_label}",
        f"起始状态：{plan.start_state}",
    ]
    for item in plan.timeline:
        lines.append(
            f"{item.start_s:g}-{item.end_s:g} 秒｜{item.purpose}｜主体动作：{item.action}｜"
            f"镜头：{item.camera}｜声音：{item.audio}"
        )
    lines.extend(
        (
            f"结束状态：{plan.end_state}",
            f"声音总则：{plan.audio_approach}",
        )
    )
    if plan.references:
        reference_text = "；".join(f"{item.title}（{item.instruction}）" for item in plan.references)
        lines.append(f"参考图职责：{reference_text}")
    return "\n".join(lines)


def enrich_prompt_with_execution_plan(*, rendered_prompt: str, plan: VideoExecutionPlanRead) -> str:
    text = str(rendered_prompt or "").strip()
    if "视频执行计划（完整覆盖" in text:
        return text
    plan_text = render_execution_plan(plan)
    return f"{text}\n\n{plan_text}".strip() if text else plan_text
