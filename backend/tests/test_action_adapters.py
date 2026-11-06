import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.office_store import OfficeStore
from core.company_operations import CompanyOperations
import core.action_adapters as adapters


class ActionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ops = CompanyOperations(OfficeStore(Path(self.tmp.name) / "adapter.db"))
        self.original_ops = adapters.OPS
        adapters.OPS = self.ops

    def tearDown(self):
        adapters.OPS = self.original_ops
        self.tmp.cleanup()

    def _approved_outbox(self, action_type, payload):
        approval = self.ops.create_approval(action_type, "Adapter test", payload)
        self.ops.decide_approval(approval["id"], "approve")
        return self.ops.list_outbox()[0]["id"]

    def test_missing_smtp_configuration_fails_safely(self):
        outbox_id = self._approved_outbox("email.send", {
            "to": "owner@example.test", "subject": "Test", "body": "No live email should be sent"
        })
        with patch.dict(os.environ, {"SMTP_HOST": "", "SMTP_USERNAME": "", "SMTP_PASSWORD": "", "SMTP_FROM": ""}, clear=False):
            with self.assertRaises(adapters.AdapterError):
                adapters.execute_outbox(outbox_id)
        row = self.ops.list_outbox()[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["attempts"], 1)

    def test_email_adapter_uses_tls_and_deterministic_outbox_header(self):
        outbox_id = self._approved_outbox("email.send", {
            "to": ["owner@example.test"], "subject": "Approved", "body": "Approved body"
        })
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.send_message.return_value = {}
        with patch.dict(os.environ, {"SMTP_HOST": "smtp.example.test", "SMTP_PORT": "587",
                                     "SMTP_USERNAME": "user", "SMTP_PASSWORD": "pw",
                                     "SMTP_FROM": "company@example.test"}, clear=False):
            with patch.object(adapters.smtplib, "SMTP", return_value=smtp):
                result = adapters.execute_outbox(outbox_id)
        self.assertTrue(result["success"])
        self.assertEqual(self.ops.list_outbox()[0]["status"], "succeeded")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["X-Bangkah-Outbox-ID"], outbox_id)
        smtp.starttls.assert_called_once()

    def test_website_deployment_requires_https_and_token(self):
        outbox_id = self._approved_outbox("website.deploy", {
            "repository": "https://example.test/site.git", "ref": "main", "target": "staging"
        })
        with patch.dict(os.environ, {"DEPLOY_WEBHOOK_URL": "http://example.test/hook", "DEPLOY_WEBHOOK_TOKEN": "secret"}, clear=False):
            with self.assertRaisesRegex(adapters.AdapterError, "HTTPS"):
                adapters.execute_outbox(outbox_id)
        self.assertEqual(self.ops.list_outbox()[0]["status"], "failed")

    def test_expense_requires_manual_executor_and_is_not_fake_completed(self):
        outbox_id = self._approved_outbox("expense.purchase", {
            "vendor": "Office Supply", "amount": 250000, "currency": "IDR"
        })
        result = adapters.execute_outbox(outbox_id)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "awaiting_executor")
        self.assertEqual(self.ops.list_outbox()[0]["status"], "awaiting_executor")

    def _email_outbox(self):
        return self._approved_outbox("email.send", {
            "to": "owner@example.test", "subject": "Retry", "body": "Retry body"
        })

    def test_failure_schedules_backoff_and_blocks_early_retry(self):
        outbox_id = self._email_outbox()
        env = {"SMTP_HOST": "", "SMTP_USERNAME": "", "SMTP_PASSWORD": "", "SMTP_FROM": "",
               "OUTBOX_MAX_ATTEMPTS": "5", "OUTBOX_BACKOFF_SECONDS": "60"}
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(adapters.AdapterError):
                adapters.execute_outbox(outbox_id)
            row = self.ops.list_outbox()[0]
            self.assertEqual(row["status"], "failed")
            self.assertEqual(row["attempts"], 1)
            self.assertTrue(row["next_retry_at"])
            with self.assertRaisesRegex(adapters.AdapterError, "Retry dijadwalkan"):
                adapters.execute_outbox(outbox_id)

    def test_exhausted_attempts_require_manual_requeue(self):
        outbox_id = self._email_outbox()
        env = {"SMTP_HOST": "", "SMTP_USERNAME": "", "SMTP_PASSWORD": "", "SMTP_FROM": "",
               "OUTBOX_MAX_ATTEMPTS": "1"}
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(adapters.AdapterError):
                adapters.execute_outbox(outbox_id)
            row = self.ops.list_outbox()[0]
            self.assertEqual(row["attempts"], 1)
            self.assertIsNone(row["next_retry_at"])
            with self.assertRaisesRegex(adapters.AdapterError, "Batas percobaan"):
                adapters.execute_outbox(outbox_id)
            requeued = self.ops.requeue_outbox(outbox_id, actor="operator")
            self.assertEqual(requeued["status"], "queued")
            self.assertEqual(requeued["attempts"], 0)

    def test_due_retry_can_be_executed_after_backoff(self):
        outbox_id = self._email_outbox()
        with patch.dict(os.environ, {"SMTP_HOST": "", "SMTP_USERNAME": "", "SMTP_PASSWORD": "",
                                     "SMTP_FROM": "", "OUTBOX_MAX_ATTEMPTS": "5",
                                     "OUTBOX_BACKOFF_SECONDS": "3600"}, clear=False):
            with self.assertRaises(adapters.AdapterError):
                adapters.execute_outbox(outbox_id)
            with self.ops._db() as db:
                db.execute("UPDATE outbox_records SET next_retry_at='2000-01-01T00:00:00+00:00' WHERE id=?",
                           (outbox_id,))
            self.assertEqual([x["id"] for x in self.ops.list_due_outbox()], [outbox_id])
            smtp = MagicMock()
            smtp.__enter__.return_value = smtp
            smtp.send_message.return_value = {}
            with patch.dict(os.environ, {"SMTP_HOST": "smtp.example.test", "SMTP_PORT": "587",
                                         "SMTP_USERNAME": "user", "SMTP_PASSWORD": "pw",
                                         "SMTP_FROM": "company@example.test"}, clear=False):
                with patch.object(adapters.smtplib, "SMTP", return_value=smtp):
                    result = adapters.execute_outbox(outbox_id)
            self.assertTrue(result["success"])
            row = self.ops.list_outbox()[0]
            self.assertEqual(row["status"], "succeeded")
            self.assertIsNone(row["next_retry_at"])

    def test_unknown_status_requires_operator_reconciliation(self):
        outbox_id = self._email_outbox()
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.send_message.side_effect = RuntimeError("connection dropped after DATA")
        with patch.dict(os.environ, {"SMTP_HOST": "smtp.example.test", "SMTP_PORT": "587",
                                     "SMTP_USERNAME": "user", "SMTP_PASSWORD": "pw",
                                     "SMTP_FROM": "company@example.test"}, clear=False):
            with patch.object(adapters.smtplib, "SMTP", return_value=smtp):
                with self.assertRaises(adapters.AdapterError):
                    adapters.execute_outbox(outbox_id)
        row = self.ops.list_outbox()[0]
        self.assertEqual(row["status"], "unknown")
        self.assertIsNone(row["next_retry_at"])
        with self.assertRaisesRegex(adapters.AdapterError, "Rekonsiliasi"):
            adapters.execute_outbox(outbox_id)

        reconciled = self.ops.reconcile_outbox(
            outbox_id, "succeeded", "Provider dashboard shows delivered.",
            external_id="provider-123", actor="operator",
        )
        self.assertEqual(reconciled["status"], "succeeded")
        self.assertEqual(reconciled["external_id"], "provider-123")
        self.assertEqual(reconciled["resolved_by"], "operator")
        self.assertTrue(reconciled["resolution_note"])
        with self.assertRaisesRegex(ValueError, "final"):
            self.ops.reconcile_outbox(outbox_id, "failed", "late change", actor="operator")

    def test_reconciliation_requires_note_and_allowed_state(self):
        outbox_id = self._email_outbox()
        with self.assertRaisesRegex(ValueError, "catatan"):
            self.ops.reconcile_outbox(outbox_id, "succeeded", "", actor="operator")
        with self.assertRaisesRegex(ValueError, "failed"):
            self.ops.reconcile_outbox(outbox_id, "maybe", "note", actor="operator")


if __name__ == "__main__":
    unittest.main()
