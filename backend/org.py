"""Organisasi: departemen, karyawan, dan resolusi penerima perintah."""

from __future__ import annotations

import uuid
from typing import Any

from . import audit, events, settings
from .db import fetch_all, fetch_one, json_dump, json_load, now

RECIPIENT_HINTS = {
    "backend": "backend",
    "back end": "backend",
    "frontend": "frontend",
    "front end": "frontend",
    "api": "api",
    "qa": "qa",
    "quality": "qa",
    "arsitek": "architect",
    "architect": "architect",
    "coo": "coo",
    "project manager": "coo",
    "lead": "lead",
    "arman": "lead",
    "sekretaris": "secretary",
    "secretary": "secretary",
    "resepsionis": "receptionist",
    "receptionist": "receptionist",
    "promosi": "promo_manager",
    "promotion": "promo_manager",
    "content writer": "promo_writer",
    "penulis": "promo_writer",
    "social media": "promo_social",
    "media sosial": "promo_social",
}


def _decode_employee(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    row["skills"] = json_load(row.get("skills"), [])
    row["tool_permissions"] = json_load(row.get("tool_permissions"), [])
    row["active"] = bool(row.get("active"))
    return row


def list_departments(conn) -> list[dict[str, Any]]:
    return fetch_all(conn, "SELECT * FROM departments ORDER BY name")


def list_employees(conn, *, active_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM employees"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY department_id, name"
    return [_decode_employee(row) for row in fetch_all(conn, sql)]


def get_employee(conn, employee_id: str) -> dict[str, Any] | None:
    return _decode_employee(
        fetch_one(conn, "SELECT * FROM employees WHERE id = ?", (employee_id,))
    )


def create_department(conn, *, name: str, manager_id: str | None = None, room: str = "", actor: str = "owner") -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Nama departemen wajib diisi.")
    department_id = f"dept_{uuid.uuid4().hex[:8]}"
    conn.execute(
        "INSERT INTO departments (id, name, manager_id, room, created_at) VALUES (?, ?, ?, ?, ?)",
        (department_id, name, manager_id, room, now()),
    )
    audit.log(
        conn, actor=actor, actor_kind="owner", action="department.created",
        detail=json_dump({"name": name}), ref_type="department", ref_id=department_id,
    )
    return fetch_one(conn, "SELECT * FROM departments WHERE id = ?", (department_id,)) or {}


def create_employee(
    conn,
    *,
    name: str,
    title: str,
    department_id: str,
    manager_id: str | None = None,
    model: str | None = None,
    skills: list[str] | None = None,
    tool_permissions: list[str] | None = None,
    room: str = "",
    desk: str = "",
    avatar: str = "🧑‍💼",
    actor: str = "owner",
) -> dict[str, Any]:
    if not (name or "").strip() or not (title or "").strip():
        raise ValueError("Nama dan jabatan wajib diisi.")
    if not fetch_one(conn, "SELECT id FROM departments WHERE id = ?", (department_id,)):
        raise ValueError(f"Departemen tidak dikenal: {department_id}")
    employee_id = f"emp_{uuid.uuid4().hex[:8]}"
    stamp = now()
    conn.execute(
        """
        INSERT INTO employees
            (id, name, title, department_id, manager_id, model, skills,
             tool_permissions, status, room, desk, avatar, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'idle', ?, ?, ?, 1, ?)
        """,
        (
            employee_id, name.strip(), title.strip(), department_id, manager_id,
            model or settings.model_for_role(employee_id),
            json_dump(skills or []), json_dump(tool_permissions or []),
            room, desk, avatar, stamp,
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO employee_states (employee_id, room, activity, source, updated_at) VALUES (?, ?, 'idle', 'task', ?)",
        (employee_id, room, stamp),
    )
    audit.log(
        conn, actor=actor, actor_kind="owner", action="employee.created",
        detail=json_dump({"name": name, "title": title, "department": department_id}),
        ref_type="employee", ref_id=employee_id,
    )
    events.publish(conn, "employee.created", actor, {"employee_id": employee_id})
    return get_employee(conn, employee_id) or {}


def update_employee(conn, employee_id: str, changes: dict[str, Any], actor: str = "owner") -> dict[str, Any]:
    employee = get_employee(conn, employee_id)
    if not employee:
        raise ValueError(f"Karyawan tidak dikenal: {employee_id}")
    allowed = {
        "name", "title", "department_id", "manager_id", "model", "skills",
        "tool_permissions", "room", "desk", "avatar", "active",
    }
    updates: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in allowed:
            continue
        if key in ("skills", "tool_permissions"):
            value = json_dump(value)
        if key == "active":
            value = 1 if value else 0
        updates[key] = value
    if not updates:
        return employee
    assignments = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(
        f"UPDATE employees SET {assignments} WHERE id = ?",
        (*updates.values(), employee_id),
    )
    audit.log(
        conn, actor=actor, actor_kind="owner", action="employee.updated",
        detail=json_dump({"changes": sorted(updates)}),
        ref_type="employee", ref_id=employee_id,
    )
    events.publish(conn, "employee.updated", actor, {"employee_id": employee_id})
    return get_employee(conn, employee_id) or {}


def set_employee_state(
    conn,
    employee_id: str,
    *,
    room: str | None = None,
    activity: str = "idle",
    source: str = "task",
    actor: str = "backend",
) -> dict[str, Any] | None:
    employee = get_employee(conn, employee_id)
    if not employee:
        raise ValueError(f"Karyawan tidak dikenal: {employee_id}")
    stamp = now()
    conn.execute(
        """
        INSERT INTO employee_states (employee_id, room, activity, source, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(employee_id) DO UPDATE SET
            room = excluded.room,
            activity = excluded.activity,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (employee_id, room or employee.get("room"), activity, source, stamp),
    )
    conn.execute(
        "UPDATE employees SET status = ?, room = COALESCE(?, room) WHERE id = ?",
        (activity, room, employee_id),
    )
    events.publish(
        conn, "employee.state", actor,
        {"employee_id": employee_id, "room": room or employee.get("room"), "activity": activity, "source": source},
    )
    return dict(fetch_one(conn, "SELECT * FROM employee_states WHERE employee_id = ?", (employee_id,)) or {})


def employee_states(conn) -> list[dict[str, Any]]:
    return fetch_all(
        conn,
        """
        SELECT e.id, e.name, e.title, e.department_id, e.status, e.model,
               s.room, s.activity, s.source, s.updated_at
        FROM employees e LEFT JOIN employee_states s ON s.employee_id = e.id
        WHERE e.active = 1
        ORDER BY e.department_id, e.name
        """,
    )


def resolve_recipient(conn, text: str) -> dict[str, Any] | None:
    """Cari karyawan dari nama, id, atau kata kunci peran/departemen."""
    value = (text or "").lower()
    employees = list_employees(conn, active_only=True)
    for employee in employees:
        if employee["id"].lower() in value or employee["name"].lower() in value:
            return employee
    # Prioritaskan frasa terpanjang agar "content writer" tidak kalah "writer".
    for hint in sorted(RECIPIENT_HINTS, key=len, reverse=True):
        if hint in value:
            target = RECIPIENT_HINTS[hint]
            for employee in employees:
                if employee["id"] == target:
                    return employee
    return None


def department_manager(conn, department_id: str) -> str | None:
    row = fetch_one(conn, "SELECT manager_id FROM departments WHERE id = ?", (department_id,))
    return row["manager_id"] if row else None


def is_manager(conn, employee_id: str) -> bool:
    """True bila karyawan memimpin orang lain atau sebuah departemen."""
    if not employee_id:
        return False
    reports = fetch_one(
        conn, "SELECT 1 AS ok FROM employees WHERE manager_id = ? AND active = 1 LIMIT 1", (employee_id,)
    )
    if reports:
        return True
    department = fetch_one(
        conn, "SELECT 1 AS ok FROM departments WHERE manager_id = ? LIMIT 1", (employee_id,)
    )
    return bool(department)
