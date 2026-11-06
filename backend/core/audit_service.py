import uuid, json
from core.office_store import LOCK, STORE, _now

def _db():
    return STORE._db()

def _init():
    with LOCK, _db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                actor_username TEXT,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                status TEXT NOT NULL,
                ip_address TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );
        """)
_init()

def log(actor_username, action, resource_type=None, resource_id=None, status="success", ip_address=None, details=None):
    eid = uuid.uuid4().hex
    with LOCK, _db() as db:
        db.execute("""INSERT INTO audit_log(id,actor_username,action,resource_type,resource_id,status,ip_address,details,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (eid, actor_username, action, resource_type, resource_id, status, ip_address,
             json.dumps(details or {}), _now()))
    return eid

def query(actor=None, action=None, resource_type=None, since=None, limit=100):
    q = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if actor:
        q += " AND actor_username=?"; params.append(actor)
    if action:
        q += " AND action=?"; params.append(action)
    if resource_type:
        q += " AND resource_type=?"; params.append(resource_type)
    if since:
        q += " AND created_at>=?"; params.append(since)
    q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
    with LOCK, _db() as db:
        return [dict(r) for r in db.execute(q, params)]
