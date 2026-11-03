"""Dokumen fisik (Paper), printer, dan persetujuan terikat payload.

Alur nyata: proposal -> DRAFT -> PRINTED (PDF dibuat) -> DELIVERED (tray
Owner) -> keputusan Owner. Semua transisi hanya lewat backend dan tercatat.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import audit, events, settings
from .db import fetch_all, fetch_one, json_dump, json_load, now, parse_time
from .pdf import write_pdf

PAPER_TYPES = {
    "task_report", "project_report", "division_report", "approval_proposal",
    "meeting_minutes", "email_draft", "website_package",
}
DELIVERY_STATUSES = {"DRAFT", "PRINTED", "DELIVERED", "EXPIRED", "ARCHIVED"}
REVIEW_STATUSES = {"UNREAD", "REVIEWED", "DEFERRED", "APPROVED", "REJECTED", "REVISION_REQUESTED"}
FINAL_REVIEW = {"APPROVED", "REJECTED", "REVISION_REQUESTED"}
DECISIONS = {"APPROVED", "REJECTED", "REVISION_REQUESTED", "DEFERRED"}


class PaperError(Exception):
    status_code = 400


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json_dump(payload).encode("utf-8")).hexdigest()


def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    row["payload"] = json_load(row.get("payload"), {})
    return row


def get_paper(conn, paper_id: str) -> dict[str, Any]:
    paper = _decode(fetch_one(conn, "SELECT * FROM papers WHERE id = ?", (paper_id,)))
    if not paper:
        raise PaperError(f"Paper {paper_id} tidak ditemukan.")
    return paper


def get_approval(conn, approval_id: str) -> dict[str, Any]:
    row = fetch_one(conn, "SELECT * FROM approvals WHERE id = ?", (approval_id,))
    if not row:
        raise PaperError(f"Persetujuan {approval_id} tidak ditemukan.")
    row["payload"] = json_load(row.get("payload"), {})
    return row


def list_papers(conn, *, delivery_status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if delivery_status:
        where = "WHERE delivery_status = ?"
        params.append(delivery_status)
    params.append(max(1, min(limit, 500)))
    rows = fetch_all(conn, f"SELECT * FROM papers {where} ORDER BY created_at DESC LIMIT ?", tuple(params))
    return [_decode(row) for row in rows]


def _tray_rows(conn) -> list[dict[str, Any]]:
    return fetch_all(
        conn,
        """
        SELECT * FROM papers
        WHERE delivery_status = 'DELIVERED'
          AND review_status NOT IN ('APPROVED', 'REJECTED', 'REVISION_REQUESTED', 'EXPIRED')
        ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                 created_at ASC
        """,
    )


def tray(conn, *, limit: int | None = None) -> list[dict[str, Any]]:
    rows = _tray_rows(conn)
    cap = max(1, limit or settings.PAPER_TRAY_LIMIT)
    return [_decode(row) for row in rows[:cap]]


def tray_summary(conn, *, limit: int | None = None) -> dict[str, Any]:
    rows = _tray_rows(conn)
    cap = max(1, limit or settings.PAPER_TRAY_LIMIT)
    visible = [_decode(row) for row in rows[:cap]]
    hidden = rows[cap:]
    by_priority: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for row in rows:
        by_priority[row.get("priority") or "normal"] = by_priority.get(row.get("priority") or "normal", 0) + 1
        by_type[row.get("type") or "unknown"] = by_type.get(row.get("type") or "unknown", 0) + 1
    summary_sheet = None
    if hidden:
        summary_sheet = {
            "title": "Ringkasan tray",
            "total": len(rows),
            "visible": len(visible),
            "overflow": len(hidden),
            "by_priority": by_priority,
            "by_type": by_type,
        }
    return {
        "papers": visible,
        "pending": len(rows),
        "limit": cap,
        "overflow": len(hidden),
        "overflow_papers": [
            {"id": row["id"], "summary": row.get("summary", ""), "priority": row.get("priority")}
            for row in hidden
        ],
        "summary_sheet": summary_sheet,
    }


def pending_count(conn) -> int:
    return len(_tray_rows(conn))


def create_paper(
    conn,
    *,
    paper_type: str,
    creator: str,
    payload: dict[str, Any],
    summary: str,
    task_id: str | None = None,
    approval_id: str | None = None,
    priority: str = "normal",
    ttl_hours: int | None = None,
    version: int = 1,
) -> dict[str, Any]:
    if paper_type not in PAPER_TYPES:
        raise PaperError(f"Jenis paper tidak sah: {paper_type}")
    paper_id = f"paper_{uuid.uuid4().hex[:12]}"
    stamp = datetime.now().astimezone()
    expires = stamp + timedelta(hours=ttl_hours or settings.APPROVAL_TTL_HOURS)
    conn.execute(
        """
        INSERT INTO papers
            (id, type, creator, target, delivery_status, review_status, version,
             payload_hash, payload, summary, priority, task_id, approval_id,
             created_at, updated_at, expires_at)
        VALUES (?, ?, ?, 'owner_tray', 'DRAFT', 'UNREAD', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            paper_id, paper_type, creator, version, payload_hash(payload),
            json_dump(payload), summary, priority, task_id, approval_id,
            stamp.isoformat(timespec="seconds"),
            stamp.isoformat(timespec="seconds"),
            expires.isoformat(timespec="seconds"),
        ),
    )
    audit.log(
        conn, actor=creator, actor_kind="employee", action="paper.created",
        detail=json_dump({"type": paper_type, "hash": payload_hash(payload), "summary": summary}),
        ref_type="paper", ref_id=paper_id,
    )
    events.publish(conn, "paper.created", creator, {"paper_id": paper_id, "type": paper_type})
    return get_paper(conn, paper_id)


