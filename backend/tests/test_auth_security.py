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
    with LOCK, _db() as db:
        db.execute("UPDATE auth_sessions SET expires_at='2000-01-01T00:00:00+00:00' WHERE token=?", (token,))


class AuthSessionTests(unittest.TestCase):
    USER = "unit.owner"
    PASSWORD = "correct-horse-battery"

    def setUp(self):
        _delete_user(self.USER)
        sessions.create_user(self.USER, self.PASSWORD, "owner", department_id="executive")

    def tearDown(self):
        _delete_user(self.USER)

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


if __name__ == "__main__":
    unittest.main()
