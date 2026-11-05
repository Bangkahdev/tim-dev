import importlib.util
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

# Orchestrator intent parsing has no CrewAI runtime dependency. Provide a tiny
# import stub in test environments where the optional application runtime is absent.
if importlib.util.find_spec("crewai") is None:
    crewai_stub = types.ModuleType("crewai")
    crewai_stub.LLM = object
    sys.modules["crewai"] = crewai_stub

from core.office_store import OfficeStore
from core.knowledge_base import KnowledgeBase
from core.office_tools import OfficeTools
from core.orchestrator import OfficeOrchestrator


class InteractionAndRagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "office.db"
        self.store = OfficeStore(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_employee_interaction_is_persisted_for_bubbles(self):
        interaction = self.store.record_interaction(
            "lead", "backend", "Bima, tolong implementasikan endpoint portfolio.",
            "meeting", "task_assignment", 60
        )
        snapshot = self.store.snapshot()
        saved = next(x for x in snapshot["interactions"] if x["id"] == interaction["id"])
        self.assertEqual(saved["sender_name"], "Arman")
        self.assertEqual(saved["recipient_name"], "Bima")
        self.assertIn("implementasikan endpoint", saved["message"])
        employee = next(x for x in snapshot["employees"] if x["id"] == "lead")
        self.assertEqual(employee["status"], "talking")

    def test_recipient_is_marked_listening(self):
        self.store.record_interaction("lead", "qa", "Tika, siapkan skenario uji.", "meeting", ttl_seconds=60)
        qa = next(x for x in self.store.snapshot()["employees"] if x["id"] == "qa")
        self.assertEqual(qa["status"], "listening")

    def test_new_speaker_replaces_previous_active_turn(self):
        self.store.move_all("meeting")
        self.store.record_interaction("lead", "backend", "Bima, bagaimana progres API?", "meeting", "meeting_reply", 60)
        self.store.record_interaction("backend", "lead", "Endpoint sudah tersedia untuk diuji.", "meeting", "meeting_reply", 60)
        snapshot = self.store.snapshot()
        statuses = {e["id"]: e["status"] for e in snapshot["employees"]}
        self.assertEqual(statuses["backend"], "talking")
        self.assertEqual(statuses["lead"], "listening")
        self.assertEqual(statuses["qa"], "idle")
        self.assertEqual(len(snapshot["interactions"]), 1)
        self.assertEqual(snapshot["interactions"][0]["sender_id"], "backend")

    def test_meeting_broadcast_keeps_all_room_members_listening(self):
        self.store.move_all("meeting")
        self.store.record_interaction(
            "lead", None, "Tim, kita mulai briefing.", "meeting", "meeting_briefing", 60
        )
        snapshot = self.store.snapshot()
        statuses = {e["id"]: e["status"] for e in snapshot["employees"]}
        self.assertEqual(statuses["lead"], "talking")
        self.assertTrue(all(statuses[eid] == "listening" for eid in ("coo", "architect", "backend", "api", "frontend", "qa")))


    def test_deterministic_planner_turns_office_commands_into_actions(self):
        planner = OfficeOrchestrator()
        gather = planner._fallback_plan("Arman, kumpulkan semua karyawan ke ruang meeting")
        gather_tools = [item["tool"] for item in gather["actions"]]
        self.assertIn("move_all_employees", gather_tools)
        self.assertIn("create_meeting", gather_tools)

        move = planner._fallback_plan("Pindahkan Bima ke ruang API")
        self.assertIn({"tool": "move_employee", "arguments": {"employee_id": "backend", "room_id": "api"}}, move["actions"])

        report = planner._fallback_plan("Buatkan laporan aktivitas minggu ini")
        self.assertIn({"tool": "generate_weekly_report", "arguments": {"days": 7}}, report["actions"])

        lounge = planner._fallback_plan("Kumpulkan semua karyawan ke area santai sekarang")
        self.assertIn({"tool": "move_all_employees", "arguments": {"room_id": "lounge"}}, lounge["actions"])


    def test_collective_office_instruction_assigns_real_tasks_to_all_staff(self):
        planner = OfficeOrchestrator()
        plan = planner._fallback_plan("Suruh semua orang bikin kopi sekarang")
        self.assertIn({"tool": "move_all_employees", "arguments": {"room_id": "kitchen"}}, plan["actions"])
        assigned = [x["arguments"].get("assignee_id") for x in plan["actions"] if x["tool"] == "create_task"]
        self.assertEqual(set(assigned), {"lead", "coo", "architect", "backend", "api", "frontend", "qa"})

    def test_employee_direct_chat_can_execute_self_room_move(self):
        import core.orchestrator as orchestrator_module
        planner = OfficeOrchestrator()
        tools = OfficeTools(self.store)
        with mock.patch.object(orchestrator_module, "STORE", self.store), \
             mock.patch.object(orchestrator_module, "TOOLS", tools), \
             mock.patch.object(orchestrator_module.KNOWLEDGE, "search", return_value=[]), \
             mock.patch.object(orchestrator_module, "make_llm", side_effect=RuntimeError("model offline")):
            result = planner.handle_employee_chat("backend", "Bima, pindah ke ruang API")
        self.assertEqual(len(result["actions"]), 1)
        backend = next(e for e in self.store.snapshot()["employees"] if e["id"] == "backend")
        self.assertEqual(backend["room_id"], "api")

    def test_orchestrator_executes_real_room_move_tool(self):
        import core.orchestrator as orchestrator_module

        planner = OfficeOrchestrator()
        tools = OfficeTools(self.store)
        with mock.patch.object(orchestrator_module, "STORE", self.store), \
             mock.patch.object(orchestrator_module, "TOOLS", tools), \
             mock.patch.object(orchestrator_module.KNOWLEDGE, "search", return_value=[]), \
             mock.patch.object(planner, "_planner_prompt", side_effect=RuntimeError("model offline")):
            result = planner.handle_chat("Pindahkan Bima ke ruang API")

        self.assertFalse(result["errors"])
        employee = next(e for e in self.store.snapshot()["employees"] if e["id"] == "backend")
        self.assertEqual(employee["room_id"], "api")
        self.assertIn("memindahkan karyawan", result["reply"])

    def test_collective_command_changes_database_and_assigns_each_person(self):
        import core.orchestrator as orchestrator_module
        planner = OfficeOrchestrator()
        tools = OfficeTools(self.store)
        with mock.patch.object(orchestrator_module, "STORE", self.store), \
             mock.patch.object(orchestrator_module, "TOOLS", tools), \
             mock.patch.object(orchestrator_module.KNOWLEDGE, "search", return_value=[]), \
             mock.patch.object(planner, "_planner_prompt", side_effect=RuntimeError("model offline")):
            result = planner.handle_chat("Suruh semua orang bikin kopi sekarang")
        self.assertFalse(result["errors"])
        snapshot = self.store.snapshot()
        self.assertTrue(all(e["room_id"] == "kitchen" for e in snapshot["employees"]))
        assigned = {t["assignee_id"] for t in snapshot["tasks"]}
        self.assertEqual(assigned, {"lead", "coo", "architect", "backend", "api", "frontend", "qa"})

    def test_rag_indexes_and_retrieves_document_without_embeddings(self):
        kb = KnowledgeBase(self.db_path)
        kb._embed_many = lambda texts: [None for _ in texts]
        kb.add_document(
            "Portfolio Architecture", 
            "Portfolio menggunakan frontend responsif. Backend menyediakan endpoint REST untuk proyek dan profil."
            "\n\nQA memeriksa navigasi, aksesibilitas, dan responsivitas.",
            "test:portfolio"
        )
        results = kb.search("endpoint REST backend portfolio", limit=3)
        self.assertTrue(results)
        self.assertEqual(results[0]["title"], "Portfolio Architecture")
        self.assertIn(results[0]["method"], {"sqlite-fts", "sqlite-like"})


if __name__ == "__main__":
    unittest.main()