def create_approval_bundle(
    conn,
    *,
    approval_type: str,
    payload: dict[str, Any],
    requester: str,
    summary: str,
    task_id: str | None = None,
    priority: str = "high",
    ttl_hours: int | None = None,
) -> dict[str, Any]:
    """Tulis persetujuan + outbox + paper dalam satu transaksi (APR-10)."""
    digest = payload_hash(payload)
    approval_id = f"appr_{uuid.uuid4().hex[:12]}"
    stamp = datetime.now().astimezone()
    expires = stamp + timedelta(hours=ttl_hours or settings.APPROVAL_TTL_HOURS)
    idempotency_key = f"{approval_type}:{digest}:{uuid.uuid4().hex[:8]}"
    conn.execute(
        """
        INSERT INTO approvals
            (id, type, payload, payload_hash, requester, status, expires_at,
             execution_status, idempotency_key, created_at)
        VALUES (?, ?, ?, ?, ?, 'PENDING', ?, 'PENDING', ?, ?)
        """,
        (
            approval_id, approval_type, json_dump(payload), digest, requester,
            expires.isoformat(timespec="seconds"), idempotency_key,
            stamp.isoformat(timespec="seconds"),
        ),
    )
    conn.execute(
        """
        INSERT INTO approval_outbox
            (approval_id, idempotency_key, status, created_at, updated_at)
        VALUES (?, ?, 'PENDING', ?, ?)
        """,
        (approval_id, idempotency_key, stamp.isoformat(timespec="seconds"), stamp.isoformat(timespec="seconds")),
    )
    paper = create_paper(
        conn,
        paper_type="email_draft" if approval_type == "email" else "website_package" if approval_type == "website" else "approval_proposal",
        creator=requester,
        payload=payload,
        summary=summary,
        task_id=task_id,
        approval_id=approval_id,
        priority=priority,
        ttl_hours=ttl_hours,
    )
    audit.log(
        conn, actor=requester, actor_kind="employee", action="approval.requested",
        detail=json_dump({"type": approval_type, "hash": digest, "approval_id": approval_id}),
        ref_type="approval", ref_id=approval_id,
    )
    return {"approval": get_approval(conn, approval_id), "paper": paper}


