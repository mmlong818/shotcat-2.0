"""工作台首次启动所需的模型就绪检查与原子配置。"""

from __future__ import annotations

import hashlib

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.bootstrap import bootstrap_all_registries
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider, ProviderStatus
from app.schemas.llm import (
    InitialModelConnection,
    InitialModelSetupRequest,
    InitialModelSetupStatusRead,
    ModelCapabilitySetupRead,
)
from app.services.llm.provider_registry import (
    get_provider_spec,
    is_provider_category_supported,
    resolve_provider_key_from_name,
)


def _missing_status(
    category: ModelCategoryKey,
    *,
    reason: str,
    message: str,
    model: Model | None = None,
    provider: Provider | None = None,
    provider_key: str | None = None,
) -> ModelCapabilitySetupRead:
    """统一构造未就绪结果，确保响应永远不会带出敏感凭证。"""

    return ModelCapabilitySetupRead(
        category=category,
        ready=False,
        reason=reason,
        message=message,
        model_id=model.id if model else None,
        model_name=model.name if model else None,
        provider_id=provider.id if provider else (model.provider_id if model else None),
        provider_key=provider_key,
        provider_name=provider.name if provider else None,
        has_api_key=bool((provider.api_key or "").strip()) if provider else False,
    )


async def _category_status(
    db: AsyncSession,
    *,
    settings: ModelSettings | None,
    category: ModelCategoryKey,
) -> ModelCapabilitySetupRead:
    """检查默认模型、类别、供应商状态及必需 Key 是否完整。"""

    setting_field = f"default_{category.value}_model_id"
    model_id = getattr(settings, setting_field, None) if settings else None
    if not model_id:
        return _missing_status(
            category,
            reason="missing_default_model",
            message=f"尚未配置默认{('文字' if category == ModelCategoryKey.text else '图片')}模型",
        )

    model = await db.get(Model, model_id)
    if model is None:
        return _missing_status(
            category,
            reason="model_not_found",
            message="默认模型记录不存在，请重新配置",
        )
    if model.category != category:
        return _missing_status(
            category,
            reason="model_category_mismatch",
            message="默认模型类别不匹配，请重新配置",
            model=model,
        )

    provider = await db.get(Provider, model.provider_id)
    if provider is None:
        return _missing_status(
            category,
            reason="provider_not_found",
            message="模型供应商记录不存在，请重新配置",
            model=model,
        )

    bootstrap_all_registries()
    try:
        provider_key = resolve_provider_key_from_name(provider.name)
        provider_spec = get_provider_spec(provider_key)
    except HTTPException:
        return _missing_status(
            category,
            reason="unsupported_provider",
            message="当前供应商不受支持，请重新配置",
            model=model,
            provider=provider,
        )

    if not is_provider_category_supported(provider_key, category):
        return _missing_status(
            category,
            reason="unsupported_category",
            message="当前供应商不支持这类模型，请重新配置",
            model=model,
            provider=provider,
            provider_key=provider_key,
        )
    provider_status = provider.status.value if isinstance(provider.status, ProviderStatus) else str(provider.status)
    if provider_status.strip().lower() == ProviderStatus.disabled.value:
        return _missing_status(
            category,
            reason="provider_disabled",
            message="模型供应商已停用，请重新配置",
            model=model,
            provider=provider,
            provider_key=provider_key,
        )
    has_api_key = bool((provider.api_key or "").strip())
    if provider_spec.requires_api_key and not has_api_key:
        return _missing_status(
            category,
            reason="missing_api_key",
            message="模型供应商尚未填写 API Key",
            model=model,
            provider=provider,
            provider_key=provider_key,
        )

    return ModelCapabilitySetupRead(
        category=category,
        ready=True,
        reason=None,
        message="已就绪",
        model_id=model.id,
        model_name=model.name,
        provider_id=provider.id,
        provider_key=provider_key,
        provider_name=provider.name,
        has_api_key=has_api_key,
    )


