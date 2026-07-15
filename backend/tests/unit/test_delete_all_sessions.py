from unittest.mock import MagicMock, patch

from auth import AuthenticatedUser
from routers import interview
from services import session_store

USER = AuthenticatedUser(id="user-1", email="user-1@example.com")


def _supabase_returning(rows):
    """A Supabase mock whose select(...) chain resolves to `rows`."""
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=rows)
    return sb


async def test_delete_all_is_scoped_to_the_calling_user():
    """The service-role key bypasses RLS, so this user_id filter is the only thing
    keeping one user's delete off another user's rows."""
    sb = _supabase_returning([{"id": "s-1"}, {"id": "s-2"}])
    with patch.object(interview, "get_supabase", return_value=sb):
        result = await interview.delete_all_sessions(user=USER)

    assert result == {"deleted": 2}
    sb.table.return_value.delete.return_value.eq.assert_called_once_with("user_id", "user-1")


async def test_delete_all_evicts_deleted_sessions_from_the_cache():
    """A deleted session left in SESSIONS would still be servable from this replica."""
    session_store.SESSIONS["s-1"] = {"user_id": "user-1"}
    session_store.SESSIONS["s-2"] = {"user_id": "user-1"}
    sb = _supabase_returning([{"id": "s-1"}, {"id": "s-2"}])
    try:
        with patch.object(interview, "get_supabase", return_value=sb):
            await interview.delete_all_sessions(user=USER)
        assert "s-1" not in session_store.SESSIONS
        assert "s-2" not in session_store.SESSIONS
    finally:
        session_store.SESSIONS.pop("s-1", None)
        session_store.SESSIONS.pop("s-2", None)


async def test_delete_all_issues_no_delete_when_user_has_no_sessions():
    sb = _supabase_returning([])
    with patch.object(interview, "get_supabase", return_value=sb):
        result = await interview.delete_all_sessions(user=USER)

    assert result == {"deleted": 0}
    sb.table.return_value.delete.assert_not_called()


async def test_delete_all_noop_when_supabase_unconfigured():
    with patch.object(interview, "get_supabase", return_value=None):
        assert await interview.delete_all_sessions(user=USER) == {"deleted": 0}
