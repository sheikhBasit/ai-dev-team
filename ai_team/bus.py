"""In-process agent-to-agent pub/sub chat bus with SQLite persistence.

Usage:
    from ai_team.bus import bus

    # Publish a message
    bus.publish("reviewer", "Hey coder, line 42 has a SQL injection risk")

    # Subscribe to messages for a role (returns all unread messages)
    msgs = bus.consume("coder")  # returns list[AgentMessage]

    # Get all messages (for dashboard / evaluator)
    all_msgs = bus.all_messages()

    # Thread tracking
    bus.set_thread("my-thread-id")   # tag future publishes
    bus.load_thread("my-thread-id")  # restore history from SQLite
"""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

logger = logging.getLogger("ai_team.bus")

_DEFAULT_DB_PATH = str(Path.home() / ".ai-dev-team" / "bus.db")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT    NOT NULL DEFAULT '',
    role      TEXT    NOT NULL,
    to_role   TEXT    NOT NULL,
    content   TEXT    NOT NULL,
    timestamp TEXT    NOT NULL
)
"""

_INSERT_SQL = """
INSERT INTO messages (thread_id, role, to_role, content, timestamp)
VALUES (?, ?, ?, ?, ?)
"""

_SELECT_THREAD_SQL = """
SELECT role, to_role, content, timestamp
FROM messages
WHERE thread_id = ?
ORDER BY id
"""


class AgentBus:
    """Thread-safe agent-to-agent pub/sub bus with SQLite persistence."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self._messages: list[dict] = []
        self._cursors: dict[str, int] = defaultdict(int)
        self._lock = Lock()
        self._thread_id: str = ""

        # Ensure the directory exists before opening the DB
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # check_same_thread=False: we guard all access with self._lock
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_thread(self, thread_id: str) -> None:
        """Set the current thread_id used for all future publish() calls."""
        with self._lock:
            self._thread_id = thread_id

    def load_thread(self, thread_id: str) -> None:
        """Load all messages for thread_id from SQLite into the in-memory list.

        Does NOT reset existing in-memory messages — call reset() first if you
        want a clean slate.
        """
        with self._lock:
            rows = self._conn.execute(_SELECT_THREAD_SQL, (thread_id,)).fetchall()
            for role, to_role, content, timestamp in rows:
                self._messages.append(
                    {
                        "role": role,
                        "to": to_role,
                        "content": content,
                        "timestamp": timestamp,
                    }
                )
            self._thread_id = thread_id

    def publish(self, from_role: str, content: str, to_role: str = "all") -> None:
        """Publish a message from one agent role to another (or broadcast)."""
        timestamp = datetime.now(timezone.utc).isoformat()
        msg: dict = {
            "role": from_role,
            "to": to_role,
            "content": content,
            "timestamp": timestamp,
        }
        with self._lock:
            self._messages.append(msg)
            self._persist(from_role, to_role, content, timestamp)
        logger.debug("[bus] %s → %s: %s", from_role, to_role, content[:80])

    def consume(self, role: str) -> list[dict]:
        """Return all unread messages addressed to `role` or broadcast ('all').

        Advances the read cursor so the same messages aren't returned twice.
        """
        with self._lock:
            cursor = self._cursors[role]
            pending = [
                m
                for m in self._messages[cursor:]
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
                {
                    "role": m["role"],
                    "content": m["content"],
                    "timestamp": m["timestamp"],
                }
                for m in self._messages
            ]

    def reset(self) -> None:
        """Clear in-memory messages and cursors (called at pipeline start).

        SQLite data is intentionally preserved so load_thread() can restore
        history in future sessions.
        """
        with self._lock:
            self._messages.clear()
            self._cursors.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _persist(
        self, role: str, to_role: str, content: str, timestamp: str
    ) -> None:
        """Insert a single message row into SQLite.

        Must be called while self._lock is held (it is called from publish()).
        """
        self._conn.execute(
            _INSERT_SQL,
            (self._thread_id, role, to_role, content, timestamp),
        )
        self._conn.commit()


# Module-level singleton — uses the default DB path
bus = AgentBus()
