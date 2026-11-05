"""Domain dan DNS internal untuk kantor Bangkah.

Ini adalah *model backend*, bukan Active Directory Domain Services Windows
sungguhan, dan bukan join domain komputer host. Semua komputer di kantor
(desktop workstation) tercatat sebagai anggota domain internal
``bangkah.my.id`` (atau nilai ``BANGKAH_DOMAIN``), dengan catatan DNS internal
yang dapat dilihat dan dicek melalui API. Setiap operasi (join domain,
tambah rekaman DNS) ditulis ke audit trail perusahaan agar jujur dan dapat
ditracking.

Semua data ada di SQLite yang sama dengan OfficeStore (`backend/data/office.db`
secara default), bukan directory service terpisah.
"""

import os
import threading

from core.office_store import LOCK, STORE, _now

DEFAULT_DOMAIN = "bangkah.my.id"
DEFAULT_OU = "OU=Workstations,DC=bangkah,DC=my,DC=id"

STATE_LOCK = threading.RLock()

# Rekaman DNS internal yang di-seed saat pertama kali diinisialisasi: setiap
# workstation katalog serta domain controller virtual, semuanya arahkan ke
# loopback karena ini layanan internal simulasi, bukan jaringan fisik.
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


def _domain_labels(domain_name: str) -> list:
    return [part for part in str(domain_name or DEFAULT_DOMAIN).split(".") if part]


def _ou_path_for(domain_name: str) -> str:
    labels = _domain_labels(domain_name)
    dc = ",".join("DC=" + part for part in labels)
    return "OU=Workstations," + dc


class DomainService:
    def __init__(self, store=STORE):
        self.store = store
        self.domain_name = os.getenv("BANGKAH_DOMAIN", DEFAULT_DOMAIN).strip() or DEFAULT_DOMAIN
        self.ou_path = _ou_path_for(self.domain_name)
        self._initialize()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
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
                CREATE TABLE IF NOT EXISTS domain_computers (
                    workstation_id TEXT PRIMARY KEY,
                    joined_at TEXT NOT NULL,
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
            row = db.execute("SELECT * FROM domain_state WHERE id=1").fetchone()
            if row is None:
                db.execute("""INSERT INTO domain_state
                    (id,domain_name,internal_dns_managed,joined_at,detail)
                    VALUES(1,?,0,'',?)""",
                    (self.domain_name,
                     "Domain dan DNS internal dikembangkan sebagai layanan backend (model), "
                     "bukan Active Directory Windows sungguhan."))
            # Seed catatan DNS internal sekali saja, tanpa menimpa yang ada.
            for name, rtype, value in _SEED_DNS_RECORDS:
                exists = db.execute(
                    "SELECT 1 FROM dns_records WHERE name=? AND type=? AND source='internal'",
                    (name, rtype)).fetchone()
                if not exists:
                    db.execute("""INSERT INTO dns_records(name,type,value,ttl,created_at,source)
                        VALUES(?,?,?,?,?,'internal')""",
                        (name, rtype, value, 300, _now()))

    def state(self) -> dict:
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM domain_state WHERE id=1").fetchone()
            computers = [dict(r) for r in db.execute(
                "SELECT workstation_id,joined_at,ou_path FROM domain_computers ORDER BY joined_at")]
            record_count = db.execute("SELECT COUNT(*) AS n FROM dns_records WHERE source='internal'").fetchone()["n"]
        detail = (row["detail"] if row else "") if row else ""
        if row and not row["internal_dns_managed"]:
            detail = "Belum ada workstation yang bergabung ke domain internal."
        return {
            "domain_name": row["domain_name"] if row else self.domain_name,
            "ou_path": self.ou_path,
            "internal_dns_managed": bool(row["internal_dns_managed"]) if row else False,
            "joined_at": row["joined_at"] if row else None,
            "joined_count": len(computers),
            "joined_computers": computers,
            "dns_record_count": record_count,
            "detail": detail,
            "model_note": "DNS internal hanya berlaku di lingkungan simulasi kantor ini; DNS eksternal dan email belum diaktifkan.",
        }

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------
    def join_domain(self, workstation_id: str, actor: str = "system") -> dict:
        workstation_id = str(workstation_id or "").strip()
        if not workstation_id:
            raise ValueError("Workstation ID wajib diisi.")
        now = _now()
        with LOCK, self._db() as db:
            row = db.execute("SELECT 1 FROM domain_computers WHERE workstation_id=?",
                             (workstation_id,)).fetchone()
            if row is None:
                db.execute("""INSERT INTO domain_computers
                    (workstation_id,joined_at,ou_path,detail)
                    VALUES(?,?,?,?)""",
                    (workstation_id, now, self.ou_path,
                     "Bergabung ke domain %s melalui layanan domain internal." % self.domain_name))
                db.execute("""UPDATE domain_state
                    SET internal_dns_managed=1,joined_at=?,detail=?
                    WHERE id=1""",
                    (now,
                     "DNS internal diaktifkan setelah workstation pertama bergabung ke domain."))
            else:
                db.execute("UPDATE domain_computers SET joined_at=? WHERE workstation_id=?",
                           (now, workstation_id))
                db.execute("""UPDATE domain_state
                    SET internal_dns_managed=1,joined_at=? WHERE id=1""", (now,))
            self.store._event(db, "domain_join", actor, workstation_id,
                              "%s bergabung ke domain %s (DNS internal)."
                              % (workstation_id, self.domain_name))
        return {"workstation_id": workstation_id, "domain": self.domain_name,
                "ou_path": self.ou_path, "joined_at": now}

    def dns_lookup(self, name: str) -> dict | None:
        name = str(name or "").strip().lower()
        if not name:
            return None
        with LOCK, self._db() as db:
            row = db.execute("""SELECT name,type,value,ttl FROM dns_records
                WHERE lower(name)=? ORDER BY id LIMIT 1""", (name,)).fetchone()
        if row is None:
            return None
        return {"name": row["name"], "type": row["type"], "value": row["value"],
                "ttl": row["ttl"], "source": "internal"}

    def dns_records(self) -> list:
        with LOCK, self._db() as db:
            rows = db.execute("""SELECT name,type,value,ttl,source FROM dns_records
                ORDER BY id""").fetchall()
        return [dict(row) for row in rows]

    def add_dns_record(self, name: str, rtype: str, value: str,
                       actor: str = "system") -> dict:
        name = str(name or "").strip()
        rtype = str(rtype or "A").strip().upper()
        value = str(value or "").strip()
        if not name or not value:
            raise ValueError("Nama dan nilai rekaman DNS wajib diisi.")
        if rtype not in ("A", "CNAME", "TXT", "MX"):
            raise ValueError("Tipe rekaman DNS tidak didukung: %s" % rtype)
        now = _now()
        with LOCK, self._db() as db:
            db.execute("""INSERT INTO dns_records(name,type,value,ttl,created_at,source)
                VALUES(?,?,?,?,?,'admin')""",
                (name, rtype, value, 300, now))
            self.store._event(db, "dns_record_added", actor, name,
                              "%s %s -> %s" % (name, rtype, value))
        return {"name": name, "type": rtype, "value": value, "ttl": 300,
                "source": "admin", "created_at": now}


DOMAIN = DomainService()
