import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.office_store import OfficeStore
from core.company_operations import CompanyOperations


class CompanyOperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = OfficeStore(Path(self.tmp.name) / "company.db")
        self.ops = CompanyOperations(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_departments_and_employee_department_mapping(self):
        departments = {x["id"]: x for x in self.ops.departments()}
        self.assertEqual(departments["engineering"]["employee_count"], 5)
        employees = {x["id"]: x for x in self.ops.employees()}
        self.assertEqual(employees["backend"]["department_id"], "engineering")
        self.assertEqual(employees["coo"]["department_id"], "operations")

    def test_task_completion_requires_evidence_and_valid_transition(self):
        task = self.ops.create_task("Build API", "Build endpoints", "backend",
                                    acceptance_criteria="returns JSON")
        self.ops.transition_task(task["id"], "in_progress")
        with self.assertRaisesRegex(ValueError, "bukti"):
            self.ops.transition_task(task["id"], "completed")
        result = self.ops.transition_task(task["id"], "completed", [
            {"type": "commit", "reference": "https://example.test/commit/abc123", "note": "Tests passed"}
        ])
        self.assertEqual(result["status"], "completed")
        loaded = next(x for x in self.ops.tasks() if x["id"] == task["id"])
        self.assertEqual(len(loaded["evidence"]), 1)
        with self.assertRaisesRegex(ValueError, "Transisi"):
            self.ops.transition_task(task["id"], "in_progress")

    def test_task_transition_rejects_unknown_evidence_reference(self):
        task = self.ops.create_task("Task", assignee_id="qa")
        with self.assertRaisesRegex(ValueError, "reference"):
            self.ops.transition_task(task["id"], "in_progress", [{"type": "link", "reference": ""}])

    def test_meeting_lifecycle_requires_minutes(self):
        meeting = self.ops.create_meeting("Sprint review", ["lead", "qa"], "Review quality")
        started = self.ops.update_meeting(meeting["id"], "start")
        self.assertEqual(started["status"], "in_progress")
        with self.assertRaisesRegex(ValueError, "Notulen"):
            self.ops.update_meeting(meeting["id"], "complete")
        finished = self.ops.update_meeting(meeting["id"], "complete", minutes="QA findings reviewed",
                                           decisions=["Fix critical issue"], followups=["Bima to patch"])
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(finished["decisions"], ["Fix critical issue"])
        self.assertEqual(finished["attendee_ids"], ["lead", "qa"])

    def test_meeting_cannot_start_twice(self):
        meeting = self.ops.create_meeting("Review", [])
        self.ops.update_meeting(meeting["id"], "start")
        with self.assertRaisesRegex(ValueError, "Transisi"):
            self.ops.update_meeting(meeting["id"], "start")

    def test_paper_lifecycle_and_pdf_print_job(self):
        paper = self.ops.create_paper("Weekly report", "Bangkah progress\nAll tests passed",
                                      paper_type="report", origin="Arman", priority="high")
        self.assertEqual(paper["status"], "unread")
        self.assertEqual(self.ops.update_paper_status(paper["id"], "read")["status"], "read")
        job = self.ops.create_print_job(paper["id"])
        self.assertEqual(job["status"], "completed")
        output = self.ops.print_file_path(job["id"])
        self.assertTrue(output.is_file())
        self.assertEqual(output.read_bytes()[:4], b"%PDF")

    def test_approval_payload_is_hashed_and_immutable(self):
        payload = {"to": "owner@example.test", "subject": "Review", "body": "Please review"}
        approval = self.ops.create_approval("email.send", "Send review email", payload)
        expected = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                              separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(approval["payload_sha256"], expected)
        with self.assertRaises(Exception):
            with self.store._db() as db:
                db.execute("UPDATE approval_records SET payload_json='{}' WHERE id=?", (approval["id"],))

    def test_approval_decision_is_one_way_and_queues_outbox(self):
        approval = self.ops.create_approval("email.send", "Send status",
            {"to": "a@example.test", "subject": "Status", "body": "Ready"})
        decided = self.ops.decide_approval(approval["id"], "approve")
        self.assertEqual(decided["status"], "approved")
        queue = self.ops.list_outbox()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["approval_id"], approval["id"])
        with self.assertRaisesRegex(ValueError, "sudah diputuskan"):
            self.ops.decide_approval(approval["id"], "reject")

    def test_approval_linked_paper_is_updated_only_by_decision(self):
        approval = self.ops.create_approval("website.deploy", "Deploy site",
            {"repository": "https://example.test/site.git", "ref": "main", "target": "staging"})
        paper = self.ops.create_paper("Deployment proposal", "Release the latest site.", approval_id=approval["id"])
        with self.assertRaisesRegex(ValueError, "endpoint approval"):
            self.ops.update_paper_status(paper["id"], "approved")
        self.ops.decide_approval(approval["id"], "reject", note="Needs review")
        self.assertEqual(self.ops.get_paper(paper["id"])["status"], "rejected")

    def test_approval_rejects_credentials_in_payload(self):
        with self.assertRaisesRegex(ValueError, "Rahasia"):
            self.ops.create_approval("email.send", "unsafe", {
                "to": "a@example.test", "subject": "x", "body": "x", "smtp_password": "secret"
            })

    def test_approval_validates_email_recipient_and_deployment_ref(self):
        with self.assertRaisesRegex(ValueError, "Email penerima"):
            self.ops.create_approval("email.send", "bad", {"to": "not-an-email", "subject": "x", "body": "y"})
        with self.assertRaisesRegex(ValueError, "karakter tidak valid"):
            self.ops.create_approval("website.deploy", "bad", {"repository": "https://example.test/site.git", "ref": "main;rm -rf"})

    def test_approval_review_list_exposes_exact_payload_only_when_requested(self):
        payload = {"to": "owner@example.test", "subject": "Review", "body": "Final draft"}
        approval = self.ops.create_approval("email.send", "Review outbound email", payload)
        compact = self.ops.list_approvals()
        detailed = self.ops.list_approvals(include_payload=True)
        self.assertNotIn("payload", compact[0])
        self.assertEqual(detailed[0]["payload"], payload)
        self.assertEqual(detailed[0]["id"], approval["id"])

    def test_expense_rejects_non_finite_amount_and_deploy_rejects_non_https_repository(self):
        with self.assertRaisesRegex(ValueError, "jumlah positif"):
            self.ops.create_approval("expense.purchase", "Invalid amount", {
                "vendor": "Vendor", "amount": float("nan"), "currency": "IDR"
            })
        with self.assertRaisesRegex(ValueError, "HTTPS atau SSH"):
            self.ops.create_approval("website.deploy", "Invalid repository", {
                "repository": "http://example.test/site.git", "ref": "main", "target": "staging"
            })

    def test_outbox_payload_integrity_is_verified_when_read(self):
        approval = self.ops.create_approval("website.deploy", "Deploy staging", {
            "repository": "https://example.test/site.git", "ref": "main", "target": "staging"
        })
        self.ops.decide_approval(approval["id"], "approve")
        outbox_id = self.ops.list_outbox()[0]["id"]
        with self.store._db() as db:
            db.execute("DROP TRIGGER approval_payload_immutable")
            db.execute("UPDATE approval_records SET payload_sha256='bad-hash' WHERE id=?", (approval["id"],))
        with self.assertRaisesRegex(ValueError, "tidak cocok"):
            self.ops.get_outbox_item(outbox_id)

    def test_outbox_claim_is_single_use_until_reconciliation(self):
        approval = self.ops.create_approval("expense.purchase", "Hardware purchase",
            {"vendor": "Example", "amount": 100, "currency": "IDR"})
        self.ops.decide_approval(approval["id"], "approve")
        outbox_id = self.ops.list_outbox()[0]["id"]
        claimed = self.ops.claim_outbox(outbox_id)
        self.assertEqual(claimed["status"], "executing")
        self.assertEqual(claimed["attempts"], 1)
        with self.assertRaisesRegex(ValueError, "sedang diproses"):
            self.ops.claim_outbox(outbox_id)
        self.ops.update_outbox(outbox_id, "awaiting_executor", error="Manual process")
        self.assertEqual(self.ops.list_outbox()[0]["status"], "awaiting_executor")

    def test_unknown_outbox_result_cannot_be_retried(self):
        approval = self.ops.create_approval("website.deploy", "Deploy",
            {"repository": "https://example.test/site.git", "ref": "main", "target": "production"})
        self.ops.decide_approval(approval["id"], "approve")
        outbox_id = self.ops.list_outbox()[0]["id"]
        self.ops.claim_outbox(outbox_id)
        self.ops.update_outbox(outbox_id, "unknown", error="Provider timeout")
        with self.assertRaisesRegex(ValueError, "tidak dapat diulang"):
            self.ops.claim_outbox(outbox_id)

    def test_audit_cursor_returns_monotonic_ids(self):
        self.store.add_event("test_a", "owner", "first")
        first = self.ops.audit(0, 1)
        self.store.add_event("test_b", "owner", "second")
        second = self.ops.audit(first[-1]["id"], 10)
        self.assertTrue(all(x["id"] > first[-1]["id"] for x in second))


if __name__ == "__main__":
    unittest.main()
