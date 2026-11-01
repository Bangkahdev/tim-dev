"""Event realtime dengan ID berurutan (SYN-01 s.d. SYN-09).

Event disimpan di SQLite sehingga ID terus naik setelah restart. Klien yang
tersambung ulang mengirim ID terakhir dan menerima event yang terlewat; bila
selisihnya melewati retensi, klien diminta mengambil snapshot penuh.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from .db import fetch_all, fetch_one, json_dump, json_load, now
from . import settings

_subscribers: dict[int, asyncio.Queue] = {}
_subscriber_seq = 0
_subscriber_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def _prune(conn) -> None:
    floor = "datetime('now', ?)"
    conn.execute(
        f"DELETE FROM event_log WHERE datetime(created_at) < {floor}",
        (f"-{settings.EVENT_RETENTION_HOURS} hours",),
    )
    conn.execute(
        """
        DELETE FROM event_log
        WHERE id NOT IN (SELECT id FROM event_log ORDER BY id DESC LIMIT ?)
        """,
        (settings.EVENT_RETENTION_COUNT,),
    )


def publish(conn, event_type: str, actor: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    created_at = now()
    cursor = conn.execute(
        "INSERT INTO event_log (type, actor, payload, created_at) VALUES (?, ?, ?, ?)",
        (event_type, actor, json_dump(payload or {}), created_at),
    )
    _prune(conn)
    event = {
        "id": int(cursor.lastrowid),
        "type": event_type,
        "actor": actor,
        "payload": payload or {},
        "created_at": created_at,
    }
    _fanout(event)
    return event


def _fanout(event: dict[str, Any]) -> None:
    loop = _loop
    if loop is None:
        return
    with _subscriber_lock:
        queues = list(_subscribers.values())
    for queue in queues:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            # Event loop sudah berhenti; pelanggan akan tersambung ulang.
            pass


def attach_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe() -> tuple[int, asyncio.Queue]:
    global _subscriber_seq
    with _subscriber_lock:
        _subscriber_seq += 1
        subscription_id = _subscriber_seq
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        _subscribers[subscription_id] = queue
    return subscription_id, queue


def unsubscribe(subscription_id: int) -> None:
    with _subscriber_lock:
        _subscribers.pop(subscription_id, None)


def latest_id(conn) -> int:
    row = fetch_one(conn, "SELECT COALESCE(MAX(id), 0) AS latest FROM event_log")
    return int(row["latest"]) if row else 0


def oldest_id(conn) -> int:
    row = fetch_one(conn, "SELECT COALESCE(MIN(id), 0) AS oldest FROM event_log")
    return int(row["oldest"]) if row else 0


def replay(conn, last_event_id: int = 0, limit: int = 1000) -> dict[str, Any]:
    latest = latest_id(conn)
    oldest = oldest_id(conn)
    gap = bool(last_event_id and oldest and last_event_id < oldest - 1)
    if gap:
        return {
            "events": [],
            "latest_id": latest,
            "gap": True,
            "snapshot_required": True,
        }
    rows = fetch_all(
        conn,
        "SELECT * FROM event_log WHERE id > ? ORDER BY id ASC LIMIT ?",
        (max(0, last_event_id), max(1, min(limit, 5000))),
    )
    events = [
        {
            "id": row["id"],
            "type": row["type"],
            "actor": row["actor"],
            "payload": json_load(row["payload"], {}),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return {
        "events": events,
        "latest_id": latest,
        "gap": False,
        "snapshot_required": False,
    }


def ack(conn, client_id: str, event_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO event_acks (client_id, event_id, at) VALUES (?, ?, ?)",
        (client_id, int(event_id), now()),
    )
