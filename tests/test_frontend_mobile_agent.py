"""Tests for frontend_mobile agent — Android Kotlin/Jetpack Compose specialist."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_react_loop_module(mock_response, changed_files):
    """Return a fake ai_team.agents.react_loop module with a mock react_loop."""
    mod = ModuleType("ai_team.agents.react_loop")
    mod.react_loop = MagicMock(return_value=(mock_response, changed_files))
    return mod


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------

class TestImport:
    def test_agent_is_importable(self):
        from ai_team.agents.frontend_mobile import frontend_mobile_agent  # noqa: F401

    def test_system_prompt_is_importable(self):
        from ai_team.agents.frontend_mobile import SYSTEM_PROMPT  # noqa: F401


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT content
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_system_prompt_mentions_kotlin(self):
        from ai_team.agents.frontend_mobile import SYSTEM_PROMPT

        assert "Kotlin" in SYSTEM_PROMPT

    def test_system_prompt_mentions_compose(self):
        from ai_team.agents.frontend_mobile import SYSTEM_PROMPT

        assert "Compose" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Return shape — use sys.modules injection to avoid langchain_core dependency
# ---------------------------------------------------------------------------

class TestFrontendMobileAgentReturn:
    def _make_mock_response(self):
        msg = MagicMock()
        msg.content = "// generated Kotlin code"
        return msg

    def _run_agent(self, state: dict, changed_files: list | None = None):
        """Run frontend_mobile_agent with all heavy deps mocked via sys.modules."""
        from ai_team.agents.frontend_mobile import frontend_mobile_agent

        if changed_files is None:
            changed_files = []

        mock_response = self._make_mock_response()
        react_loop_fn = MagicMock(return_value=(mock_response, changed_files))

        # Build fake react_loop module
        fake_rl_mod = ModuleType("ai_team.agents.react_loop")
        fake_rl_mod.react_loop = react_loop_fn  # type: ignore[attr-defined]

        # Build fake config module that exposes get_llm_for_agent
        fake_config = ModuleType("ai_team.config")
        mock_get_llm = MagicMock(return_value=MagicMock())
        fake_config.get_llm_for_agent = mock_get_llm  # type: ignore[attr-defined]

        with (
            patch.dict(sys.modules, {
                "ai_team.agents.react_loop": fake_rl_mod,
                "ai_team.config": fake_config,
            }),
            patch("ai_team.agents.frontend_mobile.bus") as mock_bus,
        ):
            mock_bus.consume.return_value = []
            result = frontend_mobile_agent(state)

        return result, react_loop_fn, mock_get_llm, mock_bus

    def test_returns_dict_with_required_keys(self):
        result, *_ = self._run_agent({"project_dir": "/tmp/project"})

        assert "code_changes" in result
        assert "total_tokens" in result
        assert "inject_message" in result

    def test_inject_message_cleared_to_empty_string(self):
        result, *_ = self._run_agent({
            "inject_message": "do something",
            "project_dir": "/tmp",
        })

        assert result["inject_message"] == ""

    def test_code_changes_is_list(self):
        changed = ["app/src/main/kotlin/Screen.kt"]
        result, *_ = self._run_agent({"project_dir": "/tmp/project"}, changed_files=changed)

        assert isinstance(result["code_changes"], list)

    def test_total_tokens_is_int(self):
        result, *_ = self._run_agent({})

        assert isinstance(result["total_tokens"], int)

    def test_bus_consume_called_with_frontend_mobile(self):
        _result, _rl, _llm, mock_bus = self._run_agent({})

        mock_bus.consume.assert_called_once_with("frontend_mobile")

    def test_bus_publish_called_after_react_loop(self):
        _result, _rl, _llm, mock_bus = self._run_agent({})

        mock_bus.publish.assert_called_once()
        call_args = mock_bus.publish.call_args
        assert call_args[0][0] == "frontend_mobile"
        assert "Mobile code complete." in call_args[0][1]

    def test_get_llm_for_agent_called_with_frontend_mobile(self):
        _result, _rl, mock_get_llm, _bus = self._run_agent({})

        mock_get_llm.assert_called_once_with("frontend_mobile")
