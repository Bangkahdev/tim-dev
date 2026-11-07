import os
import unittest

import core.auth.authentication as A
from core.auth import sessions
from core.auth.password import hash_password, verify_password
from core.office_store import LOCK, STORE


def _db():
    return STORE._db()


def _delete_user(username):
    with LOCK, _db() as db:
        db.execute("DELETE FROM auth_sessions WHERE username=?", (username,))
        db.execute("DELETE FROM auth_users WHERE username=?", (username,))


def _expire(token):
    import hashlib
    token_hash = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
    with LOCK, _db() as db:
        db.execute("UPDATE auth_sessions SET expires_at='2000-01-01T00:00:00+00:00' WHERE token_hash=?", (token_hash,))


class AuthSessionTests(unittest.TestCase):
    def _clear_throttle(self):
        sessions.clear_login_throttle()

    USER = "unit.owner"
    PASSWORD = "correct-horse-battery"

    def setUp(self):
        self._clear_throttle()
        _delete_user(self.USER)
        sessions.create_user(self.USER, self.PASSWORD, "owner", department_id="executive")

    def tearDown(self):
        _delete_user(self.USER)
        self._clear_throttle()

    def test_login_rejects_wrong_password(self):
        self.assertIsNone(A.login(self.USER, "wrong-password"))

    def test_login_creates_verified_session(self):
        result = A.login(self.USER, self.PASSWORD)
        self.assertIsNotNone(result)
        user = A.current_user(result["token"])
        self.assertEqual(user["username"], self.USER)
        self.assertEqual(user["role"], "owner")
        self.assertEqual(user["department_id"], "executive")

    def test_revoked_session_is_rejected(self):
        result = A.login(self.USER, self.PASSWORD)
        A.logout(result["token"])
        self.assertIsNone(A.current_user(result["token"]))

    def test_expired_session_is_rejected(self):
        result = A.login(self.USER, self.PASSWORD)
        _expire(result["token"])
        self.assertIsNone(A.current_user(result["token"]))

    def test_disabled_account_cannot_login_or_keep_session(self):
        result = A.login(self.USER, self.PASSWORD)
        sessions.set_user_enabled(self.USER, False)
        self.assertIsNone(A.login(self.USER, self.PASSWORD))
        self.assertIsNone(A.current_user(result["token"]))

    def test_session_token_is_random_and_not_a_credential(self):
        first = A.login(self.USER, self.PASSWORD)["token"]
        second = A.login(self.USER, self.PASSWORD)["token"]
        self.assertNotEqual(first, second)
        self.assertGreater(len(first), 32)
        self.assertNotEqual(first, self.PASSWORD)

    def test_password_is_hashed_not_stored_plain(self):
        with LOCK, _db() as db:
            stored = db.execute("SELECT password_hash FROM auth_users WHERE username=?",
                                (self.USER,)).fetchone()["password_hash"]
        self.assertNotIn(self.PASSWORD, stored)
        self.assertTrue(stored.startswith("$2"))
        self.assertTrue(verify_password(self.PASSWORD, stored))
        self.assertFalse(verify_password("nope", stored))

    def test_invalid_role_is_rejected(self):
        with self.assertRaises(ValueError):
            sessions.create_user("bad.role.user", "long-enough-password", "superuser")

    def test_server_source_has_no_anonymous_owner_or_body_actor(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "office_server.py").read_text(encoding="utf-8")
        self.assertNotIn('"anonymous"', source)
        self.assertNotIn('body.get("actor"', source)
        self.assertNotIn('actor="operator"', source)
        self.assertNotIn('actor="owner"', source)
        self.assertNotIn('route.count("/") == 2', source)
        self.assertNotIn('route.count("/") == 3', source)

    def test_bootstrap_owner_is_explicit_and_idempotent(self):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        db_path = Path(tempfile.mkdtemp(prefix="bangkah-bootstrap-")) / "office.db"
        code = (
            "from core.auth import sessions as s\n"
            "print('first', s.ensure_bootstrap_owner())\n"
            "print('second', s.ensure_bootstrap_owner())\n"
            "user = s.get_user('owner')\n"
            "print('role', user['role'])\n"
            "print('login', bool(s.verify_user('owner', 'bootstrap-password-123')))\n"
        )
        env = {**os.environ, "BANGKAH_DB_PATH": str(db_path),
               "BANGKAH_OWNER_PASSWORD": "bootstrap-password-123"}
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("first owner", result.stdout)
        self.assertIn("second None", result.stdout)
        self.assertIn("role owner", result.stdout)
        self.assertIn("login True", result.stdout)



    def test_login_throttles_per_username_and_ip_with_injectable_clock(self):
        # 5 failures/10min -> lock 15min (exponential backoff on continued failures), 429+Retry-After at HTTP layer tested separately.
        t = {"now": 1_000_000.0}
        clock = lambda: t["now"]
        ip = "10.0.0.55"
        for _ in range(5):
            self.assertIsNone(A.login(self.USER, "wrong-password", client_ip=ip, clock=clock))
        with self.assertRaises(A.LoginThrottled) as ctx:
            A.login(self.USER, "wrong-password", client_ip=ip, clock=clock)
        self.assertGreaterEqual(ctx.exception.retry_after, 15 * 60)
        # different IP for same user hits looser global limit only after many failures, so this pair is still isolated by its own lock;
        # advance past lock window for the locked pair
        t["now"] += 15 * 60 + 1
        self.assertIsNone(A.login(self.USER, "wrong-password", client_ip=ip, clock=clock))  # counter restarted, not auto-success
        # success resets pair/user counters
        self._clear_throttle()
        for _ in range(4):
            self.assertIsNone(A.login(self.USER, "wrong-password", client_ip=ip, clock=clock))
        self.assertIsNotNone(A.login(self.USER, self.PASSWORD, client_ip=ip, clock=clock))
        for _ in range(4):
            self.assertIsNone(A.login(self.USER, "wrong-password", client_ip=ip, clock=clock))
        self.assertIsNotNone(A.login(self.USER, self.PASSWORD, client_ip=ip, clock=clock))

    def test_nonexistent_user_same_generic_failure_and_is_throttled(self):
        t = {"now": 2_000_000.0}
        clock = lambda: t["now"]
        ip = "10.0.0.77"
        for _ in range(5):
            self.assertIsNone(A.login("nobody.here." + self.USER, "wrong-password", client_ip=ip, clock=clock))
        with self.assertRaises(A.LoginThrottled):
            A.login("nobody.here." + self.USER, "wrong-password", client_ip=ip, clock=clock)

    def test_global_per_username_limit_slows_distributed_guessing(self):
        t = {"now": 3_000_000.0}
        clock = lambda: t["now"]
        # spread failures across many IPs to avoid per-pair lock dominating first
        for i in range(sessions.GLOBAL_MAX_FAILURES):
            ip = f"10.9.{i // 250}.{i % 250}"
            try:
                A.login(self.USER, "wrong-password", client_ip=ip, clock=clock)
            except A.LoginThrottled:
                pass
        with self.assertRaises(A.LoginThrottled):
            A.login(self.USER, self.PASSWORD, client_ip="10.9.200.1", clock=clock)

    def test_login_failures_and_lockouts_are_audited(self):
        t = {"now": 4_000_000.0}
        clock = lambda: t["now"]
        ip = "10.0.0.88"
        with LOCK, _db() as db:
            db.execute("DELETE FROM events WHERE actor=?", (self.USER,))
            before = db.execute("SELECT COUNT(*) n FROM events WHERE event_type IN ('auth_login_failed','auth_login_locked','auth_login_global_lock') AND actor=?", (self.USER,)).fetchone()["n"]
        for _ in range(5):
            A.login(self.USER, "wrong-password", client_ip=ip, clock=clock)
        try:
            A.login(self.USER, "wrong-password", client_ip=ip, clock=clock)
        except A.LoginThrottled:
            pass
        with LOCK, _db() as db:
            after = db.execute("SELECT COUNT(*) n FROM events WHERE event_type IN ('auth_login_failed','auth_login_locked','auth_login_global_lock') AND actor=?", (self.USER,)).fetchone()["n"]
        self.assertGreater(after, before)


    def test_session_token_is_hashed_in_db_not_plaintext(self):
        import hashlib
        result = A.login(self.USER, self.PASSWORD, client_ip="10.1.2.3")
        token = result["token"]
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with LOCK, _db() as db:
            cols = {row["name"] for row in db.execute("PRAGMA table_info(auth_sessions)")}
            self.assertIn("token_hash", cols)
            self.assertNotIn("token", cols)
            row = db.execute("SELECT token_hash, username FROM auth_sessions WHERE token_hash=?", (token_hash,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["username"], self.USER)
            # plaintext token must not appear anywhere in session rows
            raw = db.execute("SELECT * FROM auth_sessions").fetchall()
            for r in raw:
                self.assertNotIn(token, [str(v) for v in dict(r).values()])

    def test_direct_loopback_without_xff_exempt_from_global_lock_but_pair_lock_applies(self):
        t = {"now": 5_000_000.0}
        clock = lambda: t["now"]
        # Exceed global limit count while exempt from global lock (loopback direct, no XFF).
        # Each 5-failure burst locks the pair; advance past pair lock+window between bursts.
        for _ in range((sessions.GLOBAL_MAX_FAILURES // sessions.MAX_FAILURES) + 2):
            for _ in range(sessions.MAX_FAILURES):
                try:
                    A.login(self.USER, "wrong-password", client_ip="127.0.0.1", clock=clock, xff_present=False)
                except A.LoginThrottled:
                    pass
            t["now"] += sessions.LOCK_MAX_SECONDS + sessions.WINDOW_SECONDS + 1
        # Still not globally locked (exempt): next attempt is a normal failure, not LoginThrottled-by-global.
        t["now"] += sessions.LOCK_MAX_SECONDS + sessions.WINDOW_SECONDS + 1
        self.assertIsNone(A.login(self.USER, "wrong-password", client_ip="127.0.0.1", clock=clock, xff_present=False))
        # Pair lock still applies on this same (user, 127.0.0.1).
        for _ in range(sessions.MAX_FAILURES - 1):
            self.assertIsNone(A.login(self.USER, "wrong-password", client_ip="127.0.0.1", clock=clock, xff_present=False))
        with self.assertRaises(A.LoginThrottled):
            A.login(self.USER, "wrong-password", client_ip="127.0.0.1", clock=clock, xff_present=False)

    def test_loopback_with_xff_not_exempt_from_global_lock(self):
        t = {"now": 6_000_000.0}
        clock = lambda: t["now"]
        # request came via loopback proxy carrying XFF (real client) -> global lock applies
        for i in range(sessions.GLOBAL_MAX_FAILURES):
            ip = f"10.8.{i // 250}.{i % 250}"
            try:
                A.login(self.USER, "wrong-password", client_ip=ip, clock=clock, xff_present=True)
            except A.LoginThrottled:
                pass
        with self.assertRaises(A.LoginThrottled):
            A.login(self.USER, self.PASSWORD, client_ip="10.8.200.1", clock=clock, xff_present=True)

    def test_global_lock_is_audited(self):
        t = {"now": 7_000_000.0}
        clock = lambda: t["now"]
        for i in range(sessions.GLOBAL_MAX_FAILURES):
            ip = f"10.7.{i // 250}.{i % 250}"
            try:
                A.login(self.USER, "wrong-password", client_ip=ip, clock=clock, xff_present=True)
            except A.LoginThrottled:
                pass
        try:
            A.login(self.USER, "wrong-password", client_ip="10.7.200.1", clock=clock, xff_present=True)
        except A.LoginThrottled:
            pass
        with LOCK, _db() as db:
            n = db.execute("SELECT COUNT(*) n FROM events WHERE event_type='auth_login_global_lock' AND actor=?", (self.USER,)).fetchone()["n"]
        self.assertGreater(n, 0)

    def test_plaintext_session_migration(self):
        # simulate legacy table and verify migration hashes tokens
        import hashlib, sqlite3
        from core.office_store import LOCK, STORE
        user = "mig." + self.USER
        _delete_user(user)
        sessions.create_user(user, self.PASSWORD, "employee", department_id="engineering")
        with LOCK, STORE._db() as db:
            db.execute("ALTER TABLE auth_sessions RENAME TO auth_sessions_hashed_tmp")
            db.execute("CREATE TABLE auth_sessions (token TEXT PRIMARY KEY, username TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)")
            db.execute("INSERT INTO auth_sessions(token,username,created_at,expires_at,revoked) VALUES(?,?,?,?,0)",
                       ("legacy-plain-token-abc", user, "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"))
        # run migration
        with LOCK, STORE._db() as db:
            sessions._migrate_auth_sessions(db)
            cols = {r["name"] for r in db.execute("PRAGMA table_info(auth_sessions)")}
            self.assertIn("token_hash", cols)
            row = db.execute("SELECT token_hash FROM auth_sessions WHERE username=?", (user,)).fetchone()
            self.assertEqual(row["token_hash"], hashlib.sha256(b"legacy-plain-token-abc").hexdigest())
        # migrated session usable via hash verification
        self.assertIsNotNone(sessions.get_session("legacy-plain-token-abc"))
        _delete_user(user)


if __name__ == "__main__":
    unittest.main()
