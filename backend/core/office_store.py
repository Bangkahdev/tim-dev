"""Persistent operational state for Bangkah AI Office.

This store deliberately keeps office operations separate from LLM conversations.
AI agents may request actions, but validated Python code performs the mutations.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
import uuid
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "office.db"
LOCK = threading.RLock()

ROOMS = {
    "owner": "Ruang Owner",
    "meeting": "Ruang Meeting",
    "manager": "Ruang Lead Manager",
    "planning": "Ruang Project Manager",
    "architect": "Ruang Arsitektur",
    "backend": "Ruang Backend",
    "api": "Ruang API Studio",
    "frontend": "Ruang Frontend",
    "qa": "Ruang Quality Assurance",
    "lounge": "Area Santai",
    "kitchen": "Dapur",
}

ROSTER = {
    "lead": ("Arman", "Lead Manager", "manager"),
    "coo": ("Sinta", "COO / Project Manager", "planning"),
    "architect": ("Raka", "System Architect", "architect"),
    "backend": ("Bima", "Backend Developer", "backend"),
    "api": ("Naya", "API Specialist", "api"),
    "frontend": ("Dira", "Frontend Developer", "frontend"),
    "qa": ("Tika", "QA Engineer", "qa"),
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class OfficeStore:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _initialize(self):
        with LOCK, self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name TEXT PRIMARY KEY, applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS employees (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
                    room_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'idle',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS owner_player_state (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    x REAL NOT NULL DEFAULT 50,
                    y REAL NOT NULL DEFAULT 90,
                    room_id TEXT NOT NULL DEFAULT 'corridor',
                    activity TEXT NOT NULL DEFAULT 'idle',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                    assignee_id TEXT, status TEXT NOT NULL DEFAULT 'pending',
                    priority TEXT NOT NULL DEFAULT 'normal', created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(assignee_id) REFERENCES employees(id)
                );
                CREATE TABLE IF NOT EXISTS meetings (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, room_id TEXT NOT NULL,
                    agenda TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'scheduled',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meeting_attendees (
                    meeting_id TEXT NOT NULL, employee_id TEXT NOT NULL,
                    PRIMARY KEY(meeting_id, employee_id),
                    FOREIGN KEY(meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
                    FOREIGN KEY(employee_id) REFERENCES employees(id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
                    actor TEXT NOT NULL, entity_id TEXT, detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS employee_interactions (
                    id TEXT PRIMARY KEY,
                    sender_id TEXT NOT NULL,
                    recipient_id TEXT,
                    room_id TEXT,
                    message TEXT NOT NULL,
                    interaction_type TEXT NOT NULL DEFAULT 'conversation',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(sender_id) REFERENCES employees(id),
                    FOREIGN KEY(recipient_id) REFERENCES employees(id)
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    sender_role TEXT NOT NULL DEFAULT 'agent',
                    content TEXT NOT NULL,
                    message_type TEXT NOT NULL DEFAULT 'text',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_channel_created
                    ON chat_messages(channel_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_interactions_created ON employee_interactions(created_at);
                CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            """)
            for employee_id, (name, role, room) in ROSTER.items():
                db.execute("""INSERT OR IGNORE INTO employees
                    (id,name,role,room_id,status,updated_at) VALUES (?,?,?,?,?,?)""",
                    (employee_id, name, role, room, "idle", _now()))

            # Split the old shared Development/Manager rooms into actual departments.
            migration = "split_virtual_office_departments_v1"
            already_applied = db.execute(
                "SELECT 1 FROM schema_migrations WHERE name=?", (migration,)
            ).fetchone()
            if not already_applied:
                db.execute("UPDATE employees SET room_id='planning' WHERE id='coo' AND room_id='manager'")
                db.execute("UPDATE employees SET room_id='architect' WHERE id='architect' AND room_id='development'")
                db.execute("UPDATE employees SET room_id='backend' WHERE id='backend' AND room_id='development'")
                db.execute("INSERT INTO schema_migrations(name,applied_at) VALUES(?,?)", (migration, _now()))

    def _event(self, db, event_type, actor, entity_id, detail):
        db.execute("INSERT INTO events(event_type,actor,entity_id,detail,created_at) VALUES(?,?,?,?,?)",
                   (event_type, actor, entity_id, detail, _now()))

    def snapshot(self):
        with LOCK, self._db() as db:
            now = _now()
            # Jangan biarkan status talking/listening tertinggal setelah bubble kedaluwarsa.
            db.execute("""UPDATE employees SET status='idle',updated_at=?
                WHERE status IN ('talking','listening') AND id NOT IN (
                    SELECT sender_id FROM employee_interactions WHERE expires_at>?
                    UNION SELECT recipient_id FROM employee_interactions
                    WHERE recipient_id IS NOT NULL AND expires_at>?
                    UNION SELECT attendee.id FROM employee_interactions i
                    JOIN employees attendee ON attendee.room_id=i.room_id
                    WHERE i.recipient_id IS NULL AND i.interaction_type='meeting_briefing'
                      AND i.expires_at>? AND attendee.id<>i.sender_id
                    UNION SELECT id FROM employees WHERE EXISTS (
                      SELECT 1 FROM employee_interactions g
                      WHERE g.interaction_type='group_chat' AND g.expires_at>?
                    )
                )""", (now, now, now, now, now))
            employees = [dict(r) for r in db.execute("SELECT * FROM employees ORDER BY id")]
            tasks = [dict(r) for r in db.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100")]
            meetings = [dict(r) for r in db.execute("SELECT * FROM meetings ORDER BY created_at DESC LIMIT 30")]
            events = [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")]
            interactions = [dict(r) for r in db.execute("""SELECT i.*,
                s.name AS sender_name, r.name AS recipient_name
                FROM employee_interactions i
                JOIN employees s ON s.id=i.sender_id
                LEFT JOIN employees r ON r.id=i.recipient_id
                WHERE i.expires_at>? ORDER BY i.created_at DESC LIMIT 100""", (now,))]
        return {"rooms": ROOMS, "employees": employees, "tasks": tasks,
                "meetings": meetings, "events": events, "interactions": interactions}

    def set_employee_status(self, employee_id: str, status: str, detail="", actor="system"):
        allowed = {"idle", "working", "talking", "listening", "completed", "failed", "blocked"}
        if employee_id not in ROSTER:
            raise ValueError("Karyawan tidak dikenal.")
        if status not in allowed:
            raise ValueError("Status karyawan tidak valid.")
        with LOCK, self._db() as db:
            db.execute("UPDATE employees SET status=?,updated_at=? WHERE id=?", (status, _now(), employee_id))
            if detail:
                self._event(db, "employee_status", actor, employee_id,
                            f"{ROSTER[employee_id][0]}: {detail[:240]}")
        return {"employee_id": employee_id, "status": status}

    def record_interaction(self, sender_id: str, recipient_id: str | None, message: str,
                           room_id: str | None = None, interaction_type="conversation", ttl_seconds=60):
        if sender_id not in ROSTER:
            raise ValueError("Pengirim interaksi tidak dikenal.")
        if recipient_id is not None and recipient_id not in ROSTER:
            raise ValueError("Penerima interaksi tidak dikenal.")
        if room_id is not None and room_id not in ROOMS:
            raise ValueError("Ruangan interaksi tidak dikenal.")
        message = str(message or "").strip()
        if not message:
            raise ValueError("Isi percakapan tidak boleh kosong.")
        now_dt = datetime.now().astimezone()
        now = now_dt.isoformat(timespec="seconds")
        expires = (now_dt + timedelta(seconds=max(5, min(int(ttl_seconds), 180)))).isoformat(timespec="seconds")
        interaction_id = str(uuid.uuid4())
        with LOCK, self._db() as db:
            if interaction_type == "group_chat_reply":
                db.execute("UPDATE employee_interactions SET expires_at=? WHERE interaction_type='group_chat' AND expires_at>?",
                           (now, now))
            # Satu giliran aktif untuk broadcast grup; semua anggota menjadi pendengar.
            if interaction_type == "group_chat":
                db.execute("UPDATE employee_interactions SET expires_at=? WHERE interaction_type='group_chat' AND expires_at>?",
                           (now, now))
                db.execute("UPDATE employees SET status='idle',updated_at=? WHERE status IN ('talking','listening')",
                           (now,))
            # Hanya satu giliran bicara aktif per percakapan/ruangan.
            elif room_id:
                db.execute("UPDATE employee_interactions SET expires_at=? WHERE room_id=? AND expires_at>?",
                           (now, room_id, now))
                db.execute("""UPDATE employees SET status='idle',updated_at=?
                    WHERE room_id=? AND status IN ('talking','listening')""", (now, room_id))
            elif recipient_id:
                db.execute("""UPDATE employee_interactions SET expires_at=? WHERE expires_at>? AND
                    ((sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?))""",
                    (now, now, sender_id, recipient_id, recipient_id, sender_id))
                db.execute("""UPDATE employees SET status='idle',updated_at=?
                    WHERE id IN (?,?) AND status IN ('talking','listening')""",
                    (now, sender_id, recipient_id))
            db.execute("""INSERT INTO employee_interactions
                (id,sender_id,recipient_id,room_id,message,interaction_type,created_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (interaction_id, sender_id, recipient_id, room_id, message[:1200], interaction_type, now, expires))
            db.execute("UPDATE employees SET status='talking',updated_at=? WHERE id=?", (now, sender_id))
            if recipient_id:
                db.execute("""UPDATE employees SET status='listening',updated_at=?
                    WHERE id=? AND status NOT IN ('working','failed','blocked')""", (now, recipient_id))
            elif interaction_type == "meeting_briefing" and room_id:
                db.execute("""UPDATE employees SET status='listening',updated_at=?
                    WHERE room_id=? AND id<>? AND status NOT IN ('working','failed','blocked')""",
                    (now, room_id, sender_id))
            elif interaction_type == "group_chat":
                db.execute("""UPDATE employees SET status='listening',updated_at=?
                    WHERE id<>? AND status NOT IN ('working','failed','blocked')""",
                    (now, sender_id))
            receiver = ROSTER[recipient_id][0] if recipient_id else "tim"
            self._event(db, "employee_interaction", sender_id, interaction_id,
                        f"{ROSTER[sender_id][0]} berbicara kepada {receiver}: {message[:180]}")
        return {"id": interaction_id, "sender_id": sender_id, "recipient_id": recipient_id,
                "room_id": room_id, "message": message[:1200], "created_at": now,
                "expires_at": expires}

    def add_chat_message(self, channel_id: str, sender_id: str, sender_name: str,
                         sender_role: str, content: str, message_type="text", metadata=None):
        """Persist chat history for the team channel or one employee DM."""
        if channel_id != "team" and channel_id not in ROSTER:
            raise ValueError("Channel chat tidak dikenal.")
        if sender_id != "owner" and sender_id not in ROSTER:
            raise ValueError("Pengirim chat tidak dikenal.")
        content = str(content or "").strip()
        if not content or len(content) > 8000:
            raise ValueError("Pesan wajib diisi dan maksimal 8.000 karakter.")
        if sender_role not in ("owner", "agent", "system"):
            raise ValueError("Tipe pengirim tidak valid.")
        now = _now()
        message_id = str(uuid.uuid4())
        with LOCK, self._db() as db:
            db.execute("""INSERT INTO chat_messages
                (id,channel_id,sender_id,sender_name,sender_role,content,message_type,metadata_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (message_id, channel_id, sender_id, str(sender_name)[:100], sender_role,
                 content, str(message_type)[:40], json.dumps(metadata or {}, ensure_ascii=False), now))
        return {"id": message_id, "channel_id": channel_id, "sender_id": sender_id,
                "sender_name": str(sender_name)[:100], "sender_role": sender_role,
                "content": content, "message_type": message_type,
                "metadata": metadata or {}, "created_at": now}

    def list_chat_messages(self, channel_id: str, limit=100):
        if channel_id != "team" and channel_id not in ROSTER:
            raise ValueError("Channel chat tidak dikenal.")
        limit = max(1, min(int(limit), 200))
        with LOCK, self._db() as db:
            rows = db.execute("""SELECT * FROM (
                    SELECT rowid AS sequence, * FROM chat_messages WHERE channel_id=?
                    ORDER BY rowid DESC LIMIT ?
                ) ORDER BY sequence ASC""", (channel_id, limit)).fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            item.pop("sequence", None)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            except json.JSONDecodeError:
                item["metadata"] = {}
                item.pop("metadata_json", None)
            messages.append(item)
        return messages

    def add_event(self, event_type: str, actor: str, detail: str, entity_id=None):
        with LOCK, self._db() as db:
            self._event(db, event_type, actor, entity_id, str(detail)[:1000])

    def move_employee(self, employee_id: str, room_id: str, actor="owner"):
        if employee_id not in ROSTER:
            raise ValueError("Karyawan tidak dikenal.")
        if room_id not in ROOMS:
            raise ValueError("Ruangan tidak dikenal.")
        with LOCK, self._db() as db:
            db.execute("UPDATE employees SET room_id=?,updated_at=? WHERE id=?", (room_id, _now(), employee_id))
            self._event(db, "employee_moved", actor, employee_id,
                        f"{ROSTER[employee_id][0]} dipindahkan ke {ROOMS[room_id]}.")
        return {"employee_id": employee_id, "room_id": room_id, "room_name": ROOMS[room_id]}

    def move_all(self, room_id: str, actor="owner"):
        if room_id not in ROOMS:
            raise ValueError("Ruangan tidak dikenal.")
        with LOCK, self._db() as db:
            db.execute("UPDATE employees SET room_id=?,updated_at=?", (room_id, _now()))
            self._event(db, "employees_moved", actor, room_id,
                        f"Seluruh karyawan dipindahkan ke {ROOMS[room_id]}.")
        return {"count": len(ROSTER), "room_id": room_id, "room_name": ROOMS[room_id]}

    def create_task(self, title: str, description="", assignee_id=None, priority="normal", actor="owner"):
        title = str(title).strip()
        if not title or len(title) > 200:
            raise ValueError("Judul tugas wajib diisi (maksimal 200 karakter).")
        if assignee_id and assignee_id not in ROSTER:
            raise ValueError("Karyawan penerima tugas tidak dikenal.")
        if priority not in ("low", "normal", "high", "urgent"):
            raise ValueError("Prioritas tugas tidak valid.")
        task_id = str(uuid.uuid4())
        now = _now()
        with LOCK, self._db() as db:
            db.execute("INSERT INTO tasks(id,title,description,assignee_id,status,priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                       (task_id, title, str(description)[:5000], assignee_id, "pending", priority, now, now))
            self._event(db, "task_created", actor, task_id, f"Tugas dibuat: {title}")
        return {"id": task_id, "title": title, "assignee_id": assignee_id,
                "status": "pending", "priority": priority, "created_at": now}

    def update_task(self, task_id: str, status: str, actor="owner"):
        if status not in ("pending", "in_progress", "blocked", "completed", "cancelled", "failed"):
            raise ValueError("Status tugas tidak valid.")
        with LOCK, self._db() as db:
            row = db.execute("SELECT title FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise ValueError("Tugas tidak ditemukan.")
            db.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (status, _now(), task_id))
            self._event(db, "task_updated", actor, task_id, f"Tugas '{row['title']}' berubah menjadi {status}.")
        return {"id": task_id, "status": status}

    def create_meeting(self, title: str, attendee_ids=None, agenda="", room_id="meeting", actor="owner"):
        title = str(title).strip()
        attendee_ids = list(dict.fromkeys(attendee_ids or []))
        if not title or len(title) > 200:
            raise ValueError("Judul rapat wajib diisi (maksimal 200 karakter).")
        if room_id not in ROOMS:
            raise ValueError("Ruangan rapat tidak dikenal.")
        invalid = set(attendee_ids) - set(ROSTER)
        if invalid:
            raise ValueError("Daftar peserta mengandung karyawan tidak dikenal.")
        meeting_id, now = str(uuid.uuid4()), _now()
        with LOCK, self._db() as db:
            db.execute("INSERT INTO meetings(id,title,room_id,agenda,status,created_at) VALUES(?,?,?,?,?,?)",
                       (meeting_id, title, room_id, str(agenda)[:5000], "scheduled", now))
            db.executemany("INSERT INTO meeting_attendees(meeting_id,employee_id) VALUES(?,?)",
                           [(meeting_id, employee_id) for employee_id in attendee_ids])
            self._event(db, "meeting_created", actor, meeting_id, f"Rapat dibuat: {title}")
        return {"id": meeting_id, "title": title, "room_id": room_id,
                "attendee_ids": attendee_ids, "status": "scheduled", "created_at": now}

    def owner_player_state(self):
        """Return the persisted position and activity of the human owner avatar."""
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM owner_player_state WHERE id=1").fetchone()
            if row:
                return dict(row)
            state = {"id": 1, "x": 50.0, "y": 90.0, "room_id": "corridor",
                     "activity": "idle", "updated_at": _now()}
            db.execute("""INSERT OR IGNORE INTO owner_player_state
                (id,x,y,room_id,activity,updated_at) VALUES(1,?,?,?,?,?)""",
                (state["x"], state["y"], state["room_id"], state["activity"], state["updated_at"]))
            return state

    def update_owner_player(self, x, y, room_id="corridor", activity="idle"):
        """Persist movement without generating noisy events for every key frame."""
        try:
            x, y = float(x), float(y)
        except (TypeError, ValueError):
            raise ValueError("Koordinat karakter tidak valid.")
        if not (0 <= x <= 100 and 0 <= y <= 100):
            raise ValueError("Posisi karakter harus berada di dalam kantor.")
        valid_rooms = set(ROOMS) | {"corridor", "entrance"}
        valid_activities = {"idle", "walking", "working", "making_coffee", "meeting", "resting", "viewing_archive"}
        if room_id not in valid_rooms:
            raise ValueError("Lokasi karakter tidak dikenal.")
        if activity not in valid_activities:
            raise ValueError("Aktivitas karakter tidak dikenal.")
        now = _now()
        with LOCK, self._db() as db:
            old = db.execute("SELECT room_id,activity FROM owner_player_state WHERE id=1").fetchone()
            db.execute("""INSERT INTO owner_player_state(id,x,y,room_id,activity,updated_at)
                VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                x=excluded.x,y=excluded.y,room_id=excluded.room_id,
                activity=excluded.activity,updated_at=excluded.updated_at""",
                (x, y, room_id, activity, now))
            if old is None or old["room_id"] != room_id:
                self._event(db, "owner_moved", "owner", "owner", f"Owner berpindah ke {ROOMS.get(room_id, room_id)}.")
        return {"id": 1, "x": x, "y": y, "room_id": room_id, "activity": activity, "updated_at": now}

    def interact_owner(self, target, x=None, y=None, room_id="corridor"):
        """Record a meaningful in-world interaction by the owner avatar."""
        actions = {
            "computer": ("working", "Owner menggunakan workstation untuk membuka pekerjaan dan proyek."),
            "coffee": ("making_coffee", "Owner membuat kopi di pantry."),
            "meeting": ("meeting", "Owner bergabung ke ruang meeting."),
            "lounge": ("resting", "Owner beristirahat di area santai."),
            "archive": ("viewing_archive", "Owner membuka arsip perusahaan Bangkah."),
        }
        if target not in actions:
            raise ValueError("Objek interaksi tidak dikenal.")
        activity, detail = actions[target]
        current = self.owner_player_state()
        state = self.update_owner_player(
            current["x"] if x is None else x,
            current["y"] if y is None else y,
            room_id,
            activity,
        )
        with LOCK, self._db() as db:
            self._event(db, "owner_interaction", "owner", target, detail)
        state["interaction"] = target
        state["detail"] = detail
        return state

    def weekly_report(self, days=7):
        since = (datetime.now().astimezone() - timedelta(days=days)).isoformat(timespec="seconds")
        with LOCK, self._db() as db:
            events = [dict(r) for r in db.execute("SELECT * FROM events WHERE created_at>=? ORDER BY id", (since,))]
            tasks = [dict(r) for r in db.execute("SELECT * FROM tasks WHERE created_at>=? ORDER BY created_at", (since,))]
            counts = {r["status"]: r["n"] for r in db.execute("SELECT status,COUNT(*) n FROM tasks WHERE created_at>=? GROUP BY status", (since,))}
        return {"period_days": days, "since": since, "generated_at": _now(),
                "summary": {"events": len(events), "tasks_created": len(tasks), "task_status": counts},
                "tasks": tasks, "events": events}


STORE = OfficeStore()
