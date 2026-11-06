"""Slice C: FTP service model (loopback, Directory-authenticated)."""

import os, threading, socket
from core.office_store import LOCK, STORE, _now
from core.validation import safe_username, safe_path

FTP_ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "ftp_storage")
os.makedirs(FTP_ROOT, exist_ok=True)


class FTPService:
    def __init__(self, store=STORE):
        self.store = store
        self.host = "127.0.0.1"
        self.port = 2121
        self._running = False
        self._thread = None
        self._initialize()

    def _db(self):
        return self.store._db()

    def _initialize(self):
        with LOCK, self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS ftp_config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ftp_permissions (username TEXT NOT NULL, path TEXT NOT NULL, perm TEXT NOT NULL, PRIMARY KEY(username,path));
                CREATE TABLE IF NOT EXISTS ftp_transfers (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, action TEXT, path TEXT, size INTEGER, result TEXT, created_at TEXT);
            """)

    def start(self):
        self._running = True
        return {"status": "RUNNING", "host": self.host, "port": self.port}

    def stop(self):
        self._running = False
        return {"status": "STOPPED"}

    def health(self):
        return {"liveness": "OK", "running": self._running}

    def provision_home(self, username):
        username = safe_username(username)
        path = os.path.join(FTP_ROOT, "users", username)
        os.makedirs(path, exist_ok=True)
        for sub in ("documents", "projects", "uploads"):
            os.makedirs(os.path.join(path, sub), exist_ok=True)
        return path

    def audit(self, username, action, path, size=0, result="SUCCESS"):
        with LOCK, self._db() as db:
            db.execute("""INSERT INTO ftp_transfers(username,action,path,size,result,created_at) VALUES(?,?,?,?,?,?)""",
                       (username, action, path, size, result, _now()))
            self.store._event(db, "FTP_" + action.upper(), username, path, "%s %s" % (action, path))


FTP = FTPService()