def print_paper(conn, paper_id: str, *, printer: str = "printer_kantor", actor: str | None = None) -> dict[str, Any]:
    paper = get_paper(conn, paper_id)
    if paper["delivery_status"] in ("EXPIRED", "ARCHIVED"):
        raise PaperError("Paper sudah tidak dapat dicetak.")
    if paper["delivery_status"] == "PRINTED":
        job = fetch_one(conn, "SELECT * FROM print_jobs WHERE paper_id = ? ORDER BY created_at DESC LIMIT 1", (paper_id,))
        return {"paper": paper, "print_job": job}
    if paper["delivery_status"] != "DRAFT":
        raise PaperError("Hanya paper DRAFT yang dapat dicetak.")
    pdf_path = settings.PRINT_DIR / f"{paper_id}_v{paper['version']}.pdf"
    lines = [f"Jenis: {paper['type']}", f"Dibuat oleh: {paper['creator']}", ""]
    lines.extend(f"{key}: {value}" for key, value in paper["payload"].items() if not isinstance(value, (dict, list)))
    if paper["payload"].get("body"):
        lines.extend(["", "Isi:", str(paper["payload"]["body"])])
    if paper["payload"].get("diff"):
        lines.extend(["", "Perubahan:", str(paper["payload"]["diff"])])
    write_pdf(pdf_path, paper["summary"] or paper["type"], lines)
    job_id = f"print_{uuid.uuid4().hex[:10]}"
    stamp = now()
    conn.execute(
        "INSERT INTO print_jobs (id, paper_id, printer, created_at, pdf_path, status) VALUES (?, ?, ?, ?, ?, 'DONE')",
        (job_id, paper_id, printer, stamp, str(pdf_path)),
    )
    conn.execute(
        "UPDATE papers SET delivery_status = 'PRINTED', updated_at = ? WHERE id = ?",
        (stamp, paper_id),
    )
    audit.log(
        conn, actor=actor or paper["creator"], actor_kind="employee", action="paper.printed",
        detail=json_dump({"printer": printer, "pdf": str(pdf_path)}),
        ref_type="paper", ref_id=paper_id,
    )
    events.publish(conn, "paper.printed", actor or paper["creator"], {"paper_id": paper_id, "pdf": str(pdf_path)})
    return {"paper": get_paper(conn, paper_id), "print_job": fetch_one(conn, "SELECT * FROM print_jobs WHERE id = ?", (job_id,))}


def deliver_paper(conn, paper_id: str, *, actor: str | None = None) -> dict[str, Any]:
    paper = get_paper(conn, paper_id)
    if paper["delivery_status"] != "PRINTED":
        raise PaperError("Paper harus dicetak sebelum diantar ke tray.")
    stamp = now()
    conn.execute(
        "UPDATE papers SET delivery_status = 'DELIVERED', updated_at = ? WHERE id = ?",
        (stamp, paper_id),
    )
    conn.execute(
        "INSERT INTO world_events (at, type, actor, object, room, payload) VALUES (?, 'paper.delivered', ?, 'tray_owner', 'owner_room', ?)",
        (stamp, actor or paper["creator"], json_dump({"paper_id": paper_id})),
    )
    audit.log(
        conn, actor=actor or paper["creator"], actor_kind="employee", action="paper.delivered",
        detail=json_dump({"paper_id": paper_id}), ref_type="paper", ref_id=paper_id,
    )
    events.publish(conn, "paper.delivered", actor or paper["creator"], {"paper_id": paper_id})
    return get_paper(conn, paper_id)


def _expire_if_needed(conn, paper: dict[str, Any]) -> bool:
    expires = parse_time(paper.get("expires_at"))
    if expires and expires <= datetime.now().astimezone() and paper["review_status"] not in FINAL_REVIEW:
        conn.execute(
            "UPDATE papers SET delivery_status = 'EXPIRED', review_status = 'EXPIRED', updated_at = ? WHERE id = ?",
            (now(), paper["id"]),
        )
        audit.log(
            conn, actor="system", actor_kind="backend", action="paper.expired",
            detail=json_dump({"paper_id": paper["id"]}),
            ref_type="paper", ref_id=paper["id"],
        )
        events.publish(conn, "paper.expired", "system", {"paper_id": paper["id"]})
        return True
    return False


