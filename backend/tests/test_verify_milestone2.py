"""White-box tests for the independent Milestone 2 verifier.

The verifier is supposed to trust only the database and the sink logs, so these
tests build that evidence directly and then check the verifier's verdict.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.company_operations import CompanyOperations
from core.office_store import OfficeStore
from tools.verify_milestone2 import (
    DEPLOY_REPOSITORY,
    EMAIL_SUBJECT,
    EXHAUSTED_SUBJECT,
    EXPENSE_VENDOR,
    MISSING_SUBJECT,
    REJECT_SUBJECT,
    UNKNOWN_SUBJECT,
    _normalize,
    _record_outbox_id,
    _sink_ids,
    read_jsonl,
    scan_for_secrets,
    verify_main,
    verify_negative,
)


def _write_jsonl(path: Path, records: list[dict]):
    path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class VerifierHelperTests(unittest.TestCase):
    def test_read_jsonl_missing_and_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_jsonl(Path(tmp) / "missing.jsonl"), [])
            path = Path(tmp) / "log.jsonl"
            path.write_text('{"ok": true}\n\nnot-json\n', encoding="utf-8")
            records = read_jsonl(path)
            self.assertEqual(records[0], {"ok": True})
            self.assertEqual(records[1]["kind"], "invalid-json")

    def test_normalize_line_endings_and_trailing_whitespace(self):
        self.assertEqual(_normalize("a\r\nb  \r\n"), _normalize("a\nb"))

    def test_deploy_sink_outbox_id_falls_back_to_body(self):
        record = {"idempotency_key": "OUT-1", "body": {"outbox_id": "OUT-1"}}
        self.assertEqual(_record_outbox_id(record), "OUT-1")
        self.assertEqual(_sink_ids([record]), {"OUT-1"})

    def test_secret_scan_reports_file_without_echoing_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.log"
            path.write_text("prefix super-secret-value suffix", encoding="utf-8")
            hits = scan_for_secrets([path], [("SMTP_PASSWORD", "super-secret-value")])
            self.assertEqual(len(hits), 1)
            self.assertIn("SMTP_PASSWORD", hits[0])
            self.assertNotIn("super-secret-value", hits[0])


class VerifierMainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="m2-verifier-")
        self.root = Path(self.tmp.name)
        self.db = self.root / "main.db"
        self.ops = CompanyOperations(OfficeStore(self.db))
        self.smtp_log = self.root / "smtp.jsonl"
        self.deploy_log = self.root / "deploy.jsonl"

        self.email_approval, self.email_outbox = self._approved(
            "email.send", {
                "to": ["owner@example.test"],
                "subject": EMAIL_SUBJECT,
                "body": "Approved body for the sink.",
            })
        self.ops.claim_outbox(self.email_outbox)
        email_item = self.ops.get_outbox_item(self.email_outbox)
        self.email_message_id = f"<{self.email_outbox.lower()}@example.test>"
        self.ops.update_outbox(
            self.email_outbox, "succeeded",
            external_id=self.email_message_id, result={"provider": "smtp"})

        self.deploy_approval, self.deploy_outbox = self._approved(
            "website.deploy", {
                "repository": DEPLOY_REPOSITORY,
                "ref": "main",
                "target": "staging",
            })
        self.ops.claim_outbox(self.deploy_outbox)
        deploy_item = self.ops.get_outbox_item(self.deploy_outbox)
        self.deploy_id = "DEP-TEST123"
        self.ops.update_outbox(
            self.deploy_outbox, "succeeded",
            external_id=self.deploy_id, result={"provider": "deployment_webhook"})

        reject_approval, _ = self._approved(
            "email.send", {
                "to": "owner@example.test",
                "subject": REJECT_SUBJECT,
                "body": "Never delivered.",
            }, decide="reject")
        self.reject_approval = reject_approval

        _, self.expense_outbox = self._approved(
            "expense.purchase", {
                "vendor": EXPENSE_VENDOR,
                "amount": 149.5,
                "currency": "USD",
            })
        self.ops.claim_outbox(self.expense_outbox)
        self.ops.update_outbox(
            self.expense_outbox, "awaiting_executor",
            error="Manual process required.")

        _write_jsonl(self.smtp_log, [{
            "kind": "smtp",
            "outbox_id": self.email_outbox,
            "message_id": self.email_message_id,
            "subject": EMAIL_SUBJECT,
            "to": ["owner@example.test"],
            "body": "Approved body for the sink.\r\n",
            "authenticated_user": "milestone2",
        }])
        _write_jsonl(self.deploy_log, [{
            "kind": "deploy",
            "idempotency_key": self.deploy_outbox,
            "deployment_id": self.deploy_id,
            "content_type": "application/json",
            "authorization_sha256": _sha256("Bearer deploy-secret"),
            "body": {
                "outbox_id": self.deploy_outbox,
                "approval_id": self.deploy_approval["id"],
                "payload_sha256": deploy_item["payload_sha256"],
                **deploy_item["payload"],
            },
        }])
        self.probe = self.root / "probe.json"
        self.probe.write_text(json.dumps({
            "all_persisted": True,
            "checks": {"email": True, "negative": True},
        }), encoding="utf-8")

    def tearDown(self):
        self.ops.close()
        self.tmp.cleanup()

    def _approved(self, action_type, payload, decide="approve"):
        approval = self.ops.create_approval(
            action_type, "Verifier test", payload,
            actor="owner", actor_role="owner",
        )
        self.ops.decide_approval(approval["id"], decide, "owner", "test")
        items = [
            item for item in self.ops.list_outbox()
            if item["approval_id"] == approval["id"]
        ]
        return approval, (items[0]["id"] if items else None)

    def _verify_main(self):
        scan_files = [self.db, self.smtp_log, self.deploy_log, self.probe]
        return verify_main(
            self.db, self.smtp_log, self.deploy_log,
            _sha256("Bearer deploy-secret"), "milestone2",
            self.probe, scan_files, [],
        )

    def test_clean_evidence_passes(self):
        checks, details = self._verify_main()
        failed = {name: detail for name, detail in details.items()
                  if not checks.get(name)}
        self.assertEqual(failed, {})
        self.assertTrue(all(checks.values()))

    def test_duplicate_delivery_record_fails_idempotency_check(self):
        _write_jsonl(self.smtp_log, [
            {
                "kind": "smtp",
                "outbox_id": self.email_outbox,
                "message_id": self.email_message_id,
                "subject": EMAIL_SUBJECT,
                "to": ["owner@example.test"],
                "body": "Approved body for the sink.",
                "authenticated_user": "milestone2",
            },
            {
                "kind": "smtp",
                "outbox_id": self.email_outbox,
                "message_id": self.email_message_id,
                "subject": EMAIL_SUBJECT,
                "to": ["owner@example.test"],
                "body": "Approved body for the sink.",
                "authenticated_user": "milestone2",
            },
        ])
        checks, _details = self._verify_main()
        self.assertFalse(checks["main_email_delivered_once"])
        self.assertFalse(checks["duplicate_execute_no_second_delivery"])

    def test_secret_in_artifacts_fails(self):
        leaked = self.root / "leaked.log"
        leaked.write_text("smtp password is verifier-secret-value", encoding="utf-8")
        scan_files = [self.db, self.smtp_log, self.deploy_log, self.probe, leaked]
        checks, _details = verify_main(
            self.db, self.smtp_log, self.deploy_log,
            _sha256("Bearer deploy-secret"), "milestone2",
            self.probe, scan_files,
            [("SMTP_PASSWORD", "verifier-secret-value")],
        )
        self.assertFalse(checks["secrets_absent_from_artifacts"])


class VerifierNegativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="m2-verifier-neg-")
        self.root = Path(self.tmp.name)
        self.db = self.root / "negative.db"
        self.ops = CompanyOperations(OfficeStore(self.db))
        self.unknown_log = self.root / "unknown.jsonl"
        self.exhausted_log = self.root / "exhausted.jsonl"
        self.deploy_log = self.root / "deploy.jsonl"
        self._build_negative_evidence()

    def tearDown(self):
        self.ops.close()
        self.tmp.cleanup()

    def _approved(self, action_type, payload):
        approval = self.ops.create_approval(
            action_type, "Negative verifier test", payload,
            actor="owner", actor_role="owner",
        )
        self.ops.decide_approval(approval["id"], "approve", "owner", "test")
        return approval, next(
            item["id"] for item in self.ops.list_outbox()
            if item["approval_id"] == approval["id"]
        )

    def _build_negative_evidence(self):
        missing_approval, missing = self._approved("email.send", {
            "to": "owner@example.test", "subject": MISSING_SUBJECT, "body": "No SMTP."})
        self.ops.claim_outbox(missing)
        self.ops.update_outbox(
            missing, "failed", error="SMTP belum dikonfigurasi.",
            next_retry_at="2099-01-01T00:00:00+00:00")

        deploy_approval, deploy = self._approved("website.deploy", {
            "repository": "https://example.test/http.git", "ref": "main",
            "target": "staging"})
        self.ops.claim_outbox(deploy)
        self.ops.update_outbox(
            deploy, "failed", error="DEPLOY_WEBHOOK_URL wajib menggunakan HTTPS.",
            next_retry_at="2099-01-01T00:00:00+00:00")

        unknown_approval, unknown = self._approved("email.send", {
            "to": "owner@example.test", "subject": UNKNOWN_SUBJECT,
            "body": "Unknown body."})
        self.ops.claim_outbox(unknown)
        self.ops.update_outbox(unknown, "unknown", error="Connection dropped.")
        message_id = f"<{unknown.lower()}@example.test>"
        _write_jsonl(self.unknown_log, [{
            "kind": "smtp", "outbox_id": unknown, "message_id": message_id,
            "subject": UNKNOWN_SUBJECT, "to": ["owner@example.test"],
            "body": "Unknown body.", "authenticated_user": "milestone2",
        }])
        self.ops.reconcile_outbox(
            unknown, "succeeded", "Sink log confirms one message.",
            external_id=message_id, actor="owner")

        exhausted_approval, exhausted = self._approved("email.send", {
            "to": "owner@example.test", "subject": EXHAUSTED_SUBJECT,
            "body": "Never delivered."})
        self.ops.claim_outbox(exhausted)
        self.ops.update_outbox(exhausted, "failed", error="SMTP auth rejected.")
        self.ops.requeue_outbox(exhausted, actor="owner")
        self.exhausted_log.write_text("", encoding="utf-8")
        self.deploy_log.write_text("", encoding="utf-8")

        _, expense = self._approved("expense.purchase", {
            "vendor": EXPENSE_VENDOR, "amount": 25, "currency": "USD"})
        self.ops.claim_outbox(expense)
        self.ops.update_outbox(expense, "awaiting_executor",
                               error="Manual process required.")

    def test_clean_negative_evidence_passes(self):
        checks, details = verify_negative(
            self.db, self.root / "main-smtp.jsonl", self.unknown_log,
            self.exhausted_log, self.deploy_log, [self.db], [])
        failed = {name: detail for name, detail in details.items()
                  if not checks.get(name)}
        self.assertEqual(failed, {})
        self.assertTrue(all(checks.values()))


if __name__ == "__main__":
    unittest.main()