async def get_initial_model_setup_status(db: AsyncSession) -> InitialModelSetupStatusRead:
    """返回启动门禁需要的文字、图片模型状态。"""

    settings = await db.get(ModelSettings, 1)
    text = await _category_status(db, settings=settings, category=ModelCategoryKey.text)
    image = await _category_status(db, settings=settings, category=ModelCategoryKey.image)
    return InitialModelSetupStatusRead(ready=text.ready and image.ready, text=text, image=image)


def _configured_provider_id(category: ModelCategoryKey, provider_key: str) -> str:
    """为文字和图片保留独立供应商记录，使两者可以使用不同 Key。"""

    return f"startup-{category.value}-{provider_key}"[:64]


def _configured_model_id(category: ModelCategoryKey, provider_key: str, model_name: str) -> str:
    """生成稳定且长度受控的数据库模型 ID，真实模型 ID 仍保存在 name。"""

    digest = hashlib.sha256(f"{provider_key}:{model_name}".encode("utf-8")).hexdigest()[:12]
    return f"startup-{category.value}-{digest}"


async def _upsert_connection(
    db: AsyncSession,
    *,
    category: ModelCategoryKey,
    connection: InitialModelConnection,
) -> Model:
    """校验并写入一类供应商和模型；调用方在同一事务中更新默认值。"""

    bootstrap_all_registries()
    provider_key = connection.provider_key.strip().lower()
    provider_spec = get_provider_spec(provider_key)
    if not is_provider_category_supported(provider_key, category):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"供应商 {provider_spec.display_name} 不支持 {category.value} 模型",
        )

    provider_id = _configured_provider_id(category, provider_key)
    provider = await db.get(Provider, provider_id)
    incoming_key = connection.api_key.strip()
    if provider_spec.requires_api_key and not incoming_key and not (
        provider and (provider.api_key or "").strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"请填写 {provider_spec.display_name} API Key",
        )
    base_url = connection.base_url or provider_spec.default_base_url or ""
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"请填写 {provider_spec.display_name} API Base URL",
        )

    if provider is None:
        provider = Provider(
            id=provider_id,
            name=provider_spec.display_name,
            base_url=base_url,
            image_base_url=base_url if category == ModelCategoryKey.image else None,
            api_key=incoming_key,
            api_secret="",
            description="工作台首次启动配置",
            status=ProviderStatus.active,
            created_by="startup-setup",
        )
        db.add(provider)
    else:
        provider.name = provider_spec.display_name
        provider.base_url = base_url
        if category == ModelCategoryKey.image:
            provider.image_base_url = base_url
        if incoming_key:
            provider.api_key = incoming_key
        provider.status = ProviderStatus.active

    model_name = connection.model_name.strip()
    model_id = _configured_model_id(category, provider_key, model_name)
    model = await db.get(Model, model_id)
    if model is None:
        model = Model(
            id=model_id,
            name=model_name,
            category=category,
            provider_id=provider.id,
            params={},
            description="工作台首次启动配置",
            created_by="startup-setup",
        )
        db.add(model)
    else:
        model.name = model_name
        model.category = category
        model.provider_id = provider.id
    await db.flush()
    return model


async def save_initial_model_setup(
    db: AsyncSession,
    *,
    body: InitialModelSetupRequest,
) -> InitialModelSetupStatusRead:
    """原子保存缺失的文字/图片连接，并将其设为默认模型。"""

    settings = await db.get(ModelSettings, 1)
    if settings is None:
        settings = ModelSettings(id=1)
        db.add(settings)
        await db.flush()

    if body.text is not None:
        text_model = await _upsert_connection(db, category=ModelCategoryKey.text, connection=body.text)
        settings.default_text_model_id = text_model.id
    if body.image is not None:
        image_model = await _upsert_connection(db, category=ModelCategoryKey.image, connection=body.image)
        settings.default_image_model_id = image_model.id
    if body.text is None and body.image is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少配置一种模型")

    await db.flush()
    result = await get_initial_model_setup_status(db)
    if not result.ready:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请完成文字和图片模型配置")
    return result
