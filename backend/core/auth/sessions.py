import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone

from core.office_store import LOCK, STORE, _now
from core.rbac import ROLES

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
DEFAULT_SESSION_HOURS = 8

MAX_FAILURES = 5
WINDOW_SECONDS = 10 * 60
LOCK_BASE_SECONDS = 15 * 60
LOCK_MAX_SECONDS = 60 * 60
GLOBAL_MAX_FAILURES = 30
GLOBAL_WINDOW_SECONDS = 10 * 60
GLOBAL_LOCK_SECONDS = 15 * 60

_ATTEMPTS: dict[str, tuple[int, float, float]] = {}
_ATTEMPTS_LOCK = threading.Lock()
_FAKE_HASH = None


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


def _clock(clock):
    return clock if callable(clock) else time.time


def _now_ts(clock):
    return float(_clock(clock)())


def _ip(value):
    import ipaddress
    value = str(value or "").strip()
    if not value:
        return "unknown"
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return "unknown"


def _key(kind, *parts):
    return kind + ":" + "|".join(str(p) for p in parts)


def clear_login_throttle():
    """Test helper: forget failed-login counters."""
    with _ATTEMPTS_LOCK:
        _ATTEMPTS.clear()


def _attempt_state(key, now_ts, window):
    with _ATTEMPTS_LOCK:
        count, first, lock_until = _ATTEMPTS.get(key, (0, now_ts, 0.0))
        if lock_until and now_ts < lock_until:
            return count, lock_until - now_ts
        if lock_until and now_ts >= lock_until:
            count, first, lock_until = 0, now_ts, 0.0
        if now_ts - first > window:
            count, first, lock_until = 0, now_ts, 0.0
        _ATTEMPTS[key] = (count, first, lock_until)
        return count, 0.0


def _record_failure(key, now_ts, window, max_failures, lock_base, lock_max=None):
    lock_max = lock_max or lock_base
    with _ATTEMPTS_LOCK:
        count, first, lock_until = _ATTEMPTS.get(key, (0, now_ts, 0.0))
        if lock_until and now_ts < lock_until:
            return lock_until - now_ts
        if now_ts - first > window or (lock_until and now_ts >= lock_until):
            count, first = 0, now_ts
        count += 1
        lock_until = 0.0
        retry_after = 0.0
        if count >= max_failures:
            over = count - max_failures
            duration = min(lock_base * (2 ** over), lock_max)
            lock_until = now_ts + duration
            retry_after = duration
        _ATTEMPTS[key] = (count, first, lock_until)
        return retry_after


def _reset_attempt(key):
    with _ATTEMPTS_LOCK:
        _ATTEMPTS.pop(key, None)


def _fake_hash():
    global _FAKE_HASH
    if _FAKE_HASH is None:
        from core.auth.password import hash_password
        _FAKE_HASH = hash_password("bangkah-invalid-password-timing-parity")
    return _FAKE_HASH


def _audit(event_type, actor, detail):
    try:
        STORE.add_event(event_type, actor or "system", str(detail)[:1000], None)
    except Exception:
        pass


class LoginThrottled(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = max(1, int(retry_after))
        super().__init__("Too many failed login attempts.")


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


def verify_user(username, password, client_ip=None, clock=None):
    from core.auth.password import verify_password as _verify
    username = str(username or "").strip()
    password = "" if password is None else str(password)
    ip = _ip(client_ip)
    now_ts = _now_ts(clock)
    pair_key = _key("pair", username, ip)
    user_key = _key("user", username)

    for key, window, max_failures in (
        (pair_key, WINDOW_SECONDS, MAX_FAILURES),
        (user_key, GLOBAL_WINDOW_SECONDS, GLOBAL_MAX_FAILURES),
    ):
        _, retry_after = _attempt_state(key, now_ts, window)
        if retry_after > 0:
            _audit("auth_login_locked", username or "unknown", f"ip={ip} retry_after={int(retry_after)}")
            raise LoginThrottled(retry_after)

    with LOCK, _db() as db:
        row = db.execute(
            """SELECT password_hash,role,enabled,employee_id,department_id
               FROM auth_users WHERE username=?""",
            (username,),
        ).fetchone()

    if not row or not row["enabled"]:
        _verify(password, _fake_hash())
        ra1 = _record_failure(pair_key, now_ts, WINDOW_SECONDS, MAX_FAILURES, LOCK_BASE_SECONDS, LOCK_MAX_SECONDS)
        ra2 = _record_failure(user_key, now_ts, GLOBAL_WINDOW_SECONDS, GLOBAL_MAX_FAILURES, GLOBAL_LOCK_SECONDS, GLOBAL_LOCK_SECONDS)
        retry_after = max(ra1, ra2)
        detail = f"ip={ip} reason={'disabled' if row else 'missing'}"
        if retry_after:
            detail += f" locked retry_after={int(retry_after)}"
        _audit("auth_login_failed", username or "unknown", detail)
        if retry_after:
            raise LoginThrottled(retry_after)
        return None

    if not _verify(password, row["password_hash"]):
        ra1 = _record_failure(pair_key, now_ts, WINDOW_SECONDS, MAX_FAILURES, LOCK_BASE_SECONDS, LOCK_MAX_SECONDS)
        ra2 = _record_failure(user_key, now_ts, GLOBAL_WINDOW_SECONDS, GLOBAL_MAX_FAILURES, GLOBAL_LOCK_SECONDS, GLOBAL_LOCK_SECONDS)
        retry_after = max(ra1, ra2)
        detail = f"ip={ip} reason=bad_password"
        if retry_after:
            detail += f" locked retry_after={int(retry_after)}"
        _audit("auth_login_failed", username, detail)
        if retry_after:
            raise LoginThrottled(retry_after)
        return None

    _reset_attempt(pair_key)
    _reset_attempt(user_key)
    _audit("auth_login_success", username, f"ip={ip}")
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
