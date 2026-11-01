"""Rapat multi-agen: transkrip, notulen, keputusan, dan tindak lanjut (MTG).

Rapat berjalan deterministik agar tidak bergantung pada LLM. Setiap peserta
berbicara bergiliran sesuai agenda dengan jumlah putaran terbatas, lalu
notulen disimpan sebagai dokumen, diindeks lewat folder docs, dan dikirim ke
tray Owner sebagai Paper.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import audit, events, org, papers, settings, tasks
from .db import fetch_one, json_dump, json_load, now
from .sandbox import redact

DEFAULT_PARTICIPANTS = ("secretary", "lead", "coo")


class MeetingError(Exception):
    status_code = 400


def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    row["participants"] = json_load(row.get("participants"), [])
    row["transcript"] = json_load(row.get("transcript"), [])
    row["decisions"] = json_load(row.get("decisions"), [])
    return row


def get_meeting(conn, meeting_id: str) -> dict[str, Any]:
    row = fetch_one(conn, "SELECT * FROM meetings WHERE id = ?", (meeting_id,))
    meeting = _decode(row)
    if not meeting:
        raise MeetingError(f"Rapat {meeting_id} tidak ditemukan.")
    return meeting


def _resolve_participant(conn, value: str) -> dict[str, Any] | None:
    employee = org.get_employee(conn, str(value))
    if employee:
        return employee
    return org.resolve_recipient(conn, str(value))


def _default_participants(conn) -> list[str]:
    result: list[str] = []
    for employee_id in DEFAULT_PARTICIPANTS:
        employee = org.get_employee(conn, employee_id)
        if employee and employee.get("active"):
            result.append(employee_id)
    return result


def create_meeting(
    conn,
    *,
    title: str,
    agenda: str = "",
    participants: list[str] | None = None,
    room: str = "ruang_rapat",
    scheduled_at: str | None = None,
    created_by: str = "owner",
    actor_kind: str = "owner",
    run_now: bool = False,
    rounds: int | None = None,
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise MeetingError("Judul rapat wajib diisi.")
    participant_ids: list[str] = []
    for item in participants or []:
        employee = _resolve_participant(conn, str(item))
        if not employee or not employee.get("active"):
            raise MeetingError(f"Peserta rapat tidak dikenal atau nonaktif: {item}")
        if employee["id"] not in participant_ids:
            participant_ids.append(employee["id"])
    meeting_id = f"meet_{uuid.uuid4().hex[:10]}"
    stamp = now()
    conn.execute(
        """
        INSERT INTO meetings
            (id, title, agenda, participants, room, scheduled_at, status,
             transcript, minutes, decisions, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'SCHEDULED', '[]', '', '[]', ?, ?)
        """,
        (
            meeting_id, title, (agenda or "").strip(), json_dump(participant_ids),
            room or "ruang_rapat", scheduled_at, created_by, stamp,
        ),
    )
    audit.log(
        conn, actor=created_by, actor_kind=actor_kind, action="meeting.created",
        detail=json_dump({"title": title, "participants": participant_ids, "room": room}),
        ref_type="meeting", ref_id=meeting_id,
    )
    events.publish(conn, "meeting.created", created_by, {"meeting_id": meeting_id, "title": title})
    if run_now:
        return run_meeting(conn, meeting_id, actor=created_by, rounds=rounds)
    return get_meeting(conn, meeting_id)


def _speech(employee: dict[str, Any], title: str, agenda: str, round_no: int) -> str:
    focus = agenda or title
    role = employee.get("id")
    templates = {
        "lead": "Saya menjaga arah teknis, pembagian kerja, dan kriteria selesai.",
        "coo": "Saya menyelaraskan prioritas, tenggat, dan ketergantungan antar-task.",
        "secretary": "Saya mencatat keputusan dan menyiapkan tindak lanjut untuk Owner.",
        "architect": "Saya memeriksa desain, integrasi, dan risiko arsitektur.",
        "backend": "Saya menyiapkan implementasi backend, data, dan pengujiannya.",
        "api": "Saya memastikan kontrak API, dokumentasi, dan integrasi berjalan.",
        "frontend": "Saya menyiapkan antarmuka, aksesibilitas, dan pengalaman pengguna.",
        "qa": "Saya menyiapkan skenario uji, bukti hasil tes, dan kriteria penerimaan.",
        "promo_manager": "Saya menyiapkan rencana promosi dan materi yang perlu disetujui.",
        "promo_writer": "Saya menyiapkan copywriting dan draf materi komunikasi.",
        "promo_social": "Saya menyiapkan kalender konten dan kebutuhan media sosial.",
        "receptionist": "Saya mencatat pesan masuk dan kebutuhan front office.",
    }
    base = templates.get(
        role, "Saya menindaklanjuti bagian yang menjadi tanggung jawab saya."
    )
    if round_no <= 1:
        return f"{base} Untuk agenda '{focus}', saya usulkan langkah awal yang langsung bisa dikerjakan."
    return (
        f"Pada putaran {round_no}, saya memastikan hasil '{focus}' tetap selaras "
        "dengan kriteria penerimaan dan siap ditinjau."
    )


def _minutes_markdown(
    meeting: dict[str, Any],
    participants: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    task: dict[str, Any],
    file_path: Path,
) -> str:
    lines = [
        f"# Notulen: {meeting['title']}",
        "",
        f"- Rapat: {meeting['id']}",
        f"- Ruang: {meeting['room']}",
        f"- Agenda: {meeting['agenda'] or '-'}",
        f"- Peserta: {', '.join(item['name'] for item in participants)}",
        f"- Dokumen: {file_path}",
        "",
        "## Transkrip",
    ]
    for item in transcript:
        lines.append(f"- **{item['name']}** ({item.get('role', 'peserta')}): {item['content']}")
    lines.extend(["", "## Keputusan"])
    for item in decisions:
        lines.append(f"- {item['text']}")
    lines.extend(
        [
            "",
            "## Tindak lanjut",
            f"- Task `{task['id']}` untuk {task['assignee']}: {task['title']}",
            "",
            "Dokumen ini dihasilkan backend dan diindeks ke knowledge base.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_meeting(
    conn,
    meeting_id: str,
    *,
    actor: str = "owner",
    rounds: int | None = None,
) -> dict[str, Any]:
    meeting = get_meeting(conn, meeting_id)
    if meeting["status"] == "COMPLETED":
        return meeting
    if meeting["status"] not in ("SCHEDULED", "IN_PROGRESS"):
        raise MeetingError("Rapat tidak dapat dijalankan pada status ini.")

    participant_ids = meeting["participants"] or _default_participants(conn)
    if not participant_ids:
        raise MeetingError("Rapat membutuhkan minimal satu peserta aktif.")
    participants: list[dict[str, Any]] = []
    for employee_id in participant_ids:
        employee = org.get_employee(conn, employee_id)
        if employee and employee.get("active"):
            participants.append(employee)
    if not participants:
        raise MeetingError("Tidak ada peserta aktif untuk rapat ini.")

    max_rounds = max(1, settings.MAX_MEETING_ROUNDS)
    round_count = max(1, min(int(rounds or max_rounds), max_rounds))
    originals = {
        employee["id"]: fetch_one(
            conn, "SELECT room, activity FROM employee_states WHERE employee_id = ?",
            (employee["id"],),
        )
        for employee in participants
    }
    for employee in participants:
        org.set_employee_state(
            conn, employee["id"], room=meeting["room"], activity="working",
            source="meeting", actor=actor,
        )

    stamp = now()
    transcript = list(meeting["transcript"])
    if not transcript:
        chair = participants[0]
        transcript.append(
            {
                "at": stamp,
                "speaker": chair["id"],
                "name": chair["name"],
                "role": "pembuka",
                "content": f"Rapat '{meeting['title']}' dibuka. Agenda: {meeting['agenda'] or meeting['title']}.",
            }
        )
    token_budget = max(100, settings.MAX_MEETING_TOKENS)
    for round_no in range(1, round_count + 1):
        for employee in participants:
            if sum(len(item.get("content", "")) for item in transcript) // 4 >= token_budget:
                break
            transcript.append(
                {
                    "at": now(),
                    "speaker": employee["id"],
                    "name": employee["name"],
                    "role": "peserta",
                    "content": _speech(employee, meeting["title"], meeting["agenda"], round_no),
                }
            )

    decision_text = (
        f"Rapat '{meeting['title']}' menyepakati tindak lanjut agenda: "
        f"{meeting['agenda'] or meeting['title']}."
    )
    decisions = list(meeting["decisions"])
    decisions.append({"text": decision_text, "at": now(), "by": "rapat"})

    assignee = next((item["id"] for item in participants if item["id"] != "secretary"), participants[0]["id"])
    task = tasks.create_task(
        conn,
        title=f"Tindak lanjut rapat: {meeting['title']}",
        description=(
            f"Tindak lanjut dari rapat {meeting_id}. Agenda: "
            f"{meeting['agenda'] or meeting['title']}."
        ),
        assignee=assignee,
        priority="high" if meeting["agenda"] else "normal",
        kind="non_code",
        acceptance_criteria=["Tindak lanjut rapat terdokumentasi dan ditinjau."],
        due_at=(datetime.now().astimezone() + timedelta(days=3)).isoformat(timespec="seconds"),
        created_by=actor,
        actor_kind="owner" if actor == "owner" else "manager",
    )

    minutes_dir = settings.DOCS_DIR / "meetings"
    minutes_dir.mkdir(parents=True, exist_ok=True)
    minutes_path = minutes_dir / f"{meeting_id}.md"
    minutes = _minutes_markdown(meeting, participants, transcript, decisions, task, minutes_path)
    minutes_path.write_text(redact(minutes), encoding="utf-8")

    paper = papers.create_paper(
        conn,
        paper_type="meeting_minutes",
        creator=actor,
        payload={
            "meeting_id": meeting_id,
            "title": meeting["title"],
            "agenda": meeting["agenda"],
            "transcript": transcript,
            "decisions": decisions,
            "minutes": minutes,
            "file": str(minutes_path),
            "task_id": task["id"],
            "token_estimate": max(1, len(minutes) // 4),
        },
        summary=f"Notulen rapat: {meeting['title']}",
        task_id=task["id"],
        priority="high",
    )
    papers.print_paper(conn, paper["id"], actor=actor)
    papers.deliver_paper(conn, paper["id"], actor=actor)

    conn.execute(
        "UPDATE meetings SET status = 'COMPLETED', transcript = ?, minutes = ?, decisions = ? WHERE id = ?",
        (json_dump(transcript), minutes, json_dump(decisions), meeting_id),
    )
    for employee in participants:
        original = originals.get(employee["id"]) or {}
        org.set_employee_state(
            conn,
            employee["id"],
            room=original.get("room") or employee.get("room"),
            activity=original.get("activity") or "idle",
            source="meeting",
            actor=actor,
        )
    audit.log(
        conn, actor=actor, actor_kind="owner" if actor == "owner" else "manager",
        action="meeting.completed",
        detail=json_dump(
            {
                "meeting_id": meeting_id,
                "rounds": round_count,
                "participants": [item["id"] for item in participants],
                "task_id": task["id"],
                "paper_id": paper["id"],
                "minutes": str(minutes_path),
            }
        ),
        ref_type="meeting", ref_id=meeting_id,
    )
    events.publish(
        conn, "meeting.completed", actor,
        {"meeting_id": meeting_id, "task_id": task["id"], "paper_id": paper["id"]},
    )
    return get_meeting(conn, meeting_id)


def interject(conn, meeting_id: str, content: str, *, actor: str = "owner") -> dict[str, Any]:
    meeting = get_meeting(conn, meeting_id)
    if meeting["status"] not in ("SCHEDULED", "IN_PROGRESS"):
        raise MeetingError("Owner hanya dapat menyela rapat yang belum selesai.")
    content = (content or "").strip()
    if not content:
        raise MeetingError("Isi interupsi wajib diisi.")
    transcript = list(meeting["transcript"])
    transcript.append(
        {
            "at": now(),
            "speaker": "owner",
            "name": "Owner",
            "role": "owner",
            "content": content,
        }
    )
    conn.execute(
        "UPDATE meetings SET transcript = ? WHERE id = ?",
        (json_dump(transcript), meeting_id),
    )
    audit.log(
        conn, actor=actor, actor_kind="owner", action="meeting.interjection",
        detail=json_dump({"meeting_id": meeting_id, "content": content}),
        ref_type="meeting", ref_id=meeting_id,
    )
    events.publish(conn, "meeting.interjection", actor, {"meeting_id": meeting_id})
    return get_meeting(conn, meeting_id)
