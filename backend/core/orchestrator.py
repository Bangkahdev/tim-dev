"""Converts owner chat into validated office actions and agent conversations."""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from config import make_llm, model_for
from core.employee_health import EMPLOYEES
from core.knowledge_base import KNOWLEDGE
from core.office_store import STORE, ROOMS, ROSTER
from core.office_tools import TOOLS

ALLOWED_ACTIONS = {
    "move_employee", "move_all_employees", "create_task", "update_task",
    "create_meeting", "generate_weekly_report",
}
ROLE_TASKS = [
    ("coo", "Rencana dan kebutuhan", "Susun requirement, prioritas, ruang lingkup, dan acceptance criteria."),
    ("architect", "Arsitektur sistem", "Rancang arsitektur, struktur folder, model data, dan kontrak antar-komponen."),
    ("backend", "Implementasi backend", "Implementasikan backend, business logic, validasi, dan penyimpanan data."),
    ("api", "Integrasi API", "Rancang dan implementasikan endpoint, kontrak API, serta integrasi layanan."),
    ("frontend", "Implementasi frontend", "Bangun antarmuka, responsivitas, interaksi, dan integrasi frontend."),
    ("qa", "Quality assurance", "Susun test case, jalankan pengujian, dokumentasikan bug dan hasil QA."),
]
ROOM_ALIASES = {
    "owner": ("owner", "ruang owner", "ruangan owner"),
    "meeting": ("meeting", "rapat", "ruang rapat", "ruang meeting", "ruangan meeting"),
    "manager": ("manager", "lead", "ruang lead", "ruang manager", "ruang manajer"),
    "planning": ("planning", "coo", "project manager", "ruang perencanaan", "ruang project manager"),
    "architect": ("architect", "arsitek", "arsitektur", "ruang arsitektur"),
    "backend": ("backend", "back-end", "ruang backend", "ruang pengembangan server"),
    "api": ("api", "api studio", "ruang api"),
    "frontend": ("frontend", "front-end", "ruang frontend"),
    "qa": ("qa", "quality assurance", "pengujian", "ruang qa"),
    "lounge": ("lounge", "area santai", "ruang santai"),
    "kitchen": ("kitchen", "dapur", "pantry"),
}


def _extract_json(text: str) -> dict | None:
    text = str(text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9_])" + re.escape(phrase.lower()) + r"(?![a-z0-9_])", text.lower()))


def _room_from_text(text: str, default="meeting") -> str | None:
    lower = text.lower()
    # Alias seperti "api" harus cocok sebagai kata utuh, bukan substring "aplikasi".
    for room_id, aliases in ROOM_ALIASES.items():
        if any(_contains_phrase(lower, alias) for alias in aliases):
            return room_id
    return default


def _employee_from_text(text: str) -> str | None:
    lower = text.lower()
    for employee_id, (name, role, _room) in ROSTER.items():
        aliases = (name.lower(), employee_id.lower())
        if any(_contains_phrase(lower, alias) for alias in aliases):
            return employee_id
    return None


def _is_question_only(text: str) -> bool:
    lower = text.strip().lower()
    return bool(re.match(r"^(bagaimana|gimana|apa itu|apakah|bisakah|bolehkah|kenapa|mengapa|jelaskan|tolong jelaskan)\b", lower))


def _is_gather_request(text: str) -> bool:
    lower = text.lower()
    if _is_question_only(text):
        return False
    return bool(
        re.search(r"\b(kumpulkan|kumpul|panggil|ajak|satukan|arahkan semua|bawa semua|pindahkan semua)\b", lower)
        and re.search(r"\b(semua|seluruh|karyawan|pegawai|tim|staff|staf)\b", lower)
    ) or bool(re.search(r"\b(adakan|buat|mulai)\s+(rapat|meeting|briefing)\b", lower))


def _is_report_request(text: str) -> bool:
    lower = text.lower()
    if _is_question_only(text):
        return False
    return "laporan" in lower and any(x in lower for x in ("minggu", "mingguan", "weekly", "aktivitas", "kerja", "pekerjaan"))


