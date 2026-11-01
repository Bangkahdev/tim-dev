"""Sesi Owner berumur pendek (NFR-SEC-08).

Token asli hanya diberikan sekali ke klien dan tidak pernah disimpan backend;
yang tersimpan adalah hash SHA-256. Sesi dapat dicabut dan kedaluwarsa.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from .db import fetch_one, now
from . import settings


class AuthError(Exception):
    status_code = 401


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(conn, *, hours: int | None = None, token: str | None = None) -> dict:
    raw = token or secrets.token_urlsafe(32)
    created = datetime.now().astimezone()
    expires = created + timedelta(hours=hours or settings.OWNER_SESSION_HOURS)
    conn.execute(
        """
        INSERT INTO owner_sessions (token_hash, created_at, expires_at, revoked, last_seen_at)
        VALUES (?, ?, ?, 0, ?)
        """,
        (
            hash_token(raw),
            created.isoformat(timespec="seconds"),
            expires.isoformat(timespec="seconds"),
            created.isoformat(timespec="seconds"),
        ),
    )
    return {
        "token": raw,
        "created_at": created.isoformat(timespec="seconds"),
        "expires_at": expires.isoformat(timespec="seconds"),
        "hours": hours or settings.OWNER_SESSION_HOURS,
    }


def verify_token(conn, token: str | None) -> dict | None:
    if not token:
        return None
    row = fetch_one(
        conn,
        "SELECT * FROM owner_sessions WHERE token_hash = ?",
        (hash_token(token),),
    )
    if not row or row["revoked"]:
        return None
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except ValueError:
        return None
    if expires <= datetime.now().astimezone():
        return None
    conn.execute(
        "UPDATE owner_sessions SET last_seen_at = ? WHERE token_hash = ?",
        (now(), row["token_hash"]),
    )
    return row


def revoke(conn, token: str) -> bool:
    cursor = conn.execute(
        "UPDATE owner_sessions SET revoked = 1 WHERE token_hash = ? AND revoked = 0",
        (hash_token(token),),
    )
    return cursor.rowcount > 0


def purge_expired(conn) -> None:
    conn.execute(
        "DELETE FROM owner_sessions WHERE datetime(expires_at) < datetime('now', '-1 day')"
    )


def token_matches_config(candidate: str | None) -> bool:
    """Bila API_AUTH_TOKEN diisi, sesi hanya terbit dengan token itu."""
    expected = settings.API_AUTH_TOKEN
    if not expected:
        return True
    return bool(candidate) and secrets.compare_digest(candidate, expected)