def decide_paper(
    conn,
    paper_id: str,
    *,
    decision: str,
    actor: str,
    actor_kind: str,
    note: str = "",
) -> dict[str, Any]:
    decision = (decision or "").upper()
    if decision not in DECISIONS:
        raise PaperError(f"Keputusan tidak sah: {decision}")
    if actor_kind != "owner":
        raise PaperError("Hanya sesi Owner yang dapat memutuskan paper.")
    paper = get_paper(conn, paper_id)
    if _expire_if_needed(conn, paper):
        raise PaperError("Paper sudah kedaluwarsa dan tidak dapat disetujui.")
    if paper["delivery_status"] != "DELIVERED":
        raise PaperError("Paper belum berada di tray Owner.")
    if paper["review_status"] in FINAL_REVIEW:
        raise PaperError("Paper ini sudah diputuskan dan tidak dapat diputuskan dua kali.")

    if decision == "DEFERRED":
        conn.execute(
            "UPDATE papers SET review_status = 'DEFERRED', updated_at = ? WHERE id = ?",
            (now(), paper_id),
        )
        audit.log(
            conn, actor=actor, actor_kind="owner", action="paper.deferred",
            detail=json_dump({"paper_id": paper_id, "note": note}),
            ref_type="paper", ref_id=paper_id,
        )
        events.publish(conn, "paper.deferred", actor, {"paper_id": paper_id})
        return get_paper(conn, paper_id)

    approval_id = paper.get("approval_id")
    if approval_id:
        approval = get_approval(conn, approval_id)
        if approval["payload_hash"] != paper["payload_hash"]:
            conn.execute(
                "UPDATE papers SET review_status = 'REVISION_REQUESTED', decision_note = ?, updated_at = ? WHERE id = ?",
                ("Payload berubah setelah diajukan; persetujuan dibatalkan.", now(), paper_id),
            )
            audit.log(
                conn, actor=actor, actor_kind="owner", action="approval.invalidated",
                detail=json_dump({"paper_id": paper_id, "approval_id": approval_id, "reason": "hash_mismatch"}),
                ref_type="approval", ref_id=approval_id,
            )
            raise PaperError("Payload berubah; persetujuan dibatalkan dan item kembali ke antrean.")

    stamp = now()
    conn.execute(
        """
        UPDATE papers
        SET review_status = ?, decided_by = ?, decided_at = ?, decision_note = ?, updated_at = ?
        WHERE id = ?
        """,
        (decision, actor, stamp, note, stamp, paper_id),
    )
    if approval_id:
        approval_status = {
            "APPROVED": "APPROVED",
            "REJECTED": "REJECTED",
            "REVISION_REQUESTED": "REVISION_REQUESTED",
        }[decision]
        execution_status = "PENDING"
        conn.execute(
            "UPDATE approvals SET status = ?, decided_by = ?, decided_at = ?, execution_status = ? WHERE id = ?",
            (approval_status, actor, stamp, execution_status, approval_id),
        )
        conn.execute(
            "UPDATE approval_outbox SET status = ?, updated_at = ? WHERE approval_id = ?",
            ("CANCELLED" if decision == "REJECTED" else "PENDING", stamp, approval_id),
        )
    audit.record_decision(
        conn,
        actor=actor,
        action=f"paper.{decision.lower()}",
        ref_type="paper",
        ref_id=paper_id,
        payload_hash=paper["payload_hash"],
        note=note,
    )
    events.publish(
        conn,
        "paper.decided",
        actor,
        {"paper_id": paper_id, "decision": decision, "approval_id": approval_id},
    )
    return get_paper(conn, paper_id)


