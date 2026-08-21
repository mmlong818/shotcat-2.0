from __future__ import annotations

import subprocess
import pytest

import glm


def test_client_config_uses_codex_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SHOTCAT_CODEX_MODEL", raising=False)
    monkeypatch.setattr(glm, "_read_key_file", lambda _name: "")
    monkeypatch.setattr(glm.shutil, "which", lambda name: "C:/bin/codex.exe" if name == "codex" else None)

    assert glm._client_config("glm-4.6") == ("codex", "", "", "")


def test_client_config_can_explicitly_prefer_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOTCAT_TEXT_PROVIDER", "codex")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    monkeypatch.setenv("SHOTCAT_CODEX_MODEL", "gpt-local")
    monkeypatch.setattr(glm.shutil, "which", lambda name: "C:/bin/codex.exe" if name == "codex" else None)

    assert glm._client_config("glm-4.6") == ("codex", "", "", "gpt-local")


def test_codex_adapter_reads_final_json_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(glm.shutil, "which", lambda _name: "C:/bin/codex.exe")
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        output = '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"shots\\":[{\\"index\\":1}]}"}}'
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(glm.subprocess, "run", fake_run)
    result = glm._chat_json_with_codex("系统规则", "用户正文", model="", timeout=30)

    assert result == {"shots": [{"index": 1}]}
    assert captured["command"][-1] == "-"
    assert "--ephemeral" in captured["command"]
    assert "--ignore-rules" in captured["command"]
    assert "--json" in captured["command"]
    assert captured["kwargs"]["input"].endswith("用户正文")
    assert "shell" not in captured["kwargs"]


def test_chat_json_records_codex_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(glm, "_client_config", lambda _model: ("codex", "", "", "gpt-test"))
    monkeypatch.setattr(glm, "_chat_json_with_codex", lambda *_args, **_kwargs: {"ok": True})

    assert glm.chat_json("系统", "正文") == {"ok": True}
    assert glm.LAST_REQUEST_DEBUG["provider"] == "codex"
    assert glm.LAST_REQUEST_DEBUG["model"] == "gpt-test"
