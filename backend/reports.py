"""Laporan per divisi/proyek, ekspor PDF, dan dashboard biaya (RPT-03, RPT-04, CCC-04..06)."""

from __future__ import annotations

import json
from typing import Any

from . import audit, papers, settings, tasks
from .db import fetch_all, fetch_one, json_dump, now


def _evidence_summary(raw: Any) -> str:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return raw[:160]
    if not isinstance(raw, dict) or not raw:
        return "-"
    for key in ("summary", "ringkasan", "note", "notes", "test_output"):
        value = raw.get(key)
        if value:
            return str(value)[:160]
    return json_dump(raw)[:160]


def project_metrics(conn, project_id: str) -> dict[str, Any]:
    project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        raise ValueError(f"Proyek tidak dikenal: {project_id}")
    rows = fetch_all(conn, "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at", (project_id,))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    usage = fetch_one(
        conn,
        """
        SELECT COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
               COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
               COALESCE(SUM(total_tokens), 0) AS total_tokens,
               COALESCE(SUM(estimated_cost), 0) AS estimated_cost,
               COUNT(*) AS calls
        FROM usage_records WHERE project_id = ?
        """,
        (project_id,),
    )
    return {"project": project, "tasks": rows, "task_counts": counts, "usage": usage or {}}


def project_markdown(conn, project_id: str) -> str:
    data = project_metrics(conn, project_id)
    project = data["project"]
    lines = [
        f"# Laporan Proyek: {project['name']}",
        "",
        f"- Status: {project['status']}",
        f"- Departemen: {project.get('department_id') or '-'}",
        f"- Penanggung jawab: {project.get('created_by') or '-'}",
        f"- Workspace: {project.get('workspace_path') or '-'}",
        f"- Dibuat: {project.get('created_at') or '-'}",
    ]
    if project.get("completed_at"):
        lines.append(f"- Selesai: {project['completed_at']}")
    if project.get("archive_path"):
        lines.append(f"- Arsip: {project['archive_path']}")
    lines.extend(["", "## Deliverable", "", project.get("deliverable") or "Belum ditetapkan.", ""])
    lines.extend(["## Ringkasan Task", "", "| Status | Jumlah |", "| --- | --- |"])
    for status in tasks.STATUSES:
        lines.append(f"| {status} | {data['task_counts'].get(status, 0)} |")
    lines.extend(["", "## Task", "", "| Judul | Penanggung jawab | Status | Bukti |", "| --- | --- | --- | --- |"])
    for row in data["tasks"]:
        lines.append(
            f"| {row['title']} | {row.get('assignee') or '-'} | {row['status']} | {_evidence_summary(row.get('evidence'))} |"
        )
    usage = data["usage"]
    lines.extend(
        [
            "",
            "## Penggunaan Token",
            "",
            f"- Total token: {usage.get('total_tokens', 0)}",
            f"- Estimasi biaya: {usage.get('estimated_cost', 0)}",
            f"- Jumlah panggilan: {usage.get('calls', 0)}",
            "",
        ]
    )
    return "\n".join(lines)


def division_metrics(conn, department_id: str) -> dict[str, Any]:
    department = fetch_one(conn, "SELECT * FROM departments WHERE id = ?", (department_id,))
    if not department:
        raise ValueError(f"Departemen tidak dikenal: {department_id}")
    employees = fetch_all(
        conn, "SELECT * FROM employees WHERE department_id = ? ORDER BY created_at", (department_id,)
    )
    employee_ids = [row["id"] for row in employees]
    placeholders = ",".join("?" for _ in employee_ids) or "''"
    task_rows = (
        fetch_all(
            conn,
            f"SELECT * FROM tasks WHERE assignee IN ({placeholders}) ORDER BY created_at",
            tuple(employee_ids),
        )
        if employee_ids
        else []
    )
    counts: dict[str, int] = {}
    for row in task_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    projects = fetch_all(conn, "SELECT * FROM projects WHERE department_id = ?", (department_id,))
    usage = (
        fetch_one(
            conn,
            f"""
            SELECT COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COALESCE(SUM(estimated_cost), 0) AS estimated_cost, COUNT(*) AS calls
            FROM usage_records WHERE employee_id IN ({placeholders})
            """,
            tuple(employee_ids),
        )
        if employee_ids
        else {"total_tokens": 0, "estimated_cost": 0, "calls": 0}
    )
    return {
        "department": department,
        "employees": employees,
        "tasks": task_rows,
        "task_counts": counts,
        "projects": projects,
        "usage": usage or {},
    }


