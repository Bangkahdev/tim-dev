import tempfile
import unittest
from pathlib import Path

from core.business_cycle import BusinessCycle, check_rbac_and_approval, record_pipeline_result
from core.company_operations import CompanyOperations
from core.office_store import OfficeStore


class BusinessCycleTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.ops = CompanyOperations(OfficeStore(self.root / "office.db"))
        self.workspace = self.root / "projects"

    def test_full_cycle_produces_evidence_and_persists(self):
        result = BusinessCycle(self.ops, workspace_root=self.workspace).run(
            "Build a small Python CLI utility that counts lines, words and characters, "
            "with tests and a README",
            "pilot-test",
        )
        self.assertEqual(result["test_exit_code"], 0)
        self.assertEqual(result["owner_decision"], "approved")
        checks = result["checks"]
        # NFR-SEC-09/10 (FS+network isolation) is honestly NOT met by in-process guards; do not require it True.
        for k, v in checks.items():
            if k == "sandbox_fs_network_isolation_NFR_SEC_09_10":
                self.assertFalse(v, checks)
            else:
                self.assertTrue(v, f"{k}={v} :: {checks}")
        project_dir = Path(result["project_dir"])
        for artifact in ("PLAN.md", "ARCHITECTURE.md", "QA-REPORT.md",
                         "MANAGER-REVIEW.md", "artifacts/test-output.txt"):
            self.assertTrue((project_dir / artifact).is_file(), artifact)
        paper = self.ops.get_paper(result["paper_id"])
        self.assertEqual(paper["status"], "approved")
        job = self.ops.get_print_job(result["print_job_id"])
        self.assertEqual(job["status"], "completed")

    def test_static_rbac_and_approval_boundary(self):
        checks = check_rbac_and_approval(self.ops)
        self.assertTrue(all(checks.values()), checks)

    def test_pipeline_result_records_evidence_and_report(self):
        project_dir = self.root / "pipeline-pilot"
        (project_dir / ".factory").mkdir(parents=True)
        report = project_dir / "report.md"
        report.write_text("# Report\n\nQA passed.\n", encoding="utf-8")
        (project_dir / ".factory" / "state.json").write_text(
            '{"qa_status": "PASS", "last_report": "%s"}' % str(report).replace("\\", "\\\\"),
            encoding="utf-8",
        )
        task = self.ops.create_task("Pipeline task", assignee_id="backend", project_key="pipeline-pilot")
        self.ops.transition_task(task["id"], "in_progress", actor="lead")

        result = record_pipeline_result(self.ops, project_dir, [task["id"]])

        self.assertTrue(result["qa_passed"])
        tasks = {t["id"]: t for t in self.ops.tasks()}
        self.assertEqual(tasks[task["id"]]["status"], "completed")
        self.assertTrue(tasks[task["id"]]["evidence"])
        self.assertEqual(result["paper"]["status"], "unread")
        self.assertEqual(result["print_job"]["status"], "completed")
        with self.ops._db() as db:
            delivered = db.execute(
                "SELECT 1 FROM events WHERE event_type='paper_delivered' AND entity_id=?",
                (result["paper"]["id"],),
            ).fetchone()
        self.assertIsNotNone(delivered)


if __name__ == "__main__":
    unittest.main()
