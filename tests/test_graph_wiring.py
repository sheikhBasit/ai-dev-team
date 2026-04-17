"""Tests for graph wiring: frontend routing and auditor integration."""

from __future__ import annotations



# ── frontend_router_node importability ──────────────────────────────────────

def test_frontend_router_node_importable():
    from ai_team.graph import frontend_router_node
    assert callable(frontend_router_node)


# ── route_to_coder conditional edge ─────────────────────────────────────────

def test_route_to_coder_web():
    from ai_team.graph import route_to_coder
    assert route_to_coder({"frontend_target": "web"}) == "frontend_web"


def test_route_to_coder_mobile():
    from ai_team.graph import route_to_coder
    assert route_to_coder({"frontend_target": "mobile"}) == "frontend_mobile"


def test_route_to_coder_desktop():
    from ai_team.graph import route_to_coder
    assert route_to_coder({"frontend_target": "desktop"}) == "frontend_desktop"


def test_route_to_coder_backend():
    from ai_team.graph import route_to_coder
    assert route_to_coder({"frontend_target": "backend"}) == "coder"


def test_route_to_coder_empty_string():
    from ai_team.graph import route_to_coder
    assert route_to_coder({"frontend_target": ""}) == "coder"


def test_route_to_coder_missing_key():
    from ai_team.graph import route_to_coder
    assert route_to_coder({}) == "coder"


# ── build_graph compiles without error ──────────────────────────────────────

def test_build_graph_compiles():
    """build_graph() must complete without raising."""
    from ai_team.graph import build_graph
    graph = build_graph()
    assert graph is not None
