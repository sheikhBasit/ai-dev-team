"""Tests for new State fields added in the frontend/auditor/intervention upgrade."""

from ai_team.state import State


def test_frontend_target_field_exists():
    assert "frontend_target" in State.__annotations__, (
        "State is missing 'frontend_target' field"
    )


def test_audit_findings_field_exists():
    assert "audit_findings" in State.__annotations__, (
        "State is missing 'audit_findings' field"
    )


def test_paused_field_exists():
    assert "paused" in State.__annotations__, (
        "State is missing 'paused' field"
    )


def test_inject_message_field_exists():
    assert "inject_message" in State.__annotations__, (
        "State is missing 'inject_message' field"
    )


def test_skip_current_field_exists():
    assert "skip_current" in State.__annotations__, (
        "State is missing 'skip_current' field"
    )


def test_abort_field_exists():
    assert "abort" in State.__annotations__, (
        "State is missing 'abort' field"
    )
