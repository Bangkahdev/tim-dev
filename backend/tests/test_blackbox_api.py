"""Black-box tests: exercise the system only through its public HTTP interface.

These tests start the real HTTP handler on loopback and assert status codes,
error shapes, headers (Retry-After), and observable behavior without reaching
into internals beyond the documented API.
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


class BlackboxHttpApiTests(unittest.TestCase):
    PORT = None
    HTTPD = None
    SUFFIX = uuid.uuid4().hex[:8]
    PW = "integration-password-123"

    @classmethod
    def setUpClass(cls):
        cls.HTTPD = ThreadingHTTPServer(("127.0.0.1", 0), server.OfficeHandler)
        cls.PORT = cls.HTTPD.server_address[1]
        threading.Thread(target=cls.HTTPD.serve_forever, daemon=True).start()
        cls.owner = f"bb.owner.{cls.SUFFIX}"
        with LOCK, STORE._db() as db:
            db.execute("DELETE FROM auth_sessions WHERE username LIKE ?", (f"%{cls.SUFFIX}%",))
            db.execute("DELETE FROM auth_users WHERE username LIKE ?", (f"%{cls.SUFFIX}%",))
        sessions.create_user(cls.owner, cls.PW, "owner", department_id="executive")

    @classmethod
    def tearDownClass(cls):
        cls.HTTPD.shutdown(); cls.HTTPD.server_close()
        with LOCK, STORE._db() as db:
            db.execute("DELETE FROM auth_sessions WHERE username LIKE ?", (f"%{cls.SUFFIX}%",))
            db.execute("DELETE FROM auth_users WHERE username LIKE ?", (f"%{cls.SUFFIX}%",))

    def setUp(self):
        sessions.clear_login_throttle()

    def req(self, method, path, body=None, token=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.PORT, timeout=15)
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = "Bearer " + token
        if headers:
            h.update(headers)
        c.request(method, path, json.dumps(body).encode() if body is not None else None, h)
        r = c.getresponse(); raw = r.read(); hdrs = {k: v for k, v in r.getheaders()}
        c.close()
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"raw": raw.decode("utf-8", "replace")}
        return r.status, hdrs, data

    def test_protected_routes_require_auth_and_bad_token_rejected(self):
        for method, path in (("GET", "/api/departments"), ("GET", "/api/status"), ("GET", "/api/tasks")):
            st, _, body = self.req(method, path)
            self.assertEqual(st, 401, body)
        st, _, body = self.req("GET", "/api/departments", token="garbage-token")
        self.assertEqual(st, 401, body)

    def test_login_success_returns_session_and_me_works(self):
        st, _, body = self.req("POST", "/api/auth/login", {"username": self.owner, "password": self.PW})
        self.assertEqual(st, 200, body)
        self.assertTrue(body.get("session", {}).get("token"))
        token = body["session"]["token"]
        st, _, me = self.req("GET", "/api/auth/me", token=token)
        self.assertEqual(st, 200, me)
        self.assertEqual(me["user"]["username"], self.owner)

    def test_invalid_credentials_generic_and_nonexistent_same_shape(self):
        st, _, a = self.req("POST", "/api/auth/login", {"username": self.owner, "password": "wrong"})
        st2, _, b = self.req("POST", "/api/auth/login", {"username": "nope." + self.SUFFIX, "password": "wrong"})
        self.assertEqual(st, 401); self.assertEqual(st2, 401)
        self.assertEqual(a.get("error", {}).get("code"), b.get("error", {}).get("code"))
        self.assertEqual(a.get("error", {}).get("message"), b.get("error", {}).get("message"))

    def test_throttle_returns_429_with_retry_after_and_generic_message(self):
        sessions.clear_login_throttle()
        status = hdrs = data = None
        for _ in range(7):
            status, hdrs, data = self.req("POST", "/api/auth/login", {"username": self.owner, "password": "wrong"})
        self.assertEqual(status, 429, data)
        self.assertIn("Retry-After", hdrs)
        self.assertEqual(data.get("error", {}).get("message"), "Login failed")

    def test_logout_revokes_session(self):
        st, _, body = self.req("POST", "/api/auth/login", {"username": self.owner, "password": self.PW})
        token = body["session"]["token"]
        self.req("POST", "/api/auth/logout", {}, token=token)
        st, _, _ = self.req("GET", "/api/auth/me", token=token)
        self.assertEqual(st, 401)

    def test_unknown_route_or_method_denied_safely(self):
        st, _, body = self.req("POST", "/api/auth/login", {"username": self.owner, "password": self.PW})
        token = body["session"]["token"]
        st, _, _ = self.req("GET", "/api/this-route-does-not-exist-xyz", token=token)
        self.assertIn(st, (401, 403, 404))
