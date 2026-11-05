import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.office_store import OfficeStore
from core.office_tools import OfficeTools


class OfficeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = OfficeStore(Path(self.tmp.name) / "office.db")
        self.tools = OfficeTools(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_move_all_employees(self):
        result = self.tools.execute("move_all_employees", {"room_id": "meeting"})
        self.assertEqual(result["count"], 7)
        self.assertTrue(all(e["room_id"] == "meeting" for e in self.store.snapshot()["employees"]))

    def test_move_employee_persists_room_and_event(self):
        result = self.tools.execute("move_employee", {"employee_id": "backend", "room_id": "meeting"})
        snapshot = self.store.snapshot()
        employee = next(e for e in snapshot["employees"] if e["id"] == "backend")
        self.assertEqual(result["room_id"], "meeting")
        self.assertEqual(employee["room_id"], "meeting")
        self.assertTrue(any(e["event_type"] == "employee_moved" for e in snapshot["events"]))

    def test_create_and_update_task(self):
        task = self.tools.execute("create_task", {
            "title": "Build portfolio UI", "assignee_id": "frontend", "priority": "high"
        })
        updated = self.tools.execute("update_task", {"task_id": task["id"], "status": "in_progress"})
        self.assertEqual(updated["status"], "in_progress")

    def test_meeting_and_weekly_report(self):
        meeting = self.tools.execute("create_meeting", {
            "title": "Portfolio kickoff", "attendee_ids": ["lead", "architect", "frontend"]
        })
        self.assertEqual(meeting["status"], "scheduled")
        report = self.tools.execute("generate_weekly_report", {"days": 7})
        self.assertGreaterEqual(report["summary"]["events"], 1)


    def test_roster_has_distinct_real_rooms(self):
        snapshot = self.store.snapshot()
        employees = {e["id"]: e for e in snapshot["employees"]}
        self.assertEqual(employees["lead"]["room_id"], "manager")
        self.assertEqual(employees["coo"]["room_id"], "planning")
        self.assertEqual(employees["architect"]["room_id"], "architect")
        self.assertEqual(employees["backend"]["room_id"], "backend")
        self.assertIn("lounge", snapshot["rooms"])
        self.assertIn("kitchen", snapshot["rooms"])

    def test_legacy_shared_rooms_are_migrated_once(self):
        db_path = Path(self.tmp.name) / "legacy.db"
        legacy = OfficeStore(db_path)
        with sqlite3.connect(db_path) as db:
            db.execute("UPDATE employees SET room_id='manager' WHERE id='coo'")
            db.execute("UPDATE employees SET room_id='development' WHERE id IN ('architect','backend')")
            db.execute("DELETE FROM schema_migrations WHERE name='split_virtual_office_departments_v1'")
        migrated = OfficeStore(db_path).snapshot()
        employees = {e["id"]: e for e in migrated["employees"]}
        self.assertEqual(employees["coo"]["room_id"], "planning")
        self.assertEqual(employees["architect"]["room_id"], "architect")
        self.assertEqual(employees["backend"]["room_id"], "backend")

    def test_reject_unknown_employee_and_room(self):
        with self.assertRaises(ValueError):
            self.tools.execute("move_employee", {"employee_id": "intruder", "room_id": "meeting"})
        with self.assertRaises(ValueError):
            self.tools.execute("move_all_employees", {"room_id": "unknown"})

    def test_chat_messages_persist_by_channel(self):
        owner = self.store.add_chat_message("team", "owner", "Owner", "owner", "Kumpul di ruang meeting")
        reply = self.store.add_chat_message("team", "lead", "Arman", "agent", "Saya koordinasikan tim.")
        dm = self.store.add_chat_message("backend", "backend", "Bima", "agent", "Saya siap membantu.")
        team = self.store.list_chat_messages("team")
        backend = self.store.list_chat_messages("backend")
        self.assertEqual([m["id"] for m in team], [owner["id"], reply["id"]])
        self.assertEqual(backend[0]["id"], dm["id"])
        self.assertEqual(team[0]["sender_role"], "owner")

    def test_group_interaction_marks_every_available_employee_as_listening(self):
        self.store.record_interaction("lead", None, "Briefing untuk seluruh kantor", None, "group_chat", 60)
        statuses = {e["id"]: e["status"] for e in self.store.snapshot()["employees"]}
        self.assertEqual(statuses["lead"], "talking")
        self.assertTrue(all(statuses[eid] == "listening" for eid in ("coo", "architect", "backend", "api", "frontend", "qa")))

    def test_reject_unknown_action(self):
        with self.assertRaises(ValueError):
            self.tools.execute("run_arbitrary_shell", {})


if __name__ == "__main__":
    unittest.main()

class OwnerSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = OfficeStore(Path(self.tmp.name) / 'simulator.db')

    def tearDown(self):
        self.tmp.cleanup()

    def test_owner_player_state_persists_position_and_room(self):
        updated = self.store.update_owner_player(48.5, 82.0, 'lounge', 'walking')
        loaded = self.store.owner_player_state()
        self.assertEqual(loaded['room_id'], 'lounge')
        self.assertEqual(loaded['activity'], 'walking')
        self.assertAlmostEqual(loaded['x'], 48.5)
        self.assertAlmostEqual(loaded['y'], 82.0)

    def test_owner_interactions_are_recorded_as_company_events(self):
        result = self.store.interact_owner('coffee', 82, 22, 'kitchen')
        self.assertEqual(result['activity'], 'making_coffee')
        self.assertEqual(result['interaction'], 'coffee')
        events = self.store.snapshot()['events']
        self.assertTrue(any(e['event_type'] == 'owner_interaction' and e['entity_id'] == 'coffee' for e in events))

    def test_owner_player_rejects_invalid_coordinates_and_interactions(self):
        with self.assertRaises(ValueError):
            self.store.update_owner_player(120, 5, 'corridor', 'idle')
        with self.assertRaises(ValueError):
            self.store.interact_owner('launch_a_rocket')
