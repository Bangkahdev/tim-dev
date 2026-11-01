"""Percakapan persisten (CHT-01). Riwayat bertahan setelah restart."""

from __future__ import annotations

from typing import Any

from .db import fetch_all, now


def append(
    conn,
    *,
    thread_type: str,
    thread_id: str,
    sender: str,
    role: str,
    content: str,
) -> dict[str, Any]:
    cursor = conn.execute(
        """
        INSERT INTO chat_messages (thread_type, thread_id, sender, role, content, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (thread_type, thread_id, sender, role, content, now()),
    )
    return {
        "id": int(cursor.lastrowid),
        "thread_type": thread_type,
        "thread_id": thread_id,
        "sender": sender,
        "role": role,
        "content": content,
        "created_at": now(),
    }


def history(
    conn,
    *,
    thread_type: str,
    thread_id: str,
    limit: int = 50,
    before_id: int | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [thread_type, thread_id]
    before = ""
    if before_id is not None:
        before = "AND id < ?"
        params.append(before_id)
    params.append(max(1, min(limit, 200)))
    rows = fetch_all(
        conn,
        f"""
        SELECT * FROM chat_messages
        WHERE thread_type = ? AND thread_id = ? {before}
        ORDER BY id DESC LIMIT ?
        """,
        tuple(params),
    )
    return list(reversed(rows))


def clear(conn, *, thread_type: str, thread_id: str) -> None:
    conn.execute(
        "DELETE FROM chat_messages WHERE thread_type = ? AND thread_id = ?",
        (thread_type, thread_id),
    )
