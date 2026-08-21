"""与 LLM 相关的 Pydantic Schema（Provider/Model/ModelSettings）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.llm import LogLevel, ModelCategoryKey, ProviderStatus


class ProviderBase(BaseModel):
    """供应商通用字段（不含敏感字段）。"""

    name: str = Field(..., description="供应商名称")
    base_url: str = Field(..., description="文本/通用 API Base URL")
    image_base_url: str | None = Field(None, description="图片能力 API Base URL（可选覆盖）")
    video_base_url: str | None = Field(None, description="视频能力 API Base URL（可选覆盖）")
    description: str = Field("", description="说明")
    status: ProviderStatus = Field(
        ProviderStatus.testing,
        description="状态：active/testing/disabled",
    )
    created_by: str = Field("", description="创建人")


class ProviderCreate(ProviderBase):
    """创建供应商时的请求体，允许填写敏感字段。"""

    id: str = Field(..., description="供应商 ID")
    api_key: str = Field("", description="API Key（敏感，不在响应中回显）")
    api_secret: str = Field("", description="API Secret（敏感，不在响应中回显）")


class ProviderUpdate(BaseModel):
    """更新供应商时的可选字段。"""

    name: str | None = Field(None, description="供应商名称")
    base_url: str | None = Field(None, description="文本/通用 API Base URL")
    image_base_url: str | None = Field(None, description="图片能力 API Base URL（可选覆盖）")
    video_base_url: str | None = Field(None, description="视频能力 API Base URL（可选覆盖）")
    description: str | None = Field(None, description="说明")
    status: ProviderStatus | None = Field(
        None,
        description="状态：active/testing/disabled",
    )
    api_key: str | None = Field(None, description="API Key（敏感，不在响应中回显）")
    api_secret: str | None = Field(None, description="API Secret（敏感，不在响应中回显）")


class ProviderRead(ProviderBase):
    """对外返回的供应商信息（不包含 api_key/api_secret）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="供应商 ID")


class ProviderSupportedRead(BaseModel):
    """系统支持的供应商能力清单。"""

    key: str = Field(..., description="供应商稳定键")
    display_name: str = Field(..., description="供应商展示名")
    aliases: list[str] = Field(default_factory=list, description="可识别别名")
    supported_categories: list[ModelCategoryKey] = Field(
        default_factory=list,
        description="支持的模型类别",
    )
    default_base_url: str | None = Field(None, description="默认 API Base URL")
    requires_api_key: bool = Field(True, description="是否要求 api_key")
    requires_api_secret: bool = Field(False, description="是否要求 api_secret")
    is_experimental: bool = Field(False, description="是否实验性供应商")


class VideoGenerationOptionsRead(BaseModel):
    """当前默认视频模型对应的生成参数选项。"""

    provider: str = Field(..., description="供应商稳定键")
    model_id: str = Field(..., description="默认视频模型 ID")
    model_name: str = Field(..., description="默认视频模型名称")
    allowed_ratios: list[str] = Field(default_factory=list, description="当前模型允许的比例选项")
    default_ratio: str = Field(..., description="当前模型默认比例")


class ImageGenerationOptionsRead(BaseModel):
    """当前默认图片模型对应的关键帧规格选项。"""

    provider: str = Field(..., description="供应商稳定键")
    model_id: str = Field(..., description="默认图片模型 ID")
    model_name: str = Field(..., description="默认图片模型名称")
    supported_ratios: list[str] = Field(default_factory=list, description="当前模型支持的目标比例")
    default_resolution_profile: str = Field(..., description="当前模型默认分辨率档位")
    ratio_size_profiles: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="按比例和分辨率档位映射得到的像素尺寸",
    )


class ModelBase(BaseModel):
    """模型通用字段。"""

    name: str = Field(..., description="模型名称")
    category: ModelCategoryKey = Field(..., description="模型类别：text/image/video")
    provider_id: str = Field(..., description="所属供应商 ID")
    params: dict[str, Any] = Field(default_factory=dict, description="模型参数（JSON）")
    description: str = Field("", description="说明")
    created_by: str = Field("", description="创建人")


class ModelCreate(ModelBase):
    """创建模型请求体。"""

    id: str = Field(..., description="模型 ID")


class ModelUpdate(BaseModel):
    """更新模型请求体（全部可选）。"""

    name: str | None = Field(None, description="模型名称")
    category: ModelCategoryKey | None = Field(None, description="模型类别")
    provider_id: str | None = Field(None, description="所属供应商 ID")
    params: dict[str, Any] | None = Field(None, description="模型参数（JSON）")
    description: str | None = Field(None, description="说明")


class ModelRead(ModelBase):
    """对外返回的模型信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="模型 ID")


class ModelSettingsBase(BaseModel):
    """模型全局设置通用字段。"""

    default_text_model_id: str | None = Field(None, description="默认文本模型 ID")
    default_image_model_id: str | None = Field(None, description="默认图片模型 ID")
    default_video_model_id: str | None = Field(None, description="默认视频模型 ID")
    api_timeout: int = Field(30, description="API 超时（秒）")
    log_level: LogLevel = Field(LogLevel.info, description="日志级别")


class ModelSettingsUpdate(ModelSettingsBase):
    """更新或保存模型全局设置请求体。"""

    pass


class ModelSettingsRead(ModelSettingsBase):
    """对外返回的模型全局设置。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="设置行 ID（通常为 1）")


class ModelCapabilitySetupRead(BaseModel):
    """单类模型的启动可用状态；只返回是否存在 Key，不返回 Key 本身。"""

    category: ModelCategoryKey = Field(..., description="模型类别")
    ready: bool = Field(..., description="该类别是否已具备可用模型和供应商")
    reason: str | None = Field(None, description="未就绪原因代码")
    message: str = Field(..., description="面向用户的状态说明")
    model_id: str | None = Field(None, description="当前默认模型 ID")
    model_name: str | None = Field(None, description="当前默认模型名称")
    provider_id: str | None = Field(None, description="当前供应商 ID")
    provider_key: str | None = Field(None, description="当前供应商稳定键")
    provider_name: str | None = Field(None, description="当前供应商名称")
    has_api_key: bool = Field(False, description="供应商是否已保存 API Key")


class InitialModelSetupStatusRead(BaseModel):
    """工作台启动时使用的文字与图片模型配置状态。"""

    ready: bool = Field(..., description="文字与图片模型是否都已就绪")
    text: ModelCapabilitySetupRead
    image: ModelCapabilitySetupRead


class InitialModelConnection(BaseModel):
    """首次启动时保存的一类外部模型连接。"""

    provider_key: str = Field(..., min_length=1, max_length=64, description="供应商稳定键")
    base_url: str | None = Field(None, max_length=1024, description="兼容 API Base URL")
    api_key: str = Field("", max_length=4096, description="API Key（敏感，不在响应中回显）")
    model_name: str = Field(..., min_length=1, max_length=255, description="供应商侧模型 ID")

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        """只接受 HTTP(S) 端点，避免把无效地址保存到运行时配置。"""

        normalized = (value or "").strip()
        if not normalized:
            return None
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return normalized.rstrip("/")


class InitialModelSetupRequest(BaseModel):
    """首次启动配置请求；已就绪的类别可以省略并保持原配置。"""

    text: InitialModelConnection | None = None
    image: InitialModelConnection | None = None
