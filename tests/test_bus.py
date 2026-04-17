"""Tests for AgentBus — SQLite persistence and thread tracking."""

import threading

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_bus(tmp_path):
    """Each test gets a fresh AgentBus pointed at a temp DB directory."""
    db_dir = tmp_path / ".ai-dev-team"
    db_dir.mkdir()
    db_path = str(db_dir / "bus.db")

    # Import the class (not the singleton) so we can create an isolated instance
    from ai_team.bus import AgentBus

    bus = AgentBus(db_path=db_path)
    yield bus
    # Cleanup: close DB connection
    bus._conn.close()


# ---------------------------------------------------------------------------
# publish() — memory + SQLite persistence
# ---------------------------------------------------------------------------

class TestPublish:
    def test_publish_stores_in_memory(self, isolated_bus):
        isolated_bus.publish("coder", "hello world", to_role="reviewer")
        msgs = isolated_bus.all_messages()
        assert len(msgs) == 1
        assert msgs[0]["content"] == "hello world"
        assert msgs[0]["role"] == "coder"
        assert msgs[0]["to"] == "reviewer"

    def test_publish_persists_to_sqlite(self, isolated_bus):
        isolated_bus.publish("coder", "persisted msg", to_role="reviewer")
        # Query DB directly
        cur = isolated_bus._conn.cursor()
        cur.execute("SELECT role, to_role, content FROM messages")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0] == ("coder", "reviewer", "persisted msg")

    def test_publish_default_to_role_is_all(self, isolated_bus):
        isolated_bus.publish("coder", "broadcast")
        msgs = isolated_bus.all_messages()
        assert msgs[0]["to"] == "all"

    def test_publish_timestamp_present(self, isolated_bus):
        isolated_bus.publish("coder", "ts test")
        msgs = isolated_bus.all_messages()
        assert "timestamp" in msgs[0]
        assert msgs[0]["timestamp"]  # non-empty

    def test_publish_multiple_messages(self, isolated_bus):
        isolated_bus.publish("coder", "msg1")
        isolated_bus.publish("reviewer", "msg2")
        isolated_bus.publish("tester", "msg3")
        assert len(isolated_bus.all_messages()) == 3
        cur = isolated_bus._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM messages")
        assert cur.fetchone()[0] == 3


# ---------------------------------------------------------------------------
# consume() — returns unread messages for a role, advances cursor
# ---------------------------------------------------------------------------

class TestConsume:
    def test_consume_returns_messages_addressed_to_role(self, isolated_bus):
        isolated_bus.publish("coder", "hey reviewer", to_role="reviewer")
        isolated_bus.publish("coder", "broadcast")
        msgs = isolated_bus.consume("reviewer")
        assert len(msgs) == 2  # direct + broadcast

    def test_consume_excludes_own_messages(self, isolated_bus):
        isolated_bus.publish("reviewer", "my own message", to_role="reviewer")
        msgs = isolated_bus.consume("reviewer")
        assert len(msgs) == 0

    def test_consume_advances_cursor(self, isolated_bus):
        isolated_bus.publish("coder", "first")
        isolated_bus.consume("reviewer")  # reads first
        isolated_bus.publish("coder", "second")
        msgs = isolated_bus.consume("reviewer")
        assert len(msgs) == 1
        assert msgs[0]["content"] == "second"

    def test_consume_empty_when_no_messages(self, isolated_bus):
        msgs = isolated_bus.consume("coder")
        assert msgs == []

    def test_consume_filters_by_role(self, isolated_bus):
        isolated_bus.publish("coder", "for reviewer", to_role="reviewer")
        isolated_bus.publish("coder", "for tester", to_role="tester")
        reviewer_msgs = isolated_bus.consume("reviewer")
        tester_msgs = isolated_bus.consume("tester")
        assert len(reviewer_msgs) == 1
        assert reviewer_msgs[0]["content"] == "for reviewer"
        assert len(tester_msgs) == 1
        assert tester_msgs[0]["content"] == "for tester"


# ---------------------------------------------------------------------------
# all_messages()
# ---------------------------------------------------------------------------

class TestAllMessages:
    def test_all_messages_returns_copy(self, isolated_bus):
        isolated_bus.publish("coder", "msg")
        result = isolated_bus.all_messages()
        result.clear()  # mutating the returned list should not affect internal state
        assert len(isolated_bus.all_messages()) == 1

    def test_all_messages_empty_on_fresh_bus(self, isolated_bus):
        assert isolated_bus.all_messages() == []

    def test_all_messages_preserves_order(self, isolated_bus):
        for i in range(5):
            isolated_bus.publish("coder", f"msg{i}")
        msgs = isolated_bus.all_messages()
        contents = [m["content"] for m in msgs]
        assert contents == ["msg0", "msg1", "msg2", "msg3", "msg4"]


# ---------------------------------------------------------------------------
# as_state_messages()
# ---------------------------------------------------------------------------

class TestAsStateMessages:
    def test_as_state_messages_format(self, isolated_bus):
        isolated_bus.publish("coder", "hello")
        state_msgs = isolated_bus.as_state_messages()
        assert len(state_msgs) == 1
        assert set(state_msgs[0].keys()) == {"role", "content", "timestamp"}

    def test_as_state_messages_empty(self, isolated_bus):
        assert isolated_bus.as_state_messages() == []


