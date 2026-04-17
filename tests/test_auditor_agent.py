"""Tests for the Auditor Agent — code quality, architecture drift, tech debt."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

class TestAuditorImport:
    def test_auditor_agent_is_importable(self):
        from ai_team.agents.auditor import auditor_agent  # noqa: F401
        assert callable(auditor_agent)

    def test_system_prompt_is_importable(self):
        from ai_team.agents.auditor import SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 0


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT content requirements
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_system_prompt_mentions_architecture(self):
        from ai_team.agents.auditor import SYSTEM_PROMPT
        assert "Architecture" in SYSTEM_PROMPT

    def test_system_prompt_mentions_techdebt(self):
        from ai_team.agents.auditor import SYSTEM_PROMPT
        assert "TechDebt" in SYSTEM_PROMPT

    def test_system_prompt_mentions_quality(self):
        from ai_team.agents.auditor import SYSTEM_PROMPT
        assert "Quality" in SYSTEM_PROMPT

    def test_system_prompt_mentions_test_coverage(self):
        from ai_team.agents.auditor import SYSTEM_PROMPT
        assert "TestCoverage" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# auditor_agent() — return contract
# ---------------------------------------------------------------------------

class TestAuditorAgentReturn:
    def _make_mock_response(self, content: str = "") -> MagicMock:
        msg = MagicMock()
        msg.content = content
        return msg

    def test_returns_dict_with_audit_findings_key(self):
        from ai_team.agents.auditor import auditor_agent

        mock_response = self._make_mock_response('{"severity": "pass", "file": "", "line": 0, "message": "ok"}')
        mock_findings = [{"severity": "pass", "file": "", "line": 0, "message": "ok", "agent": ""}]

        with (
            patch("ai_team.agents.auditor.get_llm_for_agent") as mock_llm,
            patch("ai_team.agents.auditor.react_loop", return_value=(mock_response, [])),
            patch("ai_team.agents.auditor.parse_findings", return_value=mock_findings),
            patch("ai_team.agents.auditor.bus") as mock_bus,
        ):
            mock_llm.return_value = MagicMock()
            mock_bus.publish = MagicMock()
            result = auditor_agent({"code_changes": [], "project_dir": "/tmp/project"})

        assert "audit_findings" in result

    def test_returns_dict_with_total_tokens_key(self):
        from ai_team.agents.auditor import auditor_agent

        mock_response = self._make_mock_response("")
        mock_findings = [{"severity": "info", "file": "foo.py", "line": 1, "message": "ok", "agent": ""}]

        with (
            patch("ai_team.agents.auditor.get_llm_for_agent") as mock_llm,
            patch("ai_team.agents.auditor.react_loop", return_value=(mock_response, [])),
            patch("ai_team.agents.auditor.parse_findings", return_value=mock_findings),
            patch("ai_team.agents.auditor.bus") as mock_bus,
        ):
            mock_llm.return_value = MagicMock()
            mock_bus.publish = MagicMock()
            result = auditor_agent({"code_changes": [], "project_dir": "/tmp/project"})

        assert "total_tokens" in result

    def test_audit_findings_is_a_list(self):
        from ai_team.agents.auditor import auditor_agent

        mock_response = self._make_mock_response("")
        mock_findings = [
            {"severity": "warn", "file": "a.py", "line": 10, "message": "Quality: long func", "agent": ""},
        ]

        with (
            patch("ai_team.agents.auditor.get_llm_for_agent") as mock_llm,
            patch("ai_team.agents.auditor.react_loop", return_value=(mock_response, [])),
            patch("ai_team.agents.auditor.parse_findings", return_value=mock_findings),
            patch("ai_team.agents.auditor.bus") as mock_bus,
        ):
            mock_llm.return_value = MagicMock()
            mock_bus.publish = MagicMock()
            result = auditor_agent({"code_changes": ["a.py"], "project_dir": "/tmp"})

        assert isinstance(result["audit_findings"], list)

    def test_bus_publish_called_once(self):
        from ai_team.agents.auditor import auditor_agent

        mock_response = self._make_mock_response("")
        mock_findings = [{"severity": "info", "file": "", "line": 0, "message": "ok", "agent": ""}]

        with (
            patch("ai_team.agents.auditor.get_llm_for_agent") as mock_llm,
            patch("ai_team.agents.auditor.react_loop", return_value=(mock_response, [])),
            patch("ai_team.agents.auditor.parse_findings", return_value=mock_findings),
            patch("ai_team.agents.auditor.bus") as mock_bus,
        ):
            mock_llm.return_value = MagicMock()
            mock_bus.publish = MagicMock()
            auditor_agent({"code_changes": [], "project_dir": "/tmp"})

        mock_bus.publish.assert_called_once()

    def test_react_loop_called_with_max_iterations_10(self):
        from ai_team.agents.auditor import auditor_agent

        mock_response = self._make_mock_response("")
        mock_findings: list[dict] = []

        with (
            patch("ai_team.agents.auditor.get_llm_for_agent") as mock_llm,
            patch("ai_team.agents.auditor.react_loop", return_value=(mock_response, [])) as mock_rl,
            patch("ai_team.agents.auditor.parse_findings", return_value=mock_findings),
            patch("ai_team.agents.auditor.bus") as mock_bus,
        ):
            mock_llm.return_value = MagicMock()
            mock_bus.publish = MagicMock()
            auditor_agent({"code_changes": [], "project_dir": "/tmp"})

        call_kwargs = mock_rl.call_args
        assert call_kwargs.kwargs.get("max_iterations") == 10
