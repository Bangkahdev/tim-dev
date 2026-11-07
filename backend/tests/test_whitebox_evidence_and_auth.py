"""White-box tests: exercise internal logic/branches directly (not via HTTP).

Covers: company completion-evidence validation, session token hashing/migration
behavior, login-throttle state machine/audit paths, and verifier helpers.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from core.auth import authentication as A
from core.auth import sessions
from core.company_operations import CompanyOperations
from core.office_store import LOCK, OfficeStore, STORE


class WhiteboxEvidenceValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ops = CompanyOperations(OfficeStore(Path(self.tmp.name) / "co.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def _task(self):
        t = self.ops.create_task("WB", assignee_id="backend")
        self.ops.transition_task(t["id"], "in_progress")
        return t

    def test_rejects_empty_and_meaningless_evidence(self):
        t = self._task()
        with self.assertRaises(ValueError):
            self.ops.transition_task(t["id"], "completed", evidence=[])
        with self.assertRaises(ValueError):
            self.ops.transition_task(t["id"], "completed", evidence=[{"type": "note", "reference": "x"}])

    def test_accepts_structured_passing_exit_code(self):
        t = self._task()
        self.ops.transition_task(t["id"], "completed", evidence=[{"type": "test", "reference": "artifacts/out.txt", "exit_code": 0}])
        self.assertEqual(next(x for x in self.ops.tasks() if x["id"] == t["id"])["status"], "completed")

    def test_rejects_structured_failing_exit_code(self):
        t = self._task()
        with self.assertRaisesRegex(ValueError, "kegagalan|exit_code"):
            self.ops.transition_task(t["id"], "completed", evidence=[{"type": "test", "reference": "artifacts/out.txt", "exit_code": 1}])

    def test_accepts_textual_exit_code_zero_and_rejects_nonzero(self):
        t = self._task()
        self.ops.transition_task(t["id"], "completed", evidence=[{"type": "test", "reference": "pytest", "note": "Exit code 0, artifact ok"}])
        self.assertEqual(next(x for x in self.ops.tasks() if x["id"] == t["id"])["status"], "completed")
        t2 = self._task()
        with self.assertRaises(ValueError):
            self.ops.transition_task(t2["id"], "completed", evidence=[{"type": "test", "reference": "pytest", "note": "exit_code=2"}])

    def test_accepts_concrete_non_test_deliverable_reference(self):
        t = self._task()
        self.ops.transition_task(t["id"], "completed", evidence=[{"type": "document", "reference": "PLAN.md"}])
        self.assertEqual(next(x for x in self.ops.tasks() if x["id"] == t["id"])["status"], "completed")


class WhiteboxAuthInternalsTests(unittest.TestCase):
    USER = "wb.owner"
    PW = "correct-horse-battery"

    def setUp(self):
        sessions.clear_login_throttle()
        with LOCK, STORE._db() as db:
            db.execute("DELETE FROM auth_sessions WHERE username=?", (self.USER,))
            db.execute("DELETE FROM auth_users WHERE username=?", (self.USER,))
        sessions.create_user(self.USER, self.PW, "owner", department_id="executive")

    def tearDown(self):
        with LOCK, STORE._db() as db:
            db.execute("DELETE FROM auth_sessions WHERE username=?", (self.USER,))
            db.execute("DELETE FROM auth_users WHERE username=?", (self.USER,))
        sessions.clear_login_throttle()

    def test_raw_token_never_persisted_only_sha256(self):
        res = A.login(self.USER, self.PW, client_ip="10.9.9.1")
        token = res["token"]
        digest = hashlib.sha256(token.encode()).hexdigest()
        with LOCK, STORE._db() as db:
            row = db.execute("SELECT token_hash FROM auth_sessions WHERE username=? ORDER BY created_at DESC LIMIT 1", (self.USER,)).fetchone()
            cols = {r["name"] for r in db.execute("PRAGMA table_info(auth_sessions)")}
        self.assertEqual(row["token_hash"], digest)
        self.assertIn("token_hash", cols)
        self.assertNotIn("token", cols)

    def test_get_session_resolves_by_hash_and_rejects_unknown(self):
        res = A.login(self.USER, self.PW, client_ip="10.9.9.2")
        self.assertEqual(A.current_user(res["token"])["username"], self.USER)
        self.assertIsNone(A.current_user("not-a-real-token"))

    def test_throttle_pair_lock_independent_of_other_ip(self):
        t = {"now": 9_000_000.0}
        clock = lambda: t["now"]
        for _ in range(5):
            A.login(self.USER, "bad", client_ip="10.1.1.1", clock=clock)
        with self.assertRaises(A.LoginThrottled):
            A.login(self.USER, "bad", client_ip="10.1.1.1", clock=clock)
        # different IP, pair not locked (global not reached)
        self.assertIsNone(A.login(self.USER, "bad", client_ip="10.1.1.2", clock=clock))

    def test_audit_records_lock_and_bypass(self):
        t = {"now": 9_100_000.0}
        clock = lambda: t["now"]
        with LOCK, STORE._db() as db:
            db.execute("DELETE FROM events WHERE actor=?", (self.USER,))
        for _ in range(5):
            A.login(self.USER, "bad", client_ip="10.2.2.2", clock=clock)
        try:
            A.login(self.USER, "bad", client_ip="10.2.2.2", clock=clock)
        except A.LoginThrottled:
            pass
        # loopback-direct bypass path audits bypass event
        try:
            A.login(self.USER, "bad", client_ip="127.0.0.1", clock=clock, xff_present=False)
        except A.LoginThrottled:
            pass
        with LOCK, STORE._db() as db:
            kinds = {r["event_type"] for r in db.execute("SELECT event_type FROM events WHERE actor=?", (self.USER,))}
        self.assertIn("auth_login_locked", kinds)
        self.assertIn("auth_login_throttle_bypass", kinds)