# ---------------------------------------------------------------------------
# set_thread() + load_thread() — round-trip
# ---------------------------------------------------------------------------

class TestThreading:
    def test_set_thread_and_publish_stores_thread_id(self, isolated_bus):
        isolated_bus.set_thread("thread-abc")
        isolated_bus.publish("coder", "threaded message")
        cur = isolated_bus._conn.cursor()
        cur.execute("SELECT thread_id FROM messages")
        row = cur.fetchone()
        assert row[0] == "thread-abc"

    def test_publish_without_set_thread_uses_empty_string(self, isolated_bus):
        isolated_bus.publish("coder", "no thread")
        cur = isolated_bus._conn.cursor()
        cur.execute("SELECT thread_id FROM messages")
        row = cur.fetchone()
        assert row[0] == ""

    def test_load_thread_populates_memory(self, isolated_bus):
        # Publish messages under thread-1
        isolated_bus.set_thread("thread-1")
        isolated_bus.publish("coder", "thread1 msg1")
        isolated_bus.publish("reviewer", "thread1 msg2")

        # Publish messages under thread-2
        isolated_bus.set_thread("thread-2")
        isolated_bus.publish("coder", "thread2 msg")

        # Reset in-memory state and load only thread-1
        isolated_bus.reset()
        assert isolated_bus.all_messages() == []

        isolated_bus.load_thread("thread-1")
        msgs = isolated_bus.all_messages()
        assert len(msgs) == 2
        contents = [m["content"] for m in msgs]
        assert "thread1 msg1" in contents
        assert "thread1 msg2" in contents
        assert "thread2 msg" not in contents

    def test_load_thread_empty_thread_returns_nothing(self, isolated_bus):
        isolated_bus.load_thread("nonexistent-thread")
        assert isolated_bus.all_messages() == []

    def test_load_thread_round_trip_preserves_fields(self, isolated_bus):
        isolated_bus.set_thread("thread-rt")
        isolated_bus.publish("coder", "round trip", to_role="reviewer")

        isolated_bus.reset()
        isolated_bus.load_thread("thread-rt")

        msgs = isolated_bus.all_messages()
        assert len(msgs) == 1
        assert msgs[0]["role"] == "coder"
        assert msgs[0]["to"] == "reviewer"
        assert msgs[0]["content"] == "round trip"
        assert "timestamp" in msgs[0]

    def test_set_thread_changes_thread_for_subsequent_publishes(self, isolated_bus):
        isolated_bus.set_thread("thread-A")
        isolated_bus.publish("coder", "in A")
        isolated_bus.set_thread("thread-B")
        isolated_bus.publish("coder", "in B")

        cur = isolated_bus._conn.cursor()
        cur.execute("SELECT thread_id, content FROM messages ORDER BY id")
        rows = cur.fetchall()
        assert rows[0] == ("thread-A", "in A")
        assert rows[1] == ("thread-B", "in B")


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_in_memory_messages(self, isolated_bus):
        isolated_bus.publish("coder", "msg1")
        isolated_bus.publish("coder", "msg2")
        isolated_bus.reset()
        assert isolated_bus.all_messages() == []

    def test_reset_clears_cursors(self, isolated_bus):
        isolated_bus.publish("coder", "msg1")
        isolated_bus.consume("reviewer")  # advance cursor
        isolated_bus.reset()
        # After reset, publish new message — reviewer should see it (cursor reset)
        isolated_bus.publish("coder", "msg2")
        msgs = isolated_bus.consume("reviewer")
        assert len(msgs) == 1

    def test_reset_does_not_delete_sqlite_data(self, isolated_bus):
        """reset() is in-memory only — SQLite history is preserved for load_thread."""
        isolated_bus.set_thread("thread-persist")
        isolated_bus.publish("coder", "persisted")
        isolated_bus.reset()
        # DB still has the row
        cur = isolated_bus._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM messages")
        assert cur.fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_publishes_all_stored(self, isolated_bus):
        errors = []

        def publish_many(role: str, n: int) -> None:
            try:
                for i in range(n):
                    isolated_bus.publish(role, f"{role}-{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=publish_many, args=(f"agent{j}", 20))
            for j in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(isolated_bus.all_messages()) == 100
        cur = isolated_bus._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM messages")
        assert cur.fetchone()[0] == 100, "All 100 messages must be persisted to SQLite"
        cur.close()


# ---------------------------------------------------------------------------
# DB schema — table and columns exist
# ---------------------------------------------------------------------------

class TestDbSchema:
    def test_messages_table_exists(self, isolated_bus):
        cur = isolated_bus._conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
        )
        assert cur.fetchone() is not None

    def test_messages_table_has_required_columns(self, isolated_bus):
        cur = isolated_bus._conn.cursor()
        cur.execute("PRAGMA table_info(messages)")
        col_names = {row[1] for row in cur.fetchall()}
        required = {"id", "thread_id", "role", "to_role", "content", "timestamp"}
        assert required.issubset(col_names)
