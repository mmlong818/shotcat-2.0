"""视频能力映射单测。"""

from __future__ import annotations

import pytest

from app.core.contracts.video_generation import VideoGenerationInput
from app.core.integrations.video_capabilities import (
    VideoModelCapability,
    clear_video_model_capability_overrides,
    infer_ratio_from_size,
    register_video_model_capability,
    resolve_video_capability,
    validate_video_options,
)


def test_infer_ratio_from_size_supports_ratio_and_resolution() -> None:
    assert infer_ratio_from_size("16:9") == "16:9"
    assert infer_ratio_from_size("1920x1080") == "16:9"
    assert infer_ratio_from_size("720x1280") == "9:16"
    assert infer_ratio_from_size("abc") is None


def test_resolve_video_capability_prefers_longest_prefix() -> None:
    clear_video_model_capability_overrides(provider="openai")
    register_video_model_capability(
        provider="openai",
        model_prefix="gpt-video",
        capability=VideoModelCapability(supports_seed=False),
    )
    register_video_model_capability(
        provider="openai",
        model_prefix="gpt-video-pro",
        capability=VideoModelCapability(supports_seed=True, supports_watermark=False),
    )
    try:
        cap = resolve_video_capability(provider="openai", model="gpt-video-pro-1")
        assert cap.supports_seed is True
        assert cap.supports_watermark is False
    finally:
        clear_video_model_capability_overrides(provider="openai")


def test_validate_video_options_rejects_capability_mismatch() -> None:
    clear_video_model_capability_overrides(provider="volcengine")
    register_video_model_capability(
        provider="volcengine",
        model_prefix="seedream-video",
        capability=VideoModelCapability(supports_seed=False),
    )
    try:
        inp = VideoGenerationInput(prompt="test", model="seedream-video-v1", ratio="16:9", seed=7)
        with pytest.raises(ValueError) as exc_info:
            validate_video_options(provider="volcengine", model=inp.model, input_=inp)
        assert "seed is not supported" in str(exc_info.value)
    finally:
        clear_video_model_capability_overrides(provider="volcengine")


def test_minimax_h3_capability_exposes_real_duration_and_resolution_limits() -> None:
    capability = resolve_video_capability(provider="minimax", model="MiniMax-H3")
    assert capability.min_seconds == 4
    assert capability.max_seconds == 15
    assert capability.allowed_resolutions == {"768P", "2K"}
    assert capability.default_resolution == "768P"
    assert "first_last" in (capability.supported_reference_modes or set())
    assert "first_last_key" not in (capability.supported_reference_modes or set())

    valid = VideoGenerationInput(
        prompt="test",
        model="MiniMax-H3",
        ratio="16:9",
        seconds=5,
        resolution="2K",
    )
    validate_video_options(provider="minimax", model=valid.model, input_=valid)

    invalid = valid.model_copy(update={"seconds": 3})
    with pytest.raises(ValueError, match="seconds must be >= 4"):
        validate_video_options(provider="minimax", model=invalid.model, input_=invalid)
