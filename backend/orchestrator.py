"""Orchestrator: instruksi -> rencana JSON -> tool allowlist (CMD-01..04).

Perencana deterministik menjadi fallback wajib saat LLM tidak tersedia
(CMD-03). Rencana tetap divalidasi ulang sebelum dieksekusi, dan izin tool
ditegakkan lagi oleh tools.execute.
"""

from __future__ import annotations

import re
from typing import Any

from . import audit, events, org, papers, tasks, tools
from .db import fetch_all, fetch_one

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ROOM_RE = re.compile(r"\b(?:ke|menuju|di)\s+(ruang\s+[A-Za-zÀ-ÿ ]+|meeting|rapat|lounge|pantry|dapur)", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _after_colon(text: str) -> str:
    if ":" in text:
        return _clean(text.split(":", 1)[1])
    return ""


def _extract_task_title(text: str) -> str:
    after = _after_colon(text)
    if after:
        return after
    title = re.sub(
        r"(?i)^(tolong\s+)?(buat|buatkan|tambahkan|kerjakan|minta|suruh)\s+(tugas|task)\s*(untuk|kepada)?\s*",
        "",
        text,
    )
    return _clean(title) or "Task baru"


def _extract_meeting_title(text: str) -> str:
    after = _after_colon(text)
    if after:
        return after
    match = re.search(r"(?i)(tentang|mengenai|untuk membahas)\s+(.+)$", text)
    return _clean(match.group(2)) if match else "Rapat koordinasi"


def _extract_meeting_agenda(text: str) -> str:
    after = _after_colon(text)
    return after or _extract_meeting_title(text)


def _extract_email(text: str) -> tuple[str | None, str, str]:
    match = EMAIL_RE.search(text)
    recipient = match.group(0) if match else None
    after = _after_colon(text)
    subject = "Pesan dari Bangkah"
    body = after
    if "tentang" in text.lower():
        tail = re.split(r"(?i)tentang", text, maxsplit=1)[1]
        subject = _clean(re.split(r"(?i)\b(isi|dengan|body)\b", tail, maxsplit=1)[0])
        if after:
            body = after
    if not body:
        body = text
    return recipient, subject, body


def _extract_move(text: str, conn) -> tuple[dict | None, str | None]:
    employee = org.resolve_recipient(conn, text)
    room_match = ROOM_RE.search(text)
    room = _clean(room_match.group(1)) if room_match else None
    return employee, room


def company_status(conn) -> dict[str, Any]:
    employees = org.employee_states(conn)
    projects = fetch_all(conn, "SELECT * FROM projects ORDER BY created_at DESC")
    active_tasks = tasks.list_tasks(conn, status="IN_PROGRESS", limit=500)
    pending = fetch_all(conn, "SELECT * FROM tasks WHERE status = 'PENDING'", ())
    failed = fetch_all(conn, "SELECT id, title, assignee FROM tasks WHERE status = 'FAILED'", ())
    return {
        "employees_working": [e["id"] for e in employees if e.get("activity") == "working"],
        "employees_idle": [e["id"] for e in employees if e.get("activity") in (None, "idle")],
        "employees_blocked": [e["id"] for e in employees if e.get("activity") == "blocked"],
        "projects_active": [p for p in projects if p.get("status") in ("PLANNED", "RUNNING", "IN_PROGRESS")],
        "tasks_in_progress": active_tasks,
        "tasks_pending": pending,
        "tasks_failed": failed,
        "pending_approvals": papers.pending_count(conn),
    }


def build_plan(conn, text: str, actor: str = "secretary") -> dict[str, Any]:
    original = _clean(text)
    lower = original.lower()
    plan: dict[str, Any] = {
        "intent": "chat",
        "steps": [],
        "requires_approval": False,
        "needs_clarification": False,
        "clarification": "",
        "summary": "",
        "original": original,
        "actor": actor,
    }

    if not original:
        plan.update(
            intent="clarification",
            needs_clarification=True,
            clarification="Apa yang ingin Anda kerjakan?",
            summary="Perintah kosong.",
        )
        return plan

    if re.search(r"(?i)\b(email|surel)\b", original):
        recipient, subject, body = _extract_email(original)
        plan["intent"] = "draft_email"
        plan["requires_approval"] = True
        if not recipient:
            plan.update(
                needs_clarification=True,
                clarification="Email ini ditujukan ke alamat mana?",
                summary="Alamat penerima email belum jelas.",
            )
            return plan
        plan["steps"] = [{
            "tool": "draft_email",
            "args": {"to": recipient, "subject": subject, "body": body},
        }]
        plan["summary"] = f"Siapkan draf email ke {recipient} untuk persetujuan Owner."
        return plan

    if re.search(r"(?i)\b(website|situs|deploy|publikasi)\b", original):
        package = _after_colon(original) or original
        plan["intent"] = "publish_website"
        plan["requires_approval"] = True
        plan["steps"] = [{
            "tool": "propose_website_publish",
            "args": {"summary": _extract_meeting_title(original), "diff": package},
        }]
        plan["summary"] = "Ajukan paket perubahan website untuk persetujuan Owner."
        return plan

    if re.search(r"(?i)\b(pindah|pindahkan|geser|antar)\b", original) and re.search(r"(?i)\b(ruang|rapat|meeting|lounge|pantry|dapur)\b", original):
        employee, room = _extract_move(original, conn)
        plan["intent"] = "move_employee"
        if not employee or not room:
            missing = "karyawan" if not employee else "ruang tujuan"
            plan.update(
                needs_clarification=True,
                clarification=f"Siapa/ke mana? Sebutkan {missing} yang dimaksud.",
                summary="Tujuan perpindahan belum lengkap.",
            )
            return plan
        plan["steps"] = [{
            "tool": "move_employee",
            "args": {"employee_id": employee["id"], "room": room, "activity": "walking"},
        }]
        plan["summary"] = f"Pindahkan {employee['name']} ke {room}."
        return plan

    if re.search(r"(?i)\b(rapat|meeting)\b", original):
        participants = [e["id"] for e in org.list_employees(conn, active_only=True) if e["name"].lower() in lower]
        plan["intent"] = "create_meeting"
        plan["steps"] = [{
            "tool": "create_meeting",
            "args": {
                "title": _extract_meeting_title(original),
                "agenda": _extract_meeting_agenda(original),
                "participants": participants,
                "room": "ruang_rapat",
            },
        }]
        plan["summary"] = "Jadwalkan rapat dan kumpulkan peserta."
        return plan

    if re.search(r"(?i)\bproyek baru\b|\bmulai proyek\b|\bbuat proyek\b", original):
        name = _after_colon(original) or re.sub(r"(?i).*proyek", "", original).strip() or "Proyek baru"
        plan["intent"] = "create_project"
        plan["requires_approval"] = True
        plan["steps"] = [{
            "tool": "create_project",
            "args": {"name": name, "deliverable": "Perangkat lunak yang diuji dan terdokumentasi."},
        }]
        plan["summary"] = f"Buat proyek {name} dan ajukan pipeline untuk persetujuan."
        return plan

    if re.search(r"(?i)\b(laporan|report)\b", original):
        plan["intent"] = "generate_report"
        plan["steps"] = [{
            "tool": "generate_report",
            "args": {"title": _after_colon(original) or "Laporan mingguan", "body": _clean(original)},
        }]
        plan["summary"] = "Susun laporan dan cetak ke tray Owner."
        return plan

    if re.search(r"(?i)\b(cari|telusuri|knowledge|arsip|kebijakan|dokumen)\b", original):
        query = _after_colon(original) or re.sub(r"(?i)^(tolong\s+)?(cari|telusuri)\s*", "", original)
        plan["intent"] = "search_knowledge"
        plan["steps"] = [{"tool": "search_knowledge", "args": {"query": _clean(query)}}]
        plan["summary"] = f"Cari konteks perusahaan untuk: {query}."
        return plan

    if re.search(r"(?i)\b(status|progres|kemajuan|perkembangan|bagaimana kondisi)\b", original):
        plan["intent"] = "status"
        plan["summary"] = "Bacakan status perusahaan dari backend."
        plan["status"] = company_status(conn)
        return plan

    if re.search(r"(?i)\b(tugas|task|kerjakan|buatkan|buat)\b", original):
        employee = org.resolve_recipient(conn, original)
        plan["intent"] = "create_task"
        if not employee:
            plan.update(
                needs_clarification=True,
                clarification="Tugas ini untuk siapa? Sebutkan nama karyawan atau divisi.",
                summary="Penerima tugas belum jelas.",
            )
            return plan
        plan["steps"] = [{
            "tool": "create_task",
            "args": {
                "title": _extract_task_title(original),
                "assignee": employee["id"],
                "description": original,
                "priority": "high" if re.search(r"(?i)\b(penting|segera|urgent)\b", original) else "normal",
            },
        }]
        plan["summary"] = f"Buat task untuk {employee['name']}."
        return plan

    plan["summary"] = "Tidak ada aksi tool yang diperlukan."
    return plan


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    steps = plan.get("steps") or []
    if not isinstance(steps, list):
        raise tools.ToolError("Rencana tidak valid: steps harus berupa daftar.")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise tools.ToolError(f"Langkah {index + 1} tidak valid.")
        name = step.get("tool")
        if name not in tools.REGISTRY:
            raise tools.UnknownTool(f"Tool tidak ada di allowlist: {name}")
        if not isinstance(step.get("args", {}), dict):
            raise tools.ToolError(f"Argumen langkah {index + 1} tidak valid.")
    return plan


def execute_plan(conn, plan: dict[str, Any], actor: str) -> dict[str, Any]:
    validate_plan(plan)
    results: list[dict[str, Any]] = []
    if plan.get("needs_clarification"):
        return {"status": "clarification", "clarification": plan.get("clarification"), "plan": plan, "results": []}
    if not plan.get("steps"):
        status = "status" if plan.get("intent") == "status" else "no_action"
        return {"status": status, "summary": plan.get("summary"), "plan": plan, "results": []}

    for step in plan["steps"]:
        result = tools.execute(conn, actor=actor, tool_name=step["tool"], args=step.get("args", {}))
        results.append({"tool": step["tool"], "result": result})
    events.publish(conn, "command.completed", actor, {"intent": plan.get("intent"), "steps": len(results)})
    audit.log(
        conn, actor=actor, actor_kind="manager", action="command.executed",
        detail=str({"intent": plan.get("intent"), "steps": [s["tool"] for s in plan["steps"]]}),
        ref_type="command", ref_id=plan.get("intent"),
    )
    return {"status": "executed", "summary": plan.get("summary"), "plan": plan, "results": results}
