from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from services import session_guard, session_store


def _iso(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _supabase(active_rows, message_rows=(), active_count=0):
    """Mocks the two reads the sweep makes, plus check_session_limit's count query.

    select("id, created_at") -> active session rows
    select("session_id, created_at").in_(...) -> message rows
    select("id", count="exact") -> the post-sweep count
    """
    sb = MagicMock()

    def select(*args, **kwargs):
        chain = MagicMock()
        if kwargs.get("count") == "exact":
            chain.eq.return_value.eq.return_value.execute.return_value = MagicMock(count=active_count)
        elif args and args[0] == "session_id, created_at":
            chain.in_.return_value.execute.return_value = MagicMock(data=list(message_rows))
        else:
            chain.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=list(active_rows))
        return chain

    sb.table.return_value.select.side_effect = select
    return sb


def test_session_idle_past_the_timeout_is_marked_abandoned():
    stale_minutes = session_guard.SESSION_IDLE_TIMEOUT_MINUTES + 10
    sb = _supabase(
        active_rows=[{"id": "s-old", "created_at": _iso(stale_minutes)}],
        message_rows=[{"session_id": "s-old", "created_at": _iso(stale_minutes)}],
    )
    with patch.object(session_guard, "get_supabase", return_value=sb):
        session_guard.sweep_abandoned_sessions("user-1")

    update_payload = sb.table.return_value.update.call_args[0][0]
    assert update_payload["status"] == "abandoned"
    assert update_payload["ended_at"]
    sb.table.return_value.update.return_value.in_.assert_called_once_with("id", ["s-old"])


def test_session_with_a_recent_message_is_left_alone():
    """The whole point: a live session must never be swept out from under the user."""
    sb = _supabase(
        # created_at is ancient -- only the recent message should save it.
        active_rows=[{"id": "s-live", "created_at": _iso(session_guard.SESSION_IDLE_TIMEOUT_MINUTES + 120)}],
        message_rows=[{"session_id": "s-live", "created_at": _iso(1)}],
    )
    with patch.object(session_guard, "get_supabase", return_value=sb):
        session_guard.sweep_abandoned_sessions("user-1")

    sb.table.return_value.update.assert_not_called()


def test_message_less_session_falls_back_to_created_at():
    sb = _supabase(
        active_rows=[{"id": "s-fresh", "created_at": _iso(1)}],
        message_rows=[],
    )
    with patch.object(session_guard, "get_supabase", return_value=sb):
        session_guard.sweep_abandoned_sessions("user-1")

    sb.table.return_value.update.assert_not_called()


def test_unparseable_timestamp_is_not_swept():
    sb = _supabase(
        active_rows=[{"id": "s-weird", "created_at": "not-a-timestamp"}],
        message_rows=[],
    )
    with patch.object(session_guard, "get_supabase", return_value=sb):
        session_guard.sweep_abandoned_sessions("user-1")

    sb.table.return_value.update.assert_not_called()


def test_swept_sessions_are_evicted_from_the_cache():
    stale_minutes = session_guard.SESSION_IDLE_TIMEOUT_MINUTES + 10
    session_store.SESSIONS["s-old"] = {"user_id": "user-1"}
    sb = _supabase(
        active_rows=[{"id": "s-old", "created_at": _iso(stale_minutes)}],
        message_rows=[{"session_id": "s-old", "created_at": _iso(stale_minutes)}],
    )
    try:
        with patch.object(session_guard, "get_supabase", return_value=sb):
            session_guard.sweep_abandoned_sessions("user-1")
        assert "s-old" not in session_store.SESSIONS
    finally:
        session_store.SESSIONS.pop("s-old", None)


def test_sweep_noop_when_supabase_unconfigured():
    with patch.object(session_guard, "get_supabase", return_value=None):
        session_guard.sweep_abandoned_sessions("user-1")


def test_check_session_limit_sweeps_before_counting():
    """The lockout fix: three abandoned sessions must not block a new start."""
    stale_minutes = session_guard.SESSION_IDLE_TIMEOUT_MINUTES + 10
    sb = _supabase(
        active_rows=[
            {"id": "s-1", "created_at": _iso(stale_minutes)},
            {"id": "s-2", "created_at": _iso(stale_minutes)},
            {"id": "s-3", "created_at": _iso(stale_minutes)},
        ],
        message_rows=[],
        active_count=0,  # post-sweep: all three are now 'abandoned'
    )
    with patch.object(session_guard, "get_supabase", return_value=sb):
        session_guard.check_session_limit("user-1")  # must not raise

    sb.table.return_value.update.return_value.in_.assert_called_once_with("id", ["s-1", "s-2", "s-3"])


def test_check_session_limit_still_rejects_when_sessions_are_genuinely_active():
    sb = _supabase(
        active_rows=[{"id": "s-live", "created_at": _iso(1)}],
        message_rows=[{"session_id": "s-live", "created_at": _iso(1)}],
        active_count=session_guard.MAX_ACTIVE_SESSIONS,
    )
    with patch.object(session_guard, "get_supabase", return_value=sb):
        with pytest.raises(HTTPException) as exc:
            session_guard.check_session_limit("user-1")

    assert exc.value.status_code == 429
    sb.table.return_value.update.assert_not_called()