def division_markdown(conn, department_id: str) -> str:
    data = division_metrics(conn, department_id)
    department = data["department"]
    lines = [
        f"# Laporan Divisi: {department['name']}",
        "",
        f"- Manajer: {department.get('manager_id') or '-'}",
        f"- Ruang: {department.get('room') or '-'}",
        f"- Karyawan aktif: {sum(1 for row in data['employees'] if row.get('active'))}",
        "",
        "## Karyawan",
        "",
        "| Nama | Jabatan | Status | Model |",
        "| --- | --- | --- | --- |",
    ]
    for row in data["employees"]:
        lines.append(f"| {row['name']} | {row['title']} | {row.get('status') or '-'} | {row.get('model') or '-'} |")
    lines.extend(["", "## Ringkasan Task", "", "| Status | Jumlah |", "| --- | --- |"])
    for status in tasks.STATUSES:
        lines.append(f"| {status} | {data['task_counts'].get(status, 0)} |")
    lines.extend(["", "## Proyek", "", "| Nama | Status | Task selesai |", "| --- | --- | --- |"])
    for project in data["projects"]:
        counts = fetch_one(
            conn,
            "SELECT COUNT(*) AS total, SUM(status = 'COMPLETED') AS done FROM tasks WHERE project_id = ?",
            (project["id"],),
        )
        total = int(counts["total"] or 0) if counts else 0
        done = int(counts["done"] or 0) if counts else 0
        lines.append(f"| {project['name']} | {project['status']} | {done}/{total} |")
    usage = data["usage"]
    lines.extend(
        [
            "",
            "## Penggunaan Token",
            "",
            f"- Total token: {usage.get('total_tokens', 0)}",
            f"- Estimasi biaya: {usage.get('estimated_cost', 0)}",
            f"- Jumlah panggilan: {usage.get('calls', 0)}",
            "",
        ]
    )
    return "\n".join(lines)


def division_performance(conn) -> list[dict[str, Any]]:
    return fetch_all(
        conn,
        """
        SELECT d.id, d.name, d.manager_id,
               (SELECT COUNT(*) FROM employees e WHERE e.department_id = d.id AND e.active = 1) AS employees,
               (SELECT COUNT(*) FROM tasks t JOIN employees e ON e.id = t.assignee
                 WHERE e.department_id = d.id) AS tasks_total,
               (SELECT COUNT(*) FROM tasks t JOIN employees e ON e.id = t.assignee
                 WHERE e.department_id = d.id AND t.status = 'COMPLETED') AS tasks_done,
               (SELECT COUNT(*) FROM tasks t JOIN employees e ON e.id = t.assignee
                 WHERE e.department_id = d.id AND t.status NOT IN ('COMPLETED', 'FAILED')) AS tasks_open,
               (SELECT COUNT(*) FROM projects p WHERE p.department_id = d.id) AS projects_total,
               (SELECT COUNT(*) FROM projects p WHERE p.department_id = d.id AND p.status = 'ACTIVE') AS projects_active,
               (SELECT COALESCE(SUM(u.total_tokens), 0) FROM usage_records u JOIN employees e ON e.id = u.employee_id
                 WHERE e.department_id = d.id) AS total_tokens,
               (SELECT COALESCE(SUM(u.estimated_cost), 0) FROM usage_records u JOIN employees e ON e.id = u.employee_id
                 WHERE e.department_id = d.id) AS estimated_cost
        FROM departments d ORDER BY d.id
        """,
    )


