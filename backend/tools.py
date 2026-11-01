"""Allowlist tool dan penegakan izin per karyawan (CMD-01, CMD-02, CMD-07).

LLM hanya boleh mengusulkan nama tool dari registry ini. Setiap eksekusi
memeriksa izin karyawan di database, sehingga prompt atau keluaran model tidak
dapat memperluas wewenang.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import audit, emailer, events, knowledge, meetings, org, papers, settings, tasks, website
from .db import fetch_all, fetch_one, json_dump, now
from .sandbox import redact


class ToolError(Exception):
    status_code = 400


class PermissionDenied(ToolError):
    status_code = 403


class UnknownTool(ToolError):
    status_code = 400


Handler = Callable[[Any, str, dict[str, Any]], dict[str, Any]]


def _resolve(conn, args: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = args.get(key)
        if not value:
            continue
        if isinstance(value, dict):
            return value
        employee = org.get_employee(conn, str(value))
        if employee:
            return employee
        employee = org.resolve_recipient(conn, str(value))
        if employee:
            return employee
    return {}


def _create_task(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    assignee = _resolve(conn, args, "assignee", "recipient", "untuk")
    if not assignee:
        raise ToolError("Penerima task tidak dikenal.")
    task = tasks.create_task(
        conn,
        title=args.get("title") or args.get("judul") or "Task baru",
        description=args.get("description", ""),
        assignee=assignee["id"],
        project_id=args.get("project_id"),
        priority=args.get("priority", "normal"),
        kind=args.get("kind", "code"),
        depends_on=args.get("depends_on", []),
        acceptance_criteria=args.get("acceptance_criteria", []),
        due_at=args.get("due_at"),
        created_by=actor,
        actor_kind="manager" if actor != "owner" else "owner",
    )
    return {"task": task}


def _update_task(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    task_id = args.get("task_id")
    if not task_id:
        raise ToolError("task_id wajib diisi.")
    task = tasks.get_task(conn, task_id)
    if actor == "owner":
        actor_kind = "owner"
    elif actor == task.get("assignee"):
        actor_kind = "employee"
    elif org.is_manager(conn, actor):
        actor_kind = "manager"
    else:
        actor_kind = "employee"
    updated = tasks.transition(
        conn,
        task_id=task_id,
        to_status=args.get("to_status", ""),
        actor=actor,
        actor_kind=actor_kind,
        note=args.get("note", ""),
        evidence=args.get("evidence"),
    )
    return {"task": updated}


def _move_employee(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    employee = _resolve(conn, args, "employee_id", "employee", "nama", "recipient")
    if not employee:
        raise ToolError("Karyawan tidak dikenal.")
    room = str(args.get("room") or args.get("ruang") or "").strip()
    if not room:
        raise ToolError("Ruang tujuan wajib diisi.")
    state = org.set_employee_state(
        conn, employee["id"], room=room, activity=args.get("activity", "walking"), source="command", actor=actor
    )
    return {"employee": employee, "state": state}


def _create_meeting(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    raw_participants = args.get("participants") or args.get("peserta") or []
    if isinstance(raw_participants, str):
        raw_participants = [raw_participants]
    meeting = meetings.create_meeting(
        conn,
        title=str(args.get("title") or args.get("judul") or ""),
        agenda=str(args.get("agenda") or ""),
        participants=[str(item) for item in raw_participants],
        room=str(args.get("room") or "ruang_rapat"),
        scheduled_at=args.get("scheduled_at"),
        created_by=actor,
        actor_kind="owner" if actor == "owner" else "manager",
        run_now=bool(args.get("run_now")),
        rounds=args.get("rounds"),
    )
    return {"meeting": meeting}


def _run_meeting(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    meeting_id = str(args.get("meeting_id") or "").strip()
    if not meeting_id:
        raise ToolError("meeting_id wajib diisi.")
    return {"meeting": meetings.run_meeting(conn, meeting_id, actor=actor, rounds=args.get("rounds"))}


def _generate_report(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title") or args.get("judul") or "Laporan").strip()
    body = str(args.get("body") or args.get("isi") or "").strip()
    if not body:
        body = "Belum ada isi laporan."
    stamp = datetime.now().astimezone()
    filename = f"{title.lower().replace(' ', '-')[:40]}-{stamp:%Y%m%d-%H%M%S}.md"
    path = settings.REPORT_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    paper = papers.create_paper(
        conn,
        paper_type="task_report",
        creator=actor,
        payload={"title": title, "body": body, "file": str(path), "hash": papers.payload_hash({"title": title, "body": body})},
        summary=title,
        task_id=args.get("task_id"),
        priority=args.get("priority", "normal"),
    )
    if args.get("auto_deliver", True):
        papers.print_paper(conn, paper["id"], actor=actor)
        paper = papers.deliver_paper(conn, paper["id"], actor=actor)
    return {"paper": paper, "file": str(path)}


def _create_project(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name") or args.get("nama") or "").strip()
    if not name:
        raise ToolError("Nama proyek wajib diisi.")
    project_id = f"proj_{uuid.uuid4().hex[:10]}"
    workspace = settings.WORKSPACE_DIR / name.lower().replace(" ", "-")[:45]
    workspace.mkdir(parents=True, exist_ok=True)
    stamp = now()
    conn.execute(
        """
        INSERT INTO projects
            (id, name, department_id, workspace_path, status, deliverable, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'PLANNED', ?, ?, ?, ?)
        """,
        (
            project_id, name, args.get("department_id", "engineering"), str(workspace),
            args.get("deliverable", ""), actor, stamp, stamp,
        ),
    )
    audit.log(
        conn, actor=actor, actor_kind="manager", action="project.created",
        detail=json_dump({"name": name, "workspace": str(workspace)}),
        ref_type="project", ref_id=project_id,
    )
    events.publish(conn, "project.created", actor, {"project_id": project_id, "name": name})
    return {"project": dict(fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,)) or {})}


def _draft_email(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return emailer.create_draft(
            conn,
            to=str(args.get("to") or args.get("recipient") or ""),
            subject=str(args.get("subject") or args.get("subjek") or ""),
            body=str(args.get("body") or args.get("isi") or ""),
            attachments=[str(item) for item in (args.get("attachments") or [])],
            requester=actor,
            task_id=args.get("task_id"),
            auto_deliver=bool(args.get("auto_deliver", True)),
        )
    except emailer.EmailError as error:
        raise ToolError(str(error)) from error


def _propose_website(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return website.create_deployment(
            conn,
            diff=str(args.get("diff") or args.get("changes") or ""),
            summary=str(args.get("summary") or args.get("ringkasan") or "Perubahan website"),
            requester=actor,
            task_id=args.get("task_id"),
            auto_deliver=bool(args.get("auto_deliver", True)),
        )
    except website.WebsiteError as error:
        raise ToolError(str(error)) from error


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(settings.BASE_DIR))
    except ValueError:
        return str(path)


def _search_knowledge(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or args.get("q") or "").strip().lower()
    if not query:
        raise ToolError("Kata kunci pencarian wajib diisi.")
    roots = [settings.DOCS_DIR, settings.REPORT_DIR]
    results: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if knowledge.contains_secrets(text):
                continue
            if query in text.lower():
                index = text.lower().find(query)
                results.append({
                    "path": _display_path(path),
                    "snippet": redact(text[max(0, index - 80): index + 200]),
                })
            if len(results) >= 8:
                break
    return {"query": query, "results": results}


def _print_paper(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    paper_id = args.get("paper_id")
    if not paper_id:
        raise ToolError("paper_id wajib diisi.")
    return papers.print_paper(conn, paper_id, actor=actor)


def _deliver_paper(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    paper_id = args.get("paper_id")
    if not paper_id:
        raise ToolError("paper_id wajib diisi.")
    return {"paper": papers.deliver_paper(conn, paper_id, actor=actor)}


def _log_message(conn, actor: str, args: dict[str, Any]) -> dict[str, Any]:
    sender = args.get("sender", "tamu")
    content = str(args.get("content") or args.get("message") or "").strip()
    if not content:
        raise ToolError("Isi pesan wajib diisi.")
    interaction_id = f"int_{uuid.uuid4().hex[:10]}"
    conn.execute(
        "INSERT INTO interactions (id, sender, recipient, content, room, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (interaction_id, sender, actor, content, args.get("room", "front_office"), now()),
    )
    audit.log(
        conn, actor=actor, actor_kind="employee", action="message.logged",
        detail=json_dump({"from": sender}), ref_type="interaction", ref_id=interaction_id,
    )
    return {"interaction_id": interaction_id}


REGISTRY: dict[str, dict[str, Any]] = {
    "create_task": {"handler": _create_task, "risk": "internal"},
    "update_task": {"handler": _update_task, "risk": "internal"},
    "move_employee": {"handler": _move_employee, "risk": "internal"},
    "create_meeting": {"handler": _create_meeting, "risk": "internal"},
    "run_meeting": {"handler": _run_meeting, "risk": "internal"},
    "generate_report": {"handler": _generate_report, "risk": "internal"},
    "create_project": {"handler": _create_project, "risk": "internal"},
    "draft_email": {"handler": _draft_email, "risk": "external"},
    "propose_website_publish": {"handler": _propose_website, "risk": "external"},
    "search_knowledge": {"handler": _search_knowledge, "risk": "internal"},
    "print_paper": {"handler": _print_paper, "risk": "internal"},
    "deliver_paper": {"handler": _deliver_paper, "risk": "internal"},
    "log_message": {"handler": _log_message, "risk": "internal"},
}

TOOL_NAMES = tuple(REGISTRY.keys())


def _permissions(employee: dict[str, Any]) -> set[str]:
    return set(employee.get("tool_permissions") or [])


def is_allowed(conn, actor: str, tool_name: str) -> bool:
    if actor == "owner":
        return True
    employee = org.get_employee(conn, actor)
    if not employee or not employee.get("active"):
        return False
    permissions = _permissions(employee)
    return "*" in permissions or tool_name in permissions


def execute(conn, *, actor: str, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {}
    if tool_name not in REGISTRY:
        raise UnknownTool(f"Tool tidak ada di allowlist: {tool_name}")
    if not is_allowed(conn, actor, tool_name):
        audit.log(
            conn, actor=actor, actor_kind="employee", action="tool.denied",
            detail=json_dump({"tool": tool_name}), ref_type="tool", ref_id=tool_name,
        )
        error = PermissionDenied(f"{actor} tidak memiliki izin untuk {tool_name}.")
        error.actor = actor  # type: ignore[attr-defined]
        error.tool_name = tool_name  # type: ignore[attr-defined]
        raise error
    employee = org.get_employee(conn, actor)
    if actor == "owner":
        actor_kind = "owner"
    elif employee and org.is_manager(conn, actor):
        actor_kind = "manager"
    else:
        actor_kind = "employee"
    started = now()
    try:
        result = REGISTRY[tool_name]["handler"](conn, actor, args)
    except Exception as error:
        audit.log(
            conn, actor=actor, actor_kind=actor_kind, action="tool.failed",
            detail=json_dump({"tool": tool_name, "error": redact(str(error))}),
            ref_type="tool", ref_id=tool_name,
        )
        raise
    audit.log(
        conn, actor=actor, actor_kind=actor_kind, action="tool.executed",
        detail=json_dump({"tool": tool_name, "args": sorted(args), "at": started}),
        ref_type="tool", ref_id=tool_name,
    )
    return result
