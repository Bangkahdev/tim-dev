import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ControlledRealAgentRunnerTests(unittest.TestCase):
    def test_runner_writes_into_exact_project_dir_with_mocked_worker_and_verifier(self):
        from core.company_operations import CompanyOperations
        from core.office_store import OfficeStore
        from core.business_cycle import DeterministicWorker
        import tools.run_milestone1_real_agent as mod

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "test.db"
            project_dir = root / "exact-run-dir"
            fake_verifier = {"checks": {"OVERALL_VERIFIABLE": True, "hidden.all_pass": True}, "details": {}}
            with patch.object(mod, "sandbox_required", return_value=False), \
                 patch.object(mod, "ensure_sandbox_canaries", return_value={"ok": True, "fs_isolated": True, "network_isolated": True, "details": {}}), \
                 patch.object(mod, "CrewAIAgentWorker", DeterministicWorker), \
                 patch.object(mod, "owner_verify", return_value=fake_verifier):
                rc = mod.main(["--project-dir", str(project_dir), "--db", str(db), "--project-key", "m1-mock", "--external-sandbox", "mocked", "--allow-unverified-real"])
            self.assertEqual(rc, 0)
            self.assertTrue((project_dir / "wordcount" / "core.py").is_file(), "worker must write into the exact run project_dir")
            self.assertTrue((project_dir / "artifacts" / "sandbox-canary.json").is_file())
            self.assertTrue((project_dir / "artifacts" / "owner-verifier.json").is_file())
            ops = CompanyOperations(OfficeStore(db))
            try:
                with ops._db() as dbh:
                    paper = dbh.execute("SELECT 1 FROM paper_records WHERE title=? LIMIT 1", ("Final Report: m1-mock",)).fetchone()
                    completed = dbh.execute("SELECT COUNT(*) n FROM task_meta tm JOIN tasks t ON t.id=tm.task_id WHERE tm.project_key=? AND t.status='completed'", ("m1-mock",)).fetchone()
                self.assertIsNotNone(paper)
                self.assertEqual(completed["n"], 5)
            finally:
                ops.close()

    def test_real_worker_refuses_without_crewai(self):
        from core.business_cycle import CrewAIAgentWorker
        # simulate missing crewai
        orig = sys.modules.get("crewai")
        try:
            sys.modules["crewai"] = None
            with self.assertRaises(RuntimeError):
                CrewAIAgentWorker().produce(Path(tempfile.mkdtemp()), "cmd", Path(__file__))
        finally:
            if orig is None:
                sys.modules.pop("crewai", None)
            else:
                sys.modules["crewai"] = orig

    def test_deterministic_worker_is_honest_integration_fixture(self):
        from core.business_cycle import DeterministicWorker
        self.assertEqual(DeterministicWorker.mode, "deterministic_integration")


if __name__ == "__main__":
    unittest.main()