def usage_summary(conn, *, days: int = 30) -> dict[str, Any]:
    by_employee = fetch_all(
        conn,
        """
        SELECT u.employee_id, e.name AS employee_name, e.department_id, u.model,
               SUM(u.prompt_tokens) AS prompt_tokens, SUM(u.completion_tokens) AS completion_tokens,
               SUM(u.total_tokens) AS total_tokens, SUM(u.estimated_cost) AS estimated_cost,
               COUNT(*) AS calls
        FROM usage_records u LEFT JOIN employees e ON e.id = u.employee_id
        GROUP BY u.employee_id, u.model ORDER BY total_tokens DESC
        """,
    )
    by_model = fetch_all(
        conn,
        """
        SELECT model, SUM(total_tokens) AS total_tokens, SUM(estimated_cost) AS estimated_cost,
               COUNT(*) AS calls
        FROM usage_records GROUP BY model ORDER BY total_tokens DESC
        """,
    )
    by_project = fetch_all(
        conn,
        """
        SELECT u.project_id, p.name AS project_name,
               SUM(u.total_tokens) AS total_tokens, SUM(u.estimated_cost) AS estimated_cost,
               COUNT(*) AS calls
        FROM usage_records u LEFT JOIN projects p ON p.id = u.project_id
        GROUP BY u.project_id ORDER BY total_tokens DESC
        """,
    )
    by_day = fetch_all(
        conn,
        """
        SELECT substr(at, 1, 10) AS day, SUM(total_tokens) AS total_tokens,
               SUM(estimated_cost) AS estimated_cost, COUNT(*) AS calls
        FROM usage_records GROUP BY day ORDER BY day DESC LIMIT ?
        """,
        (max(1, min(days, 365)),),
    )
    totals = fetch_one(
        conn,
        """
        SELECT COALESCE(SUM(total_tokens), 0) AS total_tokens,
               COALESCE(SUM(estimated_cost), 0) AS estimated_cost, COUNT(*) AS calls
        FROM usage_records
        """,
    )
    return {
        "by_employee": by_employee,
        "by_model": by_model,
        "by_project": by_project,
        "by_day": by_day,
        "totals": totals or {},
        "budget": settings.DAILY_TOKEN_BUDGET,
    }


def activity(
    conn,
    *,
    department_id: str | None = None,
    employee_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    employees = fetch_all(conn, "SELECT id, name, department_id, title FROM employees")
    names = {row["id"]: row for row in employees}
    clauses: list[str] = []
    params: list[Any] = []
    if employee_id:
        clauses.append("actor = ?")
        params.append(employee_id)
    elif department_id:
        ids = [row["id"] for row in employees if row["department_id"] == department_id]
        if not ids:
            return []
        clauses.append(f"actor IN ({','.join('?' for _ in ids)})")
        params.extend(ids)
    if action:
        clauses.append("action = ?")
        params.append(action)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 500)))
    rows = fetch_all(conn, f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ?", tuple(params))
    for row in rows:
        employee = names.get(row["actor"])
        row["actor_name"] = employee["name"] if employee else row["actor"]
        row["department_id"] = employee["department_id"] if employee else None
    return rows


def _export(conn, *, paper_type: str, title: str, body: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    paper = papers.create_paper(
        conn,
        paper_type=paper_type,
        creator=actor,
        payload={"title": title, "body": body, **payload},
        summary=title,
        priority="normal",
    )
    print_result = papers.print_paper(conn, paper["id"], actor=actor)
    paper = papers.deliver_paper(conn, paper["id"], actor=actor)
    job = print_result.get("print_job") or {}
    return {"paper": paper, "pdf_path": job.get("pdf_path")}


def export_project(conn, project_id: str, *, actor: str = "owner") -> dict[str, Any]:
    data = project_metrics(conn, project_id)
    title = f"Laporan proyek: {data['project']['name']}"
    return _export(
        conn,
        paper_type="project_report",
        title=title,
        body=project_markdown(conn, project_id),
        payload={"project_id": project_id},
        actor=actor,
    )


def export_division(conn, department_id: str, *, actor: str = "owner") -> dict[str, Any]:
    data = division_metrics(conn, department_id)
    title = f"Laporan divisi: {data['department']['name']}"
    return _export(
        conn,
        paper_type="division_report",
        title=title,
        body=division_markdown(conn, department_id),
        payload={"department_id": department_id},
        actor=actor,
    )


def record_usage(
    conn,
    *,
    employee_id: str,
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int | None = None,
    estimated_cost: float = 0.0,
    project_id: str | None = None,
    actor: str = "system",
) -> dict[str, Any]:
    if not employee_id:
        raise ValueError("employee_id wajib diisi.")
    total = int(total_tokens if total_tokens is not None else prompt_tokens + completion_tokens)
    conn.execute(
        """
        INSERT INTO usage_records
            (employee_id, model, prompt_tokens, completion_tokens, total_tokens, estimated_cost, at, project_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            employee_id, model or "unknown", max(0, int(prompt_tokens)),
            max(0, int(completion_tokens)), max(0, total), float(estimated_cost), now(), project_id,
        ),
    )
    audit.log(
        conn, actor=actor, actor_kind="backend", action="usage.recorded",
        detail=json_dump({"employee_id": employee_id, "model": model, "total_tokens": total, "project_id": project_id}),
        ref_type="employee", ref_id=employee_id,
    )
    return {
        "employee_id": employee_id,
        "model": model or "unknown",
        "total_tokens": max(0, total),
        "estimated_cost": float(estimated_cost),
        "project_id": project_id,
    }
