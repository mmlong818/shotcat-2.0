"""Script processing agents parsing regression tests."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.chains.agents import ConsistencyCheckerAgent
from app.schemas.skills.script_processing import ScriptConsistencyCheckResult


class _MockChatModel(BaseChatModel):
    def __init__(self, response: str) -> None:
        super().__init__()
        self._response = response

    @property
    def _llm_type(self) -> str:  # pragma: no cover
        return "mock-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # type: ignore[override]
        msg = AIMessage(content=self._response)
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _checker() -> ConsistencyCheckerAgent:
    return ConsistencyCheckerAgent(_MockChatModel('{"issues": [], "has_issues": false, "summary": null}'))


def test_consistency_format_output_accepts_unquoted_keys() -> None:
    agent = _checker()
    raw = "{issues: [], has_issues: false, summary: null}"

    result = agent.format_output(raw)

    assert isinstance(result, ScriptConsistencyCheckResult)
    assert result.has_issues is False
    assert result.issues == []


def test_consistency_format_output_accepts_python_literal_style() -> None:
    agent = _checker()
    raw = "{'issues': [], 'has_issues': False, 'summary': None}"

    result = agent.format_output(raw)

    assert isinstance(result, ScriptConsistencyCheckResult)
    assert result.has_issues is False
    assert result.summary is None


def test_consistency_format_output_accepts_model_call_style() -> None:
    agent = _checker()
    raw = "ScriptConsistencyCheckResult(issues=[], has_issues=False, summary=None)"

    result = agent.format_output(raw)

    assert isinstance(result, ScriptConsistencyCheckResult)
    assert result.has_issues is False
    assert result.issues == []


