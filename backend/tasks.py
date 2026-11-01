"""Task nyata dan matriks transisinya (PRJ-04, PRJ-09 s.d. PRJ-13).

Aturan inti:
- Status hanya berubah lewat matriks di bagian 4.6.1.
- COMPLETED hanya dapat ditetapkan backend setelah bukti tervalidasi.
- Setiap transisi dicatat di task_transitions dan audit_log.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from . import audit, events, settings
from .db import fetch_all, fetch_one, json_dump, json_load, now, parse_time

STATUSES = ("PENDING", "IN_PROGRESS", "REVIEW", "QA", "COMPLETED", "BLOCKED", "FAILED")
PRIORITIES = ("low", "normal", "high", "urgent")
KINDS = ("code", "non_code")

# from -> to -> aktor yang sah
MATRIX: dict[str, dict[str, set[str]]] = {
    "PENDING": {
        "IN_PROGRESS": {"backend", "owner", "manager", "secretary"},
    },
    "IN_PROGRESS": {
        "REVIEW": {"employee"},
        "BLOCKED": {"employee", "backend"},
        "FAILED": {"backend"},
    },
    "REVIEW": {
        "IN_PROGRESS": {"manager"},
        "QA": {"manager"},
        "BLOCKED": {"employee", "backend"},
    },
    "QA": {
        "COMPLETED": {"backend"},
        "IN_PROGRESS": {"backend"},
        "BLOCKED": {"employee", "backend"},
        "FAILED": {"backend"},
    },
    "BLOCKED": {
        "IN_PROGRESS": {"manager", "backend", "owner"},
    },
    "FAILED": {
        "IN_PROGRESS": {"manager", "owner"},
    },
    "COMPLETED": {},
}


class TaskError(Exception):
    status_code = 400


class TaskNotFound(TaskError):
    status_code = 404


class TaskTransitionDenied(TaskError):
    status_code = 409


def _task_row(conn, task_id: str) -> dict[str, Any]:
    row = fetch_one(conn, "SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not row:
        raise TaskNotFound(f"Task {task_id} tidak ditemukan.")
    return _decode(row)


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    row["depends_on"] = json_load(row.get("depends_on"), [])
    row["acceptance_criteria"] = json_load(row.get("acceptance_criteria"), [])
    row["evidence"] = json_load(row.get("evidence"), {})
    return row


def _encode(task: dict[str, Any]) -> dict[str, Any]:
    task = dict(task)
    for key in ("depends_on", "acceptance_criteria", "evidence"):
        if not isinstance(task.get(key), str):
            task[key] = json_dump(task.get(key, [] if key != "evidence" else {}))
    return task


def get_task(conn, task_id: str) -> dict[str, Any]:
    return _task_row(conn, task_id)


def list_tasks(
    conn,
    *,
    status: str | None = None,
    assignee: str | None = None,
    project_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status.upper())
    if assignee:
        clauses.append("assignee = ?")
        params.append(assignee)
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 500)))
    rows = fetch_all(
        conn,
        f"SELECT * FROM tasks {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params),
    )
    return [_decode(row) for row in rows]


def overdue_tasks(conn) -> list[dict[str, Any]]:
    rows = fetch_all(
        conn,
        "SELECT * FROM tasks WHERE status NOT IN ('COMPLETED', 'FAILED') AND due_at IS NOT NULL AND due_at < ?",
        (now(),),
    )
    return [_decode(row) for row in rows]


def create_task(
    conn,
    *,
    title: str,
    assignee: str | None = None,
    description: str = "",
    project_id: str | None = None,
    priority: str = "normal",
    kind: str = "code",
    depends_on: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    due_at: str | None = None,
    created_by: str = "system",
    actor_kind: str = "backend",
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise TaskError("Judul task wajib diisi.")
    if assignee:
        employee = fetch_one(conn, "SELECT id, active FROM employees WHERE id = ?", (assignee,))
        if not employee or not employee["active"]:
            raise TaskError(f"Penerima task tidak dikenal: {assignee}")
    if project_id and not fetch_one(conn, "SELECT id FROM projects WHERE id = ?", (project_id,)):
        raise TaskError(f"Proyek tidak dikenal: {project_id}")
    priority = (priority or "normal").lower()
    if priority not in PRIORITIES:
        raise TaskError(f"Prioritas tidak sah: {priority}")
    kind = (kind or "code").lower()
    if kind not in KINDS:
        raise TaskError(f"Jenis task tidak sah: {kind}")
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    stamp = now()
    conn.execute(
        """
        INSERT INTO tasks
            (id, project_id, title, description, assignee, priority, status,
             depends_on, acceptance_criteria, evidence, attempts, kind,
             blocked_reason, due_at, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, '{}', 0, ?, NULL, ?, ?, ?, ?)
        """,
        (
            task_id, project_id, title, description, assignee, priority,
            json_dump(depends_on or []),
            json_dump(acceptance_criteria or []),
            kind, due_at, created_by, stamp, stamp,
        ),
    )
    audit.log(
        conn,
        actor=created_by,
        actor_kind=actor_kind,
        action="task.created",
        detail=json_dump({"title": title, "assignee": assignee, "priority": priority}),
        ref_type="task",
        ref_id=task_id,
    )
    events.publish(
        conn,
        "task.created",
        created_by,
        {"task_id": task_id, "assignee": assignee, "status": "PENDING"},
    )
    return get_task(conn, task_id)


def _dependencies_done(conn, task: dict[str, Any]) -> bool:
    for dependency_id in task["depends_on"]:
        dependency = fetch_one(conn, "SELECT status FROM tasks WHERE id = ?", (dependency_id,))
        if not dependency or dependency["status"] != "COMPLETED":
            return False
    return True


def _is_manager_of(conn, task: dict[str, Any], actor: str) -> bool:
    if actor == "lead":
        return True
    if not task.get("assignee"):
        return False
    row = fetch_one(
        conn,
        """
        SELECT d.manager_id
        FROM employees e JOIN departments d ON d.id = e.department_id
        WHERE e.id = ?
        """,
        (task["assignee"],),
    )
    return bool(row and row["manager_id"] == actor)


def _actor_allowed(
    conn,
    task: dict[str, Any],
    to_status: str,
    actor: str,
    actor_kind: str,
) -> bool:
    allowed = MATRIX.get(task["status"], {}).get(to_status, set())
    if actor_kind not in allowed:
        return False
    if actor_kind == "employee":
        return actor == task.get("assignee")
    if actor_kind == "manager":
        return _is_manager_of(conn, task, actor)
    if actor_kind in ("owner", "backend", "secretary"):
        return True
    return False


def _safe_project_file(root: Path, relative: str) -> bool:
    try:
        target = (root / relative).resolve()
        root = root.resolve()
    except (OSError, ValueError):
        return False
    return target == root or root in target.parents


def validate_completion_evidence(conn, task: dict[str, Any], evidence: dict[str, Any]) -> tuple[bool, str]:
    """PRJ-11: kode butuh file nyata + tes exit 0 atau commit terverifikasi."""
    files = evidence.get("files") or []
    if not isinstance(files, list) or not files:
        return False, "Bukti file belum dilampirkan."
    project = None
    if task.get("project_id"):
        project = fetch_one(conn, "SELECT workspace_path FROM projects WHERE id = ?", (task["project_id"],))
    root = Path(project["workspace_path"]) if project and project.get("workspace_path") else settings.WORKSPACE_DIR
    root.mkdir(parents=True, exist_ok=True)
    existing = []
    for relative in files:
        if not isinstance(relative, str) or not _safe_project_file(root, relative):
            return False, f"Path bukti tidak sah: {relative!r}."
        if (root / relative).is_file():
            existing.append(relative)
    if not existing:
        return False, "File bukti tidak ditemukan di workspace proyek."

    if task["kind"] == "code":
        tests = evidence.get("test_results") or []
        passed = any(
            isinstance(item, dict) and int(item.get("exit_code", 1)) == 0
            for item in tests
        )
        commit = evidence.get("commit")
        verified_commit = bool(commit and evidence.get("commit_verified"))
        if not (passed or verified_commit):
            return False, "Tes belum lulus (exit code 0) dan commit belum terverifikasi."
        return True, f"{len(existing)} file bukti, tes/commit tervalidasi."

    reviewed_by = evidence.get("reviewed_by")
    reviewer_kind = evidence.get("reviewer_kind")
    if reviewed_by and reviewer_kind in ("manager", "owner"):
        return True, "File bukti ada dan telah ditinjau manajer/owner."
    return False, "Task non-kode butuh peninjauan Manajer atau Owner."


def _initial_evidence(evidence: dict[str, Any]) -> bool:
    return any(bool(evidence.get(key)) for key in ("files", "test_results", "commit", "notes", "artifacts"))


def transition(
    conn,
    *,
    task_id: str,
    to_status: str,
    actor: str,
    actor_kind: str,
    note: str = "",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task = _task_row(conn, task_id)
    to_status = (to_status or "").upper()
    from_status = task["status"]
    if to_status not in STATUSES:
        raise TaskError(f"Status tidak sah: {to_status}")
    if to_status == from_status:
        raise TaskTransitionDenied("Task sudah berada pada status itu.")
    if to_status not in MATRIX.get(from_status, {}):
        raise TaskTransitionDenied(f"Transisi {from_status} -> {to_status} tidak diizinkan.")
    if not _actor_allowed(conn, task, to_status, actor, actor_kind):
        raise TaskTransitionDenied(
            f"{actor} ({actor_kind}) tidak berwenang memindahkan task ke {to_status}."
        )

    merged_evidence = dict(task["evidence"])
    if evidence:
        merged_evidence.update(evidence)

    if from_status == "PENDING" and to_status == "IN_PROGRESS":
        if not task.get("assignee"):
            raise TaskTransitionDenied("Penerima task belum ditetapkan.")
        if not _dependencies_done(conn, task):
            raise TaskTransitionDenied("Dependensi task belum selesai.")

    if from_status == "IN_PROGRESS" and to_status == "REVIEW":
        if not _initial_evidence(merged_evidence):
            raise TaskTransitionDenied("Bukti awal wajib dilampirkan sebelum REVIEW.")

    if from_status == "REVIEW" and to_status == "IN_PROGRESS":
        if not note.strip():
            raise TaskTransitionDenied("Catatan revisi wajib diisi.")

    if from_status == "REVIEW" and to_status == "QA":
        passed = (merged_evidence.get("review") or {}).get("passed")
        if not (passed or note.strip()):
            raise TaskTransitionDenied("Tinjauan manajer belum dinyatakan lulus.")

    if to_status == "BLOCKED":
        if not (note.strip() or merged_evidence.get("blocked_reason")):
            raise TaskTransitionDenied("Alasan dan penghalang wajib dicatat.")

    if from_status == "FAILED" and to_status == "IN_PROGRESS":
        if not note.strip():
            raise TaskTransitionDenied("Percobaan ulang wajib disertai catatan.")

    if to_status == "FAILED" and from_status in ("IN_PROGRESS", "QA"):
        if task["attempts"] < settings.MAX_REPAIR_ROUNDS:
            raise TaskTransitionDenied(
                "Batas MAX_REPAIR_ROUNDS belum tercapai; gunakan REVIEW/QA atau BLOCKED."
            )

    if to_status == "COMPLETED":
        ok, reason = validate_completion_evidence(conn, task, merged_evidence)
        if not ok:
            raise TaskTransitionDenied(f"Bukti belum tervalidasi: {reason}")

    attempts = task["attempts"]
    if from_status == "QA" and to_status == "IN_PROGRESS":
        attempts += 1
    if from_status == "FAILED" and to_status == "IN_PROGRESS":
        attempts = 0

    blocked_reason = task.get("blocked_reason")
    if to_status == "BLOCKED":
        blocked_reason = note.strip() or str(merged_evidence.get("blocked_reason", "")).strip()
    elif to_status == "IN_PROGRESS":
        blocked_reason = None

    stamp = now()
    conn.execute(
        """
        UPDATE tasks
        SET status = ?, evidence = ?, attempts = ?, blocked_reason = ?, updated_at = ?
        WHERE id = ?
        """,
        (to_status, json_dump(merged_evidence), attempts, blocked_reason, stamp, task_id),
    )
    conn.execute(
        """
        INSERT INTO task_transitions
            (task_id, from_status, to_status, actor, actor_kind, note, at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (task_id, from_status, to_status, actor, actor_kind, note.strip(), stamp),
    )
    audit.log(
        conn,
        actor=actor,
        actor_kind=actor_kind,
        action="task.transition",
        detail=json_dump(
            {
                "from": from_status,
                "to": to_status,
                "note": note.strip(),
                "attempts": attempts,
            }
        ),
        ref_type="task",
        ref_id=task_id,
    )
    events.publish(
        conn,
        "task.transitioned",
        actor,
        {"task_id": task_id, "from": from_status, "to": to_status},
    )
    return get_task(conn, task_id)


def update_evidence(conn, task_id: str, evidence: dict[str, Any], actor: str, actor_kind: str) -> dict[str, Any]:
    task = _task_row(conn, task_id)
    if actor_kind == "employee" and actor != task.get("assignee"):
        raise TaskTransitionDenied("Hanya penerima task yang dapat memperbarui bukti.")
    merged = dict(task["evidence"])
    merged.update(evidence)
    conn.execute(
        "UPDATE tasks SET evidence = ?, updated_at = ? WHERE id = ?",
        (json_dump(merged), now(), task_id),
    )
    audit.log(
        conn,
        actor=actor,
        actor_kind=actor_kind,
        action="task.evidence_updated",
        detail=json_dump({"keys": sorted(evidence)}),
        ref_type="task",
        ref_id=task_id,
    )
    return get_task(conn, task_id)


def escalation_candidates(conn, hours: int = 24) -> list[dict[str, Any]]:
    """Task FAILED yang tidak ditangani manajer dalam N jam (PRJ-12)."""
    cutoff = datetime.now().astimezone().timestamp() - hours * 3600
    rows = list_tasks(conn, status="FAILED", limit=500)
    return [row for row in rows if (parse_time(row["updated_at"]) or datetime.now().astimezone()).timestamp() < cutoff]
