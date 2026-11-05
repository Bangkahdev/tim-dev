import datetime
import os
import tempfile
import unittest
from pathlib import Path

from core.office_store import OfficeStore, ROSTER
from core.workstations import DesktopError, DesktopOperations
from core.employee_activity import EmployeeActivityEngine, _duty_open


def _isolated_engine(**kwargs):
    kwargs.setdefault("duty_hours", "0-24")
    kwargs.setdefault("tick_seconds", 0)
    root = Path(tempfile.mkdtemp())
    store = OfficeStore(root / "activity.db")
    desktop = DesktopOperations(store, workspace_root=root / "workspace", owner_password="test-pass")
    desktop.clear_login_throttle()
    engine = EmployeeActivityEngine(store, desktop, **kwargs)
    return root, store, desktop, engine


class EmployeeActivityTests(unittest.TestCase):
    def setUp(self):
        self.root, self.store, self.desktop, self.engine = _isolated_engine()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)
        os.environ.pop("BANGKAH_EMPLOYEE_DUTY_HOURS", None)

    def _engine(self, **kw):
        engine = EmployeeActivityEngine(self.store, self.desktop, duty_hours="0-24", tick_seconds=0, **kw)
        return engine

    def test_tick_logs_every_employee_in_and_writes_files(self):
        inner = EmployeeActivityEngine(self.store, self.desktop, duty_hours="0-24", tick_seconds=0)
        result = inner.tick(force=True)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["units"]), 7)
        for account_id in ROSTER:
            sandbox = self.root / "workspace" / {
                "lead": "PC-MGT-001", "coo": "PC-MGT-002", "architect": "PC-ARC-001",
                "backend": "PC-BE-001", "api": "PC-API-001", "frontend": "PC-FE-001",
                "qa": "PC-QA-001",
            }[account_id] / "work"
            children = list(sandbox.rglob("*"))
            self.assertTrue([p for p in children if p.is_file()], account_id)

    def test_tick_records_audited_work_events_and_feed(self):
        self._engine().tick(force=True)
        feed = self.engine.feed()
        work_events = [e for e in feed if e["event_type"] == "employee_work"]
        self.assertEqual(len(work_events), 7)
        self.assertTrue({e["actor"] for e in work_events} >= set(ROSTER))

    def test_feed_after_id_pagination(self):
        self._engine().tick(force=True)
        first = self.engine.feed(0, 5)
        self.assertEqual(len(first), 5)
        cursor = first[-1]["id"]
        rest = self.engine.feed(cursor, 100)
        self.assertTrue(all(e["id"] > cursor for e in rest))

    def test_engine_sets_employees_working_and_repeats_units(self):
        self._engine().tick(force=True)
        snapshot = self.store.snapshot()
        for emp in snapshot["employees"]:
            if emp["id"] in ROSTER:
                self.assertEqual(emp["status"], "working", emp["id"])
        second = self._engine().tick(force=True)
        self.assertEqual(len(second["units"]), 7)
        summary = self._engine().summary()
        for entry in summary["employees"]:
            self.assertEqual(entry["units_done"], 2, entry["employee_id"])
            self.assertEqual(entry["units_today"], 2, entry["employee_id"])

    def test_talking_employee_status_is_preserved(self):
        inner = self._engine()
        from datetime import timedelta
        expires = (datetime.datetime.now().astimezone() + timedelta(seconds=90)).isoformat()
        created = datetime.datetime.now().astimezone().isoformat()
        with self.store._db() as db:
            db.execute("UPDATE employees SET status='talking' WHERE id='backend'")
            db.execute("""INSERT INTO employee_interactions
                (id,sender_id,recipient_id,room_id,message,interaction_type,created_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                ("inter-live", "backend", "qa", None, "Syncing rapid.",
                 "conversation", created, expires))
            db.execute("UPDATE employees SET status='talking' WHERE id='backend'")
        result = inner.tick(force=True)
        self.assertEqual(result["errors"], [])
        snapshot = self.store.snapshot()
        backend = [e for e in snapshot["employees"] if e["id"] == "backend"][0]
        self.assertEqual(backend["status"], "talking")

    def test_rate_limit_skips_when_disabled_or_closed(self):
        # Outside the duty window, nothing starts.
        engine_off = _isolated_engine(duty_hours="9-10", tick_seconds=0)
        result = engine_off[3].tick(force=True, now=datetime.datetime.now().astimezone())
        result["units"] == []
        # Overtime (ignore_window) works after hours.
        result = engine_off[3].tick(force=True, ignore_window=True,
                                    now=datetime.datetime.now().astimezone())
        self.assertEqual(len(result["units"]), 7)
        self.assertTrue(result["overtime"])

    def test_disabled_engine_reports_honestly(self):
        os.environ["BANGKAH_EMPLOYEE_ACTIVITY"] = "0"
        os.environ["BANGKAH_EMPLOYEE_ACCOUNTS"] = "0"
        try:
            _, _, _, engine = _isolated_engine(duty_hours="0-24")
            result = engine.tick(force=True, ignore_window=True)
            self.assertFalse(result["enabled"])
            self.assertEqual(result["units"], [])
        finally:
            os.environ.pop("BANGKAH_EMPLOYEE_ACTIVITY", None)
            os.environ.pop("BANGKAH_EMPLOYEE_ACCOUNTS", None)

    def test_frozen_accounts_make_engine_report_honest_errors(self):
        os.environ["BANGKAH_EMPLOYEE_ACCOUNTS"] = "0"
        try:
            _, _, _, engine = _isolated_engine(duty_hours="0-24")
            result = engine.tick(force=True, ignore_window=True)
            self.assertEqual(len(result["errors"]), 7)
            self.assertTrue(all("tidak aktif" in e["error"] for e in result["errors"]))
        finally:
            os.environ.pop("BANGKAH_EMPLOYEE_ACCOUNTS", None)

    def test_day_boundary_resets_daily_units(self):
        inner = self._engine()
        inner.tick(force=True, now=datetime.datetime(2026, 11, 5, 10, 0, 0,
                                                    tzinfo=datetime.timezone.utc))
        rows_before = inner.summary()["employees"]
        units_before = {e["employee_id"]: e["units_done"] for e in rows_before}
        self.assertGreater(sum(units_before.values()), 0)
        inner.tick(force=True, now=datetime.datetime(2026, 11, 6, 10, 0, 0,
                                                    tzinfo=datetime.timezone.utc))
        summary = inner.summary()
        for entry in summary["employees"]:
            self.assertEqual(entry["units_today"], 1, entry["employee_id"])
            self.assertEqual(entry["units_done"], 2, entry["employee_id"])

    def test_assigned_task_is_referenced(self):
        inner = self._engine()
        with self.store._db() as db:
            db.execute(
                "INSERT INTO tasks(id,title,assignee_id,status,created_at,updated_at) "
                "VALUES('t1','Migrate session builder','backend','in_progress','2026-11-05','2026-11-05')")
        result = inner.tick(force=True)
        backend_unit = [u for u in result["units"] if u["employee_id"] == "backend"][0]
        self.assertIn("Migrate session builder", backend_unit["task"])
        feed = [e for e in inner.feed() if e["actor"] == "backend"
                and e["event_type"] == "employee_work"]
        self.assertIn("Migrate session builder", feed[0]["detail"])

    def test_duty_open_window_parsing(self):
        day_now = datetime.datetime(2026, 11, 5, 12, 0, tzinfo=datetime.timezone.utc)
        night_now = datetime.datetime(2026, 11, 5, 23, 0, tzinfo=datetime.timezone.utc)
        self.assertTrue(_duty_open(day_now, "9-17"))
        self.assertFalse(_duty_open(night_now, "9-17"))
        self.assertTrue(_duty_open(night_now, "22-6"))
        self.assertFalse(_duty_open(day_now, "22-6"))
        self.assertFalse(_duty_open(day_now, "invalid"))

    def test_shift_end_closes_session_and_idles(self):
        inner = EmployeeActivityEngine(self.store, self.desktop, duty_hours="9-17", tick_seconds=0)
        inner.tick(force=True, now=datetime.datetime(2026, 11, 5, 10, 0, 0,
                                                    tzinfo=datetime.timezone.utc))
        self.assertEqual(inner.summary()["employees"][0]["status"], "on_shift")
        # Clock moves past duty closing the shift.
        inner.tick(force=True, now=datetime.datetime(2026, 11, 5, 18, 0, 0,
                                                    tzinfo=datetime.timezone.utc))
        summary = inner.summary()["employees"]
        self.assertTrue(all(e["status"] == "off_shift" for e in summary))
        # Sessions from the shift were closed.
        stations = inner.desktop.list_workstations()
        self.assertTrue(all(s["status"] == "offline" for s in stations if s["id"] != "OWNER-PC-001"))


if __name__ == "__main__":
    unittest.main()
