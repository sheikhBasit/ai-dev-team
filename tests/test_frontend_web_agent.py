"""Tests for frontend_web_agent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

def test_frontend_web_agent_is_importable():
    from ai_team.agents.frontend_web import frontend_web_agent  # noqa: F401


def test_system_prompt_mentions_typescript():
    from ai_team.agents.frontend_web import SYSTEM_PROMPT

    assert "TypeScript" in SYSTEM_PROMPT


def test_system_prompt_mentions_nextjs():
    from ai_team.agents.frontend_web import SYSTEM_PROMPT

    assert "Next.js" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Functional tests — mock react_loop and bus so no real LLM calls happen
# ---------------------------------------------------------------------------

@pytest.fixture()
def minimal_state() -> dict:
    return {
        "task": "Add a login page",
        "project_dir": "/tmp/test-project",
        "project_context": "Next.js 14 app",
        "architecture_spec": "Use App Router with server components",
        "work_items": [],
        "inject_message": "Sultan says: prioritise mobile layout",
        "total_tokens": 0,
    }


def _make_fake_ai_message(content: str = "Done.") -> MagicMock:
    msg = MagicMock()
    msg.content = content
    return msg


def _patch_lazy_imports(fake_react_loop_fn, mock_bus_obj):
    """Context manager stack to patch lazy imports inside frontend_web_agent."""
    import sys

    # Pre-populate sys.modules so the lazy imports inside the function
    # resolve to our mocks instead of the real (unavailable) modules.
    fake_react_loop_module = MagicMock()
    fake_react_loop_module.react_loop = fake_react_loop_fn

    fake_bus_module = MagicMock()
    fake_bus_module.bus = mock_bus_obj

    return patch.dict(
        sys.modules,
        {
            "ai_team.agents.react_loop": fake_react_loop_module,
            "ai_team.bus": fake_bus_module,
        },
    )


def test_frontend_web_agent_returns_expected_keys(minimal_state):
    fake_response = _make_fake_ai_message("Frontend code written.")
    fake_changed = ["src/app/login/page.tsx"]
    mock_bus = MagicMock()
    mock_bus.consume.return_value = []

    def fake_react_loop(llm, system_prompt, user_message, **kwargs):
        return fake_response, fake_changed

    with (
        _patch_lazy_imports(fake_react_loop, mock_bus),
        patch("ai_team.agents.frontend_web.get_llm_for_agent", return_value=MagicMock()),
    ):
        from ai_team.agents.frontend_web import frontend_web_agent

        result = frontend_web_agent(minimal_state)

    assert "code_changes" in result
    assert "total_tokens" in result
    assert "inject_message" in result


def test_frontend_web_agent_clears_inject_message(minimal_state):
    fake_response = _make_fake_ai_message()
    mock_bus = MagicMock()
    mock_bus.consume.return_value = []

    def fake_react_loop(llm, system_prompt, user_message, **kwargs):
        return fake_response, []

    with (
        _patch_lazy_imports(fake_react_loop, mock_bus),
        patch("ai_team.agents.frontend_web.get_llm_for_agent", return_value=MagicMock()),
    ):
        from ai_team.agents.frontend_web import frontend_web_agent

        result = frontend_web_agent(minimal_state)

    assert result["inject_message"] == ""


def test_frontend_web_agent_returns_code_changes_list(minimal_state):
    fake_response = _make_fake_ai_message()
    fake_changed = ["src/components/Button.tsx", "src/app/page.tsx"]
    mock_bus = MagicMock()
    mock_bus.consume.return_value = []

    def fake_react_loop(llm, system_prompt, user_message, **kwargs):
        return fake_response, fake_changed

    with (
        _patch_lazy_imports(fake_react_loop, mock_bus),
        patch("ai_team.agents.frontend_web.get_llm_for_agent", return_value=MagicMock()),
    ):
        from ai_team.agents.frontend_web import frontend_web_agent

        result = frontend_web_agent(minimal_state)

    assert isinstance(result["code_changes"], list)


def test_frontend_web_agent_publishes_completion(minimal_state):
    fake_response = _make_fake_ai_message()
    mock_bus = MagicMock()
    mock_bus.consume.return_value = []

    def fake_react_loop(llm, system_prompt, user_message, **kwargs):
        return fake_response, []

    with (
        _patch_lazy_imports(fake_react_loop, mock_bus),
        patch("ai_team.agents.frontend_web.get_llm_for_agent", return_value=MagicMock()),
    ):
        from ai_team.agents.frontend_web import frontend_web_agent

        frontend_web_agent(minimal_state)

    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args
    assert "frontend_web" in call_args[0]


def test_frontend_web_agent_inbox_messages_included_in_prompt(minimal_state):
    """Inbox messages must be forwarded to react_loop via user_msg."""
    fake_response = _make_fake_ai_message()
    inbox_msg = {"role": "architect", "content": "Use shadcn/ui for the form"}
    mock_bus = MagicMock()
    mock_bus.consume.return_value = [inbox_msg]

    captured_user_msg: list[str] = []

    def fake_react_loop(llm, system_prompt, user_message, **kwargs):
        captured_user_msg.append(user_message)
        return fake_response, []

    with (
        _patch_lazy_imports(fake_react_loop, mock_bus),
        patch("ai_team.agents.frontend_web.get_llm_for_agent", return_value=MagicMock()),
    ):
        from ai_team.agents.frontend_web import frontend_web_agent

        frontend_web_agent(minimal_state)

    assert captured_user_msg, "react_loop was not called"
    assert "Use shadcn/ui for the form" in captured_user_msg[0]


def test_frontend_web_agent_inject_message_included_in_prompt(minimal_state):
    """inject_message from state must appear in the user_msg sent to react_loop."""
    fake_response = _make_fake_ai_message()
    mock_bus = MagicMock()
    mock_bus.consume.return_value = []

    captured_user_msg: list[str] = []

    def fake_react_loop(llm, system_prompt, user_message, **kwargs):
        captured_user_msg.append(user_message)
        return fake_response, []

    with (
        _patch_lazy_imports(fake_react_loop, mock_bus),
        patch("ai_team.agents.frontend_web.get_llm_for_agent", return_value=MagicMock()),
    ):
        from ai_team.agents.frontend_web import frontend_web_agent

        frontend_web_agent(minimal_state)

    assert captured_user_msg
    assert "Sultan says: prioritise mobile layout" in captured_user_msg[0]
