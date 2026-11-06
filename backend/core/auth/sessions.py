import secrets, time, sqlite3
from core.office_store import LOCK, STORE, _now

def _db():
    return STORE._db()

def _init():
    with LOCK, _db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS auth_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
        """)

_init()

def create_user(username, password, role="employee"):
    from core.auth.password import hash_password
    now = _now()
    with LOCK, _db() as db:
        db.execute("INSERT INTO auth_users(username,password_hash,role,enabled,created_at) VALUES(?,?,?,?,?)",
                   (username, hash_password(password), role, 1, now))

def verify_user(username, password):
    with LOCK, _db() as db:
        row = db.execute("SELECT password_hash, role, enabled FROM auth_users WHERE username=?", (username,)).fetchone()
    if not row or not row["enabled"]:
        return None
    from core.auth.password import verify_password
    if not verify_password(password, row["password_hash"]):
        return None
    return {"username": username, "role": row["role"]}

def create_session(username, ttl_seconds=28800):
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = time.time() + ttl_seconds
    import datetime
    expires_iso = datetime.datetime.fromtimestamp(expires, datetime.timezone.utc).isoformat()
    with LOCK, _db() as db:
        db.execute("INSERT INTO auth_sessions(token,username,created_at,expires_at) VALUES(?,?,?,?)",
                   (token, username, now, expires_iso))
    return token

def get_session(token):
    with LOCK, _db() as db:
        row = db.execute("SELECT username,expires_at,revoked FROM auth_sessions WHERE token=?", (token,)).fetchone()
    if not row or row["revoked"]:
        return None
    from datetime import datetime, timezone
    try:
        exp = datetime.fromisoformat(row["expires_at"].replace("Z","+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        else:
            exp = exp.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None
    if exp <= datetime.now(timezone.utc):
        return None
    # fetch role
    with LOCK, _db() as db:
        u = db.execute("SELECT role,enabled FROM auth_users WHERE username=?", (row["username"],)).fetchone()
    if not u or not u["enabled"]:
        return None
    return {"username": row["username"], "role": u["role"]}

def revoke_session(token):
    with LOCK, _db() as db:
        db.execute("UPDATE auth_sessions SET revoked=1 WHERE token=?", (token,))

def revoke_all(username):
    with LOCK, _db() as db:
        db.execute("UPDATE auth_sessions SET revoked=1 WHERE username=?", (username,))
