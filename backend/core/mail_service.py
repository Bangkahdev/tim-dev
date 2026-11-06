"""Slice D: Mail service model (SMTP + POP3, internal only)."""

import os, threading
from core.office_store import LOCK, STORE, _now

MAIL_ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "mail_storage")
os.makedirs(MAIL_ROOT, exist_ok=True)


class MailService:
    def __init__(self, store=STORE):
        self.store = store
        self.smtp_host = "127.0.0.1"
        self.smtp_port = 2525
        self.pop3_host = "127.0.0.1"
        self.pop3_port = 1110
        self._running = False
        self._initialize()

    def _db(self):
        return self.store._db()

    def _initialize(self):
        with LOCK, self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS mailboxes (username TEXT PRIMARY KEY, email TEXT NOT NULL, quota INTEGER NOT NULL DEFAULT 1073741824, used INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS mail_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, mailbox TEXT NOT NULL, sender TEXT NOT NULL, recipient TEXT NOT NULL, subject TEXT, body TEXT, size INTEGER, created_at TEXT, deleted INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS mail_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, recipient TEXT, status TEXT NOT NULL DEFAULT 'queued', created_at TEXT);
            """)

    def provision_mailbox(self, username, domain="bangkah.my.id"):
        email = "%s@%s" % (username, domain)
        with LOCK, self._db() as db:
            if not db.execute("SELECT 1 FROM mailboxes WHERE username=?", (username,)).fetchone():
                db.execute("INSERT INTO mailboxes(username,email) VALUES(?,?)", (username, email))
        path = os.path.join(MAIL_ROOT, username)
        os.makedirs(path, exist_ok=True)
        return email

    def start(self):
        self._running = True
        return {"status": "RUNNING", "smtp": "%s:%d" % (self.smtp_host, self.smtp_port), "pop3": "%s:%d" % (self.pop3_host, self.pop3_port)}

    def stop(self):
        self._running = False
        return {"status": "STOPPED"}

    def health(self):
        return {"liveness": "OK", "running": self._running}


MAIL = MailService()
