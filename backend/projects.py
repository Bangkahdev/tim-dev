"""Proyek paralel, antrean, dan arsip akhir (PRJ-03, PRJ-05, PRJ-07).

Batas proyek aktif dibaca dari ``MAX_CONCURRENT_PROJECTS``. Proyek yang
menunggu berada di status QUEUED dan otomatis naik ke ACTIVE saat slot kosong.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from . import audit, events, papers, reports, settings, tasks
from .db import fetch_all, fetch_one, json_dump, now

STATUSES = ("PLANNED", "QUEUED", "ACTIVE", "PAUSED", "COMPLETED", "FAILED", "ARCHIVED")
CLOSED_STATUSES = {"COMPLETED", "FAILED", "ARCHIVED"}
PRIORITIES = ("low", "normal", "high", "urgent")
_PRIORITY_ORDER = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


class ProjectError(Exception):
    status_code = 400


def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return row


def get_project(conn, project_id: str) -> dict[str, Any]:
    row = _decode(fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,)))
    if not row:
        raise ProjectError(f"Proyek tidak dikenal: {project_id}")
    return row


def list_projects(
    conn,
    *,
    status: str | None = None,
    department_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status.upper())
    if department_id:
        clauses.append("department_id = ?")
        params.append(department_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 500)))
    rows = fetch_all(conn, f"SELECT * FROM projects {where} ORDER BY created_at DESC LIMIT ?", tuple(params))
    for row in rows:
        counts = fetch_one(
            conn,
            "SELECT COUNT(*) AS total, SUM(status = 'COMPLETED') AS done FROM tasks WHERE project_id = ?",
            (row["id"],),
        )
        row["task_total"] = int(counts["total"] or 0) if counts else 0
        row["task_done"] = int(counts["done"] or 0) if counts else 0
    return rows


def active_count(conn) -> int:
    row = fetch_one(conn, "SELECT COUNT(*) AS total FROM projects WHERE status = 'ACTIVE'")
    return int(row["total"]) if row else 0


def _workspace_for(name: str, project_id: str) -> Path:
    slug = "-".join(name.lower().split())[:45] or "proyek"
    target = settings.WORKSPACE_DIR / slug
    if target.exists():
        target = settings.WORKSPACE_DIR / f"{slug}-{project_id[-6:]}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def create_project(
    conn,
    *,
    name: str,
    department_id: str = "engineering",
    deliverable: str = "",
    actor: str = "owner",
    actor_kind: str = "manager",
    workspace_path: str | None = None,
    priority: str = "normal",
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ProjectError("Nama proyek wajib diisi.")
    priority = (priority or "normal").lower()
    if priority not in PRIORITIES:
        raise ProjectError(f"Prioritas tidak sah: {priority}")
    if not fetch_one(conn, "SELECT id FROM departments WHERE id = ?", (department_id,)):
        raise ProjectError(f"Departemen tidak dikenal: {department_id}")
    project_id = f"proj_{uuid.uuid4().hex[:10]}"
    workspace = Path(workspace_path) if workspace_path else _workspace_for(name, project_id)
    workspace.mkdir(parents=True, exist_ok=True)
    stamp = now()
    conn.execute(
        """
        INSERT INTO projects
            (id, name, department_id, workspace_path, status, deliverable,
             created_by, created_at, updated_at, priority)
        VALUES (?, ?, ?, ?, 'PLANNED', ?, ?, ?, ?, ?)
        """,
        (project_id, name, department_id, str(workspace), deliverable, actor, stamp, stamp, priority),
    )
    audit.log(
        conn, actor=actor, actor_kind=actor_kind, action="project.created",
        detail=json_dump({"name": name, "workspace": str(workspace), "priority": priority}),
        ref_type="project", ref_id=project_id,
    )
    events.publish(conn, "project.created", actor, {"project_id": project_id, "name": name})
    return get_project(conn, project_id)


def _update(conn, project_id: str, changes: dict[str, Any]) -> None:
    if not changes:
        return
    columns = ", ".join(f"{key} = ?" for key in changes)
    params = list(changes.values()) + [now(), project_id]
    conn.execute(f"UPDATE projects SET {columns}, updated_at = ? WHERE id = ?", tuple(params))


def enqueue(conn, project_id: str, *, actor: str = "owner") -> dict[str, Any]:
    project = get_project(conn, project_id)
    if project["status"] in CLOSED_STATUSES:
        raise ProjectError("Proyek yang sudah selesai tidak dapat diantrekan.")
    if project["status"] == "ACTIVE":
        return project
    _update(conn, project_id, {"status": "QUEUED", "queued_at": now()})
    audit.log(
        conn, actor=actor, actor_kind="owner" if actor == "owner" else "manager",
        action="project.queued", detail=json_dump({"name": project["name"]}),
        ref_type="project", ref_id=project_id,
    )
    events.publish(conn, "project.queued", actor, {"project_id": project_id})
    promote_queued(conn, actor=actor)
    return get_project(conn, project_id)


def promote_queued(conn, *, actor: str = "system") -> list[str]:
    limit = max(1, settings.MAX_CONCURRENT_PROJECTS)
    active = active_count(conn)
    if active >= limit:
        return []
    queued = fetch_all(
        conn,
        """
        SELECT * FROM projects WHERE status = 'QUEUED'
        ORDER BY CASE priority
            WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
            COALESCE(queued_at, created_at) ASC
        """,
    )
    started: list[str] = []
    for project in queued:
        if active >= limit:
            break
        _update(conn, project["id"], {"status": "ACTIVE", "started_at": now()})
        active += 1
        started.append(project["id"])
        audit.log(
            conn, actor=actor, actor_kind="backend", action="project.started",
            detail=json_dump({"name": project["name"], "slot": active, "limit": limit}),
            ref_type="project", ref_id=project["id"],
        )
        events.publish(conn, "project.started", actor, {"project_id": project["id"]})
    return started


def request_start(conn, project_id: str, *, requester: str = "owner") -> dict[str, Any]:
    """Mulai pipeline coding memerlukan persetujuan Owner (matriks izin)."""
    project = get_project(conn, project_id)
    if project["status"] in CLOSED_STATUSES:
        raise ProjectError("Proyek yang sudah selesai tidak dapat dimulai.")
    if project["status"] == "ACTIVE":
        raise ProjectError("Proyek ini sudah berjalan.")
    payload = {
        "project_id": project_id,
        "name": project["name"],
        "deliverable": project.get("deliverable", ""),
        "workspace_path": project.get("workspace_path", ""),
    }
    bundle = papers.create_approval_bundle(
        conn,
        approval_type="project_start",
        payload=payload,
        requester=requester,
        summary=f"Mulai proyek: {project['name']}",
        priority="high",
    )
    papers.print_paper(conn, bundle["paper"]["id"], actor=requester)
    paper = papers.deliver_paper(conn, bundle["paper"]["id"], actor=requester)
    return {"approval": bundle["approval"], "paper": paper}


def _incomplete_tasks(conn, project_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        conn,
        "SELECT id, title, status FROM tasks WHERE project_id = ? AND status NOT IN ('COMPLETED', 'FAILED')",
        (project_id,),
    )


def _digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "MANIFEST.sha256":
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def archive_project(conn, project: dict[str, Any], *, actor: str = "owner") -> dict[str, Any]:
    """Simpan cuplikan akhir proyek yang tidak boleh ditimpa (PRJ-07)."""
    stamp = datetime.now().astimezone()
    snapshot_id = f"{project['id']}-{stamp:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    root = settings.ARCHIVE_DIR / snapshot_id
    root.mkdir(parents=True, exist_ok=False)
    source = Path(project.get("workspace_path") or "")
    if source.is_dir():
        shutil.copytree(source, root / "workspace")
    task_rows = fetch_all(conn, "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at", (project["id"],))
    manifest = {
        "snapshot_id": snapshot_id,
        "project": project,
        "tasks": task_rows,
        "archived_at": now(),
        "archived_by": actor,
    }
    (root / "project.json").write_text(json_dump(manifest), encoding="utf-8")
    (root / "report.md").write_text(reports.project_markdown(conn, project["id"]), encoding="utf-8")
    (root / "evidence.json").write_text(
        json_dump([{"task_id": row["id"], "status": row["status"], "evidence": row.get("evidence")} for row in task_rows]),
        encoding="utf-8",
    )
    digest = _digest_tree(root)
    (root / "MANIFEST.sha256").write_text(digest + "\n", encoding="utf-8")
    audit.log(
        conn, actor=actor, actor_kind="owner" if actor == "owner" else "manager",
        action="project.archived",
        detail=json_dump({"snapshot": snapshot_id, "hash": digest}),
        ref_type="project", ref_id=project["id"],
    )
    return {"snapshot_id": snapshot_id, "path": str(root), "hash": digest}


def _promotion_task(conn, project: dict[str, Any], *, actor: str, archive: dict[str, Any]) -> dict[str, Any] | None:
    manager = fetch_one(
        conn,
        "SELECT id FROM employees WHERE department_id = 'promotion' AND active = 1 "
        "ORDER BY CASE WHEN id = 'promo_manager' THEN 0 ELSE 1 END LIMIT 1",
    )
    if not manager:
        return None
    return tasks.create_task(
        conn,
        title=f"Promosikan proyek: {project['name']}",
        description=(
            f"Proyek {project['name']} telah selesai. Susun rencana promosi, materi kampanye, "
            f"dan jadwal publikasi. Arsip akhir: {archive['path']}"
        ),
        assignee=manager["id"],
        project_id=project["id"],
        priority="normal",
        kind="non_code",
        acceptance_criteria=[
            "Rencana promosi dan kalender konten disusun",
            "Draf materi promosi diajukan sebagai Paper untuk persetujuan Owner",
        ],
        created_by=actor,
        actor_kind="manager" if actor != "owner" else "owner",
    )


def complete_project(
    conn,
    project_id: str,
    *,
    actor: str = "owner",
    note: str = "",
    force: bool = False,
) -> dict[str, Any]:
    project = get_project(conn, project_id)
    if project["status"] in ("COMPLETED", "ARCHIVED"):
        raise ProjectError("Proyek ini sudah selesai dan diarsipkan.")
    pending = _incomplete_tasks(conn, project_id)
    if pending and not force:
        titles = ", ".join(row["title"] for row in pending[:3])
        raise ProjectError(f"Masih ada {len(pending)} task belum selesai: {titles}")
    archive = archive_project(conn, project, actor=actor)
    _update(
        conn, project_id,
        {
            "status": "COMPLETED",
            "completed_at": now(),
            "archive_path": archive["path"],
            "archive_hash": archive["hash"],
        },
    )
    promotion = _promotion_task(conn, project, actor=actor, archive=archive)
    paper = papers.create_paper(
        conn,
        paper_type="project_report",
        creator=actor,
        payload={
            "project_id": project_id,
            "title": f"Laporan akhir proyek: {project['name']}",
            "body": reports.project_markdown(conn, project_id),
            "archive": archive,
            "note": note,
        },
        summary=f"Laporan akhir proyek {project['name']}",
        task_id=None,
        priority="normal",
    )
    papers.print_paper(conn, paper["id"], actor=actor)
    paper = papers.deliver_paper(conn, paper["id"], actor=actor)
    audit.log(
        conn, actor=actor, actor_kind="owner" if actor == "owner" else "manager",
        action="project.completed",
        detail=json_dump({"name": project["name"], "note": note, "archive": archive["snapshot_id"]}),
        ref_type="project", ref_id=project_id,
    )
    events.publish(conn, "project.completed", actor, {"project_id": project_id, "name": project["name"]})
    promote_queued(conn, actor=actor)
    return {
        "project": get_project(conn, project_id),
        "archive": archive,
        "promotion_task": promotion,
        "paper": paper,
    }


def fail_project(conn, project_id: str, *, actor: str = "owner", reason: str = "") -> dict[str, Any]:
    project = get_project(conn, project_id)
    if project["status"] in CLOSED_STATUSES:
        raise ProjectError("Proyek ini sudah ditutup.")
    _update(conn, project_id, {"status": "FAILED", "failed_reason": reason})
    audit.log(
        conn, actor=actor, actor_kind="owner" if actor == "owner" else "manager",
        action="project.failed", detail=json_dump({"name": project["name"], "reason": reason}),
        ref_type="project", ref_id=project_id,
    )
    events.publish(conn, "project.failed", actor, {"project_id": project_id, "reason": reason})
    promote_queued(conn, actor=actor)
    return {"project": get_project(conn, project_id)}
