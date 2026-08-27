"""MiniMax H3 V2 视频请求体映射。"""

from __future__ import annotations

from typing import Any

from app.core.contracts.video_generation import VideoGenerationInput, _strip_optional_b64
from app.core.integrations.minimax.video_capabilities import validate_minimax_video_options
from app.core.integrations.openai.video_payload import to_image_data_url


def build_content(input_: VideoGenerationInput) -> list[dict[str, Any]]:
    prompt = (input_.prompt or "").strip()
    if not prompt:
        raise RuntimeError("MiniMax H3 requires a non-empty text prompt")

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    first = _strip_optional_b64(input_.first_frame_base64)
    last = _strip_optional_b64(input_.last_frame_base64)
    key = _strip_optional_b64(input_.key_frame_base64)
    if key and (first or last):
        raise RuntimeError("MiniMax H3 cannot mix key reference images with first/last frames")
    if first:
        content.append(
            {"type": "image_url", "image_url": {"url": to_image_data_url(first)}, "role": "first_frame"}
        )
    if last:
        content.append(
            {"type": "image_url", "image_url": {"url": to_image_data_url(last)}, "role": "last_frame"}
        )
    if key:
        content.append(
            {"type": "image_url", "image_url": {"url": to_image_data_url(key)}, "role": "reference_image"}
        )
    return content


def build_create_task_body(input_: VideoGenerationInput) -> dict[str, Any]:
    validate_minimax_video_options(input_)
    if input_.seconds is None:
        raise RuntimeError("MiniMax H3 requires an integer duration")

    body: dict[str, Any] = {
        "model": input_.model or "MiniMax-H3",
        "content": build_content(input_),
        "duration": int(input_.seconds),
        "resolution": input_.resolution or "768P",
    }
    if input_.first_frame_base64 or input_.last_frame_base64:
        body["ratio"] = "adaptive"
    else:
        body["ratio"] = input_.ratio
    return body
