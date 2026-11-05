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


if __name__ == "__main__":
    unittest.main()
