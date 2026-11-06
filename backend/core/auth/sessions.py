import os
import re
import secrets
import time
from datetime import datetime, timezone

from core.office_store import LOCK, STORE, _now
from core.rbac import ROLES

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
DEFAULT_SESSION_HOURS = 8


def _db():
    return STORE._db()


def _session_ttl_seconds():
    try:
        hours = float(os.getenv("BANGKAH_SESSION_HOURS", str(DEFAULT_SESSION_HOURS)))
    except (TypeError, ValueError):
        hours = DEFAULT_SESSION_HOURS
    return int(max(0.05, min(hours, 24 * 30)) * 3600)


def _ensure_columns(db):
    existing = {row["name"] for row in db.execute("PRAGMA table_info(auth_users)")}
    for name, definition in {
        "employee_id": "TEXT",
        "department_id": "TEXT",
    }.items():
        if name not in existing:
            db.execute(f"ALTER TABLE auth_users ADD COLUMN {name} {definition}")


def _init():
    with LOCK, _db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS auth_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                enabled INTEGER NOT NULL DEFAULT 1,
                employee_id TEXT,
                department_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(username, revoked);
        """)
        _ensure_columns(db)


_init()


def create_user(username, password, role="employee", employee_id=None, department_id=None, enabled=True):
    from core.auth.password import hash_password
    username = str(username or "").strip()
    if not USERNAME_RE.match(username):
        raise ValueError("Username harus 3-64 karakter: huruf, angka, titik, garis bawah, atau tanda hubung.")
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("Kata sandi minimal 8 karakter.")
    if role not in ROLES:
        raise ValueError(f"Role tidak dikenal: {role}.")
    now = _now()
    with LOCK, _db() as db:
        db.execute(
            """INSERT INTO auth_users
               (username,password_hash,role,enabled,employee_id,department_id,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (username, hash_password(password), role, 1 if enabled else 0,
             (employee_id or None), (department_id or None), now),
        )
    return get_user(username)


def get_user(username):
    with LOCK, _db() as db:
        row = db.execute(
            "SELECT username,role,enabled,employee_id,department_id,created_at FROM auth_users WHERE username=?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def list_users():
    with LOCK, _db() as db:
        rows = db.execute(
            """SELECT username,role,enabled,employee_id,department_id,created_at
               FROM auth_users ORDER BY username"""
        ).fetchall()
    return [dict(row) for row in rows]


def set_user_enabled(username, enabled):
    with LOCK, _db() as db:
        db.execute("UPDATE auth_users SET enabled=? WHERE username=?", (1 if enabled else 0, username))
        if not enabled:
            db.execute("UPDATE auth_sessions SET revoked=1 WHERE username=?", (username,))


def set_user_role(username, role):
    if role not in ROLES:
        raise ValueError(f"Role tidak dikenal: {role}.")
    with LOCK, _db() as db:
        db.execute("UPDATE auth_users SET role=? WHERE username=?", (role, username))


def verify_user(username, password):
    with LOCK, _db() as db:
        row = db.execute(
            """SELECT password_hash,role,enabled,employee_id,department_id
               FROM auth_users WHERE username=?""",
            (username,),
        ).fetchone()
    if not row or not row["enabled"]:
        return None
    from core.auth.password import verify_password
    if not verify_password(password, row["password_hash"]):
        return None
    return {"username": username, "role": row["role"],
            "employee_id": row["employee_id"], "department_id": row["department_id"]}


def create_session(username, ttl_seconds=None):
    token = secrets.token_urlsafe(32)
    now = _now()
    ttl_seconds = _session_ttl_seconds() if ttl_seconds is None else int(ttl_seconds)
    expires_iso = datetime.fromtimestamp(time.time() + ttl_seconds, timezone.utc).isoformat()
    with LOCK, _db() as db:
        db.execute(
            "INSERT INTO auth_sessions(token,username,created_at,expires_at) VALUES(?,?,?,?)",
            (token, username, now, expires_iso),
        )
    return token


def get_session(token):
    token = str(token or "").strip()
    if not token:
        return None
    with LOCK, _db() as db:
        row = db.execute(
            "SELECT username,expires_at,revoked FROM auth_sessions WHERE token=?", (token,)
        ).fetchone()
    if not row or row["revoked"]:
        return None
    try:
        exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        else:
            exp = exp.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None
    if exp <= datetime.now(timezone.utc):
        return None
    with LOCK, _db() as db:
        user = db.execute(
            """SELECT role,enabled,employee_id,department_id
               FROM auth_users WHERE username=?""",
            (row["username"],),
        ).fetchone()
    if not user or not user["enabled"]:
        return None
    return {"username": row["username"], "role": user["role"],
            "employee_id": user["employee_id"], "department_id": user["department_id"]}


def revoke_session(token):
    token = str(token or "").strip()
    if not token:
        return
    with LOCK, _db() as db:
        db.execute("UPDATE auth_sessions SET revoked=1 WHERE token=?", (token,))


def revoke_all(username):
    with LOCK, _db() as db:
        db.execute("UPDATE auth_sessions SET revoked=1 WHERE username=?", (username,))


def ensure_bootstrap_owner():
    """Create the first owner account once, without hardcoded credentials.

    A password from ``BANGKAH_OWNER_PASSWORD`` is used when present. Otherwise a
    random one is generated and stored next to the database so the operator can
    read it and change it later.
    """
    with LOCK, _db() as db:
        count = db.execute("SELECT COUNT(*) AS n FROM auth_users").fetchone()["n"]
    if count:
        return None
    password = os.getenv("BANGKAH_OWNER_PASSWORD", "").strip()
    generated = False
    if not password:
        password = secrets.token_urlsafe(15)
        generated = True
    create_user("owner", password, "owner", department_id="executive")
    if generated:
        path = STORE.db_path.parent / "owner_auth_password.local"
        try:
            path.write_text(
                "Bangkah owner bootstrap password. Change it before real use.\n"
                f"username: owner\npassword: {password}\n",
                encoding="utf-8",
            )
            print(f"[AUTH] Owner bootstrap password written to {path}")
        except OSError as error:
            print(f"[AUTH] Owner bootstrap password: {password} (file write failed: {error})")
    return "owner"
