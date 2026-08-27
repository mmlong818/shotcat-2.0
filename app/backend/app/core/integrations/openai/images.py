"""OpenAI Images API（generations / edits）。"""

from __future__ import annotations

import base64
import binascii
import mimetypes
import time
from typing import Any
from urllib.parse import unquote_to_bytes, urlparse

from app.core.integrations.http_logging import (
    json_dumps_for_log,
    log_image_http_request,
    log_image_http_response,
    safe_body_for_log_openai,
)
from app.core.contracts.image_generation import (
    ImageGenerationInput,
    ImageGenerationResult,
    ImageItem,
)
from app.core.contracts.provider import ProviderConfig
from app.core.integrations.image_capabilities import resolve_image_size
from app.core.integrations.openai.image_capabilities import validate_openai_image_options


class OpenAIImageApiAdapter:
    """OpenAI 图片生成 HTTP；无状态，可单测替换。"""

    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: ImageGenerationInput,
        timeout_s: float,
    ) -> ImageGenerationResult:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for image generation tasks") from e

        base_url = (cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        resolved_size = resolve_image_size(
            provider="openai",
            model=inp.model,
            purpose=inp.purpose,
            target_ratio=inp.target_ratio,
            resolution_profile=inp.resolution_profile,
            requested_size=inp.size,
        )
        resolved_input = inp.model_copy(update={"size": resolved_size})
        validate_openai_image_options(resolved_input)
        auth_headers = {"Authorization": f"Bearer {cfg.api_key}"}

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            if resolved_input.images:
                data: dict[str, str] = {
                    "prompt": resolved_input.prompt,
                    "n": str(resolved_input.n),
                }
                if resolved_input.model:
                    data["model"] = resolved_input.model
                if resolved_input.size:
                    data["size"] = resolved_input.size
                files = []
                file_log: list[dict[str, Any]] = []
                for index, ref in enumerate(resolved_input.images, start=1):
                    filename, content, content_type = await _resolve_reference_file(
                        client=client,
                        ref=ref,
                        index=index,
                    )
                    files.append(("image[]", (filename, content, content_type)))
                    file_log.append(
                        {
                            "name": filename,
                            "content_type": content_type,
                            "bytes": len(content),
                        }
                    )

                url = f"{base_url}/images/edits"
                t0 = time.perf_counter()
                log_image_http_request(
                    provider="openai",
                    method="POST",
                    url=url,
                    headers=auth_headers,
                    body_log=json_dumps_for_log({**data, "images": file_log}),
                )
                r = await client.post(url, headers=auth_headers, data=data, files=files)
            else:
                body = {
                    "prompt": resolved_input.prompt,
                    "n": resolved_input.n,
                }
                # gpt-image 系列不支持 response_format 参数（固定返回 b64_json），
                # 仅 dall-e 系列需要显式指定；否则 OpenAI 会报 Unknown parameter。
                _model = resolved_input.model or ""
                if resolved_input.response_format and not _model.startswith(("gpt-image", "chatgpt-image")):
                    body["response_format"] = resolved_input.response_format
                if resolved_input.model:
                    body["model"] = resolved_input.model
                if resolved_input.size:
                    body["size"] = resolved_input.size
                if resolved_input.watermark is not None:
                    body["watermark"] = bool(resolved_input.watermark)

                url = f"{base_url}/images/generations"
                t0 = time.perf_counter()
                log_image_http_request(
                    provider="openai",
                    method="POST",
                    url=url,
                    headers={**auth_headers, "Content-Type": "application/json"},
                    body_log=json_dumps_for_log(safe_body_for_log_openai(body)),
                )
                r = await client.post(url, headers=auth_headers, json=body)

            dt_ms = int((time.perf_counter() - t0) * 1000)
            resp_text = ""
            try:
                resp_text = r.text or ""
            except Exception:  # noqa: BLE001
                resp_text = ""
            log_image_http_response(
                provider="openai",
                status_code=r.status_code,
                elapsed_ms=dt_ms,
                resp_headers=dict(r.headers),
                resp_text=resp_text,
            )

            r.raise_for_status()
            data = r.json()

        return _parse_openai_images_payload(data)


async def _resolve_reference_file(*, client: Any, ref: Any, index: int) -> tuple[str, bytes, str]:
    image_url = str(ref.image_url or "").strip()
    if not image_url:
        raise ValueError(
            "OpenAI Image API edits requires image bytes; resolve file_id to an image_url or data URL first"
        )
    if image_url.startswith("data:"):
        return _decode_data_image(image_url=image_url, index=index)
    if not image_url.startswith(("http://", "https://")):
        raise ValueError(f"Unsupported OpenAI reference image URL at index {index}")

    response = await client.get(image_url, follow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/"):
        guessed, _ = mimetypes.guess_type(urlparse(image_url).path)
        content_type = (guessed or "").lower()
    if not content_type.startswith("image/"):
        raise ValueError(f"OpenAI reference URL did not return an image at index {index}")
    content = response.content
    if not content:
        raise ValueError(f"OpenAI reference image is empty at index {index}")
    return _reference_filename(content_type=content_type, index=index), content, content_type


def _decode_data_image(*, image_url: str, index: int) -> tuple[str, bytes, str]:
    header, separator, payload = image_url.partition(",")
    content_type = header[5:].split(";", 1)[0].strip().lower() if separator else ""
    if not separator or ";base64" not in header.lower() or not content_type.startswith("image/"):
        raise ValueError(f"Invalid base64 image data URL at index {index}")
    try:
        content = base64.b64decode(unquote_to_bytes(payload), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"Invalid base64 image data URL at index {index}") from exc
    if not content:
        raise ValueError(f"OpenAI reference image is empty at index {index}")
    return _reference_filename(content_type=content_type, index=index), content, content_type


def _reference_filename(*, content_type: str, index: int) -> str:
    extension = mimetypes.guess_extension(content_type) or ".png"
    if extension == ".jpe":
        extension = ".jpg"
    return f"reference-{index}{extension}"


def _parse_openai_images_payload(data: dict[str, Any]) -> ImageGenerationResult:
    raw_items = data.get("data") or []
    images: list[ImageItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        b64 = item.get("b64_json")
        if not url and not b64:
            continue
        images.append(ImageItem(url=url, b64_json=b64))

    if not images:
        raise RuntimeError(f"OpenAI images response has no usable data: {data!r}")

    return ImageGenerationResult(
        images=images,
        provider="openai",
        provider_task_id=None,
        status=str(data.get("status") or "succeeded"),
    )
