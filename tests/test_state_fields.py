"""Tests for State fields — existence, types, and LangGraph reducers."""

import operator
import typing

from ai_team.state import State, FrontendTarget

# Resolve all ForwardRef annotations (needed because state.py uses
# `from __future__ import annotations`, which defers evaluation).
_hints = typing.get_type_hints(State, include_extras=True)


# --- Existence tests (original) ---

def test_frontend_target_field_exists():
    assert "frontend_target" in _hints, "State is missing 'frontend_target' field"


def test_audit_findings_field_exists():
    assert "audit_findings" in _hints, "State is missing 'audit_findings' field"


def test_paused_field_exists():
    assert "paused" in _hints, "State is missing 'paused' field"


def test_inject_message_field_exists():
    assert "inject_message" in _hints, "State is missing 'inject_message' field"


def test_skip_current_field_exists():
    assert "skip_current" in _hints, "State is missing 'skip_current' field"


def test_abort_field_exists():
    assert "abort" in _hints, "State is missing 'abort' field"


# --- Deeper type and reducer tests ---

def test_audit_findings_reducer():
    annotation = _hints["audit_findings"]
    assert hasattr(annotation, "__metadata__"), "audit_findings must be Annotated"
    assert operator.add in annotation.__metadata__, (
        "audit_findings must use operator.add reducer"
    )


def test_frontend_target_literal_type():
    annotation = _hints["frontend_target"]
    assert annotation is FrontendTarget


def test_paused_is_bool():
    assert _hints["paused"] is bool


def test_inject_message_is_str():
    assert _hints["inject_message"] is str


def test_skip_current_is_bool():
    assert _hints["skip_current"] is bool


def test_abort_is_bool():
    assert _hints["abort"] is bool
