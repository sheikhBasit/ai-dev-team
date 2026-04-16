"""In-process agent-to-agent pub/sub chat bus.

Usage:
    from ai_team.bus import bus

    # Publish a message
    bus.publish("reviewer", "Hey coder, line 42 has a SQL injection risk")

    # Subscribe to messages for a role (returns all unread messages)
    msgs = bus.consume("coder")  # returns list[AgentMessage]

    # Get all messages (for dashboard / evaluator)
    all_msgs = bus.all_messages()
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("ai_team.bus")


class AgentBus:
    """Thread-safe in-process pub/sub message bus for agent-to-agent communication."""

    def __init__(self) -> None:
        self._messages: list[dict] = []         # all messages ever published
        self._cursors: dict[str, int] = defaultdict(int)  # per-role read cursor
        self._lock = Lock()

    def publish(self, from_role: str, content: str, to_role: str = "all") -> None:
        """Publish a message from one agent role to another (or broadcast)."""
        msg: dict = {
            "role": from_role,
            "to": to_role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._messages.append(msg)
        logger.debug("[bus] %s → %s: %s", from_role, to_role, content[:80])

    def consume(self, role: str) -> list[dict]:
        """Return all unread messages addressed to `role` or broadcast ('all').
        Advances the read cursor so the same messages aren't returned twice."""
        with self._lock:
            cursor = self._cursors[role]
            pending = [
                m for m in self._messages[cursor:]
                if m["to"] in (role, "all") and m["role"] != role
            ]
            self._cursors[role] = len(self._messages)
        return pending

    def all_messages(self) -> list[dict]:
        """Return all messages ever published (for dashboard / evaluator)."""
        with self._lock:
            return list(self._messages)

    def as_state_messages(self) -> list[dict]:
        """Return messages formatted as AgentMessage TypedDicts for state storage."""
        with self._lock:
            return [
                {"role": m["role"], "content": m["content"], "timestamp": m["timestamp"]}
                for m in self._messages
            ]

    def reset(self) -> None:
        """Clear all messages and cursors (called at pipeline start)."""
        with self._lock:
            self._messages.clear()
            self._cursors.clear()


# Module-level singleton
bus = AgentBus()
