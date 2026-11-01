"""Sekretaris AI: gerbang perintah Owner (SEC-01 s.d. SEC-09).

Sekretaris memahami perintah, memilih penerima, menyusun rencana, dan meminta
persetujuan bila aksi berdampak keluar. Bila perintah ambigu, ia mengajukan
satu pertanyaan klarifikasi sebelum bertindak.
"""

from __future__ import annotations

from typing import Any

from . import audit, chat, events, orchestrator, papers, tasks
from .db import fetch_all


def daily_summary(conn) -> dict[str, Any]:
    working = tasks.list_tasks(conn, status="IN_PROGRESS", limit=500)
    review = tasks.list_tasks(conn, status="REVIEW", limit=500)
    qa = tasks.list_tasks(conn, status="QA", limit=500)
    failed = tasks.list_tasks(conn, status="FAILED", limit=500)
    blocked = tasks.list_tasks(conn, status="BLOCKED", limit=500)
    pending_papers = papers.tray(conn)
    return {
        "working": len(working),
        "review": len(review),
        "qa": len(qa),
        "failed": len(failed),
        "blocked": len(blocked),
        "pending_approvals": len(pending_papers),
        "top_papers": [
            {"id": paper["id"], "summary": paper["summary"], "priority": paper["priority"]}
            for paper in pending_papers[:5]
        ],
        "failed_tasks": [
            {"id": task["id"], "title": task["title"], "assignee": task["assignee"]}
            for task in failed
        ],
    }


def _reply_for(plan: dict[str, Any], outcome: dict[str, Any]) -> str:
    if outcome["status"] == "clarification":
        return outcome.get("clarification") or "Boleh saya minta satu klarifikasi?"
    intent = plan.get("intent")
    if intent == "status":
        status = plan.get("status") or {}
        return (
            f"Saat ini {len(status.get('tasks_in_progress', []))} task berjalan, "
            f"{len(status.get('tasks_pending', []))} menunggu, "
            f"{len(status.get('tasks_failed', []))} gagal, dan "
            f"{status.get('pending_approvals', 0)} kertas menunggu persetujuan di tray."
        )
    if outcome["status"] == "no_action":
        return plan.get("summary") or "Tidak ada aksi yang perlu dijalankan."
    results = outcome.get("results") or []
    parts: list[str] = []
    for item in results:
        result = item.get("result") or {}
        if item["tool"] == "create_task" and result.get("task"):
            task = result["task"]
            parts.append(f"Task '{task['title']}' dibuat untuk {task['assignee']} (PENDING).")
        elif item["tool"] == "move_employee" and result.get("employee"):
            parts.append(f"{result['employee']['name']} dipindahkan ke {result.get('state', {}).get('room', 'ruang tujuan')}.")
        elif item["tool"] == "create_meeting" and result.get("meeting"):
            parts.append(f"Rapat '{result['meeting']['title']}' dijadwalkan.")
        elif item["tool"] in ("draft_email", "propose_website_publish") and result.get("paper"):
            parts.append(
                f"Proposal {item['tool']} dicetak dan diantar ke tray meja Anda; menunggu keputusan."
            )
        elif item["tool"] == "generate_report" and result.get("paper"):
            parts.append("Laporan dicetak dan diantar ke tray meja Anda.")
        elif item["tool"] == "create_project" and result.get("project"):
            parts.append(f"Proyek '{result['project']['name']}' dibuat; pipeline menunggu persetujuan.")
        elif item["tool"] == "search_knowledge":
            found = len(result.get("results") or [])
            parts.append(f"Ditemukan {found} dokumen relevan.")
        else:
            parts.append(f"{item['tool']} selesai.")
    return " ".join(parts) or "Perintah dijalankan."


def papers_count(status: dict[str, Any]) -> int:
    return int(status.get("pending_approvals", 0))


def handle_command(
    conn,
    text: str,
    *,
    actor: str = "secretary",
    thread_id: str = "owner-secretary",
    preview: bool = False,
) -> dict[str, Any]:
    plan = orchestrator.build_plan(conn, text, actor=actor)
    if preview:
        reply = "Pratinjau rencana. Kirim ulang tanpa preview untuk menjalankan."
        if plan.get("needs_clarification"):
            reply = plan.get("clarification") or reply
        chat.append(conn, thread_type="secretary", thread_id=thread_id, sender="owner", role="owner", content=text)
        chat.append(conn, thread_type="secretary", thread_id=thread_id, sender="secretary", role="assistant", content=reply)
        audit.log(
            conn, actor=actor, actor_kind="manager", action="secretary.preview",
            detail=str({"intent": plan.get("intent"), "steps": len(plan.get("steps") or [])}),
            ref_type="command", ref_id=plan.get("intent"),
        )
        events.publish(conn, "secretary.preview", actor, {"intent": plan.get("intent"), "plan": plan})
        return {
            "reply": reply,
            "status": "PREVIEW",
            "plan": plan,
            "results": [],
            "clarification": plan.get("clarification"),
        }
    outcome = orchestrator.execute_plan(conn, plan, actor=actor)
    reply = _reply_for(plan, outcome)
    chat.append(conn, thread_type="secretary", thread_id=thread_id, sender="owner", role="owner", content=text)
    chat.append(conn, thread_type="secretary", thread_id=thread_id, sender="secretary", role="assistant", content=reply)
    audit.log(
        conn,
        actor=actor,
        actor_kind="manager",
        action="secretary.command",
        detail=str({"intent": plan.get("intent"), "status": outcome["status"]}),
        ref_type="command",
        ref_id=plan.get("intent"),
    )
    events.publish(
        conn,
        "secretary.reply",
        actor,
        {"intent": plan.get("intent"), "status": outcome["status"], "reply": reply},
    )
    return {
        "reply": reply,
        "status": outcome["status"],
        "plan": plan,
        "results": outcome.get("results", []),
        "clarification": outcome.get("clarification"),
    }


def agenda(conn, limit: int = 20) -> dict[str, Any]:
    meetings = fetch_all(
        conn,
        "SELECT id, title, agenda, room, scheduled_at, status FROM meetings ORDER BY COALESCE(scheduled_at, created_at) ASC LIMIT ?",
        (max(1, limit),),
    )
    summary = daily_summary(conn)
    return {"meetings": meetings, "summary": summary}
