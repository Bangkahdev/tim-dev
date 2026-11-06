"""Slice A: Infrastructure Control Plane for Bangkah."""

import threading

from core.office_store import LOCK, STORE, _now


class InfraService:
    def __init__(self, store=STORE):
        self.store = store
        self._initialize()

    def _db(self):
        return self.store._db()

    def _initialize(self):
        with LOCK, self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS infra_services (
                    service_id TEXT PRIMARY KEY,
                    service_name TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'STOPPED',
                    host TEXT NOT NULL DEFAULT '127.0.0.1',
                    port INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT,
                    last_health_check TEXT,
                    version TEXT NOT NULL DEFAULT '1.0'
                );
                CREATE TABLE IF NOT EXISTS infra_health_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    result TEXT NOT NULL,
                    checked_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS infra_configs (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            defaults = [
                ("directory", "Directory Service", "Directory", "127.0.0.1", 0),
                ("dns", "Internal DNS", "Directory", "127.0.0.1", 0),
                ("ftp", "FTP Server", "FTP", "127.0.0.1", 2121),
                ("mail_smtp", "SMTP Server", "Mail", "127.0.0.1", 2525),
                ("mail_pop3", "POP3 Server", "Mail", "127.0.0.1", 1110),
                ("dhcp", "DHCP Engine", "Network", "127.0.0.1", 0),
                ("vpn", "VPN Control Plane", "Network", "127.0.0.1", 0),
            ]
            for sid, name, stype, host, port in defaults:
                if not db.execute("SELECT 1 FROM infra_services WHERE service_id=?", (sid,)).fetchone():
                    db.execute("""INSERT INTO infra_services(service_id,service_name,service_type,enabled,status,host,port,version)
                        VALUES(?,?,?,?,?,?,?,?)""",
                        (sid, name, stype, 1, "STOPPED", host, port, "1.0"))

    def list_services(self):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM infra_services ORDER BY service_id")]

    def get_service(self, service_id):
        with LOCK, self._db() as db:
            row = db.execute("SELECT * FROM infra_services WHERE service_id=?", (service_id,)).fetchone()
        return dict(row) if row else None

    def set_status(self, service_id, status, actor="system"):
        now = _now()
        with LOCK, self._db() as db:
            db.execute("UPDATE infra_services SET status=?, last_health_check=? WHERE service_id=?",
                       (status, now, service_id))
            self.store._event(db, "service_status", actor, service_id, "Service %s -> %s" % (service_id, status))
        return self.get_service(service_id)

    def start(self, service_id, actor="system"):
        return self.set_status(service_id, "RUNNING", actor)

    def stop(self, service_id, actor="system"):
        return self.set_status(service_id, "STOPPED", actor)

    def restart(self, service_id, actor="system"):
        self.stop(service_id, actor)
        return self.start(service_id, actor)

    def health_check(self, service_id, actor="system"):
        now = _now()
        svc = self.get_service(service_id)
        result = "OK" if svc and svc["status"] == "RUNNING" else "DEGRADED"
        with LOCK, self._db() as db:
            db.execute("""INSERT INTO infra_health_checks(service_id,check_type,result,checked_at)
                VALUES(?,?,?,?)""", (service_id, "liveness", result, now))
            db.execute("UPDATE infra_services SET last_health_check=? WHERE service_id=?", (now, service_id))
        return {"service_id": service_id, "result": result, "checked_at": now}

    def set_config(self, key, value, actor="system"):
        now = _now()
        with LOCK, self._db() as db:
            db.execute("""INSERT INTO infra_configs(key,value,updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, value, now))
            self.store._event(db, "config_changed", actor, key, "Config %s updated" % key)
        return {"key": key, "value": value}

    def get_config(self, key):
        with LOCK, self._db() as db:
            row = db.execute("SELECT value FROM infra_configs WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


INFRA = InfraService()
