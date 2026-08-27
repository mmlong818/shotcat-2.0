"""MiniMax H3 视频能力声明。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.integrations.video_capabilities import ALLOWED_RATIOS, VideoModelCapability

if TYPE_CHECKING:
    from app.core.contracts.video_generation import VideoGenerationInput


_MINIMAX_H3 = VideoModelCapability(
    supports_seed=False,
    supports_watermark=False,
    allowed_ratios=set(ALLOWED_RATIOS),
    default_ratio="16:9",
    min_seconds=4,
    max_seconds=15,
    supported_reference_modes={"text_only", "first", "last", "first_last", "key"},
    allowed_resolutions={"768P", "2K"},
    default_resolution="768P",
)
_MINIMAX_MODEL_OVERRIDES: dict[str, VideoModelCapability] = {}


def register_minimax_video_capability(*, model_prefix: str, capability: VideoModelCapability) -> None:
    prefix = model_prefix.strip().lower()
    if not prefix:
        raise ValueError("model_prefix must not be empty")
    _MINIMAX_MODEL_OVERRIDES[prefix] = capability


def clear_minimax_video_capability_overrides() -> None:
    _MINIMAX_MODEL_OVERRIDES.clear()


def resolve_minimax_video_capability(model: str | None) -> VideoModelCapability:
    value = (model or "").strip().lower()
    for prefix, capability in sorted(
        _MINIMAX_MODEL_OVERRIDES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if value.startswith(prefix):
            return capability
    return _MINIMAX_H3


def validate_minimax_video_options(input_: VideoGenerationInput) -> None:
    from app.core.contracts.video_generation import VideoGenerationInput
    from app.core.integrations.video_capabilities import validate_video_options

    assert isinstance(input_, VideoGenerationInput)
    validate_video_options(provider="minimax", model=input_.model, input_=input_)
