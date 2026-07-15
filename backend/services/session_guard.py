"""
Session-level access controls:
  - ownership check (you can only access your own sessions)
  - concurrent session cap (max N active sessions per user)
  - idle timeout (sessions expire after M minutes of inactivity)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from auth import AuthenticatedUser
from services.session_store import evict, now
from services.supabase_client import get_supabase

MAX_ACTIVE_SESSIONS = int(os.environ.get("MAX_ACTIVE_SESSIONS", "3"))
SESSION_IDLE_TIMEOUT_MINUTES = int(os.environ.get("SESSION_IDLE_TIMEOUT_MINUTES", "30"))


def check_ownership(session: dict, user: AuthenticatedUser) -> None:
    owner = session.get("user_id")
    if owner and owner != user.id:
        raise HTTPException(status_code=403, detail="You don't have access to this session")


def _parse_timestamp(value) -> datetime | None:
    """Supabase timestamps come back as ISO strings; tolerate anything unparseable."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    # A naive timestamp compared against an aware cutoff raises; assume UTC.
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def sweep_abandoned_sessions(user_id: str) -> None:
    """Marks the user's stale 'active' sessions as 'abandoned'.

    Closing the tab mid-interview strands a session forever: /interview carries no
    session id, so a session can never be reopened, and ending one is only possible
    from inside the interview you can no longer reach. The row stays 'active' and keeps
    counting against MAX_ACTIVE_SESSIONS. Three of those and the user is locked out of
    starting anything at all, with no way back. Sweeping on the way in lets the cap
    heal itself, and gives the 'abandoned' status its first writer.

    Idleness is measured from the newest message, falling back to the session's
    created_at -- the same definition session_store.get_session uses to build
    last_activity_at. Deliberately NOT sessions.updated_at: the sessions_set_updated_at
    trigger only fires on writes to the sessions row, and persisting a message doesn't
    touch it, so updated_at sits frozen near creation and sweeping on it would abandon
    sessions that are actively in use.
    """
    sb = get_supabase()
    if not sb:
        return

    resp = (
        sb.table("sessions")
        .select("id, created_at")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return

    msgs = (
        sb.table("messages")
        .select("session_id, created_at")
        .in_("session_id", [r["id"] for r in rows])
        .execute()
    )
    latest: dict[str, datetime] = {}
    for m in msgs.data or []:
        ts = _parse_timestamp(m.get("created_at"))
        if ts and (m["session_id"] not in latest or ts > latest[m["session_id"]]):
            latest[m["session_id"]] = ts

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES)
    stale = []
    for r in rows:
        last_activity = latest.get(r["id"]) or _parse_timestamp(r.get("created_at"))
        # Unparseable and message-less: leave it alone rather than guess it's stale.
        if last_activity and last_activity < cutoff:
            stale.append(r["id"])
    if not stale:
        return

    sb.table("sessions").update({"status": "abandoned", "ended_at": now()}).in_("id", stale).execute()
    for session_id in stale:
        evict(session_id)


def check_session_limit(user_id: str) -> None:
    """Rejects if the user already has MAX_ACTIVE_SESSIONS open sessions."""
    sb = get_supabase()
    if not sb:
        return
    sweep_abandoned_sessions(user_id)
    resp = sb.table("sessions").select("id", count="exact").eq("user_id", user_id).eq("status", "active").execute()
    count = resp.count or 0
    if count >= MAX_ACTIVE_SESSIONS:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You already have {count} active session(s). "
                f"End an existing session before starting a new one."
            ),
        )


MAX_CANDIDATE_TURNS = int(os.environ.get("MAX_CANDIDATE_TURNS", "15"))


def is_turn_limit_reached(session: dict) -> bool:
    """True when the candidate has sent MAX_CANDIDATE_TURNS messages in this session."""
    turns = sum(1 for t in session["history"] if t["role"] == "candidate")
    return turns >= MAX_CANDIDATE_TURNS


def check_idle_timeout(session: dict) -> None:
    """Raises 410 if the session has been idle longer than SESSION_IDLE_TIMEOUT_MINUTES."""
    last_activity = session.get("last_activity_at")
    if not last_activity:
        return
    if isinstance(last_activity, str):
        try:
            last_activity = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
        except ValueError:
            return
    elapsed_minutes = (datetime.now(timezone.utc) - last_activity).total_seconds() / 60
    if elapsed_minutes > SESSION_IDLE_TIMEOUT_MINUTES:
        raise HTTPException(
            status_code=410,
            detail=(
                f"This session has been idle for over {SESSION_IDLE_TIMEOUT_MINUTES} minutes "
                f"and has expired. Start a new session to continue."
            ),
        )
