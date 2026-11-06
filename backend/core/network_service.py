"""Slice E: Network services model (DHCP + VPN, backend-simulated)."""

import threading
from core.office_store import LOCK, STORE, _now


class NetworkService:
    def __init__(self, store=STORE):
        self.store = store
        self._initialize()

    def _db(self):
        return self.store._db()

    def _initialize(self):
        with LOCK, self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS networks (id TEXT PRIMARY KEY, name TEXT NOT NULL, cidr TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS subnets (id TEXT PRIMARY KEY, network_id TEXT NOT NULL, name TEXT NOT NULL, cidr TEXT NOT NULL, gateway TEXT, dns TEXT);
                CREATE TABLE IF NOT EXISTS dhcp_scopes (id TEXT PRIMARY KEY, subnet_id TEXT NOT NULL, name TEXT NOT NULL, pool_start TEXT, pool_end TEXT, lease_seconds INTEGER NOT NULL DEFAULT 86400, enabled INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS dhcp_leases (id INTEGER PRIMARY KEY AUTOINCREMENT, scope_id TEXT NOT NULL, hostname TEXT, mac TEXT, ip TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', allocated_at TEXT, expires_at TEXT);
                CREATE TABLE IF NOT EXISTS dhcp_reservations (id INTEGER PRIMARY KEY AUTOINCREMENT, scope_id TEXT NOT NULL, hostname TEXT, mac TEXT, ip TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS vpn_peers (id TEXT PRIMARY KEY, username TEXT NOT NULL, device TEXT, allowed_ips TEXT, status TEXT NOT NULL DEFAULT 'ENABLED', created_at TEXT);
                CREATE TABLE IF NOT EXISTS network_policies (id INTEGER PRIMARY KEY AUTOINCREMENT, group_name TEXT NOT NULL, source TEXT, destination TEXT, action TEXT NOT NULL DEFAULT 'allow');
            """)
            # seed default network
            if not db.execute("SELECT 1 FROM networks WHERE id='bangkah-net'").fetchone():
                db.execute("INSERT INTO networks(id,name,cidr) VALUES(?,?,?)", ("bangkah-net", "Bangkah Internal", "10.10.0.0/16"))

    def list_networks(self):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM networks")]

    def create_subnet(self, subnet_id, network_id, name, cidr, gateway=None, dns=None):
        with LOCK, self._db() as db:
            db.execute("INSERT INTO subnets(id,network_id,name,cidr,gateway,dns) VALUES(?,?,?,?,?,?)",
                       (subnet_id, network_id, name, cidr, gateway, dns))
        return {"id": subnet_id, "name": name, "cidr": cidr}

    def list_subnets(self):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM subnets")]

    def create_scope(self, scope_id, subnet_id, name, pool_start, pool_end, lease_seconds=86400):
        with LOCK, self._db() as db:
            db.execute("""INSERT INTO dhcp_scopes(id,subnet_id,name,pool_start,pool_end,lease_seconds) VALUES(?,?,?,?,?,?)""",
                       (scope_id, subnet_id, name, pool_start, pool_end, lease_seconds))
        return {"id": scope_id, "name": name}

    def list_scopes(self):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM dhcp_scopes")]

    def allocate_lease(self, scope_id, hostname, mac, ip):
        now = _now()
        with LOCK, self._db() as db:
            cur = db.execute("""INSERT INTO dhcp_leases(scope_id,hostname,mac,ip,status,allocated_at) VALUES(?,?,?,?,?,?)""",
                             (scope_id, hostname, mac, ip, "active", now))
            lid = cur.lastrowid
        return {"id": lid, "ip": ip, "hostname": hostname}

    def list_leases(self):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM dhcp_leases")]

    def create_vpn_peer(self, peer_id, username, device, allowed_ips):
        with LOCK, self._db() as db:
            db.execute("""INSERT INTO vpn_peers(id,username,device,allowed_ips,status,created_at) VALUES(?,?,?,?,?,?)""",
                       (peer_id, username, device, allowed_ips, "ENABLED", _now()))
        return {"id": peer_id, "username": username, "status": "ENABLED"}

    def list_vpn_peers(self):
        with LOCK, self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM vpn_peers")]

    def revoke_vpn_peer(self, peer_id):
        with LOCK, self._db() as db:
            db.execute("UPDATE vpn_peers SET status='REVOKED' WHERE id=?", (peer_id,))
        return {"id": peer_id, "status": "REVOKED"}


NETWORK = NetworkService()
