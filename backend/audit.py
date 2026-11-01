"""Audit log hanya-tambah (RPT-05, APR-05, PAP-16)."""

from __future__ import annotations

import hashlib
from typing import Any

from .db import fetch_all, fetch_one, json_dump, now


def detail_hash(detail: str) -> str:
    return hashlib.sha256(detail.encode("utf-8")).hexdigest()


def log(
    conn,
    *,
    actor: str,
    actor_kind: str,
    action: str,
    detail: str = "",
    ref_type: str | None = None,
    ref_id: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO audit_log (at, actor, actor_kind, action, detail, ref_type, ref_id, detail_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now(), actor, actor_kind, action, detail, ref_type, ref_id, detail_hash(detail)),
    )
    return int(cursor.lastrowid)


def list_entries(
    conn,
    *,
    limit: int = 50,
    action: str | None = None,
    actor: str | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    before_id: int | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if action:
        clauses.append("action = ?")
        params.append(action)
    if actor:
        clauses.append("actor = ?")
        params.append(actor)
    if ref_type:
        clauses.append("ref_type = ?")
        params.append(ref_type)
    if ref_id:
        clauses.append("ref_id = ?")
        params.append(ref_id)
    if before_id is not None:
        clauses.append("id < ?")
        params.append(before_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 500)))
    return fetch_all(
        conn,
        f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ?",
        tuple(params),
    )


def count(conn) -> int:
    row = fetch_one(conn, "SELECT COUNT(*) AS total FROM audit_log")
    return int(row["total"]) if row else 0


def record_decision(
    conn,
    *,
    actor: str,
    action: str,
    ref_type: str,
    ref_id: str,
    payload_hash: str,
    note: str = "",
) -> int:
    detail = json_dump(
        {
            "decision": action,
            "payload_hash": payload_hash,
            "note": note,
            "at": now(),
        }
    )
    return log(
        conn,
        actor=actor,
        actor_kind="owner",
        action=action,
        detail=detail,
        ref_type=ref_type,
        ref_id=ref_id,
    )