def _project_request(text: str) -> bool:
    lower = text.lower()
    if _is_question_only(text):
        return False
    imperative = re.search(r"\b(buat|buatkan|bikin|bikinkan|membuat|bangun|bangunkan|membangun|kembangkan|mengembangkan|kerjakan|implementasikan|develop|build|mulai)\b", lower)
    subject = re.search(r"\b(website|web|portfolio|portofolio|aplikasi|application|sistem|dashboard|landing page|mobile app)\b", lower)
    report_only = _is_report_request(text) and not subject
    return bool(imperative and subject and not report_only)


class OfficeOrchestrator:
    def __init__(self):
        self._meeting_threads: set[threading.Thread] = set()

    def _search_office_history(self, query: str, state: dict, limit=5) -> list[dict]:
        tokens = set(t.lower() for t in re.findall(r"[\w-]{3,}", query))
        if not tokens:
            return []
        candidates = []
        for event in state.get("events", []):
            text = f"{event.get('actor','')} {event.get('event_type','')} {event.get('detail','')}"
            candidates.append(("Aktivitas kantor", "database:events", text))
        for task in state.get("tasks", []):
            text = (
                f"{task.get('title','')} {task.get('description','')} "
                f"{task.get('assignee_id','')} {task.get('status','')}"
            )
            candidates.append((str(task.get("title") or "Tugas kantor"), "database:tasks", text))
        for meeting in state.get("meetings", []):
            text = f"{meeting.get('title','')} {meeting.get('agenda','')} {meeting.get('status','')}"
            candidates.append((str(meeting.get("title") or "Rapat kantor"), "database:meetings", text))
        for interaction in state.get("interactions", []):
            text = (
                f"{interaction.get('sender_name','')} {interaction.get('recipient_name','tim')} "
                f"{interaction.get('message','')}"
            )
            candidates.append(("Percakapan antar-karyawan", "database:interactions", text))
        ranked = []
        for title, source, content in candidates:
            words = set(t.lower() for t in re.findall(r"[\w-]{3,}", content))
            overlap = tokens & words
            if overlap:
                score = len(overlap) / max(1, len(tokens))
                ranked.append({"title": title, "source": source, "content": content[:1800],
                               "score": round(score, 4), "method": "office-db"})
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:limit]

    def _planner_prompt(self, message: str, retrieved: list[dict], state: dict) -> dict | None:
        context = "\n\n".join(
            f"[{item['title']} | {item['source']} | {item['method']}]\n{item['content']}"
            for item in retrieved[:5]
        ) or "Tidak ada dokumen relevan ditemukan. Jangan mengarang fakta kantor."
        state_summary = {
            "employees": [{"id": e["id"], "name": e["name"], "role": e["role"], "room_id": e["room_id"], "status": e["status"]}
                          for e in state.get("employees", [])],
            "rooms": state.get("rooms", ROOMS),
            "pending_tasks": [t for t in state.get("tasks", []) if t.get("status") in ("pending", "in_progress", "blocked")][:15],
        }
        system = """Kamu Arman, Lead Manager dan operator kantor AI. Ubah instruksi owner menjadi rencana aksi.
Keluarkan HANYA JSON valid dengan skema:
{
 "reply": "balasan singkat bahasa Indonesia",
 "actions": [{"tool":"nama_tool","arguments":{...}}],
 "project_command": "instruksi proyek lengkap atau null",
 "meeting_agenda": "agenda atau null",
 "start_meeting": true/false
}
Tool yang diizinkan:
- move_all_employees {room_id}
- move_employee {employee_id, room_id}
- create_meeting {title, attendee_ids, agenda, room_id}
- create_task {title, description, assignee_id, priority}
- generate_weekly_report {days}
- update_task {task_id, status}

Aturan:
- Jalankan tool hanya ketika owner memberi instruksi/perintah, bukan saat bertanya kemungkinan.
- room_id yang valid: owner, meeting, manager, planning, architect, backend, api, frontend, qa, lounge, kitchen.
- ID karyawan harus salah satu: lead, coo, architect, backend, api, frontend, qa.
- Jangan membuat ID atau nama tool baru.
- Instruksi mengumpulkan seluruh tim ke rapat harus menghasilkan move_all_employees ke meeting dan create_meeting dengan semua ID karyawan.
- Instruksi membuat laporan minggu ini harus menghasilkan generate_weekly_report dengan days=7.
- Instruksi membuat website/aplikasi harus isi project_command dengan instruksi owner yang jelas; jangan mengaku kode sudah selesai. Buat action create_task untuk pembagian peran bila diminta mengarahkan/membagi tugas tim.
- Gunakan knowledge context hanya jika relevan. Jangan mengarang isi dokumen.
- Jika tidak perlu aksi, actions harus kosong dan project_command null.
- Maksimal 8 actions. Balasan harus jujur: sebutkan aksi yang direncanakan, bukan hasil sebelum tool sukses.
"""
        user = f"INSTRUKSI OWNER:\n{message}\n\nKONTEKS KNOWLEDGE (RAG):\n{context}\n\nSTATE KANTOR SAAT INI:\n{json.dumps(state_summary, ensure_ascii=False)}"
        llm = make_llm(model_for("lead"), temperature=0.1)
        output = llm.call([{"role": "system", "content": system}, {"role": "user", "content": user}])
        return _extract_json(output)

    def _fallback_plan(self, message: str) -> dict:
        actions: list[dict] = []
        lower = message.lower()
        meeting_agenda = None
        start_meeting = False
        if _is_gather_request(message):
            room_id = _room_from_text(message, "meeting")
            actions.append({"tool": "move_all_employees", "arguments": {"room_id": room_id}})
            if room_id == "meeting" or any(x in lower for x in ("rapat", "meeting", "briefing")):
                meeting_agenda = message[:700]
                actions.append({"tool": "create_meeting", "arguments": {
                    "title": "Briefing Tim Bangkah", "attendee_ids": list(ROSTER),
                    "agenda": meeting_agenda, "room_id": room_id,
                }})
                start_meeting = True

        # Perintah lokasi individu: "Bima pindah ke ruang API" atau "pindahkan Raka ke meeting".
        employee_id = _employee_from_text(message)
        destination = _room_from_text(message, None)
        has_move_intent = bool(re.search(r"\b(pindah|pindahkan|pergi|bawa|tempatkan|arah\w*|move)\b", lower))
        has_destination_phrase = bool(re.search(r"\bke\s+(?:ruang|ruangan|room)\b", lower))
        if employee_id and destination and not _is_gather_request(message) and (has_move_intent or has_destination_phrase):
            actions.append({"tool": "move_employee", "arguments": {
                "employee_id": employee_id, "room_id": destination,
            }})

        # Instruksi kolektif non-proyek: buat satu task per anggota agar
        # perintah seperti "suruh semua orang siapkan kopi" benar-benar tercatat.
        collective = bool(re.search(r"\b(semua|seluruh|segenap)\b", lower) and
                          re.search(r"\b(karyawan|pegawai|orang|tim|staf|staff)\b", lower))
        collective_verb = bool(re.search(r"\b(suruh|minta|arahkan|perintahkan|instruksikan|tugaskan|kerjakan|siapkan|buat|bikin|susun|periksa|uji|review|rapikan|bersihkan)\b", lower))
        if collective and collective_verb and not _is_gather_request(message) and not _is_report_request(message) and not _project_request(message):
            task_title = re.sub(r"^.*?\b(?:semua|seluruh|segenap)\b.*?\b(?:karyawan|pegawai|orang|tim|staf|staff)\b", "", message, flags=re.I).strip(" :,-")
            task_title = re.sub(r"^(?:untuk|agar|supaya|tolong)\s+", "", task_title, flags=re.I).strip()
            task_title = task_title or message
            if re.search(r"\b(kopi|minum|pantry|dapur)\b", lower):
                actions.append({"tool": "move_all_employees", "arguments": {"room_id": "kitchen"}})
            for member_id, (member_name, _role, _room) in ROSTER.items():
                actions.append({"tool": "create_task", "arguments": {
                    "title": task_title[:120],
                    "description": f"Instruksi kolektif dari owner: {message}",
                    "assignee_id": member_id,
                    "priority": "normal",
                }})

        # Pemberian tugas langsung kepada satu karyawan.
        if not _project_request(message) and re.search(r"\b(beri|berikan|tugaskan|assign)\b", lower) and re.search(r"\b(tugas|task)\b", lower) and employee_id:
            aliases = [ROSTER[employee_id][0], employee_id]
            tail = message
            for alias in aliases:
                match = re.search(re.escape(alias), message, re.I)
                if match:
                    tail = message[match.end():].strip(" :,-")
                    break
            tail = re.sub(r"^(?:untuk|agar|supaya|mengerjakan)\s*", "", tail, flags=re.I).strip()
            if tail:
                actions.append({"tool": "create_task", "arguments": {
                    "title": tail[:120], "description": message,
                    "assignee_id": employee_id, "priority": "normal",
                }})

        if _is_report_request(message):
            days = 7 if any(x in lower for x in ("minggu ini", "mingguan", "weekly")) else 7
            actions.append({"tool": "generate_weekly_report", "arguments": {"days": days}})
        project_command = message if _project_request(message) else None
        return {"reply": "Saya akan menjalankan instruksi yang bisa dieksekusi dan mencatat hasilnya.",
                "actions": actions, "project_command": project_command,
                "meeting_agenda": meeting_agenda, "start_meeting": start_meeting}

    def _normalize_plan(self, plan: dict, message: str) -> dict:
        clean_actions = []
        for action in plan.get("actions", []) if isinstance(plan.get("actions"), list) else []:
            if not isinstance(action, dict):
                continue
            tool = str(action.get("tool", ""))
            args = action.get("arguments", {})
            if tool in ALLOWED_ACTIONS and isinstance(args, dict):
                clean_actions.append({"tool": tool, "arguments": args})
            if len(clean_actions) >= 8:
                break
        project_command = plan.get("project_command")
        if not isinstance(project_command, str) or not project_command.strip():
            project_command = message if _project_request(message) else None
        if project_command:
            clean_actions = [item for item in clean_actions if item["tool"] != "create_task"]
        meeting_agenda = plan.get("meeting_agenda")
        return {
            "reply": str(plan.get("reply") or "Instruksi sudah saya analisis.")[:1500],
            "actions": clean_actions,
            "project_command": project_command[:3000] if project_command else None,
            "meeting_agenda": str(meeting_agenda or message)[:700] if (plan.get("start_meeting") or any(x["tool"] == "create_meeting" for x in clean_actions)) else None,
            "start_meeting": bool(plan.get("start_meeting") or any(x["tool"] == "create_meeting" for x in clean_actions)),
        }

    def _create_project_tasks(self, project_command: str):
        project_name = re.sub(r"\s+", " ", project_command).strip()[:110]
        created = []
        for employee_id, label, description in ROLE_TASKS:
            task = TOOLS.execute("create_task", {
                "title": f"{label}: {project_name}",
                "description": f"Proyek: {project_command}\nTanggung jawab: {description}",
                "assignee_id": employee_id,
                "priority": "high",
            }, actor="lead")
            created.append(task)
        return created

    def _start_meeting_discussion(self, meeting: dict, agenda: str):
        thread = threading.Thread(
            target=self._run_meeting_discussion,
            args=(meeting, agenda),
            name=f"office-meeting-{meeting['id'][:8]}", daemon=True,
        )
        self._meeting_threads.add(thread)
        thread.start()

    def _run_meeting_discussion(self, meeting: dict, agenda: str):
        room_id = meeting.get("room_id", "meeting")
        participants = meeting.get("attendee_ids") or list(ROSTER)
        rag = KNOWLEDGE.search(agenda, limit=4)
        rag_context = "\n\n".join(x["content"] for x in rag)[:5000]
        try:
            lead_prompt = (
                "Kamu Arman, Lead Manager. Buat briefing singkat 2-3 kalimat untuk rapat tim. "
                "Sebutkan tujuan, pembagian fokus, dan koordinasi. Jangan mengaku pekerjaan selesai.\n"
                f"Agenda: {agenda}\nKonteks basis pengetahuan: {rag_context}"
            )
            lead_message = str(make_llm(model_for("lead"), temperature=0.25).call([
                {"role": "system", "content": "Kamu adalah Lead Manager kantor Bangkah AI."},
                {"role": "user", "content": lead_prompt},
            ])).strip()
            if lead_message:
                STORE.add_chat_message("team", "lead", "Arman", "agent", lead_message,
                                       message_type="meeting_message")
                STORE.record_interaction("lead", None, lead_message, room_id, "meeting_briefing", 120)
        except Exception as exc:
            STORE.add_event("meeting_agent_error", "lead", f"Briefing gagal dibuat: {exc}", meeting.get("id"))
            return

        previous_speaker_id = "lead"
        previous_speaker_name = "Arman"
        previous_message = lead_message
        for employee_id in participants:
            if employee_id == "lead" or employee_id not in EMPLOYEES:
                continue
            employee = EMPLOYEES[employee_id]
            try:
                prompt = (
                    f"Kamu {employee['name']}, {employee['role']}. Kamu sedang rapat dengan tim Bangkah. "
                    f"Tanggapi pesan {previous_speaker_name} secara langsung dalam 1-2 kalimat. "
                    "Sampaikan keputusan, pertanyaan, atau langkah konkret sesuai peranmu. "
                    "Jangan mengaku sudah mengerjakan sesuatu yang belum dilakukan.\n"
                    f"Agenda: {agenda}\nPesan {previous_speaker_name}: {previous_message}\n"
                    f"Konteks pengetahuan: {rag_context}"
                )
                reply = str(make_llm(employee["model"], temperature=0.35).call([
                    {"role": "system", "content": f"Kamu adalah {employee['name']} ({employee['role']}) di Bangkah AI Office. Berkomunikasilah langsung dengan rekan yang mengirim pesan."},
                    {"role": "user", "content": prompt},
                ])).strip()
                if reply:
                    STORE.add_chat_message("team", employee_id, employee["name"], "agent", reply,
                                           message_type="meeting_reply")
                    STORE.record_interaction(employee_id, previous_speaker_id, reply, room_id, "meeting_reply", 120)
                    previous_speaker_id = employee_id
                    previous_speaker_name = employee["name"]
                    previous_message = reply
            except Exception as exc:
                STORE.add_event("meeting_agent_error", employee_id,
                                f"Respons rapat {employee['name']} gagal dibuat: {exc}", meeting.get("id"))
            time.sleep(0.4)

    def handle_employee_chat(self, employee_id: str, message: str) -> dict:
        """Handle owner DMs. Arman uses the full office orchestrator; specialists
        can execute bounded self/explicit assignment actions through the same tool layer."""
        if employee_id not in EMPLOYEES:
            raise ValueError("Karyawan tidak dikenal.")
        if employee_id == "lead":
            return self.handle_chat(message)

        state = STORE.snapshot()
        retrieved = KNOWLEDGE.search(message, limit=4)
        retrieved.extend(self._search_office_history(message, state, limit=3))
        retrieved.sort(key=lambda x: x.get("score", 0), reverse=True)
        actions, errors = [], []
        lower = message.lower()
        destination = _room_from_text(message, None)
        target_id = _employee_from_text(message) or employee_id
        move_intent = bool(re.search(r"\b(pindah|pindahkan|pergi|bawa|tempatkan|move)\b", lower))
        if destination and (move_intent or re.search(r"\bke\s+(?:ruang|ruangan|room)\b", lower)):
            try:
                result = TOOLS.execute("move_employee", {"employee_id": target_id, "room_id": destination}, actor=employee_id)
                actions.append({"tool": "move_employee", "result": result})
            except Exception as exc:
                errors.append({"tool": "move_employee", "error": str(exc)})

        task_intent = bool(re.search(r"\b(kerjakan|buatkan|bikinkan|siapkan|susun|implementasikan|tangani|uji|periksa|review|bangun)\b", lower))
        is_question = _is_question_only(message) or message.strip().endswith("?")
        if task_intent and not is_question:
            title = re.sub(r"^(?:hai|halo|hei)?\s*(?:\w+[, :]\s*)?", "", message, flags=re.I).strip()[:120]
            try:
                result = TOOLS.execute("create_task", {
                    "title": title or f"Tugas dari owner untuk {EMPLOYEES[employee_id]['name']}",
                    "description": message,
                    "assignee_id": target_id,
                    "priority": "normal",
                }, actor=employee_id)
                actions.append({"tool": "create_task", "result": result})
            except Exception as exc:
                errors.append({"tool": "create_task", "error": str(exc)})

        employee = EMPLOYEES[employee_id]
        rag_context = "\n\n".join(f"[{x['title']} | {x['source']}]\n{x['content']}" for x in retrieved[:4])
        office_context = json.dumps({
            "employee": {"id": employee_id, "name": employee["name"], "role": employee["role"]},
            "my_room": next((e["room_id"] for e in state.get("employees", []) if e["id"] == employee_id), "unknown"),
            "pending_tasks": [t for t in state.get("tasks", []) if t.get("assignee_id") == employee_id and t.get("status") in ("pending", "in_progress")][:8],
        }, ensure_ascii=False)
        prompt = (
            f"Kamu {employee['name']}, {employee['role']} di Bangkah AI Office. Balas owner dalam bahasa Indonesia, "
            "singkat, natural, dan jujur. Kamu terhubung ke sistem kantor. Jika aksi sudah tercantum dalam hasil tool, "
            "konfirmasikan hanya aksi tersebut. Jika owner memberi tugas yang belum dapat dijalankan otomatis, "
            "jelaskan bahwa tugas sudah dicatat atau minta detail yang dibutuhkan. Jangan pernah mengatakan tidak punya akses ke kantor.\n\n"
            f"STATE: {office_context}\nKNOWLEDGE: {rag_context or 'Tidak ada konteks relevan.'}\nPESAN OWNER: {message}"
        )
        try:
            from config import make_llm
            answer = str(make_llm(employee["model"], temperature=0.35).call([
                {"role": "system", "content": f"Kamu {employee['name']} ({employee['role']})."},
                {"role": "user", "content": prompt},
            ])).strip()
        except Exception:
            if actions:
                answer = "Instruksi sudah saya teruskan ke sistem kantor dan perubahan tercatat."
            else:
                answer = f"Saya menerima pesanmu. Saya {employee['name']}, {employee['role']}. Apa hasil atau detail yang perlu saya siapkan?"
        if actions:
            names = [item["tool"] for item in actions]
            answer = f"Sudah saya jalankan: {', '.join(names)}. " + answer
        return {"reply": answer[:3000], "actions": actions, "errors": errors,
                "requires_approval": False, "project_command": None,
                "rag_sources": [{"title": x["title"], "source": x["source"], "score": x["score"], "method": x["method"]} for x in retrieved]}

    def start_group_replies(self, message: str):
        thread = threading.Thread(target=self._run_group_replies, args=(message,),
                                  name="office-team-chat-replies", daemon=True)
        thread.start()

    def _run_group_replies(self, message: str):
        rag = KNOWLEDGE.search(message, limit=3)
        context = "\n\n".join(item["content"] for item in rag)[:3000] or "Tidak ada dokumen relevan."
        for employee_id, employee in EMPLOYEES.items():
            if employee_id == "lead":
                continue
            try:
                prompt = (
                    f"Kamu {employee['name']}, {employee['role']}. Owner mengirim pesan ke kanal seluruh tim. "
                    "Berikan tanggapan singkat 1-3 kalimat sesuai peranmu. Jika berupa perintah, sebutkan langkah konkret "
                    "yang menjadi tanggung jawabmu. Jangan mengaku pekerjaan sudah selesai.\n"
                    f"Pesan owner: {message}\nKonteks: {context}"
                )
                reply = str(make_llm(employee["model"], temperature=0.35).call([
                    {"role": "system", "content": f"Kamu {employee['name']} di Bangkah AI Office."},
                    {"role": "user", "content": prompt},
                ])).strip()
                if reply:
                    STORE.add_chat_message("team", employee_id, employee["name"], "agent", reply,
                                           message_type="agent_reply")
                    current = next((x for x in STORE.snapshot()["employees"] if x["id"] == employee_id), None)
                    STORE.record_interaction(employee_id, "lead", reply,
                                             (current or {}).get("room_id"), "group_chat_reply", 45)
            except Exception as exc:
                STORE.add_event("group_chat_agent_error", employee_id,
                                f"Balasan grup gagal dibuat: {str(exc)[:220]}")

    def _answer_chat(self, message: str, retrieved: list[dict]) -> str:
        rag_context = "\n\n".join(
            f"[{item['title']} | {item['source']}]\n{item['content']}" for item in retrieved[:5]
        ) or "Tidak ada dokumen relevan ditemukan di Knowledge Base. Jika informasi tidak ada, katakan belum tersedia."
        snapshot = STORE.snapshot()
        recent_events = "\n".join(
            f"{event['created_at']} · {event['actor']} · {event['detail']}"
            for event in snapshot.get("events", [])[:12]
        ) or "Belum ada aktivitas kantor tercatat."
        prompt = (
            "Jawab dalam bahasa Indonesia sebagai Arman, Lead Manager Bangkah AI Office. "
            "Gunakan konteks RAG dan ringkasan aktivitas di bawah ini. Jangan mengarang pekerjaan yang belum dilakukan. "
            "Jika owner menyampaikan perintah operasional, jelaskan bahwa perintah itu harus dieksekusi melalui tool; "
            "jangan mengklaim telah melaksanakannya jika belum ada hasil tool.\n\n"
            f"KONTEKS RAG:\n{rag_context}\n\nAKTIVITAS KANTOR TERKINI:\n{recent_events}\n\n"
            f"PESAN OWNER:\n{message}"
        )
        answer = make_llm(model_for("lead"), temperature=0.3).call([
            {"role": "system", "content": "Kamu Arman, Lead Manager yang jujur dan berorientasi tindakan."},
            {"role": "user", "content": prompt},
        ])
        return str(answer or "Saya belum dapat menyusun jawaban saat ini.").strip()[:3000]

    def handle_chat(self, message: str) -> dict:
        state = STORE.snapshot()
        retrieved = KNOWLEDGE.search(message, limit=5)
        retrieved.extend(self._search_office_history(message, state, limit=5))
        retrieved.sort(key=lambda item: item.get("score", 0), reverse=True)
        retrieved = retrieved[:8]
        try:
            raw_plan = self._planner_prompt(message, retrieved, state)
        except Exception:
            raw_plan = None
        plan = self._normalize_plan(raw_plan, message) if raw_plan else self._fallback_plan(message)
        deterministic = self._fallback_plan(message)
        known = {(item["tool"], json.dumps(item["arguments"], sort_keys=True, ensure_ascii=False)) for item in plan["actions"]}
        for item in deterministic["actions"]:
            key = (item["tool"], json.dumps(item["arguments"], sort_keys=True, ensure_ascii=False))
            if key not in known:
                plan["actions"].append(item)
                known.add(key)
        if not plan["project_command"] and deterministic.get("project_command"):
            plan["project_command"] = deterministic["project_command"]
        if deterministic.get("start_meeting"):
            plan["start_meeting"] = True
            plan["meeting_agenda"] = plan.get("meeting_agenda") or deterministic.get("meeting_agenda")
        results, errors = [], []
        meeting_result = None
        for item in plan["actions"]:
            try:
                result = TOOLS.execute(item["tool"], item["arguments"], actor="lead")
                results.append({"tool": item["tool"], "result": result})
                if item["tool"] == "create_meeting":
                    meeting_result = result
            except Exception as exc:
                errors.append({"tool": item["tool"], "error": str(exc)})

        if plan["project_command"]:
            project_tasks = self._create_project_tasks(plan["project_command"])
            results.append({"tool": "create_project_work_plan", "result": {"tasks": project_tasks}})
            plan["start_meeting"] = True
            plan["meeting_agenda"] = plan.get("meeting_agenda") or plan["project_command"]
            if meeting_result is None:
                meeting_result = TOOLS.execute("create_meeting", {
                    "title": "Kickoff Proyek Bangkah", "attendee_ids": list(ROSTER),
                    "agenda": plan["project_command"], "room_id": "meeting",
                }, actor="lead")
                results.append({"tool": "create_meeting", "result": meeting_result})
                TOOLS.execute("move_all_employees", {"room_id": "meeting"}, actor="lead")

        if plan["start_meeting"] and meeting_result is None:
            meeting_result = TOOLS.execute("create_meeting", {
                "title": "Briefing Tim Bangkah", "attendee_ids": list(ROSTER),
                "agenda": plan.get("meeting_agenda") or message, "room_id": "meeting",
            }, actor="lead")
            results.append({"tool": "create_meeting", "result": meeting_result})
            TOOLS.execute("move_all_employees", {"room_id": "meeting"}, actor="lead")

        if plan["start_meeting"] and meeting_result:
            # Make sure the recorded meeting location is the actual room location.
            participants = meeting_result.get("attendee_ids") or list(ROSTER)
            for employee_id in participants:
                current = next((e for e in STORE.snapshot()["employees"] if e["id"] == employee_id), None)
                if current and current["room_id"] != meeting_result.get("room_id", "meeting"):
                    STORE.move_employee(employee_id, meeting_result.get("room_id", "meeting"), actor="lead")
            self._start_meeting_discussion(meeting_result, plan.get("meeting_agenda") or message)

        if plan["project_command"]:
            plan["reply"] = (
                "Saya sudah membuat pembagian tugas untuk Sinta, Raka, Bima, Naya, Dira, dan Tika, "
                "serta menyiapkan briefing tim. Tugas sudah tercatat sebagai pending. "
                "Untuk mulai membuat source code, setujui tombol 'Mulai pipeline coding' agar CrewAI menjalankan pipeline proyek."
            )
        elif results:
            labels = {
                "move_all_employees": "memindahkan semua karyawan",
                "move_employee": "memindahkan karyawan",
                "create_meeting": "membuat rapat",
                "generate_weekly_report": "membuat laporan",
                "create_task": "membuat tugas",
            }
            completed = [labels.get(x["tool"], x["tool"]) for x in results]
            plan["reply"] = "Sudah saya jalankan: " + ", ".join(completed) + ". Perubahan dan aktivitasnya tercatat di database kantor."
            for item in results:
                if item["tool"] == "generate_weekly_report":
                    path = item["result"].get("report_path")
                    plan["reply"] += f" Laporan tersimpan di {path}."
        elif errors:
            plan["reply"] = "Ada aksi yang belum berhasil: " + "; ".join(x["error"] for x in errors)
        elif not results and not plan["project_command"]:
            if not raw_plan:
                plan["reply"] = self._answer_chat(message, retrieved)

        return {
            "reply": plan["reply"],
            "actions": results,
            "errors": errors,
            "requires_approval": bool(plan["project_command"]),
            "project_command": plan["project_command"],
            "rag_sources": [{"title": x["title"], "source": x["source"], "score": x["score"], "method": x["method"]} for x in retrieved],
        }


ORCHESTRATOR = OfficeOrchestrator()
