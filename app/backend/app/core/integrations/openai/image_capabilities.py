"""OpenAI 图片能力声明与覆盖注册。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.integrations.image_capabilities import ImageModelCapability

if TYPE_CHECKING:
    from app.core.contracts.image_generation import ImageGenerationInput

_OPENAI_DEFAULT = ImageModelCapability(
    supports_seed=True,
    supports_watermark=True,
)

_GPT_IMAGE_2_RATIO_SIZE_PROFILES = {
    "16:9": {"standard": "1536x864", "high": "2048x1152"},
    "4:3": {"standard": "1024x768", "high": "2048x1536"},
    "1:1": {"standard": "1024x1024", "high": "2048x2048"},
    "3:2": {"standard": "1536x1024", "high": "2048x1360"},
    "2:3": {"standard": "1024x1536", "high": "1360x2048"},
    "3:4": {"standard": "768x1024", "high": "1536x2048"},
    "9:16": {"standard": "864x1536", "high": "1152x2048"},
    "21:9": {"standard": "1792x768", "high": "2688x1152"},
}

_OPENAI_BUILTIN_CAPABILITIES: dict[str, ImageModelCapability] = {
    "gpt-image-2": ImageModelCapability(
        supports_seed=False,
        supports_watermark=False,
        supported_ratios=set(_GPT_IMAGE_2_RATIO_SIZE_PROFILES),
        ratio_size_profiles=_GPT_IMAGE_2_RATIO_SIZE_PROFILES,
    ),
}

# key: 模型前缀（小写）
_OPENAI_MODEL_OVERRIDES: dict[str, ImageModelCapability] = {}


def register_openai_image_capability(*, model_prefix: str, capability: ImageModelCapability) -> None:
    prefix = model_prefix.strip().lower()
    if not prefix:
        raise ValueError("model_prefix must not be empty")
    _OPENAI_MODEL_OVERRIDES[prefix] = capability


def clear_openai_image_capability_overrides() -> None:
    _OPENAI_MODEL_OVERRIDES.clear()


def _pick_override(model: str | None) -> ImageModelCapability | None:
    if not model:
        return None
    value = model.strip().lower()
    if not value:
        return None
    for prefix, cap in sorted(_OPENAI_MODEL_OVERRIDES.items(), key=lambda item: len(item[0]), reverse=True):
        if value.startswith(prefix):
            return cap
    return None


def resolve_openai_image_capability(model: str | None) -> ImageModelCapability:
    override = _pick_override(model)
    if override is not None:
        return override
    value = str(model or "").strip().lower()
    for prefix, capability in sorted(
        _OPENAI_BUILTIN_CAPABILITIES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if value.startswith(prefix):
            return capability
    return _OPENAI_DEFAULT


def validate_openai_image_options(input_: ImageGenerationInput) -> None:
    """OpenAI 能力校验入口（避免调用侧传 provider 字面量）。"""
    from app.core.contracts.image_generation import ImageGenerationInput
    from app.core.integrations.image_capabilities import validate_image_options

    assert isinstance(input_, ImageGenerationInput)
    validate_image_options(provider="openai", model=input_.model, input_=input_)
