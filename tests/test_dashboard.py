"""Tests for the split-view dashboard — ControlState, push_output, REST endpoints."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# ControlState unit tests (pure Python — no server needed)
# ---------------------------------------------------------------------------

class TestControlState:
    def test_default_paused_false(self):
        from ai_team.web.app import ControlState
        cs = ControlState()
        assert cs.paused is False

    def test_default_inject_message_empty(self):
        from ai_team.web.app import ControlState
        cs = ControlState()
        assert cs.inject_message == ""

    def test_default_skip_current_false(self):
        from ai_team.web.app import ControlState
        cs = ControlState()
        assert cs.skip_current is False

    def test_default_abort_false(self):
        from ai_team.web.app import ControlState
        cs = ControlState()
        assert cs.abort is False

    def test_to_dict_returns_all_four_keys(self):
        from ai_team.web.app import ControlState
        cs = ControlState()
        d = cs.to_dict()
        assert set(d.keys()) == {"paused", "inject_message", "skip_current", "abort"}

    def test_to_dict_reflects_current_values(self):
        from ai_team.web.app import ControlState
        cs = ControlState(paused=True, inject_message="hello", skip_current=True, abort=False)
        d = cs.to_dict()
        assert d["paused"] is True
        assert d["inject_message"] == "hello"
        assert d["skip_current"] is True
        assert d["abort"] is False

    def test_clear_transient_clears_inject_message(self):
        from ai_team.web.app import ControlState
        cs = ControlState(inject_message="some message")
        cs.clear_transient()
        assert cs.inject_message == ""

    def test_clear_transient_clears_skip_current(self):
        from ai_team.web.app import ControlState
        cs = ControlState(skip_current=True)
        cs.clear_transient()
        assert cs.skip_current is False

    def test_clear_transient_does_not_touch_paused(self):
        from ai_team.web.app import ControlState
        cs = ControlState(paused=True, inject_message="x", skip_current=True)
        cs.clear_transient()
        assert cs.paused is True

    def test_clear_transient_does_not_touch_abort(self):
        from ai_team.web.app import ControlState
        cs = ControlState(abort=True, inject_message="x", skip_current=True)
        cs.clear_transient()
        assert cs.abort is True

    def test_live_output_default_empty_list(self):
        from ai_team.web.app import ControlState
        cs = ControlState()
        assert cs.live_output == []

    def test_live_output_independent_instances(self):
        """Each ControlState instance must have its own live_output list."""
        from ai_team.web.app import ControlState
        cs1 = ControlState()
        cs2 = ControlState()
        cs1.live_output.append("x")
        assert cs2.live_output == []


# ---------------------------------------------------------------------------
# push_output tests
# ---------------------------------------------------------------------------

class TestPushOutput:
    def setup_method(self):
        """Reset the module-level control state before each test."""
        from ai_team.web import app as app_module
        app_module.control.live_output.clear()

    def test_push_output_appends_to_live_output(self):
        from ai_team.web.app import push_output, control
        push_output("line one")
        assert "line one" in control.live_output

    def test_push_output_appends_multiple(self):
        from ai_team.web.app import push_output, control
        push_output("a")
        push_output("b")
        push_output("c")
        assert control.live_output == ["a", "b", "c"]

    def test_push_output_caps_at_2000(self):
        from ai_team.web.app import push_output, control
        for i in range(2100):
            push_output(f"line {i}")
        assert len(control.live_output) == 2000

    def test_push_output_keeps_most_recent_on_cap(self):
        from ai_team.web.app import push_output, control
        for i in range(2100):
            push_output(f"line {i}")
        # The most recent entries should be present
        assert control.live_output[-1] == "line 2099"
        # Old entries should have been dropped
        assert "line 0" not in control.live_output


# ---------------------------------------------------------------------------
# REST endpoint tests (TestClient)
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Create a fresh FastAPI TestClient for each test."""
    from fastapi.testclient import TestClient
    from ai_team.web import app as app_module

    def _reset():
        app_module.control.paused = False
        app_module.control.inject_message = ""
        app_module.control.skip_current = False
        app_module.control.abort = False
        app_module.control.live_output.clear()

    _reset()
    test_app = app_module.create_app()
    yield TestClient(test_app)
    _reset()


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_has_message_count(self, client):
        resp = client.get("/health")
        assert "message_count" in resp.json()

    def test_health_has_paused_field(self, client):
        resp = client.get("/health")
        assert "paused" in resp.json()


class TestControlEndpoints:
    def test_pause_sets_paused_true(self, client):
        resp = client.post("/control/pause")
        assert resp.status_code == 200
        assert resp.json() == {"status": "paused"}

    def test_resume_sets_paused_false(self, client):
        client.post("/control/pause")
        resp = client.post("/control/resume")
        assert resp.status_code == 200
        assert resp.json() == {"status": "resumed"}

    def test_inject_sets_message(self, client):
        resp = client.post("/control/inject", json={"message": "do this now"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "injected"
        assert data["message"] == "do this now"

    def test_inject_missing_message_returns_422(self, client):
        resp = client.post("/control/inject", json={})
        assert resp.status_code == 422

    def test_skip_returns_skipped(self, client):
        resp = client.post("/control/skip")
        assert resp.status_code == 200
        assert resp.json() == {"status": "skipped"}

    def test_abort_returns_aborted(self, client):
        resp = client.post("/control/abort")
        assert resp.status_code == 200
        assert resp.json() == {"status": "aborted"}


class TestControlStateEndpoint:
    def test_state_returns_dict(self, client):
        resp = client.get("/control/state")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"paused", "inject_message", "skip_current", "abort"}

    def test_state_reflects_paused(self, client):
        client.post("/control/pause")
        resp = client.get("/control/state")
        assert resp.json()["paused"] is True

    def test_state_reflects_abort(self, client):
        client.post("/control/abort")
        resp = client.get("/control/state")
        assert resp.json()["abort"] is True


class TestMessagesEndpoint:
    def test_messages_returns_list(self, client):
        resp = client.get("/messages")
        assert resp.status_code == 200
        assert "messages" in resp.json()
        assert isinstance(resp.json()["messages"], list)


class TestDashboardHTML:
    def test_root_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_html_contains_team_conversation(self, client):
        resp = client.get("/")
        assert b"Team Conversation" in resp.content

    def test_html_contains_live_output(self, client):
        resp = client.get("/")
        assert b"Live Output" in resp.content

    def test_html_no_innerHTML_on_untrusted(self, client):
        """Confirm innerHTML is not used for message/output content insertion."""
        resp = client.get("/")
        content = resp.text
        # The HTML must use textContent for data — innerHTML must not appear
        # in data-insertion paths. We check that if innerHTML is present,
        # it is only used for static structural elements, not dynamic data.
        # A simple heuristic: innerHTML must not follow a data variable directly.
        # We ban innerHTML = msg and innerHTML = line patterns.
        import re
        # These patterns indicate unsafe innerHTML usage with dynamic data
        bad_patterns = [
            r"innerHTML\s*=\s*msg",
            r"innerHTML\s*=\s*line",
            r"innerHTML\s*\+=",
            r"innerHTML\s*=\s*data",
        ]
        for pattern in bad_patterns:
            assert not re.search(pattern, content), (
                f"Unsafe innerHTML pattern found: {pattern}"
            )
