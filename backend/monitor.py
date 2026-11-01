"""Monitoring baca-saja per karyawan untuk Command Center (CCC-08)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import org, settings, tasks
from .db import fetch_one
from .sandbox import redact


class MonitorError(Exception):
    status_code = 404


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(settings.BASE_DIR))
    except (OSError, ValueError):
        return str(path)


def employee_monitor(conn, employee_id: str) -> dict[str, Any]:
    employee = org.get_employee(conn, employee_id)
    if not employee:
        raise MonitorError(f"Karyawan {employee_id} tidak ditemukan.")
    state = fetch_one(
        conn,
        "SELECT room, activity, source, updated_at FROM employee_states WHERE employee_id = ?",
        (employee_id,),
    ) or {}

    task_rows = tasks.list_tasks(conn, assignee=employee_id, limit=200)
    active_tasks = [
        task for task in task_rows
        if task["status"] not in ("COMPLETED", "FAILED")
    ]
    files: dict[str, dict[str, Any]] = {}
    terminal: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []

    for task in task_rows:
        evidence = task.get("evidence") or {}
        for relative in evidence.get("files") or []:
            if not isinstance(relative, str):
                continue
            project = fetch_one(
                conn,
                "SELECT workspace_path FROM projects WHERE id = ?",
                (task.get("project_id"),),
            ) if task.get("project_id") else None
            root = Path(project["workspace_path"]) if project and project.get("workspace_path") else settings.WORKSPACE_DIR
            path = root / relative
            files.setdefault(
                str(path),
                {
                    "task_id": task["id"],
                    "task": task["title"],
                    "path": _relative(path),
                    "exists": path.is_file(),
                },
            )
        terminal_output = evidence.get("terminal_output") or evidence.get("notes")
        if terminal_output:
            terminal.append(
                {
                    "task_id": task["id"],
                    "task": task["title"],
                    "output": redact(str(terminal_output))[:1200],
                    "at": task.get("updated_at"),
                }
            )
        for result in evidence.get("test_results") or []:
            if isinstance(result, dict):
                tests.append({"task_id": task["id"], "task": task["title"], **result})

    workspace_files: list[dict[str, Any]] = []
    project_ids = {
        task["project_id"] for task in task_rows if task.get("project_id")
    }
    for project_id in project_ids:
        project = fetch_one(
            conn,
            "SELECT workspace_path FROM projects WHERE id = ?",
            (project_id,),
        )
        if not project or not project.get("workspace_path"):
            continue
        root = Path(project["workspace_path"])
        if not root.is_dir():
            continue
        try:
            candidates = sorted(
                (path for path in root.rglob("*") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )[:5]
        except OSError:
            candidates = []
        for path in candidates:
            workspace_files.append(
                {
                    "project_id": project_id,
                    "path": _relative(path),
                    "modified_at": path.stat().st_mtime,
                }
            )

    return {
        "employee": employee,
        "state": state,
        "active_tasks": active_tasks,
        "last_files": list(files.values())[:8] + workspace_files[:5],
        "terminal_summary": terminal[:5],
        "test_results": tests[:10],
        "generated_at": state.get("updated_at"),
    }
