"""Balasan percakapan dengan persona karyawan dan riwayat persisten."""

from __future__ import annotations

import re
from typing import Any

from . import chat, org
from .db import fetch_all, fetch_one

CHAT_STYLE_RULES = (
    "Aturan menjawab:\n"
    "- Tulis teks biasa seperti pesan chat. Jangan pakai markdown: "
    "tanpa tanda bintang, tanpa tanda #, tanpa huruf tebal, tanpa daftar berpoin.\n"
    "- Bahasa Indonesia yang santai tapi sopan, seperti rekan kerja.\n"
    "- Panjang jawaban mengikuti pesan owner. Sapaan dibalas satu atau dua kalimat pendek.\n"
    "- Jangan menjelaskan peranmu sendiri dan jangan mengulang kata-kata owner atau instruksi ini.\n"
    "- Tanyakan paling banyak satu pertanyaan dalam satu balasan, hanya yang paling penting.\n"
    "- Jangan mengaku sudah mengerjakan sesuatu dan jangan mengarang fakta.\n"
)

LEAD_CHAT_SYSTEM = (
    "Kamu Arman, Lead Manager di sebuah kantor AI yang membuat aplikasi. "
    "Kamu sedang mengobrol langsung dengan owner, yaitu pemilik proyek. "
    "Tim yang bisa kamu arahkan: COO, System Architect, Backend, API, Frontend, dan QA.\n\n"
    + CHAT_STYLE_RULES
    + "- Jangan menyebut pembagian tugas tim sebelum owner menjelaskan proyeknya.\n"
    "- Setelah kebutuhan cukup jelas, ringkas dalam beberapa kalimat biasa, "
    "sebutkan siapa mengerjakan apa, lalu bilang owner bisa menekan tombol mulai kalau sudah setuju."
)


def employee_chat_system(employee: dict[str, Any], context: str) -> str:
    return (
        f"Kamu {employee['name']}, {employee['title']} di sebuah kantor AI yang membuat aplikasi. "
        "Kamu sedang mengobrol langsung dengan owner, yaitu pemilik proyek.\n"
        f"Konteks kantor saat ini: {context}\n\n"
        + CHAT_STYLE_RULES
        + "- Obrolan ini tidak memberimu akses mengubah berkas atau menjalankan pekerjaan. "
        "Kalau owner memberi tugas baru, sampaikan pemahamanmu singkat lalu sarankan "
        "agar arahannya disepakati lewat Lead Manager atau Sekretaris."
    )


def clean_reply(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n")
    value = re.sub(r"```[A-Za-z0-9_-]*\n?", "", value)
    value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value, flags=re.M)
    value = re.sub(r"^\s*[-*+]\s+", "\u2022 ", value, flags=re.M)
    value = re.sub(r"(\*\*|__)(.+?)\1", r"\2", value, flags=re.S)
    value = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"\1", value)
    value = value.replace("`", "")
    value = re.sub(r"^\s*(Lead Manager|Manager|Arman|Sekretaris|Kamu|Owner)\s*:\s*", "", value, flags=re.I)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def history_messages(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, str]]:
    messages = []
    for row in rows[-limit:]:
        role = "user" if row["role"] == "owner" else "assistant"
        messages.append({"role": role, "content": row["content"]})
    return messages


def llm_usage(llm) -> Any:
    getter = getattr(llm, "get_token_usage_summary", None)
    if not getter:
        return None
    try:
        return getter()
    except Exception:
        return None


def _make_llm(model: str, temperature: float):
    from config import make_llm

    return make_llm(model, temperature=temperature)


def lead_reply(conn, message: str) -> dict[str, Any]:
    from config import model_for

    llm = _make_llm(model_for("lead"), 0.4)
    rows = chat.history(conn, thread_type="lead", thread_id="owner-lead", limit=20)
    messages = (
        [{"role": "system", "content": LEAD_CHAT_SYSTEM}]
        + history_messages(rows)
        + [{"role": "user", "content": message}]
    )
    answer = clean_reply(llm.call(messages))
    if not answer:
        raise RuntimeError("Model mengembalikan balasan kosong.")
    chat.append(conn, thread_type="lead", thread_id="owner-lead", sender="owner", role="owner", content=message)
    saved = chat.append(conn, thread_type="lead", thread_id="owner-lead", sender="lead", role="manager", content=answer)
    return {"reply": answer, "message": saved}


def employee_reply(conn, employee_id: str, message: str) -> dict[str, Any]:
    employee = org.get_employee(conn, employee_id)
    if not employee:
        raise ValueError("Karyawan tidak dikenal.")
    llm = _make_llm(employee["model"], 0.45)
    project = fetch_one(conn, "SELECT * FROM projects ORDER BY updated_at DESC LIMIT 1")
    current = fetch_one(
        conn,
        "SELECT title, status FROM tasks WHERE assignee = ? ORDER BY updated_at DESC LIMIT 1",
        (employee_id,),
    )
    context = (
        f"proyek terkini {project['name'] if project else 'belum ada'}, "
        f"status {project['status'] if project else 'idle'}, "
        f"tugas terakhirmu: {current['title'] + ' (' + current['status'] + ')' if current else 'belum ada tugas tercatat'}"
    )
    rows = chat.history(conn, thread_type="employee", thread_id=employee_id, limit=20)
    messages = (
        [{"role": "system", "content": employee_chat_system(employee, context)}]
        + history_messages(rows)
        + [{"role": "user", "content": message}]
    )
    reply = clean_reply(llm.call(messages))
    if not reply:
        raise RuntimeError("Model mengembalikan balasan kosong.")
    chat.append(conn, thread_type="employee", thread_id=employee_id, sender="owner", role="owner", content=message)
    saved = chat.append(
        conn, thread_type="employee", thread_id=employee_id,
        sender=employee_id, role="employee", content=reply,
    )
    return {"reply": reply, "message": saved, "employee": employee}


def room_reply(conn, room: str, message: str) -> dict[str, Any]:
    rows = fetch_all(conn, "SELECT id, room FROM employees WHERE active = 1")
    match = next((row for row in rows if (row.get("room") or "").lower() == room.lower()), None)
    if match:
        return employee_reply(conn, match["id"], message)
    return lead_reply(conn, message)
