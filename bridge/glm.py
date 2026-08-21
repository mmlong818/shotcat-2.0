"""OpenAI-compatible chat client used by bridge scripts.

GLM is used when GLM_API_KEY or .glm_key exists. If not, the bridge falls
back to OpenAI through OPENAI_API_KEY or .openai_key.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


GLM_BASE = "https://open.bigmodel.cn/api/paas/v4"
OPENAI_BASE = "https://api.openai.com/v1"
OPENAI_FALLBACK_MODEL = "gpt-5.5"
LAST_REQUEST_DEBUG: dict[str, object] = {}


def _read_key_file(name: str) -> str:
    path = Path(__file__).with_name(name)
    if path.exists():
        return path.read_text(encoding="utf-8-sig").strip().lstrip("\ufeff")
    return ""


def _client_config(model: str) -> tuple[str, str, str, str]:
    preferred_provider = (os.environ.get("SHOTCAT_TEXT_PROVIDER") or "").strip().lower()
    if preferred_provider == "codex":
        if shutil.which("codex"):
            return "codex", "", "", (os.environ.get("SHOTCAT_CODEX_MODEL") or "").strip()
        raise SystemExit("SHOTCAT_TEXT_PROVIDER=codex，但未找到 Codex CLI")

    key = (os.environ.get("GLM_API_KEY") or "").strip().lstrip("\ufeff") or _read_key_file(".glm_key")
    if key:
        return "glm", GLM_BASE, key, model

    key = (os.environ.get("OPENAI_API_KEY") or "").strip().lstrip("\ufeff") or _read_key_file(".openai_key")
    if key:
        resolved_model = OPENAI_FALLBACK_MODEL if model.startswith("glm-") else model
        return "openai", OPENAI_BASE, key, resolved_model

    codex_executable = shutil.which("codex")
    if codex_executable:
        return "codex", "", "", (os.environ.get("SHOTCAT_CODEX_MODEL") or "").strip()

    raise SystemExit(
        "缺少可用文字模型：请登录 Codex，或设置 GLM_API_KEY/OPENAI_API_KEY，"
        "或写 bridge/.glm_key / bridge/.openai_key"
    )


def _extract_json(text: str):
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _extract_codex_final_message(output: str) -> str:
    for line in reversed(output.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") if isinstance(event, dict) else None
        if isinstance(item, dict) and item.get("type") == "agent_message" and item.get("text"):
            return str(item["text"])
        if isinstance(event, dict) and event.get("type") == "message" and event.get("text"):
            return str(event["text"])
    raise SystemExit("Codex 文字生成失败：未返回最终结果")


def _chat_json_with_codex(system: str, user: str, *, model: str, timeout: int):
    executable = shutil.which("codex")
    if not executable:
        raise SystemExit("未找到 Codex CLI，请先安装并登录 Codex")

    prompt = (
        system
        + "\n\n只输出合法 JSON 对象，不要解释、不要 markdown、不要调用任何工具。\n\n"
        + user
    )
    command = [
        executable,
        "exec",
        "--ephemeral",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--json",
    ]
    if model:
        command.extend(["--model", model])
    command.append("-")
    try:
        result = subprocess.run(
            command,
            input=prompt,
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"Codex 文字生成超时（{timeout}s）") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "未知错误").strip()[-1000:]
        raise SystemExit(f"Codex 文字生成失败：{detail}")
    return _extract_json(_extract_codex_final_message(result.stdout))


def chat_json(
    system: str,
    user: str,
    *,
    model: str = "glm-4.6",
    temperature: float = 0.7,
    timeout: int = 240,
    retries: int = 2,
):
    provider, base_url, api_key, resolved_model = _client_config(model)
    if provider == "codex":
        LAST_REQUEST_DEBUG.clear()
        LAST_REQUEST_DEBUG.update(
            {
                "provider": provider,
                "model": resolved_model or "current-codex-default",
                "has_temperature": False,
                "source": str(Path(__file__).resolve()),
            }
        )
        return _chat_json_with_codex(system, user, model=resolved_model, timeout=timeout)

    body = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system + "\n\n只输出合法 JSON，不要解释或 markdown。"},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    if provider != "openai":
        body["temperature"] = temperature
    LAST_REQUEST_DEBUG.clear()
    LAST_REQUEST_DEBUG.update(
        {
            "provider": provider,
            "model": resolved_model,
            "has_temperature": "temperature" in body,
            "source": str(Path(__file__).resolve()),
        }
    )

    last: BaseException | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read())
            return _extract_json(payload["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = ""
            if exc.code == 429:
                last = SystemExit(f"{provider} 速率限制(429)：{detail}")
                if attempt < retries:
                    wait = 30 * (attempt + 1)
                    print(f"  {provider} 429，等待 {wait}s 后重试 {attempt + 1}/{retries}", flush=True)
                    time.sleep(wait)
                    continue
                raise last
            raise SystemExit(f"{provider} HTTP {exc.code}: {detail}") from exc
        except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
            last = exc
            if attempt < retries:
                print(f"  {provider} 请求失败({type(exc).__name__})，重试 {attempt + 1}/{retries}", flush=True)
                continue
    if last:
        raise last
    raise RuntimeError("chat_json failed without an exception")