def revise_paper(
    conn,
    paper_id: str,
    *,
    payload: dict[str, Any],
    summary: str,
    actor: str,
) -> dict[str, Any]:
    """Buat versi baru setelah Minta Revisi; versi lama diarsipkan (PAP-10)."""
    old = get_paper(conn, paper_id)
    if old["review_status"] != "REVISION_REQUESTED":
        raise PaperError("Revisi hanya dapat dibuat setelah Owner meminta revisi.")
    old_approval = get_approval(conn, old["approval_id"]) if old.get("approval_id") else None
    conn.execute(
        "UPDATE papers SET delivery_status = 'ARCHIVED', updated_at = ? WHERE id = ?",
        (now(), paper_id),
    )
    if old.get("approval_id"):
        conn.execute(
            "UPDATE approvals SET status = 'SUPERSEDED' WHERE id = ?",
            (old["approval_id"],),
        )
        conn.execute(
            "UPDATE approval_outbox SET status = 'CANCELLED', updated_at = ? WHERE approval_id = ?",
            (now(), old["approval_id"]),
        )
    if old_approval:
        bundle = create_approval_bundle(
            conn,
            approval_type=old_approval["type"],
            payload=payload,
            requester=actor,
            summary=summary,
            task_id=old.get("task_id"),
            priority=old.get("priority", "normal"),
        )
        new_paper = bundle["paper"]
        conn.execute(
            "UPDATE papers SET version = ?, updated_at = ? WHERE id = ?",
            (old["version"] + 1, now(), new_paper["id"]),
        )
        return get_paper(conn, new_paper["id"])
    return create_paper(
        conn,
        paper_type=old["type"],
        creator=actor,
        payload=payload,
        summary=summary,
        task_id=old.get("task_id"),
        priority=old.get("priority", "normal"),
        version=old["version"] + 1,
    )


def claim_execution(conn, approval_id: str, worker: str) -> dict[str, Any] | None:
    """Satu pekerja saja yang boleh mengklaim satu eksekusi (APR-09)."""
    stamp = now()
    cursor = conn.execute(
        """
        UPDATE approval_outbox
        SET status = 'CLAIMED', claimed_by = ?, claimed_at = ?, updated_at = ?,
            attempts = attempts + 1
        WHERE approval_id = ? AND status = 'PENDING'
        """,
        (worker, stamp, stamp, approval_id),
    )
    if cursor.rowcount != 1:
        return None
    conn.execute(
        "UPDATE approvals SET execution_status = 'CLAIMED', attempts = attempts + 1 WHERE id = ?",
        (approval_id,),
    )
    return fetch_one(conn, "SELECT * FROM approval_outbox WHERE approval_id = ?", (approval_id,))


def finish_execution(
    conn,
    approval_id: str,
    *,
    status: str,
    result: str = "",
) -> dict[str, Any]:
    if status not in {"SUCCEEDED", "FAILED", "UNKNOWN"}:
        raise PaperError(f"Status eksekusi tidak sah: {status}")
    stamp = now()
    conn.execute(
        "UPDATE approval_outbox SET status = ?, result = ?, updated_at = ? WHERE approval_id = ?",
        (status, result, stamp, approval_id),
    )
    conn.execute(
        "UPDATE approvals SET execution_status = ?, result = ? WHERE id = ?",
        (status, result, approval_id),
    )
    audit.log(
        conn, actor="executor", actor_kind="backend", action="approval.execution",
        detail=json_dump({"approval_id": approval_id, "status": status}),
        ref_type="approval", ref_id=approval_id,
    )
    events.publish(conn, "approval.execution", "executor", {"approval_id": approval_id, "status": status})
    return get_approval(conn, approval_id)


def archive_old(conn, older_than_hours: int = 72) -> int:
    cutoff = datetime.now().astimezone() - timedelta(hours=older_than_hours)
    rows = fetch_all(
        conn,
        "SELECT id, decided_at FROM papers WHERE delivery_status = 'DELIVERED' AND decided_at IS NOT NULL",
    )
    count = 0
    for row in rows:
        decided = parse_time(row["decided_at"])
        if decided and decided < cutoff:
            conn.execute(
                "UPDATE papers SET delivery_status = 'ARCHIVED', updated_at = ? WHERE id = ?",
                (now(), row["id"]),
            )
            count += 1
    return count


def pdf_path(conn, paper_id: str) -> Path | None:
    row = fetch_one(conn, "SELECT pdf_path FROM print_jobs WHERE paper_id = ? ORDER BY created_at DESC LIMIT 1", (paper_id,))
    if not row:
        return None
    return Path(row["pdf_path"])
