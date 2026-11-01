"""Roster awal. Roster tinggal di database, bukan di kode (ORG-01)."""

from __future__ import annotations

import json

from . import settings
from .db import now

DEPARTMENTS = [
    ("executive", "Eksekutif", "owner", "Ruang Owner"),
    ("front_office", "Front Office", "secretary", "Front Office"),
    ("engineering", "Engineering", "lead", "Lantai Engineering"),
    ("promotion", "Promosi", "promo_manager", "Ruang Promosi"),
]

# id, nama, jabatan, departemen, atasan, ruang, meja, avatar, skills, izin tool
ROSTER = [
    (
        "secretary", "Ayu", "Sekretaris Eksekutif", "executive", "owner",
        "Ruang Sekretaris", "Meja Sekretaris", "🗂️",
        ["penjadwalan", "ringkasan", "korespondensi", "routing perintah"],
        ["*"],
    ),
    (
        "receptionist", "Mira", "Resepsionis", "front_office", "secretary",
        "Front Office", "Meja Resepsionis", "💁",
        ["sambutan tamu", "pencatatan pesan"],
        ["create_task", "log_message", "search_knowledge"],
    ),
    (
        "lead", "Arman", "Lead Manager / AI CTO", "engineering", "secretary",
        "Ruang Lead", "Meja Lead", "🧑🏻‍💼",
        ["kepemimpinan", "tinjauan teknis", "perencanaan"],
        [
            "create_task", "update_task", "move_employee", "create_meeting",
            "generate_report", "create_project", "search_knowledge",
            "print_paper", "deliver_paper",
        ],
    ),
    (
        "coo", "Sinta", "COO / Project Manager", "engineering", "lead",
        "Ruang Perencanaan", "Meja COO", "👩🏽‍💼",
        ["perencanaan", "prioritas", "koordinasi"],
        ["create_task", "update_task", "create_meeting", "generate_report", "search_knowledge", "print_paper", "deliver_paper"],
    ),
    (
        "architect", "Raka", "System Architect", "engineering", "lead",
        "Ruang Arsitek", "Meja Arsitek", "🧑🏼‍💻",
        ["arsitektur", "desain sistem", "integrasi"],
        ["update_task", "search_knowledge", "print_paper", "deliver_paper"],
    ),
    (
        "backend", "Bima", "Backend Developer", "engineering", "lead",
        "Ruang Backend", "Meja Backend", "👩🏽‍💻",
        ["python", "database", "business logic"],
        ["update_task", "search_knowledge", "print_paper", "deliver_paper"],
    ),
    (
        "api", "Naya", "API Specialist", "engineering", "lead",
        "API Studio", "Meja API", "🧑🏽‍💻",
        ["rest", "integrasi", "dokumentasi api"],
        ["update_task", "search_knowledge", "print_paper", "deliver_paper"],
    ),
    (
        "frontend", "Dira", "Frontend Developer", "engineering", "lead",
        "Ruang Frontend", "Meja Frontend", "👩🏻‍🎨",
        ["html", "css", "javascript", "ui"],
        ["update_task", "search_knowledge", "print_paper", "deliver_paper"],
    ),
    (
        "qa", "Tika", "QA Engineer", "engineering", "lead",
        "Quality Assurance", "Meja QA", "🔍",
        ["pengujian", "validasi", "laporan qa"],
        ["update_task", "search_knowledge", "print_paper", "deliver_paper"],
    ),
    (
        "promo_manager", "Bagas", "Manajer Promosi", "promotion", "secretary",
        "Ruang Promosi", "Meja Manajer Promosi", "📣",
        ["strategi kampanye", "penyuntingan", "penjadwalan konten"],
        [
            "create_task", "update_task", "create_meeting", "generate_report",
            "draft_email", "propose_website_publish", "search_knowledge",
            "print_paper", "deliver_paper",
        ],
    ),
    (
        "promo_writer", "Laras", "Content Writer", "promotion", "promo_manager",
        "Ruang Promosi", "Meja Content Writer", "✍️",
        ["copywriting", "artikel", "rilis"],
        ["update_task", "draft_email", "search_knowledge", "print_paper", "deliver_paper"],
    ),
    (
        "promo_social", "Dewi", "Social Media Specialist", "promotion", "promo_manager",
        "Ruang Promosi", "Meja Social Media", "📱",
        ["media sosial", "kalender konten", "analitik"],
        ["update_task", "draft_email", "search_knowledge", "print_paper", "deliver_paper"],
    ),
]


def seed(conn) -> None:
    stamp = now()
    conn.execute(
        """
        INSERT OR IGNORE INTO company (id, name, identity, work_start, work_end, policy, created_at)
        VALUES (1, ?, ?, '09:00', '17:00', ?, ?)
        """,
        (
            "Bangkah",
            "Perusahaan rekayasa perangkat lunak yang dijalankan oleh karyawan AI.",
            json.dumps(
                {
                    "single_owner": True,
                    "language": "id",
                    "external_actions_require_approval": True,
                },
                ensure_ascii=False,
            ),
            stamp,
        ),
    )
    for department_id, name, manager_id, room in DEPARTMENTS:
        conn.execute(
            "INSERT OR IGNORE INTO departments (id, name, manager_id, room, created_at) VALUES (?, ?, ?, ?, ?)",
            (department_id, name, manager_id, room, stamp),
        )
    for (
        employee_id, name, title, department_id, manager_id, room, desk, avatar,
        skills, permissions,
    ) in ROSTER:
        conn.execute(
            """
            INSERT OR IGNORE INTO employees
                (id, name, title, department_id, manager_id, model, skills,
                 tool_permissions, status, room, desk, avatar, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'idle', ?, ?, ?, 1, ?)
            """,
            (
                employee_id, name, title, department_id, manager_id,
                settings.model_for_role(employee_id),
                json.dumps(skills, ensure_ascii=False),
                json.dumps(permissions, ensure_ascii=False),
                room, desk, avatar, stamp,
            ),
        )
        conn.execute(
            "INSERT OR IGNORE INTO employee_states (employee_id, room, activity, source, updated_at) VALUES (?, ?, 'idle', 'task', ?)",
            (employee_id, room, stamp),
        )
    conn.execute(
        "INSERT OR IGNORE INTO player_state (id, room, activity, updated_at) VALUES (1, 'owner_room', 'idle', ?)",
        (stamp,),
    )
