"""WS2 security hardening tests.

Covers the acceptance contract for the quick security fixes:

- every POST route in the infra/ftp/mail/network group survives invalid input
  without dropping the connection, returning a traceback, or leaking raw
  exception text;
- failed-login lockout is stored in SQLite and survives a backend restart;
- (the Godot 401/429 distinction is exercised by tools/check_godot_auth.py and
  godot/scripts/auth_login_check.gd, which need the Godot binary).
"""

import http.client
import json
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer

import office_server as server
from core.auth import sessions
from core.office_store import LOCK, STORE

RAW_LEAK_MARKERS = (
    "Traceback",
    "Exception",
    "Error:",
    "sqlite3.",
    'File "',
    "KeyError",
    "TypeError",
    "ValueError",
    "AttributeError",
    "IndexError",
    "OperationalError",
)

# Values that are invalid, hostile, or simply the wrong type for every field.
INVALID_VALUES = [
    None,
    [],
    {},
    True,
    0,
    -1,
    "",
    " ",
    "x" * 5000,
    "../../etc/passwd",
    "a b c",
    "\x00",
    "'; DROP TABLE auth_users; --",
    "<script>alert(1)</script>",
    ["a"],
    {"nested": 1},
    3.14,
]

ROUTES = {
    "/api/infra/service/stop": "service_id",
    "/api/ftp/provision": "username",
    "/api/mail/provision": "username",
    "/api/network/subnet": "cidr",
    "/api/network/scope": "lease_seconds",
    "/api/network/lease": "scope_id",
    "/api/network/vpn/peer": "allowed_ips",
}


class RouteErrorFuzzTests(unittest.TestCase):
    SUFFIX = uuid.uuid4().hex[:6]
    PASSWORD = "ws2-fuzz-password-123"

    @classmethod
    def setUpClass(cls):
        cls.HTTPD = ThreadingHTTPServer(("127.0.0.1", 0), server.OfficeHandler)
        cls.PORT = cls.HTTPD.server_address[1]
        threading.Thread(target=cls.HTTPD.serve_forever, daemon=True).start()
        cls.user = f"ws2.owner.{cls.SUFFIX}"
        with LOCK, STORE._db() as db:
            db.execute("DELETE FROM auth_sessions WHERE username=?", (cls.user,))
            db.execute("DELETE FROM auth_users WHERE username=?", (cls.user,))
        sessions.create_user(cls.user, cls.PASSWORD, "owner", department_id="executive")
        cls.token = cls.login()

    @classmethod
    def tearDownClass(cls):
        cls.HTTPD.shutdown()
        cls.HTTPD.server_close()
        with LOCK, STORE._db() as db:
            db.execute("DELETE FROM auth_sessions WHERE username=?", (cls.user,))
            db.execute("DELETE FROM auth_users WHERE username=?", (cls.user,))

    @classmethod
    def login(cls):
        status, body, _ = cls.request("POST", "/api/auth/login", {
            "username": cls.user, "password": cls.PASSWORD})
        assert status == 200, (status, body)
        return body["session"]["token"]

    @classmethod
    def request(cls, method, path, body=None, token=None):
        connection = http.client.HTTPConnection("127.0.0.1", cls.PORT, timeout=20)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        payload = json.dumps(body) if body is not None else None
        connection.request(method, path, payload, headers)
        response = connection.getresponse()
        raw = response.read()
        status = response.status
        connection.close()
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        return status, data, raw.decode("utf-8", "replace")

    def _payloads(self, field):
        payloads = [{}]
        for value in INVALID_VALUES:
            payloads.append({field: value})
        # Wrong field name, extra nesting and mixed types.
        payloads.append({"unexpected": INVALID_VALUES})
        payloads.append({field: "valid-looking", "extra": {"deep": [1, 2, 3]}})
        payloads.append({field: "-" * 1000})
        self.assertGreaterEqual(len(payloads), 20)
        return payloads

    def test_invalid_input_never_leaks_raw_exception(self):
        for route, field in ROUTES.items():
            for payload in self._payloads(field):
                with self.subTest(route=route, payload=repr(payload)[:120]):
                    status, data, raw = self.request(
                        "POST", route, payload, token=self.token)
                    self.assertIsInstance(status, int)
                    self.assertLess(status, 600)
                    for marker in RAW_LEAK_MARKERS:
                        self.assertNotIn(marker, raw,
                                         f"{route} leaked {marker!r}: {raw[:400]}")
                    if status >= 400:
                        self.assertIn("error", data, data)
                    if status == 500:
                        self.assertTrue(data.get("correlation_id"), data)


class LoginThrottlePersistenceTests(unittest.TestCase):
    USER = "ws2.persist.owner"
    PASSWORD = "ws2-persist-password-123"

    def setUp(self):
        sessions.clear_login_throttle()
        with LOCK, STORE._db() as db:
            db.execute("DELETE FROM auth_sessions WHERE username=?", (self.USER,))
            db.execute("DELETE FROM auth_users WHERE username=?", (self.USER,))
        sessions.create_user(self.USER, self.PASSWORD, "owner", department_id="executive")

    def tearDown(self):
        sessions.clear_login_throttle()
        with LOCK, STORE._db() as db:
            db.execute("DELETE FROM auth_sessions WHERE username=?", (self.USER,))
            db.execute("DELETE FROM auth_users WHERE username=?", (self.USER,))

    def test_lockout_is_persisted_and_survives_reinitialization(self):
        now = {"ts": 7_000_000.0}
        clock = lambda: now["ts"]
        ip = "10.42.0.9"
        for _ in range(5):
            self.assertIsNone(
                sessions.verify_user(self.USER, "wrong-password", client_ip=ip, clock=clock))
        key = sessions._key("pair", self.USER, ip)
        with LOCK, STORE._db() as db:
            row = db.execute(
                "SELECT count, first_ts, lock_until FROM auth_login_attempts WHERE key=?",
                (key,),
            ).fetchone()
        self.assertIsNotNone(row, "failed-login counter was not written to SQLite")
        self.assertGreaterEqual(row["count"], 5)
        self.assertGreater(row["lock_until"], now["ts"])

        # Simulate a backend restart: the schema initializer runs again in the
        # new process and must not reset persisted counters.
        sessions._init()
        with self.assertRaises(sessions.LoginThrottled):
            sessions.verify_user(self.USER, self.PASSWORD, client_ip=ip, clock=clock)

    def test_successful_login_clears_persisted_counter(self):
        now = {"ts": 8_000_000.0}
        clock = lambda: now["ts"]
        ip = "10.42.0.10"
        for _ in range(4):
            self.assertIsNone(
                sessions.verify_user(self.USER, "wrong-password", client_ip=ip, clock=clock))
        self.assertIsNotNone(
            sessions.verify_user(self.USER, self.PASSWORD, client_ip=ip, clock=clock))
        with LOCK, STORE._db() as db:
            rows = db.execute(
                "SELECT key FROM auth_login_attempts WHERE key LIKE ?",
                (f"%{self.USER}%",),
            ).fetchall()
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
