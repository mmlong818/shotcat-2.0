"""MiniMax H3 视频任务创建与查询。"""

from __future__ import annotations

from typing import Any

from app.core.contracts.provider import ProviderConfig
from app.core.contracts.video_generation import VideoGenerationInput
from app.core.integrations.minimax.video_payload import build_create_task_body


class MiniMaxVideoApiAdapter:
    """MiniMax H3：POST /v2/video_generation 与 GET /v2/query/video_generation/{id}。"""

    async def create_video(
        self,
        *,
        cfg: ProviderConfig,
        input_: VideoGenerationInput,
        timeout_s: float,
    ) -> str:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from exc

        base_url = (cfg.base_url or "https://api.minimax.io").rstrip("/")
        headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(
                f"{base_url}/v2/video_generation",
                headers=headers,
                json=build_create_task_body(input_),
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            task_id = str(data.get("task_id") or "")
            if not task_id:
                raise RuntimeError(f"MiniMax video generation missing task_id: {data!r}")
            return task_id

    async def get_video(
        self,
        *,
        cfg: ProviderConfig,
        task_id: str,
        timeout_s: float,
    ) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from exc

        base_url = (cfg.base_url or "https://api.minimax.io").rstrip("/")
        headers = {"Authorization": f"Bearer {cfg.api_key}"}
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(
                f"{base_url}/v2/query/video_generation/{task_id}",
                headers=headers,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            task = data.get("task")
            if not isinstance(task, dict):
                raise RuntimeError(f"MiniMax query missing task object: {data!r}")
            return task
