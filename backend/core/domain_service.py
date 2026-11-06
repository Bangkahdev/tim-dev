"""AD DS-inspired internal Directory Service + DNS for Bangkah office.

Model backend, bukan Active Directory Windows sungguhan. Semua data disimpan
di SQLite yang sama dengan OfficeStore.
"""

import ipaddress
import os
import re
import threading

from core.office_store import LOCK, STORE, _now

DEFAULT_DOMAIN = "bangkah.my.id"
DEFAULT_OU = "OU=Workstations,DC=bangkah,DC=my,DC=id"

STATE_LOCK = threading.RLock()

_DNS_TYPES = {"A", "AAAA", "CNAME", "MX", "SRV", "PTR", "TXT"}

_SEED_DNS_RECORDS = [
    ("dc", "A", "127.0.0.1"),
    ("bangkah.my.id", "A", "127.0.0.1"),
    ("OWNER-PC-001.bangkah.my.id", "A", "127.0.0.1"),
    ("PC-MGT-001.bangkah.my.id", "A", "127.0.0.1"),
    ("PC-MGT-002.bangkah.my.id", "A", "127.0.0.1"),
    ("PC-ARC-001.bangkah.my.id", "A", "127.0.0.1"),
    ("PC-BE-001.bangkah.my.id", "A", "127.0.0.1"),
    ("PC-API-001.bangkah.my.id", "A", "127.0.0.1"),
    ("PC-FE-001.bangkah.my.id", "A", "127.0.0.1"),
    ("PC-QA-001.bangkah.my.id", "A", "127.0.0.1"),
]


def _domain_labels(domain_name):
    return [p for p in str(domain_name or DEFAULT_DOMAIN).split(".") if p]


def _ou_path_for(domain_name):
    labels = _domain_labels(domain_name)
    dc = ",".join("DC=" + p for p in labels)
    return "OU=Workstations," + dc


def _valid_value(rtype, value):
    rtype = rtype.upper()
    value = str(value or "").strip()
    if rtype == "A":
        try:
            ipaddress.IPv4Address(value)
            return True
        except ValueError:
            return False
    if rtype == "AAAA":
        try:
            ipaddress.IPv6Address(value)
            return True
        except ValueError:
            return False
    if rtype in ("CNAME", "PTR"):
        return bool(re.match(r"^[A-Za-z0-9._-]+$", value))
    if rtype == "MX":
        parts = value.split()
        if len(parts) != 2:
            return False
        try:
            int(parts[0])
        except ValueError:
            return False
        return bool(re.match(r"^[A-Za-z0-9._-]+$", parts[1]))
    if rtype == "SRV":
        parts = value.split()
        if len(parts) != 4:
            return False
        try:
            int(parts[0]); int(parts[1]); int(parts[2])
        except ValueError:
            return False
        return bool(re.match(r"^[A-Za-z0-9._-]+$", parts[3]))
    if rtype == "TXT":
        return len(value) > 0
    return False


PROTECTED_DNS = {"dc", "bangkah.my.id", "dc.bangkah.my.id"}

