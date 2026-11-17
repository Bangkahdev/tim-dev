"""Workstation registry, staff accounts, desktop sessions and a sandboxed terminal.

This module is the backend foundation of the in-game Bangkah OS. Computers in the
3D office are not decoration: each workstation has an identity, an assigned
account, persistent working files and an auditable session.

Security boundary (see docs/WORKSTATION-AND-DESKTOP.md):

- Every terminal command is parsed into an argv list. No shell is ever spawned.
- Only builtin commands and an explicit, environment-configured binary
  allowlist may run. Absolute paths and parent-directory escapes are rejected.
- Filesystem access is confined to the workstation working directory.
- Every login, file write, command and denied attempt is written to the
  company audit trail in the existing ``events`` table.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import shlex
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from .office_store import OfficeStore, STORE, LOCK, _now
from .domain_service import DOMAIN

BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BASE_DIR / "workspace" / "desktop"

# Workstations are persistent company assets. OWNER-PC-001 is the Owner's desk;
# the other seven are employee desks bound to their domain account.
WORKSTATIONS = [
    {"id": "OWNER-PC-001", "label": "Owner Workstation", "room_id": "owner", "account_id": "owner"},
    {"id": "PC-MGT-001", "label": "Arman / Lead Manager", "room_id": "manager", "account_id": "lead"},
    {"id": "PC-MGT-002", "label": "Sinta / Project Manager", "room_id": "planning", "account_id": "coo"},
    {"id": "PC-ARC-001", "label": "Raka / System Architect", "room_id": "architect", "account_id": "architect"},
    {"id": "PC-BE-001", "label": "Bima / Backend", "room_id": "backend", "account_id": "backend"},
    {"id": "PC-API-001", "label": "Naya / API Specialist", "room_id": "api", "account_id": "api"},
    {"id": "PC-FE-001", "label": "Dira / Frontend", "room_id": "frontend", "account_id": "frontend"},
    {"id": "PC-QA-001", "label": "Tika / QA Engineer", "room_id": "qa", "account_id": "qa"},
]

# Employee accounts mirror the office roster (lead, coo, architect, backend, api,
# frontend, qa). They are active whenever employee onboarding is enabled
# (BANGKAH_EMPLOYEE_ACCOUNTS, default on) so the activity engine can log them in
# at their own desk. Set it to "0" to freeze the office back to Owner-only login.
ACCOUNTS = {
    "owner": {"name": "Owner", "role": "owner", "active": True},
    "lead": {"name": "Arman", "role": "employee", "active": True},
    "coo": {"name": "Sinta", "role": "employee", "active": True},
    "architect": {"name": "Raka", "role": "employee", "active": True},
    "backend": {"name": "Bima", "role": "employee", "active": True},
    "api": {"name": "Naya", "role": "employee", "active": True},
    "frontend": {"name": "Dira", "role": "employee", "active": True},
    "qa": {"name": "Tika", "role": "employee", "active": True},
}

APP_PERMISSIONS = {
    "owner": ["files", "terminal", "infrastructure", "company"],
    "employee": ["files", "terminal", "company"],
}

BUILTIN_COMMANDS = ["pwd", "whoami", "date", "ls", "cat", "head", "tail", "wc", "grep", "find", "help", "status", "sysinfo"]
TEXT_EXTENSIONS = {".md", ".txt", ".json", ".csv", ".log", ".yaml", ".yml", ".ini", ".py", ".gd"}
MAX_FILE_BYTES = 64 * 1024
MAX_OUTPUT_CHARS = 16_000
MAX_COMMAND_CHARS = 500
SHELL_METACHARACTERS = set(";|&><`$(){}\n\r")
ABS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{1,2})")

LOGIN_FAILURES = {}
LOGIN_LOCK = threading.Lock()
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60


class DesktopError(ValueError):
    """Raised for invalid workstation/terminal/file operations."""


class DesktopAuthError(DesktopError):
    """Raised when a desktop session token is missing, expired or closed."""


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000)
    return f"pbkdf2_sha256$240000${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt_hex, digest_hex = str(stored).split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    try:
        rounds_value = int(rounds)
        salt = bytes.fromhex(salt_hex)
    except (TypeError, ValueError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds_value)
    return hmac.compare_digest(candidate.hex(), digest_hex)


class DesktopOperations:
    def __init__(self, store: OfficeStore = STORE, workspace_root: Path | str = WORKSPACE_ROOT,
                 owner_password: str | None = None):
        self.store = store
        self.db_path = store.db_path
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.credentials_path = self.db_path.parent / "owner_credentials.local"
        self.employee_credentials_path = self.db_path.parent / "employee_credentials.local"
        self._owner_password_override = owner_password
        self._employee_passwords: dict[str, str] = {}
        self._initialize()

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    def _db(self):
        return self.store._db()

    def _event(self, db, kind: str, actor: str, entity_id: str | None, detail: str):
        self.store._event(db, kind, actor, entity_id, str(detail)[:1000])

    def _initialize(self):
        with LOCK, self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workstation_catalog (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    room_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'offline',
                    last_used_at TEXT
                );
                CREATE TABLE IF NOT EXISTS workstation_accounts (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    password_hash TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 0,
                    apps_json TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS workstation_sessions (
                    id TEXT PRIMARY KEY,
                    workstation_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    closed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_ws_sessions_workstation
                    ON workstation_sessions(workstation_id, closed_at);
            """)
            for workstation in WORKSTATIONS:
                db.execute("""INSERT OR IGNORE INTO workstation_catalog
                    (id,label,room_id,account_id,status,last_used_at) VALUES(?,?,?,?,?,?)""",
                    (workstation["id"], workstation["label"], workstation["room_id"],
                     workstation["account_id"], "offline", None))
            for account_id, account in ACCOUNTS.items():
                apps = APP_PERMISSIONS.get(account["role"], [])
                db.execute("""INSERT OR IGNORE INTO workstation_accounts
                    (id,display_name,role,password_hash,active,apps_json)
                    VALUES(?,?,?,'',?,?)""",
                    (account_id, account["name"], account["role"],
                     1 if account["active"] else 0, ",".join(apps)))
            self._apply_employee_account_flags(db)
            self._ensure_owner_password(db)
            self._ensure_employee_passwords(db)

    def employee_accounts_enabled(self) -> bool:
        """Employee onboarding gate. ``BANGKAH_EMPLOYEE_ACCOUNTS=0`` freezes
        the office back to Owner-only workstation login."""
        raw = os.getenv("BANGKAH_EMPLOYEE_ACCOUNTS", "1").strip().lower()
        return raw not in ("0", "false", "off", "no")

    def _apply_employee_account_flags(self, db):
        enabled = self.employee_accounts_enabled()
        for account_id, account in ACCOUNTS.items():
            if account["role"] != "employee":
                continue
            db.execute("UPDATE workstation_accounts SET active=? WHERE id=?",
                       (1 if enabled else 0, account_id))

    def _ensure_employee_passwords(self, db):
        """Provision employee workstation passwords.

        Passwords are generated once and stored plaintext only in
        ``data/employee_credentials.local`` (chmod 600, never committed), the
        same local-secret pattern the Owner password uses. The activity engine
        reads them in-process; nothing exposes them over HTTP.
        """
        try:
            stored = self._read_employee_credentials_file()
        except OSError:
            stored = {}
        shared = os.getenv("BANGKAH_EMPLOYEE_PASSWORD", "").strip()
        employees = [a for a, b in ACCOUNTS.items() if b["role"] == "employee"]
        if employees and shared:
            password = shared
        else:
            password = None
        for account_id in employees:
            row = db.execute("SELECT password_hash, active FROM workstation_accounts WHERE id=?",
                             (account_id,)).fetchone()
            if row is None:
                continue
            plaintext = password
            if plaintext is None:
                plaintext = stored.get(account_id, "")
            if not plaintext:
                plaintext = secrets.token_urlsafe(9)
            self._employee_passwords[account_id] = plaintext
            current_hash = row["password_hash"] or ""
            if not (current_hash and _verify_password(plaintext, current_hash)):
                db.execute("UPDATE workstation_accounts SET password_hash=?,active=? WHERE id=?",
                           (_hash_password(plaintext),
                            1 if row["active"] else 0, account_id))
            elif not row["active"]:
                db.execute("UPDATE workstation_accounts SET active=0 WHERE id=?", (account_id,))
        if employees:
            try:
                self._write_employee_credentials_file()
            except OSError:
                print("[WORKSTATION] Peringatan: gagal menyimpan employee_credentials.local.",
                      flush=True)

    def _read_employee_credentials_file(self) -> dict[str, str]:
        secrets_map: dict[str, str] = {}
        if self.employee_credentials_path.is_file():
            for line in self.employee_credentials_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                account_id, _, value = line.partition("=")
                if value:
                    secrets_map[account_id.strip()] = value
        return secrets_map

    def _write_employee_credentials_file(self) -> None:
        lines = ["# Kredensial lokal workstation karyawan. Jangan commit file ini."]
        for account_id, plaintext in self._employee_passwords.items():
            lines.append(f"{account_id}={plaintext}")
        self.employee_credentials_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            os.chmod(self.employee_credentials_path, 0o600)
        except OSError:
            pass

    def employee_password(self, account_id: str) -> str:
        """Plaintext password for an employee account, for in-process use only
        (the activity engine). Never exposed through the HTTP API."""
        private_account = str(account_id or "").strip().lower()
        if private_account in self._employee_passwords:
            return self._employee_passwords[private_account]
        try:
            stored = self._read_employee_credentials_file()
        except OSError as error:
            raise DesktopError("Kredensial workstation karyawan tidak dapat dibaca.") from error
        value = stored.get(private_account, "")
        if not value:
            raise DesktopError("Kredensial workstation karyawan tidak ditemukan.")
        return value

    def _ensure_owner_password(self, db):
        row = db.execute("SELECT password_hash FROM workstation_accounts WHERE id='owner'").fetchone()
        if row is None:
            return
        if self._owner_password_override:
            db.execute("UPDATE workstation_accounts SET password_hash=?,active=1 WHERE id='owner'",
                       (_hash_password(self._owner_password_override),))
            return
        if row["password_hash"]:
            return
        env_password = os.getenv("BANGKAH_OWNER_PASSWORD", "").strip()
        password = env_password or self._read_or_create_owner_password()
        db.execute("UPDATE workstation_accounts SET password_hash=?,active=1 WHERE id='owner'",
                   (_hash_password(password),))

    def _read_or_create_owner_password(self) -> str:
        try:
            if self.credentials_path.is_file():
                for line in self.credentials_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("OWNER_PASSWORD="):
                        value = line.split("=", 1)[1].strip()
                        if value:
                            return value
            password = secrets.token_urlsafe(12)
            self.credentials_path.write_text(
                "# Kredensial lokal Owner workstation. Jangan commit file ini.\n"
                f"OWNER_PASSWORD={password}\n",
                encoding="utf-8",
            )
            try:
                os.chmod(self.credentials_path, 0o600)
            except OSError:
                pass
            print(f"[WORKSTATION] Kata sandi Owner dibuat di {self.credentials_path}. "
                  "Jangan commit atau bagikan file kredensial ini.", flush=True)
            return password
        except OSError as error:
            raise DesktopError("Kredensial Owner tidak dapat disiapkan.") from error

    # ------------------------------------------------------------------
    # Workstation catalogue and accounts
    # ------------------------------------------------------------------
    def _workstation_row(self, workstation_id: str):
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM workstation_catalog WHERE id=?", (workstation_id,)).fetchone()
        if row is None:
            raise DesktopError("Workstation tidak dikenal.")
        return dict(row)

    def _account_row(self, account_id: str):
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM workstation_accounts WHERE id=?", (account_id,)).fetchone()
        if row is None:
            raise DesktopError("Akun workstation tidak dikenal.")
        return dict(row)

    def list_accounts(self):
        """Public workstation accounts for the login screen. Password hashes
        never leave the backend."""
        with LOCK, self._db() as db:
            rows = db.execute(
                "SELECT id,display_name,role,active,apps_json FROM workstation_accounts ORDER BY id"
            ).fetchall()
        accounts = {}
        for row in rows:
            accounts[row["id"]] = {
                "id": row["id"],
                "name": row["display_name"],
                "role": row["role"],
                "active": bool(row["active"]),
                "apps": [a for a in (row["apps_json"] or "").split(",") if a],
            }
        return accounts

    def list_workstations(self):
        accounts = self.list_accounts()
        with LOCK, self._db() as db:
            rows = db.execute("SELECT * FROM workstation_catalog ORDER BY id").fetchall()
            active = {r["workstation_id"] for r in db.execute(
                "SELECT workstation_id FROM workstation_sessions WHERE closed_at IS NULL AND expires_at>?",
                (_now(),))}
        items = []
        for row in rows:
            item = dict(row)
            workstation_account = accounts.get(row["account_id"])
            item["account"] = dict(workstation_account) if workstation_account else None
            item["status"] = "online" if item["id"] in active else "offline"
            items.append(item)
        return items

    def workstation(self, workstation_id: str):
        row = self._workstation_row(workstation_id)
        accounts = self.list_accounts()
        workstation_account = accounts.get(row["account_id"])
        row["account"] = dict(workstation_account) if workstation_account else None
        row["status"] = "online" if self._active_session_for(workstation_id) else "offline"
        return row

    def _active_session_for(self, workstation_id: str):
        with LOCK, self._db() as db:
            row = db.execute("""SELECT id FROM workstation_sessions
                WHERE workstation_id=? AND closed_at IS NULL AND expires_at>?
                ORDER BY created_at DESC LIMIT 1""", (workstation_id, _now())).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Login / sessions
    # ------------------------------------------------------------------
    def _throttle_check(self, workstation_id: str):
        now = time.monotonic()
        with LOGIN_LOCK:
            entry = LOGIN_FAILURES.get(workstation_id)
            if not entry:
                return
            if now - entry["at"] > LOGIN_WINDOW_SECONDS:
                LOGIN_FAILURES.pop(workstation_id, None)
                return
            if entry["count"] >= LOGIN_MAX_ATTEMPTS:
                remaining = int(LOGIN_WINDOW_SECONDS - (now - entry["at"])) + 1
                raise DesktopError(f"Terlalu banyak percobaan login. Coba lagi dalam {remaining} detik.")

    def _throttle_fail(self, workstation_id: str):
        now = time.monotonic()
        with LOGIN_LOCK:
            entry = LOGIN_FAILURES.get(workstation_id)
            if not entry or now - entry["at"] > LOGIN_WINDOW_SECONDS:
                LOGIN_FAILURES[workstation_id] = {"count": 1, "at": now}
            else:
                entry["count"] += 1
                entry["at"] = now

    def _throttle_reset(self, workstation_id: str):
        with LOGIN_LOCK:
            LOGIN_FAILURES.pop(workstation_id, None)

    def clear_login_throttle(self):
        """Test helper: forget failed-login counters."""
        with LOGIN_LOCK:
            LOGIN_FAILURES.clear()

    def login(self, workstation_id: str, account_id: str, password: str,
              session_hours: float | None = None):
        workstation = self._workstation_row(workstation_id)
        account_id = str(account_id or "").strip().lower()
        self._throttle_check(workstation_id)
        if not account_id:
            raise DesktopError("Akun wajib diisi.")
        account = self._account_row(account_id)
        if not account["active"]:
            raise DesktopError("Akun karyawan tidak aktif.")
        if workstation["account_id"] != account_id:
            raise DesktopError("Akun ini tidak ditugaskan ke workstation tersebut.")
        if not _verify_password(str(password or ""), account["password_hash"]):
            self._throttle_fail(workstation_id)
            raise DesktopError("Kata sandi workstation salah.")
        self._throttle_reset(workstation_id)
        if session_hours is None:
            try:
                session_hours = float(os.getenv("BANGKAH_DESKTOP_SESSION_HOURS", "8"))
            except ValueError:
                session_hours = 8.0
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        session_id = "WSS-" + secrets.token_hex(8).upper()
        created = datetime.now().astimezone()
        expires = (created + timedelta(hours=max(0.05, float(session_hours)))).isoformat(timespec="seconds")
        apps = [a for a in account["apps_json"].split(",") if a]
        with LOCK, self._db() as db:
            db.execute("""INSERT INTO workstation_sessions
                (id,workstation_id,account_id,token_hash,created_at,expires_at)
                VALUES(?,?,?,?,?,?)""",
                (session_id, workstation_id, account_id, token_hash,
                 created.isoformat(timespec="seconds"), expires))
            db.execute("UPDATE workstation_catalog SET status='online',last_used_at=? WHERE id=?",
                       (created.isoformat(timespec="seconds"), workstation_id))
            self._event(db, "desktop_login", account_id, workstation_id,
                        f"{account['display_name']} masuk ke {workstation_id}.")
        return {
            "session_id": session_id,
            "token": token,
            "expires_at": expires,
            "workstation": {"id": workstation_id, "label": workstation["label"], "room_id": workstation["room_id"]},
            "account": {"id": account_id, "name": account["display_name"], "role": account["role"]},
            "apps": apps,
        }

    def _session_from_token(self, token: str):
        token = str(token or "").strip()
        if not token:
            raise DesktopAuthError("Sesi workstation tidak ditemukan. Login ulang.")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM workstation_sessions WHERE token_hash=?", (token_hash,)).fetchone()
        if row is None:
            raise DesktopAuthError("Sesi workstation tidak valid.")
        session = dict(row)
        if session["closed_at"]:
            raise DesktopAuthError("Sesi workstation sudah ditutup.")
        if session["expires_at"] <= _now():
            raise DesktopAuthError("Sesi workstation sudah berakhir. Login ulang.")
        return session

    def session_state(self, token: str):
        session = self._session_from_token(token)
        account = self._account_row(session["account_id"])
        workstation = self._workstation_row(session["workstation_id"])
        apps = [a for a in account["apps_json"].split(",") if a]
        return {
            "session_id": session["id"],
            "expires_at": session["expires_at"],
            "workstation": {"id": workstation["id"], "label": workstation["label"], "room_id": workstation["room_id"]},
            "account": {"id": account["id"], "name": account["display_name"], "role": account["role"]},
            "apps": apps,
        }

    def close_session(self, token: str):
        session = self._session_from_token(token)
        with LOCK, self._db() as db:
            db.execute("UPDATE workstation_sessions SET closed_at=? WHERE id=?", (_now(), session["id"]))
            still_active = db.execute("""SELECT 1 FROM workstation_sessions
                WHERE workstation_id=? AND closed_at IS NULL AND expires_at>?""",
                (session["workstation_id"], _now())).fetchone()
            if not still_active:
                db.execute("UPDATE workstation_catalog SET status='offline' WHERE id=?",
                           (session["workstation_id"],))
            account = self._account_row(session["account_id"])
            self._event(db, "desktop_logout", session["account_id"], session["workstation_id"],
                        f"{account['display_name']} keluar dari {session['workstation_id']}.")
        return {"closed": True, "session_id": session["id"]}

    # ------------------------------------------------------------------
    # Filesystem sandbox
    # ------------------------------------------------------------------
    def workdir(self, workstation_id: str) -> Path:
        self._workstation_row(workstation_id)
        directory = self.workspace_root / workstation_id
        directory.mkdir(parents=True, exist_ok=True)
        self._seed_workdir(workstation_id, directory)
        return directory.resolve()

    def _seed_workdir(self, workstation_id: str, directory: Path):
        workstation = self._workstation_row(workstation_id)
        files = {
            "README.md": (
                f"# {workstation['id']} / {workstation['label']}\n\n"
                "Folder kerja ini adalah sandbox workstation yang terhubung ke backend Bangkah.\n"
                "Terminal dan File Manager hanya dapat mengakses folder ini.\n\n"
                "## Catatan\n\n"
                "- Semua aktivitas login, tulis file, dan perintah tercatat di audit perusahaan.\n"
                "- Perintah shell bebas dan akses host tidak diizinkan.\n"
            ),
            "notes.txt": (
                "Catatan kerja Owner.\n"
                "Gunakan File Manager untuk melihat dan menyunting file di folder ini.\n"
            ),
            "docs/handbook.md": (
                "# Bangkah Workstation Handbook\n\n"
                "1. Buka dashboard perusahaan dari aplikasi Company.\n"
                "2. Gunakan Terminal untuk memeriksa file kerja (ls, cat, grep).\n"
                "3. Status integrasi nyata (SMTP, deployment, domain) terlihat di Infrastructure.\n\n"
                "Domain dan email perusahaan belum dikonfigurasi pada slice ini.\n"
            ),
        }
        for relative, content in files.items():
            path = directory / relative
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def _safe_path(self, workstation_id: str, relative: str) -> Path:
        base = self.workdir(workstation_id)
        raw = str(relative or ".").strip() or "."
        if "\x00" in raw:
            raise DesktopError("Nama path tidak valid.")
        if ABS_PATH_RE.match(raw):
            raise DesktopError("Path absolut tidak diizinkan.")
        try:
            resolved = (base / raw).resolve()
        except OSError as error:
            raise DesktopError("Path tidak dapat dibaca.") from error
        try:
            resolved.relative_to(base)
        except ValueError:
            raise DesktopError("Path keluar dari folder workstation tidak diizinkan.")
        return resolved

    @staticmethod
    def _relative(base: Path, path: Path) -> str:
        try:
            value = path.relative_to(base).as_posix()
        except ValueError:
            return path.name
        return value if value else "."

    def list_files(self, token: str, relative: str = "."):
        session = self._session_from_token(token)
        workstation_id = session["workstation_id"]
        base = self.workdir(workstation_id)
        target = self._safe_path(workstation_id, relative)
        if not target.exists():
            raise DesktopError("Folder tidak ditemukan.")
        if not target.is_dir():
            raise DesktopError("Path tersebut bukan folder.")
        try:
            children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as error:
            raise DesktopError("Folder tidak dapat dibaca.") from error
        entries = []
        for child in children:
            if child.name.startswith(".owner_credentials"):
                continue
            try:
                stat = child.stat()
            except OSError:
                continue
            entries.append({
                "name": child.name,
                "path": self._relative(base, child),
                "type": "directory" if child.is_dir() else "file",
                "size": stat.st_size if child.is_file() else 0,
                "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            })
        return {"workstation_id": workstation_id, "path": self._relative(base, target), "entries": entries}

    def read_file(self, token: str, relative: str):
        session = self._session_from_token(token)
        workstation_id = session["workstation_id"]
        base = self.workdir(workstation_id)
        target = self._safe_path(workstation_id, relative)
        if not target.is_file():
            raise DesktopError("File tidak ditemukan.")
        if target.suffix.lower() not in TEXT_EXTENSIONS:
            raise DesktopError("Hanya file teks yang dapat dibuka di File Manager.")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise DesktopError("File melebihi batas 64 KB untuk File Manager.")
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            raise DesktopError("File tidak dapat dibaca.") from error
        return {"path": self._relative(base, target), "content": content,
                "size": target.stat().st_size}

    def write_file(self, token: str, relative: str, content: str):
        session = self._session_from_token(token)
        workstation_id = session["workstation_id"]
        base = self.workdir(workstation_id)
        target = self._safe_path(workstation_id, relative)
        if target.suffix.lower() not in TEXT_EXTENSIONS:
            raise DesktopError("Tipe file tidak diizinkan untuk ditulis.")
        payload = str(content if content is not None else "")
        if len(payload.encode("utf-8")) > MAX_FILE_BYTES:
            raise DesktopError("Isi file melebihi batas 64 KB.")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(payload, encoding="utf-8")
        except OSError as error:
            raise DesktopError("File tidak dapat ditulis.") from error
        relative_path = self._relative(base, target)
        with LOCK, self._db() as db:
            self._event(db, "desktop_file_write", session["account_id"], workstation_id,
                        f"File ditulis melalui Bangkah OS: {relative_path}")
        return {"path": relative_path, "size": len(payload.encode("utf-8"))}

    # ------------------------------------------------------------------
    # Terminal sandbox
    # ------------------------------------------------------------------
    @staticmethod
    def _external_allowlist() -> set[str]:
        raw = os.getenv("BANGKAH_TERMINAL_ALLOWED_BINARIES", "")
        return {item.strip() for item in raw.split(",") if item.strip()}

    def _validate_args(self, argv: list[str]):
        if not argv:
            raise DesktopError("Perintah kosong.")
        for token in argv:
            if len(token) > 200:
                raise DesktopError("Argumen perintah terlalu panjang.")
            if "\x00" in token:
                raise DesktopError("Argumen perintah tidak valid.")
            if ABS_PATH_RE.match(token):
                raise DesktopError("Path absolut tidak diizinkan di terminal.")
            if ".." in re.split(r"[\\/]+", token):
                raise DesktopError("Path keluar dari folder workstation tidak diizinkan.")

    def _resolve_external(self, name: str) -> str | None:
        if not name or name not in self._external_allowlist():
            return None
        resolved = shutil.which(name)
        if not resolved:
            return None
        resolved_path = Path(resolved).resolve()
        return str(resolved_path) if resolved_path.is_file() else None

    def run_command(self, token: str, command: str):
        session = self._session_from_token(token)
        workstation_id = session["workstation_id"]
        account_id = session["account_id"]
        raw = str(command or "").strip()
        if not raw:
            raise DesktopError("Tulis perintah terlebih dahulu.")
        if len(raw) > MAX_COMMAND_CHARS:
            raise DesktopError(f"Perintah melebihi batas {MAX_COMMAND_CHARS} karakter.")
        if any(char in SHELL_METACHARACTERS for char in raw):
            self._audit_command(account_id, workstation_id, raw, "ditolak: karakter shell")
            raise DesktopError("Karakter shell (; | & > < ` $) tidak diizinkan.")
        # Forward slashes keep relative paths predictable on Windows as well.
        try:
            argv = shlex.split(raw.replace("\\", "/"), posix=True)
        except ValueError as error:
            self._audit_command(account_id, workstation_id, raw, "ditolak: kutipan tidak valid")
            raise DesktopError("Format perintah tidak valid.") from error
        self._validate_args(argv)
        workdir = self.workdir(workstation_id)
        name = argv[0]
        if name in BUILTIN_COMMANDS:
            result = self._run_builtin(name, argv[1:], workdir, account_id)
        else:
            external = self._resolve_external(name)
            if not external:
                self._audit_command(account_id, workstation_id, raw, "ditolak: tidak ada di allowlist")
                raise DesktopError(
                    "Perintah tidak tersedia. Terminal hanya menjalankan builtin "
                    f"({', '.join(BUILTIN_COMMANDS)}) dan binary yang diizinkan administrator."
                )
            result = self._run_external(external, argv[1:], workdir)
        self._audit_command(account_id, workstation_id, raw, f"exit {result['exit_code']}")
        result["command"] = raw
        return result

    def _event_with_new_db(self, kind: str, actor: str, entity_id: str | None, detail: str):
        try:
            with LOCK, self._db() as db:
                self._event(db, kind, actor, entity_id, detail)
        except Exception:
            pass

    def _audit_command(self, account_id: str, workstation_id: str, command: str, outcome: str):
        try:
            with LOCK, self._db() as db:
                self._event(db, "terminal_exec", account_id, workstation_id,
                            f"{workstation_id}: {str(command)[:300]} ({outcome})")
        except Exception:
            print(f"[WORKSTATION AUDIT ERROR] command={command!r} outcome={outcome}", flush=True)

    @staticmethod
    def _truncate(value: str) -> str:
        if len(value) > MAX_OUTPUT_CHARS:
            return value[:MAX_OUTPUT_CHARS] + "\n[output dipotong]"
        return value

    def _run_external(self, binary: str, args: list[str], workdir: Path):
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(workdir),
            "LANG": "C.UTF-8",
        }
        for key in ("SYSTEMROOT", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
            if os.environ.get(key):
                env[key] = os.environ[key]
        try:
            from core.safe_env import safe_subprocess_env
            env = safe_subprocess_env(env)
        except Exception:
            pass
        run_args = [binary, *args]
        try:
            from core.sandbox_exec import enforce_sandbox, ensure_sandbox_canaries, sandbox_status
            status = sandbox_status()
            if status.get("error") and not status.get("required"):
                print(f"[WORKSTATION SANDBOX WARNING] {status['error']}", flush=True)
            if status.get("required") and not status.get("active"):
                print(f"[WORKSTATION SANDBOX BLOCKED] {status.get('error')}", flush=True)
                try:
                    with LOCK, self._db() as db:
                        self._event(db, "sandbox_blocked", "system", str(workdir), status.get("error", "sandbox required"))
                except Exception:
                    pass
                return {"exit_code": 126, "stdout": "", "stderr": f"sandbox required but not configured/misconfigured: {status.get('error')}"}
            canary = ensure_sandbox_canaries(workdir, audit=lambda t, a, d, e: self._event_with_new_db(t, a, e, d))
            if status.get("required") and not canary.get("ok"):
                return {"exit_code": 126, "stdout": "", "stderr": f"sandbox canary failed (NFR-SEC-09/10 not evidenced): {str(canary.get('details', ''))[:500]}"}
            run_args = enforce_sandbox(run_args, workdir)
        except RuntimeError as exc:
            print(f"[WORKSTATION SANDBOX BLOCKED] {exc}", flush=True)
            try:
                with LOCK, self._db() as db:
                    self._event(db, "sandbox_blocked", "system", str(workdir), str(exc))
            except Exception:
                pass
            return {"exit_code": 126, "stdout": "", "stderr": f"sandbox required but not configured/misconfigured: {exc}"}
        try:
            completed = subprocess.run(
                run_args, cwd=str(workdir), env=env, shell=False,
                capture_output=True, text=True, timeout=5,
            )
        except subprocess.TimeoutExpired:
            return {"exit_code": 124, "stdout": "", "stderr": "Perintah melebihi batas waktu 5 detik."}
        except OSError as error:
            return {"exit_code": 127, "stdout": "", "stderr": f"Perintah gagal dijalankan: {error}"}
        return {
            "exit_code": completed.returncode,
            "stdout": self._truncate(completed.stdout or ""),
            "stderr": self._truncate(completed.stderr or ""),
        }

    def _run_builtin(self, name: str, args: list[str], workdir: Path, account_id: str):
        try:
            if name == "help":
                return self._ok(
                    "Perintah builtin: " + ", ".join(BUILTIN_COMMANDS) + "\n"
                    "Akses hanya di dalam folder workstation. Path absolut dan '..' ditolak.\n"
                    "Binary eksternal hanya jika diizinkan administrator melalui BANGKAH_TERMINAL_ALLOWED_BINARIES."
                )
            if name == "pwd":
                return self._ok(str(workdir))
            if name == "whoami":
                return self._ok(account_id)
            if name == "date":
                return self._ok(datetime.now().astimezone().isoformat(timespec="seconds"))
            if name == "ls":
                target = self._builtin_target(args[0] if args else ".", workdir)
                if not target.exists():
                    return self._error(f"ls: {args[0] if args else '.'} tidak ditemukan")
                if target.is_file():
                    return self._ok(target.name)
                items = []
                for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                    if child.name.startswith(".owner_credentials"):
                        continue
                    items.append(child.name + ("/" if child.is_dir() else ""))
                return self._ok("\n".join(items))
            if name in ("cat", "head", "tail", "wc"):
                return self._builtin_file_command(name, args, workdir)
            if name == "grep":
                return self._builtin_grep(args, workdir)
            if name == "find":
                target = self._builtin_target(args[0] if args else ".", workdir)
                if not target.exists():
                    return self._error("find: path tidak ditemukan")
                lines = []
                for path in sorted(target.rglob("*")):
                    try:
                        relative = path.relative_to(workdir).as_posix()
                    except ValueError:
                        continue
                    if path.name.startswith(".owner_credentials"):
                        continue
                    lines.append(relative + ("/" if path.is_dir() else ""))
                    if len(lines) >= 200:
                        lines.append("[daftar dipotong]")
                        break
                return self._ok("\n".join(lines))
            if name == "status":
                from .office_store import STORE
                snap = STORE.snapshot()
                tasks_cnt = len(snap.get("tasks", []))
                emps = ", ".join(e["id"] for e in snap.get("employees", []))
                return self._ok(
                    f"Workstation: {workstation_id}\n"
                    f"Account: {account_id}\n"
                    f"Time: {_now()}\n"
                    f"Tasks: {tasks_cnt} total\n"
                    f"Roster: {emps}"
                )
            if name == "sysinfo":
                import sys as _sys
                return self._ok(
                    f"OS: Bangkah OS v1.0 (Sandbox Runtime)\n"
                    f"Platform: {_sys.platform}\n"
                    f"Python: {_sys.version.split()[0]}\n"
                    f"Workspace: {workdir.name}\n"
                    f"Domain: {DOMAIN.domain_name}"
                )
            return self._error(f"{name}: perintah belum didukung")
        except DesktopError:
            raise
        except OSError as error:
            return self._error(f"{name}: {error}")

    @staticmethod
    def _ok(stdout: str):
        return {"exit_code": 0, "stdout": stdout, "stderr": ""}

    @staticmethod
    def _error(message: str):
        return {"exit_code": 1, "stdout": "", "stderr": message}

    def _builtin_target(self, raw: str, workdir: Path) -> Path:
        if ABS_PATH_RE.match(raw):
            raise DesktopError("Path absolut tidak diizinkan.")
        if ".." in re.split(r"[\\/]+", raw):
            raise DesktopError("Path keluar dari folder workstation tidak diizinkan.")
        resolved = (workdir / raw).resolve()
        try:
            resolved.relative_to(workdir.resolve())
        except ValueError:
            raise DesktopError("Path keluar dari folder workstation tidak diizinkan.")
        return resolved

    def _builtin_file_command(self, name: str, args: list[str], workdir: Path):
        args = list(args)
        count = 10
        mode = ""
        if name in ("head", "tail") and args and args[0] in ("-n", "--lines"):
            if len(args) < 3:
                return self._error(f"{name}: butuh jumlah baris dan file")
            try:
                count = max(1, min(int(args[1]), 500))
            except ValueError:
                return self._error(f"{name}: jumlah baris tidak valid")
            args = args[2:]
        if name == "wc" and args and args[0].startswith("-"):
            mode = args[0]
            args = args[1:]
            if mode not in ("-l", "-w", "-c"):
                return self._error("wc: mode yang didukung -l, -w, -c")
        if not args:
            return self._error(f"{name}: butuh nama file")
        outputs = []
        had_error = False
        for raw in args:
            target = self._builtin_target(raw, workdir)
            if not target.is_file():
                outputs.append(f"{name}: {raw}: tidak ditemukan")
                had_error = True
                continue
            if target.stat().st_size > MAX_FILE_BYTES:
                outputs.append(f"{name}: {raw}: file terlalu besar")
                had_error = True
                continue
            text = target.read_text(encoding="utf-8", errors="replace")
            if name == "cat":
                outputs.append(text.rstrip("\n"))
            elif name == "head":
                outputs.append("\n".join(text.splitlines()[:count]))
            elif name == "tail":
                outputs.append("\n".join(text.splitlines()[-count:]))
            elif name == "wc":
                if mode == "-w":
                    outputs.append(f"{len(text.split())} {raw}")
                elif mode == "-c":
                    outputs.append(f"{len(text.encode('utf-8'))} {raw}")
                else:
                    outputs.append(f"{len(text.splitlines())} {raw}")
        output = "\n".join(outputs)
        return {"exit_code": 1 if had_error else 0, "stdout": output, "stderr": ""}

    def _builtin_grep(self, args: list[str], workdir: Path):
        ignore_case = False
        if args and args[0] == "-i":
            ignore_case = True
            args = args[1:]
        if len(args) < 2:
            return self._error("grep: butuh pola dan file")
        pattern, files = args[0], args[1:]
        try:
            matcher = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as error:
            return self._error(f"grep: pola tidak valid ({error})")
        lines = []
        for raw in files:
            target = self._builtin_target(raw, workdir)
            if not target.is_file():
                lines.append(f"grep: {raw}: tidak ditemukan")
                continue
            if target.stat().st_size > MAX_FILE_BYTES:
                lines.append(f"grep: {raw}: file terlalu besar")
                continue
            for number, line in enumerate(target.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if matcher.search(line):
                    lines.append(f"{raw}:{number}:{line}")
                if len(lines) >= 200:
                    lines.append("[hasil dipotong]")
                    return self._ok("\n".join(lines))
        return self._ok("\n".join(lines))

    # ------------------------------------------------------------------
    # Honest system / integration status
    # ------------------------------------------------------------------
    def system_info(self, token: str):
        session = self._session_from_token(token)
        account = self._account_row(session["account_id"])
        workstation = self._workstation_row(session["workstation_id"])
        workdir = self.workdir(session["workstation_id"])
        integrations = {
            "smtp": {
                "configured": bool(os.getenv("SMTP_HOST", "").strip() and os.getenv("SMTP_FROM", "").strip()),
                "detail": "Email keluar hanya melalui Approval dan Outbox.",
            },
            "deploy_webhook": {
                "configured": bool(os.getenv("DEPLOY_WEBHOOK_URL", "").strip()
                                    and os.getenv("DEPLOY_WEBHOOK_TOKEN", "").strip()),
                "detail": "Deployment hanya lewat Approval dan Outbox.",
            },
            "api_token": {
                "enabled": bool(os.getenv("BANGKAH_API_TOKEN", "").strip()),
                "detail": "Bearer token untuk seluruh endpoint API.",
            },
        "domain": {
            "name": os.getenv("BANGKAH_DOMAIN", "").strip() or "bangkah.my.id",
            "dns_managed": bool(DOMAIN.state().get("internal_dns_managed", False)),
            "email_provisioned": False,
            "detail": "Domain dan DNS internal dielola sebagai layanan backend Bangkah (model simulasi, bukan Windows AD sungguhan). DNS eksternal dan email belum diaktifkan.",
        },
        }
        return {
            "workstation": {"id": workstation["id"], "label": workstation["label"], "room_id": workstation["room_id"]},
            "account": {"id": account["id"], "name": account["display_name"], "role": account["role"]},
            "apps": [a for a in account["apps_json"].split(",") if a],
            "session": {"id": session["id"], "expires_at": session["expires_at"]},
            "terminal": {
                "mode": "sandboxed-argv",
                "builtins": BUILTIN_COMMANDS,
                "external_binaries": sorted(self._external_allowlist()),
                "workdir": workdir.name,
                "limits": {"command_chars": MAX_COMMAND_CHARS, "file_bytes": MAX_FILE_BYTES,
                           "output_chars": MAX_OUTPUT_CHARS},
            },
            "integrations": integrations,
        }

    def audit(self, token: str, after_id: int = 0, limit: int = 50):
        session = self._session_from_token(token)
        after_id = max(0, int(after_id))
        limit = max(1, min(int(limit), 100))
        with LOCK, self._db() as db:
            rows = db.execute("""SELECT * FROM events WHERE id>? AND (
                    actor=? OR entity_id=? OR event_type LIKE 'terminal_%'
                    OR event_type LIKE 'desktop_%')
                ORDER BY id LIMIT ?""",
                (after_id, session["account_id"], session["workstation_id"], limit)).fetchall()
        return [dict(row) for row in rows]


DESKTOP = DesktopOperations()
