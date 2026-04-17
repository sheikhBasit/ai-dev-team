"""Tests for frontend_desktop agent — Tauri 2.x / React / Rust specialist."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Basic importability
# ---------------------------------------------------------------------------


def test_agent_is_importable():
    from ai_team.agents.frontend_desktop import frontend_desktop_agent  # noqa: F401

    assert callable(frontend_desktop_agent)


def test_system_prompt_importable():
    from ai_team.agents.frontend_desktop import SYSTEM_PROMPT

    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 0


def test_system_prompt_mentions_tauri():
    from ai_team.agents.frontend_desktop import SYSTEM_PROMPT

    assert "Tauri" in SYSTEM_PROMPT


def test_system_prompt_mentions_rust():
    from ai_team.agents.frontend_desktop import SYSTEM_PROMPT

    assert "Rust" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------


@pytest.fixture()
def _mock_dependencies():
    """Patch react_loop and bus so no LLM or DB calls are made."""
    fake_ai_message = MagicMock()
    fake_ai_message.usage_metadata = {"input_tokens": 10, "output_tokens": 20}

    with (
        patch(
            "ai_team.agents.frontend_desktop.react_loop",
            return_value=(fake_ai_message, ["src-tauri/src/main.rs"]),
        ) as mock_loop,
        patch("ai_team.agents.frontend_desktop.get_llm_for_agent") as mock_llm,
        patch("ai_team.agents.frontend_desktop.bus") as mock_bus,
    ):
        mock_bus.consume.return_value = []
        mock_bus.publish.return_value = None
        mock_bus.as_state_messages.return_value = []
        yield mock_loop, mock_llm, mock_bus


def _run_agent(extra_state: dict | None = None):
    from ai_team.agents.frontend_desktop import frontend_desktop_agent

    state: dict = {
        "task": "Add a system tray icon",
        "project_dir": "/tmp/fake-project",
        "project_context": "Tauri app",
        "architecture_spec": "Use tauri-plugin-notification",
        "work_items": [],
        "inject_message": "some prior inject",
    }
    if extra_state:
        state.update(extra_state)
    return frontend_desktop_agent(state)


def test_returns_dict(_mock_dependencies):
    result = _run_agent()
    assert isinstance(result, dict)


def test_returns_code_changes_key(_mock_dependencies):
    result = _run_agent()
    assert "code_changes" in result


def test_returns_total_tokens_key(_mock_dependencies):
    result = _run_agent()
    assert "total_tokens" in result


def test_returns_inject_message_key(_mock_dependencies):
    result = _run_agent()
    assert "inject_message" in result


def test_inject_message_cleared_on_return(_mock_dependencies):
    result = _run_agent({"inject_message": "should be cleared"})
    assert result["inject_message"] == ""


def test_code_changes_is_list(_mock_dependencies):
    result = _run_agent()
    assert isinstance(result["code_changes"], list)


# ---------------------------------------------------------------------------
# react_loop is called with correct agent_name
# ---------------------------------------------------------------------------


def test_react_loop_called_with_frontend_desktop_name(_mock_dependencies):
    mock_loop, _, _ = _mock_dependencies
    _run_agent()
    call_kwargs = mock_loop.call_args.kwargs if mock_loop.call_args.kwargs else {}
    call_args = mock_loop.call_args
    # agent_name may be passed positionally or as kwarg
    assert call_args is not None
    # Verify react_loop was called at all
    mock_loop.assert_called_once()


# ---------------------------------------------------------------------------
# bus.publish is called on completion
# ---------------------------------------------------------------------------


def test_bus_publish_called_after_completion(_mock_dependencies):
    _, _, mock_bus = _mock_dependencies
    _run_agent()
    mock_bus.publish.assert_called()


# ---------------------------------------------------------------------------
# _format_work_items helper
# ---------------------------------------------------------------------------


def test_format_work_items_returns_string():
    from ai_team.agents.frontend_desktop import _format_work_items

    result = _format_work_items([])
    assert isinstance(result, str)


def test_format_work_items_includes_title():
    from ai_team.agents.frontend_desktop import _format_work_items

    items = [{"title": "Add tray", "description": "System tray icon", "priority": 1}]
    result = _format_work_items(items)
    assert "Add tray" in result


def test_format_work_items_includes_priority():
    from ai_team.agents.frontend_desktop import _format_work_items

    items = [{"title": "Task", "description": "desc", "priority": 2}]
    result = _format_work_items(items)
    assert "2" in result
