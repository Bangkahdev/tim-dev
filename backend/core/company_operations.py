"""Persistent company operations layered on the legacy office store.

This module provides the local single-owner product workflows: departments,
validated task transitions/evidence, persisted meetings, Papers, print jobs,
immutable approval payloads, an outbox, and audit/event queries.
External delivery is intentionally separate and must be explicitly executed
only after an approval is accepted.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .office_store import OfficeStore, STORE, ROSTER, ROOMS, _now, LOCK

DEPARTMENTS = [
    {"id": "executive", "name": "Executive", "description": "Kepemimpinan dan koordinasi perusahaan."},
    {"id": "engineering", "name": "Engineering", "description": "Perancangan, pengembangan, dan quality assurance software."},
    {"id": "operations", "name": "Operations", "description": "Operasional dan koordinasi proyek."},
    {"id": "front_office", "name": "Front Office", "description": "Resepsionis dan layanan tamu."},
    {"id": "promotion", "name": "Promotion", "description": "Distribusi dan promosi hasil proyek yang telah disetujui."},
]
EMPLOYEE_DEPARTMENTS = {
    "lead": "executive", "coo": "operations", "architect": "engineering",
    "backend": "engineering", "api": "engineering", "frontend": "engineering", "qa": "engineering",
}
TASK_TRANSITIONS = {
    "pending": {"in_progress", "cancelled"},
    "in_progress": {"blocked", "completed", "failed", "cancelled"},
    "blocked": {"in_progress", "cancelled", "failed"},
    "failed": {"pending"},
    "completed": set(),
    "cancelled": set(),
}
PAPER_STATUSES = {"unread", "read", "deferred", "approved", "rejected", "archived"}
APPROVAL_ACTIONS = {"email.send", "website.deploy", "expense.purchase"}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def hmac_compare(left: str, right: str) -> bool:
    # Constant-time comparison for persisted integrity digests.
    import hmac
    return hmac.compare_digest(str(left), str(right))


class CompanyOperations:
    def __init__(self, store: OfficeStore = STORE):
        self.store = store
        self.db_path = store.db_path
        self.print_dir = self.db_path.parent / "prints"
        self.print_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _db(self):
        return self.store._db()

    def _initialize(self):
        with LOCK, self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS department_catalog (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_meta (
                    task_id TEXT PRIMARY KEY, project_key TEXT NOT NULL DEFAULT '',
                    acceptance_criteria TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS task_evidence (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL, evidence_type TEXT NOT NULL,
                    reference TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS meeting_meta (
                    meeting_id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT,
                    minutes TEXT NOT NULL DEFAULT '', decisions_json TEXT NOT NULL DEFAULT '[]',
                    followups_json TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL,
                    FOREIGN KEY(meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS paper_records (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, paper_type TEXT NOT NULL,
                    origin TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'normal',
                    status TEXT NOT NULL DEFAULT 'unread', body TEXT NOT NULL,
                    related_task_id TEXT, approval_id TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approval_records (
                    id TEXT PRIMARY KEY, action_type TEXT NOT NULL, summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', reviewer TEXT,
                    review_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    reviewed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS outbox_records (
                    id TEXT PRIMARY KEY, approval_id TEXT NOT NULL UNIQUE,
                    action_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                    attempts INTEGER NOT NULL DEFAULT 0, external_id TEXT,
                    last_error TEXT NOT NULL DEFAULT '', result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(approval_id) REFERENCES approval_records(id)
                );
                CREATE TABLE IF NOT EXISTS print_jobs (
                    id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, status TEXT NOT NULL,
                    output_path TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, completed_at TEXT,
                    FOREIGN KEY(paper_id) REFERENCES paper_records(id)
                );
                CREATE INDEX IF NOT EXISTS idx_papers_status ON paper_records(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_approvals_status ON approval_records(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_records(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_print_jobs_created ON print_jobs(created_at);
                CREATE TRIGGER IF NOT EXISTS approval_payload_immutable
                BEFORE UPDATE OF action_type,summary,payload_json,payload_sha256 ON approval_records
                BEGIN SELECT RAISE(ABORT, 'approval payload is immutable'); END;
            """)
            for department in DEPARTMENTS:
                db.execute("INSERT OR IGNORE INTO department_catalog(id,name,description) VALUES(?,?,?)",
                           (department["id"], department["name"], department["description"]))

    def _event(self, db, kind: str, actor: str, entity_id: str | None, detail: str):
        self.store._event(db, kind, actor, entity_id, str(detail)[:1000])

    def departments(self):
        with LOCK, self._db() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM department_catalog ORDER BY name")]
            counts = {d["id"]: 0 for d in rows}
            for employee_id, department_id in EMPLOYEE_DEPARTMENTS.items():
                if department_id in counts:
                    counts[department_id] += 1
            for row in rows:
                row["employee_count"] = counts.get(row["id"], 0)
            return rows

    def employees(self):
        snapshot = self.store.snapshot()
        tasks_by_employee = {}
        for task in snapshot["tasks"]:
            if task.get("assignee_id") and task.get("status") in ("pending", "in_progress", "blocked"):
                tasks_by_employee.setdefault(task["assignee_id"], task)
        results = []
        for employee in snapshot["employees"]:
            row = dict(employee)
            row["department_id"] = EMPLOYEE_DEPARTMENTS.get(row["id"], "engineering")
            row["department_name"] = next((x["name"] for x in DEPARTMENTS if x["id"] == row["department_id"]), "Engineering")
            row["active_task"] = tasks_by_employee.get(row["id"])
            results.append(row)
        return results

    def tasks(self):
        items = self.store.snapshot()["tasks"]
        with LOCK, self._db() as db:
            meta = {row["task_id"]: dict(row) for row in db.execute("SELECT * FROM task_meta")}
            evidence = {}
            for row in db.execute("SELECT * FROM task_evidence ORDER BY created_at"):
                evidence.setdefault(row["task_id"], []).append(dict(row))
        for item in items:
            item.update(meta.get(item["id"], {}))
            item["evidence"] = evidence.get(item["id"], [])
        return items

    def create_task(self, title, description="", assignee_id=None, priority="normal",
                    project_key="", acceptance_criteria="", actor="owner"):
        task = self.store.create_task(title, description, assignee_id, priority, actor)
        with LOCK, self._db() as db:
            db.execute("INSERT INTO task_meta(task_id,project_key,acceptance_criteria) VALUES(?,?,?)",
                       (task["id"], str(project_key)[:120], str(acceptance_criteria)[:4000]))
        return task

    def transition_task(self, task_id: str, target: str, evidence=None, note="", actor="owner"):
        evidence = evidence or []
        if not isinstance(evidence, list):
            raise ValueError("Evidence harus berupa daftar.")
        with LOCK, self._db() as db:
            row = db.execute("SELECT status,title FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Tugas tidak ditemukan.")
            current = row["status"]
            if target not in TASK_TRANSITIONS.get(current, set()):
                raise ValueError(f"Transisi status tidak diizinkan: {current} → {target}.")
            if target == "completed" and not evidence:
                raise ValueError("Tugas tidak dapat diselesaikan tanpa bukti hasil.")
            parsed_evidence = []
            for item in evidence:
                if not isinstance(item, dict):
                    raise ValueError("Setiap evidence harus berupa objek.")
                kind = str(item.get("type", "note"))[:30]
                reference = str(item.get("reference", "")).strip()
                detail = str(item.get("note", "")).strip()
                if not reference or len(reference) > 1000:
                    raise ValueError("Evidence membutuhkan reference maksimal 1000 karakter.")
                parsed_evidence.append((str(uuid.uuid4()), task_id, kind, reference, detail[:1000], _now()))
            now = _now()
            db.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (target, now, task_id))
            if parsed_evidence:
                db.executemany("""INSERT INTO task_evidence
                    (id,task_id,evidence_type,reference,note,created_at) VALUES(?,?,?,?,?,?)""", parsed_evidence)
            if note:
                self._event(db, "task_transition", actor, task_id,
                            f"Tugas '{row['title']}' berubah {current} → {target}: {str(note)[:600]}")
            else:
                self._event(db, "task_transition", actor, task_id,
                            f"Tugas '{row['title']}' berubah {current} → {target}.")
        return {"id": task_id, "status": target, "evidence_added": len(parsed_evidence)}

    def meetings(self):
        items = self.store.snapshot()["meetings"]
        with LOCK, self._db() as db:
            metadata = {r["meeting_id"]: dict(r) for r in db.execute("SELECT * FROM meeting_meta")}
            attendees = {}
            for row in db.execute("SELECT meeting_id,employee_id FROM meeting_attendees"):
                attendees.setdefault(row["meeting_id"], []).append(row["employee_id"])
        for item in items:
            item.update(metadata.get(item["id"], {}))
            item["decisions"] = json.loads(item.pop("decisions_json", "[]") or "[]")
            item["followups"] = json.loads(item.pop("followups_json", "[]") or "[]")
            item["attendee_ids"] = attendees.get(item["id"], [])
        return items

    def create_meeting(self, title, attendee_ids=None, agenda="", room_id="meeting", actor="owner"):
        meeting = self.store.create_meeting(title, attendee_ids, agenda, room_id, actor)
        with LOCK, self._db() as db:
            db.execute("INSERT INTO meeting_meta(meeting_id,updated_at) VALUES(?,?)", (meeting["id"], _now()))
        return meeting

    def update_meeting(self, meeting_id: str, action: str, minutes="", decisions=None, followups=None, actor="owner"):
        allowed = {"start": ("scheduled", "in_progress"), "complete": ("in_progress", "completed"),
                   "cancel": (("scheduled", "in_progress"), "cancelled")}
        if action not in allowed:
            raise ValueError("Aksi rapat tidak valid.")
        with LOCK, self._db() as db:
            meeting = db.execute("SELECT title,status FROM meetings WHERE id=?", (meeting_id,)).fetchone()
            if meeting is None:
                raise ValueError("Rapat tidak ditemukan.")
            source, target = allowed[action]
            source_states = source if isinstance(source, tuple) else (source,)
            if meeting["status"] not in source_states:
                raise ValueError("Transisi status rapat tidak diizinkan.")
            if action == "complete" and not str(minutes).strip():
                raise ValueError("Notulen wajib diisi sebelum rapat diselesaikan.")
            now = _now()
            db.execute("UPDATE meetings SET status=? WHERE id=?", (target, meeting_id))
            db.execute("""INSERT OR IGNORE INTO meeting_meta(meeting_id,updated_at)
                VALUES(?,?)""", (meeting_id, now))
            if action == "start":
                db.execute("UPDATE meeting_meta SET started_at=?,updated_at=? WHERE meeting_id=?",
                           (now, now, meeting_id))
            elif action == "complete":
                db.execute("""UPDATE meeting_meta SET ended_at=?,minutes=?,decisions_json=?,
                    followups_json=?,updated_at=? WHERE meeting_id=?""",
                    (now, str(minutes)[:10000], json.dumps(decisions or [], ensure_ascii=False),
                     json.dumps(followups or [], ensure_ascii=False), now, meeting_id))
            else:
                db.execute("UPDATE meeting_meta SET ended_at=?,updated_at=? WHERE meeting_id=?",
                           (now, now, meeting_id))
            self._event(db, "meeting_" + action, actor, meeting_id,
                        f"Rapat '{meeting['title']}' {target}.")
        return next(x for x in self.meetings() if x["id"] == meeting_id)

    def create_paper(self, title, body, paper_type="memo", origin="owner", priority="normal",
                     related_task_id=None, approval_id=None):
        title = str(title).strip()
        body = str(body).strip()
        if not title or len(title) > 240 or not body or len(body) > 30000:
            raise ValueError("Judul dan isi dokumen wajib diisi (maksimal 30.000 karakter).")
        if priority not in ("low", "normal", "high", "urgent"):
            raise ValueError("Prioritas dokumen tidak valid.")
        if related_task_id:
            exists = any(t["id"] == related_task_id for t in self.store.snapshot()["tasks"])
            if not exists:
                raise ValueError("Tugas terkait tidak ditemukan.")
        if approval_id:
            with LOCK, self._db() as db:
                if db.execute("SELECT 1 FROM approval_records WHERE id=?", (approval_id,)).fetchone() is None:
                    raise ValueError("Approval terkait tidak ditemukan.")
        paper_id, now = "PAP-" + uuid.uuid4().hex[:12].upper(), _now()
        with LOCK, self._db() as db:
            db.execute("""INSERT INTO paper_records
                (id,title,paper_type,origin,priority,status,body,related_task_id,approval_id,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (paper_id, title, str(paper_type)[:60], str(origin)[:120], priority, "unread",
                 body, related_task_id, approval_id, now, now))
            self._event(db, "paper_created", "owner", paper_id, f"Paper dibuat: {title}")
        return self.get_paper(paper_id)

    def list_papers(self, status=None, limit=100):
        limit = max(1, min(int(limit), 200))
        with LOCK, self._db() as db:
            if status and status in PAPER_STATUSES:
                rows = db.execute("SELECT * FROM paper_records WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM paper_records ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows]

    def get_paper(self, paper_id):
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM paper_records WHERE id=?", (paper_id,)).fetchone()
            if row is None:
                raise ValueError("Dokumen tidak ditemukan.")
            return dict(row)

    def update_paper_status(self, paper_id, status, actor="owner"):
        if status not in PAPER_STATUSES:
            raise ValueError("Status paper tidak valid.")
        with LOCK, self._db() as db:
            row = db.execute("SELECT title,status,approval_id FROM paper_records WHERE id=?", (paper_id,)).fetchone()
            if row is None:
                raise ValueError("Dokumen tidak ditemukan.")
            if status in ("approved", "rejected") and row["approval_id"]:
                raise ValueError("Dokumen terkait approval harus diputuskan melalui endpoint approval.")
            db.execute("UPDATE paper_records SET status=?,updated_at=? WHERE id=?", (status, _now(), paper_id))
            self._event(db, "paper_status", actor, paper_id,
                        f"Paper '{row['title']}' berubah {row['status']} → {status}.")
        return self.get_paper(paper_id)

    def create_approval(self, action_type, summary, payload, actor="owner"):
        if action_type not in APPROVAL_ACTIONS:
            raise ValueError("Jenis aksi approval tidak tersedia.")
        if not isinstance(payload, dict) or not payload:
            raise ValueError("Payload approval wajib berupa objek yang tidak kosong.")
        self._validate_action_payload(action_type, payload)
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        approval_id, now = "APR-" + uuid.uuid4().hex[:12].upper(), _now()
        with LOCK, self._db() as db:
            db.execute("""INSERT INTO approval_records
                (id,action_type,summary,payload_json,payload_sha256,status,created_at)
                VALUES(?,?,?,?,?,'pending',?)""",
                (approval_id, action_type, str(summary).strip()[:500] or action_type,
                 canonical, digest, now))
            self._event(db, "approval_requested", actor, approval_id,
                        f"Persetujuan diperlukan: {action_type} · {str(summary)[:300]}")
        return self.get_approval(approval_id, include_payload=True)

    @staticmethod
    def _validate_action_payload(action_type, payload):
        forbidden = {"password", "token", "secret", "api_key", "private_key"}
        def walk(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if str(key).lower() in forbidden or any(x in str(key).lower() for x in ("password", "secret", "api_key", "private_key")):
                        raise ValueError("Rahasia/kredensial tidak boleh disimpan dalam payload approval.")
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(payload)
        if action_type == "email.send":
            recipients = payload.get("to")
            recipients = recipients if isinstance(recipients, list) else [recipients]
            if not recipients or len(recipients) > 25 or any(not isinstance(x, str) or not EMAIL_RE.match(x) for x in recipients):
                raise ValueError("Email penerima tidak valid (maksimal 25 penerima).")
            subject = str(payload.get("subject", "")).strip()
            body = str(payload.get("body", "")).strip()
            if not subject or len(subject) > 250 or not body or len(body) > 50000:
                raise ValueError("Email membutuhkan subject (maksimal 250 karakter) dan body (maksimal 50.000 karakter).")
        elif action_type == "website.deploy":
            from urllib.parse import urlparse
            target = str(payload.get("target", "production"))
            repository = str(payload.get("repository", "")).strip()
            if target not in ("staging", "production"):
                raise ValueError("Target deployment harus staging atau production.")
            if not repository or len(repository) > 500 or not str(payload.get("ref", "")).strip():
                raise ValueError("Deployment membutuhkan repository dan ref.")
            parsed = urlparse(repository)
            if parsed.scheme not in ("https", "ssh") or not parsed.netloc:
                raise ValueError("Repository deployment harus berupa URL HTTPS atau SSH yang valid.")
            if not re.match(r"^[A-Za-z0-9._/-]{1,200}$", str(payload["ref"])):
                raise ValueError("Ref deployment mengandung karakter tidak valid.")
        elif action_type == "expense.purchase":
            import math
            try:
                amount = float(payload.get("amount", 0))
            except (TypeError, ValueError):
                amount = 0
            currency = str(payload.get("currency", "IDR")).upper()
            if not math.isfinite(amount) or amount <= 0 or not re.match(r"^[A-Z]{3}$", currency) or not str(payload.get("vendor", "")).strip():
                raise ValueError("Pengeluaran membutuhkan vendor, kode mata uang, dan jumlah positif.")

    def get_approval(self, approval_id, include_payload=False):
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM approval_records WHERE id=?", (approval_id,)).fetchone()
            if row is None:
                raise ValueError("Approval tidak ditemukan.")
            result = dict(row)
            if include_payload:
                result["payload"] = json.loads(result.pop("payload_json"))
            else:
                result.pop("payload_json", None)
            return result

    def list_approvals(self, status=None, limit=100, include_payload=False):
        limit = max(1, min(int(limit), 200))
        with LOCK, self._db() as db:
            if status in ("pending", "approved", "rejected"):
                rows = db.execute("SELECT * FROM approval_records WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM approval_records ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                payload_json = item.pop("payload_json")
                if include_payload:
                    item["payload"] = json.loads(payload_json)
                results.append(item)
            return results

    def decide_approval(self, approval_id, decision, reviewer="owner", note=""):
        if decision not in ("approve", "reject"):
            raise ValueError("Keputusan approval tidak valid.")
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM approval_records WHERE id=?", (approval_id,)).fetchone()
            if row is None:
                raise ValueError("Approval tidak ditemukan.")
            if row["status"] != "pending":
                raise ValueError("Approval sudah diputuskan dan tidak dapat diubah.")
            now = _now()
            status = "approved" if decision == "approve" else "rejected"
            db.execute("""UPDATE approval_records SET status=?,reviewer=?,review_note=?,reviewed_at=?
                WHERE id=? AND status='pending'""", (status, reviewer, str(note)[:1000], now, approval_id))
            db.execute("UPDATE paper_records SET status=?,updated_at=? WHERE approval_id=?",
                       ("approved" if decision == "approve" else "rejected", now, approval_id))
            if decision == "approve":
                outbox_id = "OUT-" + uuid.uuid4().hex[:12].upper()
                db.execute("""INSERT INTO outbox_records
                    (id,approval_id,action_type,status,created_at,updated_at)
                    VALUES(?,?,?,'queued',?,?)""", (outbox_id, approval_id, row["action_type"], now, now))
            self._event(db, "approval_" + decision, reviewer, approval_id,
                        f"Owner {decision}d: {row['summary']}")
        return self.get_approval(approval_id)

    def list_outbox(self, limit=100):
        limit = max(1, min(int(limit), 200))
        with LOCK, self._db() as db:
            rows = db.execute("""SELECT o.*,a.summary,a.payload_sha256 FROM outbox_records o
                JOIN approval_records a ON a.id=o.approval_id ORDER BY o.created_at DESC LIMIT ?""", (limit,)).fetchall()
            return [dict(row) for row in rows]

    def get_outbox_item(self, outbox_id):
        with LOCK, self._db() as db:
            row = db.execute("""SELECT o.*,a.summary,a.payload_json,a.payload_sha256,a.status AS approval_status
                FROM outbox_records o JOIN approval_records a ON a.id=o.approval_id WHERE o.id=?""", (outbox_id,)).fetchone()
            if row is None:
                raise ValueError("Outbox item tidak ditemukan.")
            result = dict(row)
            payload_json = result.pop("payload_json")
            digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            if not hmac_compare(digest, result["payload_sha256"]):
                raise ValueError("Payload outbox tidak cocok dengan hash approval.")
            result["payload"] = json.loads(payload_json)
            return result

    def claim_outbox(self, outbox_id):
        """Atomically claim one queued/failed outbox record for execution."""
        with LOCK, self._db() as db:
            row = db.execute("SELECT status FROM outbox_records WHERE id=?", (outbox_id,)).fetchone()
            if row is None:
                raise ValueError("Outbox item tidak ditemukan.")
            if row["status"] not in ("queued", "failed", "awaiting_executor"):
                raise ValueError("Outbox item sedang diproses atau tidak dapat diulang.")
            now = _now()
            cursor = db.execute("""UPDATE outbox_records SET status='executing',
                attempts=attempts+1,last_error='',updated_at=? WHERE id=? AND status=?""",
                (now, outbox_id, row["status"]))
            if cursor.rowcount != 1:
                raise ValueError("Outbox item telah diambil oleh proses lain.")
            self._event(db, "outbox_execution_started", "owner", outbox_id,
                        "Owner memulai eksekusi outbox yang telah disetujui.")
        return self.get_outbox_item(outbox_id)

    def update_outbox(self, outbox_id, status, external_id="", error="", result=None):
        if status not in ("succeeded", "failed", "unknown", "awaiting_executor"):
            raise ValueError("Status outbox tidak valid.")
        with LOCK, self._db() as db:
            row = db.execute("SELECT action_type,status FROM outbox_records WHERE id=?", (outbox_id,)).fetchone()
            if row is None:
                raise ValueError("Outbox item tidak ditemukan.")
            db.execute("""UPDATE outbox_records SET status=?,external_id=?,
                last_error=?,result_json=?,updated_at=? WHERE id=?""",
                (status, str(external_id)[:500], str(error)[:1000],
                 json.dumps(result or {}, ensure_ascii=False), _now(), outbox_id))
            self._event(db, "outbox_reconciled", "executor", outbox_id,
                        f"Eksekusi {row['action_type']} berstatus {status}.")
        return next(x for x in self.list_outbox() if x["id"] == outbox_id)

    def create_print_job(self, paper_id):
        paper = self.get_paper(paper_id)
        job_id, now = "PRN-" + uuid.uuid4().hex[:12].upper(), _now()
        with LOCK, self._db() as db:
            db.execute("INSERT INTO print_jobs(id,paper_id,status,created_at) VALUES(?,?,'queued',?)",
                       (job_id, paper_id, now))
            self._event(db, "print_job_created", "owner", job_id, f"Dokumen masuk antrean cetak: {paper['title']}")
        try:
            path = self._render_pdf(paper, job_id)
            with LOCK, self._db() as db:
                db.execute("UPDATE print_jobs SET status='completed',output_path=?,completed_at=? WHERE id=?",
                           (str(path), _now(), job_id))
                self._event(db, "print_job_completed", "printer", job_id, f"PDF selesai dibuat: {paper['title']}")
        except Exception as error:
            with LOCK, self._db() as db:
                db.execute("UPDATE print_jobs SET status='failed',error=?,completed_at=? WHERE id=?",
                           (str(error)[:1000], _now(), job_id))
                self._event(db, "print_job_failed", "printer", job_id, f"Gagal mencetak dokumen: {error}")
            raise ValueError("Dokumen gagal dicetak. Periksa instalasi ReportLab.")
        return self.get_print_job(job_id)

    def _render_pdf(self, paper, job_id):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.pdfbase.pdfmetrics import stringWidth
        path = self.print_dir / f"{job_id}.pdf"
        pdf = canvas.Canvas(str(path), pagesize=A4)
        width, height = A4
        x, y = 22 * mm, height - 24 * mm
        pdf.setFillColor(colors.HexColor("#20332d"))
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(x, y, "BANGKAH  /  COMPANY DOCUMENT")
        y -= 15 * mm
        pdf.setFillColor(colors.HexColor("#18211f"))
        pdf.setFont("Helvetica-Bold", 18)
        for line in self._wrap(paper["title"], "Helvetica-Bold", 18, width - 2*x):
            if y < 24*mm: pdf.showPage(); y = height - 24*mm
            pdf.drawString(x, y, line); y -= 8*mm
        y -= 4*mm
        pdf.setStrokeColor(colors.HexColor("#c5d0ca")); pdf.line(x, y, width-x, y); y -= 10*mm
        pdf.setFont("Helvetica", 9); pdf.setFillColor(colors.HexColor("#53615a"))
        for label, value in (("Jenis", paper["paper_type"]), ("Dari", paper["origin"]),
                             ("Prioritas", paper["priority"].upper()), ("Tanggal", paper["created_at"])):
            pdf.drawString(x, y, f"{label}: {value}"); y -= 5*mm
        y -= 5*mm
        pdf.setFillColor(colors.HexColor("#202825")); pdf.setFont("Helvetica", 10)
        for paragraph in paper["body"].splitlines() or [""]:
            for line in self._wrap(paragraph, "Helvetica", 10, width - 2*x):
                if y < 22*mm: pdf.showPage(); y = height - 22*mm; pdf.setFont("Helvetica", 10)
                pdf.drawString(x, y, line); y -= 5.5*mm
            y -= 2*mm
        pdf.setFont("Helvetica-Oblique", 8); pdf.setFillColor(colors.grey)
        pdf.drawString(x, 12*mm, f"Paper ID: {paper['id']}  ·  Generated by Bangkah HQ")
        pdf.save()
        return path

    @staticmethod
    def _wrap(text, font, size, max_width):
        words = str(text).split()
        lines, line = [], ""
        for word in words:
            candidate = (line + " " + word).strip()
            from reportlab.pdfbase.pdfmetrics import stringWidth
            if line and stringWidth(candidate, font, size) > max_width:
                lines.append(line); line = word
            else:
                line = candidate
        if line or not lines:
            lines.append(line)
        return lines

    def get_print_job(self, job_id):
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM print_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise ValueError("Print job tidak ditemukan.")
            result = dict(row)
        result["download_url"] = f"/api/print-jobs/{job_id}/download" if result["status"] == "completed" else None
        result["output_path"] = Path(result["output_path"]).name if result["output_path"] else ""
        return result

    def print_file_path(self, job_id):
        item = self.get_print_job(job_id)
        if item["status"] != "completed":
            raise ValueError("PDF belum tersedia.")
        candidate = (self.print_dir / f"{job_id}.pdf").resolve()
        try:
            candidate.relative_to(self.print_dir.resolve())
        except ValueError:
            raise ValueError("Path print job tidak valid.")
        if not candidate.is_file():
            raise ValueError("File PDF tidak ditemukan.")
        return candidate

    def list_print_jobs(self, limit=100):
        limit = max(1, min(int(limit), 200))
        with LOCK, self._db() as db:
            ids = [r["id"] for r in db.execute("SELECT id FROM print_jobs ORDER BY created_at DESC LIMIT ?", (limit,))]
        return [self.get_print_job(x) for x in ids]

    def audit(self, after_id=0, limit=100):
        after_id = max(0, int(after_id)); limit = max(1, min(int(limit), 500))
        with LOCK, self._db() as db:
            rows = db.execute("SELECT * FROM events WHERE id>? ORDER BY id LIMIT ?", (after_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def close(self):
        """Compatibility hook for tests; SQLite connections are per operation."""
        return None


OPS = CompanyOperations()
