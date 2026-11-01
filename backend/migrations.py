"""Migrasi database bernomor.

Setiap migrasi hanya ditambahkan, tidak diubah, agar database lama dapat
ditingkatkan tanpa kehilangan riwayat (ORG-06, NFR-MNT-02).
"""

from __future__ import annotations

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS company (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL,
            identity TEXT NOT NULL DEFAULT '',
            work_start TEXT NOT NULL DEFAULT '09:00',
            work_end TEXT NOT NULL DEFAULT '17:00',
            policy TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS departments (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            manager_id TEXT,
            room TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS employees (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            title TEXT NOT NULL,
            department_id TEXT NOT NULL REFERENCES departments(id),
            manager_id TEXT,
            model TEXT NOT NULL DEFAULT '',
            skills TEXT NOT NULL DEFAULT '[]',
            tool_permissions TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'idle',
            room TEXT,
            desk TEXT,
            avatar TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            department_id TEXT,
            workspace_path TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'PLANNED',
            deliverable TEXT NOT NULL DEFAULT '',
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(id),
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            assignee TEXT,
            priority TEXT NOT NULL DEFAULT 'normal',
            status TEXT NOT NULL DEFAULT 'PENDING',
            depends_on TEXT NOT NULL DEFAULT '[]',
            acceptance_criteria TEXT NOT NULL DEFAULT '[]',
            evidence TEXT NOT NULL DEFAULT '{}',
            attempts INTEGER NOT NULL DEFAULT 0,
            kind TEXT NOT NULL DEFAULT 'code',
            blocked_reason TEXT,
            due_at TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS task_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            actor TEXT NOT NULL,
            actor_kind TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            agenda TEXT NOT NULL DEFAULT '',
            participants TEXT NOT NULL DEFAULT '[]',
            room TEXT NOT NULL DEFAULT 'ruang_rapat',
            scheduled_at TEXT,
            status TEXT NOT NULL DEFAULT 'SCHEDULED',
            transcript TEXT NOT NULL DEFAULT '[]',
            minutes TEXT NOT NULL DEFAULT '',
            decisions TEXT NOT NULL DEFAULT '[]',
            created_by TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id TEXT PRIMARY KEY,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            content TEXT NOT NULL,
            room TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            expires_at TEXT
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_type TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS owner_sessions (
            token_hash TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            last_seen_at TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL,
            actor TEXT NOT NULL,
            actor_kind TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            ref_type TEXT,
            ref_id TEXT,
            detail_hash TEXT NOT NULL
        );

        CREATE TRIGGER IF NOT EXISTS audit_log_no_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log bersifat append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log bersifat append-only');
        END;

        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS event_acks (
            client_id TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            at TEXT NOT NULL,
            PRIMARY KEY (client_id, event_id)
        );

        CREATE TABLE IF NOT EXISTS world_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL,
            type TEXT NOT NULL,
            actor TEXT,
            object TEXT,
            room TEXT,
            payload TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            requester TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            decided_by TEXT,
            decided_at TEXT,
            expires_at TEXT NOT NULL,
            execution_status TEXT NOT NULL DEFAULT 'PENDING',
            idempotency_key TEXT NOT NULL UNIQUE,
            attempts INTEGER NOT NULL DEFAULT 0,
            result TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approval_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_id TEXT NOT NULL REFERENCES approvals(id),
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            claimed_by TEXT,
            claimed_at TEXT,
            result TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            creator TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT 'owner_tray',
            delivery_status TEXT NOT NULL DEFAULT 'DRAFT',
            review_status TEXT NOT NULL DEFAULT 'UNREAD',
            version INTEGER NOT NULL DEFAULT 1,
            payload_hash TEXT NOT NULL,
            payload TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            priority TEXT NOT NULL DEFAULT 'normal',
            task_id TEXT,
            approval_id TEXT REFERENCES approvals(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT,
            decided_by TEXT,
            decided_at TEXT,
            decision_note TEXT
        );

        CREATE TABLE IF NOT EXISTS print_jobs (
            id TEXT PRIMARY KEY,
            paper_id TEXT NOT NULL REFERENCES papers(id),
            printer TEXT NOT NULL,
            created_at TEXT NOT NULL,
            pdf_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'DONE'
        );

        CREATE TABLE IF NOT EXISTS usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost REAL NOT NULL DEFAULT 0,
            at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS player_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            x REAL NOT NULL DEFAULT 0,
            y REAL NOT NULL DEFAULT 0,
            z REAL NOT NULL DEFAULT 0,
            room TEXT NOT NULL DEFAULT 'owner_room',
            activity TEXT NOT NULL DEFAULT 'idle',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS employee_states (
            employee_id TEXT PRIMARY KEY REFERENCES employees(id),
            room TEXT,
            x REAL NOT NULL DEFAULT 0,
            y REAL NOT NULL DEFAULT 0,
            z REAL NOT NULL DEFAULT 0,
            activity TEXT NOT NULL DEFAULT 'idle',
            source TEXT NOT NULL DEFAULT 'task',
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
        CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);
        CREATE INDEX IF NOT EXISTS idx_events_id ON event_log(id);
        CREATE INDEX IF NOT EXISTS idx_papers_delivery ON papers(delivery_status, review_status);
        CREATE INDEX IF NOT EXISTS idx_chat_thread ON chat_messages(thread_type, thread_id, id);
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS email_messages (
            id TEXT PRIMARY KEY,
            direction TEXT NOT NULL CHECK(direction IN ('IN', 'OUT')),
            status TEXT NOT NULL DEFAULT 'DRAFT',
            from_addr TEXT NOT NULL DEFAULT '',
            to_addr TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            attachments TEXT NOT NULL DEFAULT '[]',
            message_id TEXT NOT NULL UNIQUE,
            in_reply_to TEXT,
            trust_level TEXT NOT NULL DEFAULT 'trusted',
            approval_id TEXT REFERENCES approvals(id),
            imap_uid TEXT,
            error TEXT,
            received_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS email_send_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT NOT NULL,
            at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS website_deployments (
            id TEXT PRIMARY KEY,
            approval_id TEXT REFERENCES approvals(id),
            status TEXT NOT NULL DEFAULT 'PENDING',
            summary TEXT NOT NULL DEFAULT '',
            diff TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            version TEXT NOT NULL DEFAULT '',
            previous_version TEXT,
            backup_path TEXT,
            approved_by TEXT,
            published_at TEXT,
            check_result TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_email_direction ON email_messages(direction, status);
        CREATE INDEX IF NOT EXISTS idx_email_approval ON email_messages(approval_id);
        CREATE INDEX IF NOT EXISTS idx_send_log_at ON email_send_log(at);
        CREATE INDEX IF NOT EXISTS idx_website_approval ON website_deployments(approval_id);
        """,
    ),
]


def apply_migrations(conn) -> int:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        conn.executescript(sql)
        conn.execute(f"PRAGMA user_version = {version}")
        current = version
    conn.commit()
    return current