class DomainService:
    def __init__(self, store=STORE):
        self.store = store
        self.domain_name = os.getenv("BANGKAH_DOMAIN", DEFAULT_DOMAIN).strip() or DEFAULT_DOMAIN
        self.ou_path = _ou_path_for(self.domain_name)
        self._initialize()

    def _db(self):
        return self.store._db()

    def _initialize(self):
        with LOCK, self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS domain_state (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    domain_name TEXT NOT NULL,
                    internal_dns_managed INTEGER NOT NULL DEFAULT 0,
                    joined_at TEXT,
                    detail TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS domain_ous (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    parent_id INTEGER,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS domain_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '',
                    employee_id TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    ou_id INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS domain_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    ou_id INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS domain_group_members (
                    group_id INTEGER NOT NULL,
                    member_type TEXT NOT NULL,
                    member_id INTEGER NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (group_id, member_type, member_id)
                );
                CREATE TABLE IF NOT EXISTS domain_computers (
                    workstation_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'joined',
                    joined_at TEXT NOT NULL,
                    unjoined_at TEXT,
                    ou_id INTEGER,
                    ou_path TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS dns_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'A',
                    value TEXT NOT NULL,
                    ttl INTEGER NOT NULL DEFAULT 300,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'internal'
                );
            """)
            # Migration: tambah kolom baru bila database lama.
            for stmt in (
                "ALTER TABLE domain_computers ADD COLUMN status TEXT NOT NULL DEFAULT 'joined'",
                "ALTER TABLE domain_computers ADD COLUMN unjoined_at TEXT",
                "ALTER TABLE domain_computers ADD COLUMN ou_id INTEGER",
            ):
                try:
                    db.execute(stmt)
                except Exception:
                    pass
            row = db.execute("SELECT * FROM domain_state WHERE id=1").fetchone()
            if row is None:
                db.execute("""INSERT INTO domain_state
                    (id,domain_name,internal_dns_managed,joined_at,detail)
                    VALUES(1,?,0,'',?)""",
                    (self.domain_name,
                     "Domain dan DNS internal dikembangkan sebagai layanan backend (model)."))
            # default OU
            ou = db.execute("SELECT id FROM domain_ous WHERE name='Workstations'").fetchone()
            if ou is None:
                db.execute("""INSERT INTO domain_ous(name,parent_id,path,created_at)
                    VALUES(?,?,?,?)""",
                    ("Workstations", None, self.ou_path, _now()))
            for name, rtype, value in _SEED_DNS_RECORDS:
                exists = db.execute(
                    "SELECT 1 FROM dns_records WHERE name=? AND type=? AND source='internal'",
                    (name, rtype)).fetchone()
                if not exists:
                    db.execute("""INSERT INTO dns_records(name,type,value,ttl,created_at,source)
                        VALUES(?,?,?,?,?,'internal')""",
                        (name, rtype, value, 300, _now()))

    # ---- State ----
    def _migrate(self, db):
        for stmt in (
            "ALTER TABLE domain_computers ADD COLUMN status TEXT NOT NULL DEFAULT 'joined'",
            "ALTER TABLE domain_computers ADD COLUMN unjoined_at TEXT",
            "ALTER TABLE domain_computers ADD COLUMN ou_id INTEGER",
        ):
            try:
                db.execute(stmt)
            except Exception:
                pass

    def state(self):
        self._initialize()
        with LOCK, self._db() as db:
            self._migrate(db)
            row = db.execute("SELECT * FROM domain_state WHERE id=1").fetchone()
            rows = db.execute("SELECT * FROM domain_computers ORDER BY joined_at").fetchall()
            computers = []
            for r in rows:
                d = dict(r)
                d.setdefault("status", "joined")
                d.setdefault("unjoined_at", None)
                computers.append(d)
            record_count = db.execute("SELECT COUNT(*) AS n FROM dns_records WHERE source='internal'").fetchone()["n"]
        detail = row["detail"] if row else ""
        if row and not row["internal_dns_managed"]:
            detail = "Belum ada workstation yang bergabung ke domain internal."
        return {
            "domain_name": row["domain_name"] if row else self.domain_name,
            "ou_path": self.ou_path,
            "internal_dns_managed": bool(row["internal_dns_managed"]) if row else False,
            "joined_at": row["joined_at"] if row else None,
            "joined_count": len([c for c in computers if c["status"] == "joined"]),
            "joined_computers": computers,
            "dns_record_count": record_count,
            "detail": detail,
            "model_note": "DNS internal hanya berlaku di lingkungan simulasi kantor ini.",
        }

    # ---- OU ----
    def create_ou(self, name, parent_id=None, actor="system"):
        name = str(name or "").strip()
        if not name:
            raise ValueError("Nama OU wajib diisi.")
        with LOCK, self._db() as db:
            if db.execute("SELECT 1 FROM domain_ous WHERE name=?", (name,)).fetchone():
                raise ValueError("OU sudah ada.")
        now = _now()
        with LOCK, self._db() as db:
            parent_path = self.ou_path
            if parent_id:
                prow = db.execute("SELECT path FROM domain_ous WHERE id=?", (parent_id,)).fetchone()
                if prow is None:
                    raise ValueError("Parent OU tidak ditemukan.")
                parent_path = prow["path"]
            path = "OU=%s,%s" % (name, parent_path)
            cur = db.execute("""INSERT INTO domain_ous(name,parent_id,path,created_at) VALUES(?,?,?,?)""",
                             (name, parent_id, path, now))
            oid = cur.lastrowid
            self.store._event(db, "ou_created", actor, str(oid), "OU %s dibuat." % name)
        return {"id": oid, "name": name, "parent_id": parent_id, "path": path, "created_at": now}

    def list_ous(self):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM domain_ous ORDER BY id")]

    def move_object(self, object_type, object_id, target_ou_id, actor="system"):
        object_type = str(object_type or "").strip().lower()
        if object_type not in ("user", "group", "computer"):
            raise ValueError("Tipe object tidak valid.")
        with LOCK, self._db() as db:
            ou = db.execute("SELECT id FROM domain_ous WHERE id=?", (target_ou_id,)).fetchone()
            if ou is None:
                raise ValueError("Target OU tidak ditemukan.")
            if object_type == "user":
                db.execute("UPDATE domain_users SET ou_id=? WHERE id=?", (target_ou_id, object_id))
            elif object_type == "group":
                db.execute("UPDATE domain_groups SET ou_id=? WHERE id=?", (target_ou_id, object_id))
            else:
                ourow = db.execute("SELECT path FROM domain_ous WHERE id=?", (target_ou_id,)).fetchone()
                db.execute("UPDATE domain_computers SET ou_id=?, ou_path=? WHERE workstation_id=?",
                           (target_ou_id, ourow["path"] if ourow else self.ou_path, object_id))
            self.store._event(db, "object_moved", actor, str(object_id),
                              "%s %s dipindah ke OU %s" % (object_type, object_id, target_ou_id))
        return {"object_type": object_type, "object_id": object_id, "target_ou_id": target_ou_id}

    # ---- Users ----
    def create_user(self, username, display_name="", employee_id=None, ou_id=None, actor="system"):
        username = str(username or "").strip()
        if not username:
            raise ValueError("Username wajib diisi.")
        with LOCK, self._db() as db:
            if db.execute("SELECT 1 FROM domain_users WHERE username=?", (username,)).fetchone():
                raise ValueError("User sudah ada.")
        now = _now()
        with LOCK, self._db() as db:
            cur = db.execute("""INSERT INTO domain_users(username,display_name,employee_id,enabled,ou_id,created_at)
                VALUES(?,?,?,?,?,?)""",
                (username, display_name, employee_id, 1, ou_id, now))
            uid = cur.lastrowid
            self.store._event(db, "user_created", actor, username, "User %s dibuat." % username)
        return {"id": uid, "username": username, "display_name": display_name,
                "employee_id": employee_id, "enabled": True, "ou_id": ou_id, "created_at": now}

    def list_users(self):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM domain_users ORDER BY id")]

    def set_user_enabled(self, user_id, enabled, actor="system"):
        with LOCK, self._db() as db:
            db.execute("UPDATE domain_users SET enabled=? WHERE id=?", (1 if enabled else 0, user_id))
            self.store._event(db, "user_enabled_changed", actor, str(user_id),
                              "User %s enabled=%s" % (user_id, enabled))
        return {"id": user_id, "enabled": bool(enabled)}

    # ---- Groups ----
    def create_group(self, name, description="", ou_id=None, actor="system"):
        name = str(name or "").strip()
        if not name:
            raise ValueError("Nama group wajib diisi.")
        with LOCK, self._db() as db:
            if db.execute("SELECT 1 FROM domain_groups WHERE name=?", (name,)).fetchone():
                raise ValueError("Group sudah ada.")
        now = _now()
        with LOCK, self._db() as db:
            cur = db.execute("""INSERT INTO domain_groups(name,description,ou_id,created_at) VALUES(?,?,?,?)""",
                             (name, description, ou_id, now))
            gid = cur.lastrowid
            self.store._event(db, "group_created", actor, name, "Group %s dibuat." % name)
        return {"id": gid, "name": name, "description": description, "ou_id": ou_id, "created_at": now}

    def list_groups(self):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM domain_groups ORDER BY id")]

    def add_group_member(self, group_id, member_type, member_id, actor="system"):
        member_type = str(member_type or "").strip().lower()
        if member_type not in ("user", "computer"):
            raise ValueError("Tipe member tidak valid.")
        now = _now()
        with LOCK, self._db() as db:
            if not db.execute("SELECT 1 FROM domain_groups WHERE id=?", (group_id,)).fetchone():
                raise ValueError("Group tidak ditemukan.")
            if member_type == "user" and not db.execute("SELECT 1 FROM domain_users WHERE id=?", (member_id,)).fetchone():
                raise ValueError("User tidak ditemukan.")
            if member_type == "computer" and not db.execute("SELECT 1 FROM domain_computers WHERE workstation_id=?", (str(member_id),)).fetchone():
                raise ValueError("Komputer tidak ditemukan.")
            db.execute("""INSERT OR IGNORE INTO domain_group_members(group_id,member_type,member_id,added_at)
                VALUES(?,?,?,?)""", (group_id, member_type, member_id, now))
            self.store._event(db, "group_member_added", actor, str(group_id),
                              "%s %s ditambah ke group %s" % (member_type, member_id, group_id))
        return {"group_id": group_id, "member_type": member_type, "member_id": member_id}

    def group_members(self, group_id):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM domain_group_members WHERE group_id=?", (group_id,))]

    # ---- Computers / lifecycle ----
    def join_domain(self, workstation_id, actor="system"):
        workstation_id = str(workstation_id or "").strip()
        if not workstation_id:
            raise ValueError("Workstation ID wajib diisi.")
        now = _now()
        with LOCK, self._db() as db:
            row = db.execute("SELECT 1 FROM domain_computers WHERE workstation_id=?",
                             (workstation_id,)).fetchone()
            if row is None:
                db.execute("""INSERT INTO domain_computers
                    (workstation_id,status,joined_at,unjoined_at,ou_id,ou_path,detail)
                    VALUES(?,?,?,?,?,?,?)""",
                    (workstation_id, "joined", now, None, None, self.ou_path,
                     "Bergabung ke domain %s." % self.domain_name))
            else:
                db.execute("""UPDATE domain_computers SET status='joined',joined_at=?,unjoined_at=NULL,
                    ou_path=? WHERE workstation_id=?""",
                    (now, self.ou_path, workstation_id))
            db.execute("""UPDATE domain_state SET internal_dns_managed=1,joined_at=?,detail=?
                WHERE id=1""", (now, "DNS internal diaktifkan."))
            self.store._event(db, "domain_join", actor, workstation_id,
                              "%s bergabung ke domain %s." % (workstation_id, self.domain_name))
        return {"workstation_id": workstation_id, "domain": self.domain_name,
                "ou_path": self.ou_path, "status": "joined", "joined_at": now}

    def unjoin_domain(self, workstation_id, actor="system"):
        workstation_id = str(workstation_id or "").strip()
        if not workstation_id:
            raise ValueError("Workstation ID wajib diisi.")
        now = _now()
        with LOCK, self._db() as db:
            row = db.execute("SELECT 1 FROM domain_computers WHERE workstation_id=?",
                             (workstation_id,)).fetchone()
            if row is None:
                raise ValueError("Komputer tidak terdaftar di domain.")
            db.execute("""UPDATE domain_computers SET status='unjoined',unjoined_at=? WHERE workstation_id=?""",
                       (now, workstation_id))
            self.store._event(db, "domain_unjoin", actor, workstation_id,
                              "%s keluar dari domain %s." % (workstation_id, self.domain_name))
        return {"workstation_id": workstation_id, "status": "unjoined", "unjoined_at": now}

    def rejoin_domain(self, workstation_id, actor="system"):
        r = self.join_domain(workstation_id, actor)
        with LOCK, self._db() as db:
            self.store._event(db, "domain_rejoin", actor, workstation_id,
                              "%s rejoin domain %s." % (workstation_id, self.domain_name))
        r["status"] = "joined"
        return r

    def list_computers(self):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM domain_computers ORDER BY joined_at")]

    # ---- DNS ----
    def dns_lookup(self, name, rtype=None):
        name = str(name or "").strip().lower()
        if not name:
            return None
        with LOCK, self._db() as db:
            if rtype:
                row = db.execute("""SELECT name,type,value,ttl,source FROM dns_records
                    WHERE lower(name)=? AND type=? ORDER BY id LIMIT 1""",
                    (name, rtype.upper())).fetchone()
            else:
                row = db.execute("""SELECT name,type,value,ttl,source FROM dns_records
                    WHERE lower(name)=? ORDER BY id LIMIT 1""", (name,)).fetchone()
        if row is None:
            return None
        return {"name": row["name"], "type": row["type"], "value": row["value"],
                "ttl": row["ttl"], "source": row["source"]}

    def dns_lookup_all(self, name, rtype=None):
        name = str(name or "").strip().lower()
        if not name:
            return []
        with LOCK, self._db() as db:
            if rtype:
                rows = db.execute("""SELECT name,type,value,ttl,source FROM dns_records
                    WHERE lower(name)=? AND type=? ORDER BY id""", (name, rtype.upper())).fetchall()
            else:
                rows = db.execute("""SELECT name,type,value,ttl,source FROM dns_records
                    WHERE lower(name)=? ORDER BY id""", (name,)).fetchall()
        return [dict(r) for r in rows]

    def dns_records(self, rtype=None):
        with LOCK, self._db() as db:
            if rtype:
                rows = db.execute("""SELECT name,type,value,ttl,source FROM dns_records
                    WHERE type=? ORDER BY id""", (rtype.upper(),)).fetchall()
            else:
                rows = db.execute("""SELECT name,type,value,ttl,source FROM dns_records
                    ORDER BY id""").fetchall()
        return [dict(row) for row in rows]

    def add_dns_record(self, name, rtype, value, actor="system", ttl=300):
        name = str(name or "").strip()
        rtype = str(rtype or "A").strip().upper()
        value = str(value or "").strip()
        if not name or not value:
            raise ValueError("Nama dan nilai rekaman DNS wajib diisi.")
        if rtype not in _DNS_TYPES:
            raise ValueError("Tipe rekaman DNS tidak didukung: %s" % rtype)
        try:
            ttl_i = int(ttl or 300)
        except (ValueError, TypeError):
            raise ValueError("TTL harus angka.")
        if ttl_i < 1 or ttl_i > 86400:
            raise ValueError("TTL harus antara 1 dan 86400.")
        if not _valid_value(rtype, value):
            raise ValueError("Nilai tidak valid untuk tipe %s." % rtype)
        if name.lower() in PROTECTED_DNS and rtype in ("A",):
            # allow update only, not duplicate? keep simple: allow
            pass
        now = _now()
        with LOCK, self._db() as db:
            # conflict check: CNAME cannot coexist
            existing = db.execute("SELECT type FROM dns_records WHERE lower(name)=?",
                                  (name.lower(),)).fetchall()
            existing_types = {r["type"] for r in existing}
            if rtype == "CNAME" and existing_types:
                raise ValueError("CNAME tidak boleh berdampingan dengan record lain.")
            if existing_types and "CNAME" in existing_types and rtype != "CNAME":
                raise ValueError("Nama sudah memiliki CNAME.")
            # duplicate exact
            dup = db.execute("""SELECT 1 FROM dns_records WHERE lower(name)=? AND type=? AND value=?""",
                             (name.lower(), rtype, value)).fetchone()
            if dup:
                raise ValueError("Record duplikat.")
            db.execute("""INSERT INTO dns_records(name,type,value,ttl,created_at,source)
                VALUES(?,?,?,?,?,'admin')""",
                (name, rtype, value, int(ttl or 300), now))
            self.store._event(db, "dns_record_added", actor, name,
                              "%s %s -> %s" % (name, rtype, value))
        return {"name": name, "type": rtype, "value": value, "ttl": int(ttl or 300),
                "source": "admin", "created_at": now}

    def update_dns_record(self, record_id, value=None, ttl=None, actor="system"):
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM dns_records WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise ValueError("Record tidak ditemukan.")
            new_value = value if value is not None else row["value"]
            new_ttl = ttl if ttl is not None else row["ttl"]
            if not _valid_value(row["type"], new_value):
                raise ValueError("Nilai tidak valid.")
            if row["name"].lower() in PROTECTED_DNS and row["source"]=="internal":
                # protect internal records from arbitrary deletion? update allowed value same? block type change not possible
                pass
            db.execute("UPDATE dns_records SET value=?,ttl=? WHERE id=?", (new_value, new_ttl, record_id))
            self.store._event(db, "dns_record_updated", actor, str(record_id),
                              "Record %s diperbarui." % record_id)
        return {"id": record_id, "value": new_value, "ttl": new_ttl}

    def delete_dns_record(self, record_id, actor="system"):
        with LOCK, self._db() as db:
            row = db.execute("SELECT name,type FROM dns_records WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise ValueError("Record tidak ditemukan.")
            src = db.execute("SELECT source FROM dns_records WHERE id=?", (record_id,)).fetchone()["source"]
            if src == "internal" and row["name"].lower() in PROTECTED_DNS:
                raise ValueError("Record internal dilindungi.")
            db.execute("DELETE FROM dns_records WHERE id=?", (record_id,))
            self.store._event(db, "dns_record_deleted", actor, str(record_id),
                              "Record %s %s dihapus." % (row["name"], row["type"]))
        return {"id": record_id, "deleted": True}


DOMAIN = DomainService()
