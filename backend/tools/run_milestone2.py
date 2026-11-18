#!/usr/bin/env python3
"""Milestone 2 acceptance runner — real local external-action sinks.

This is an HTTP end-to-end acceptance run, not an in-process simulation:

* a fresh ``office_server.py`` subprocess is started per scenario with a
  throwaway SQLite database;
* the real ``core.action_adapters`` SMTP and deployment code runs unchanged;
* email is delivered to a local STARTTLS/AUTH SMTP sink;
* deployment is delivered to a local HTTPS webhook sink;
* a separate independent verifier re-reads the databases and sink JSONL logs;
* a fresh Python process proves the state survives a backend restart.

Usage (from ``backend/``)::

    PYTHONPATH=.pylibs:. python3.12 tools/run_milestone2.py --cycles 3

Every cycle gets a fresh directory under the gitignored ``workspace/`` tree;
logs and databases are kept for inspection. A cycle passes only when the
runner checks, the restart probe and the independent verifier all pass.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import secrets as pysecrets
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / ".pylibs"))

from tools.external_sinks import (  # noqa: E402
    DeploySink,
    SmtpSink,
    ensure_test_certificates,
    wait_for_port,
)
from tools.verify_milestone2 import (  # noqa: E402
    DEPLOY_REPOSITORY,
    EMAIL_BODY,
    EMAIL_SUBJECT,
    EXHAUSTED_SUBJECT,
    EXPENSE_VENDOR,
    MISSING_SUBJECT,
    REJECT_SUBJECT,
    UNKNOWN_SUBJECT,
)

SMTP_USER = "milestone2"
SMTP_FROM = "company@example.test"


class CycleFailure(RuntimeError):
    pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _sanitize(value):
    if isinstance(value, dict):
        return {
            key: "<redacted>" if str(key).lower() in {
                "token", "password", "authorization", "secret", "api_key",
            } else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _clean_environment() -> dict:
    """Start from the caller's environment without service credentials."""
    clean = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if upper.startswith(("SMTP_", "DEPLOY_", "OUTBOX_", "BANGKAH_")):
            continue
        if upper in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
            continue
        clean[key] = value
    clean["PYTHONPATH"] = ".pylibs:."
    # Keep subprocess startup deterministic and offline: CrewAI/OpenTelemetry
    # telemetry must not add network stalls to acceptance runs.
    clean.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    clean.setdefault("OTEL_SDK_DISABLED", "true")
    clean.setdefault("ANONYMIZED_TELEMETRY", "False")
    return clean


class Backend:
    def __init__(self, cycle_dir: Path, label: str, python: str, env: dict,
                 port: int | None = None):
        self.cycle_dir = cycle_dir
        self.label = label
        self.python = python
        self.env = dict(env)
        self.port = int(port or _free_port())
        self.base = f"http://127.0.0.1:{self.port}"
        self.log_path = cycle_dir / f"server-{label}.log"
        self.proc = None
        self.token = ""
        self.observations: list[dict] = []

    def start(self, timeout: float = 300.0):
        self.env["BANGKAH_HOST"] = "127.0.0.1"
        self.env["BANGKAH_PORT"] = str(self.port)
        with self.log_path.open("ab") as log:
            self.proc = subprocess.Popen(
                [self.python, "office_server.py"],
                cwd=str(BACKEND),
                env=self.env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        if not wait_for_port("127.0.0.1", self.port, timeout=timeout):
            self.stop()
            raise CycleFailure(
                f"{self.label}: backend did not listen on {self.port}. "
                f"Log: {self.log_path}"
            )
        return self

    def stop(self, timeout: float = 20.0):
        if self.proc is None:
            return
        proc, self.proc = self.proc, None
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=timeout)
        return proc.returncode

    def request(self, method: str, path: str, body=None, token: str | None = None,
                label: str = "", timeout: float = 40.0):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        bearer = token if token is not None else self.token
        if bearer:
            request.add_header("Authorization", f"Bearer {bearer}")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.status
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            status = error.code
            raw = error.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise CycleFailure(f"{self.label}: {method} {path} failed: {error}") from error
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            payload = {"raw": raw[:1000]}
        if label:
            self.observations.append({
                "label": label,
                "method": method,
                "path": path,
                "status": status,
                "response": _sanitize(payload),
            })
        return status, payload

    def login(self, username: str, password: str):
        status, payload = self.request(
            "POST", "/api/auth/login",
            {"username": username, "password": password},
            token="", label="owner login",
        )
        if status != 200 or not payload.get("session", {}).get("token"):
            raise CycleFailure(f"{self.label}: owner login failed with HTTP {status}")
        self.token = payload["session"]["token"]
        # The session token is a credential; keep it out of observations.
        self.observations[-1]["response"] = {"status": "authenticated"}
        return self.token

    def get_outbox(self, label: str = ""):
        status, payload = self.request("GET", "/api/outbox", label=label)
        if status != 200:
            raise CycleFailure(f"{self.label}: GET /api/outbox -> HTTP {status}")
        return payload.get("outbox", [])

    def outbox_for(self, approval_id: str, label: str = ""):
        return [
            item for item in self.get_outbox(label)
            if item.get("approval_id") == approval_id
        ]


def _require(checks: dict, name: str, condition: bool, detail: str = ""):
    checks[name] = bool(condition)
    if not condition:
        raise CycleFailure(f"{name} failed{': ' + detail if detail else ''}")


def _create_approval(api: Backend, action_type: str, summary: str, payload: dict,
                     label: str) -> dict:
    status, body = api.request(
        "POST", "/api/approvals",
        {"action_type": action_type, "summary": summary, "payload": payload},
        label=label,
    )
    if status != 201 or "approval" not in body:
        raise CycleFailure(f"{api.label}: create approval -> HTTP {status}: {body}")
    return body["approval"]


def _decide(api: Backend, approval_id: str, decision: str, note: str,
            label: str, expect: int = 200):
    status, body = api.request(
        "POST", f"/api/approvals/{approval_id}/{decision}",
        {"note": note}, label=label,
    )
    if status != expect:
        raise CycleFailure(
            f"{api.label}: {decision} {approval_id} -> HTTP {status}: {body}")
    return body


def _execute(api: Backend, outbox_id: str, label: str):
    return api.request("POST", f"/api/outbox/{outbox_id}/execute", {}, label=label)


def _main_scenario(api: Backend, checks: dict, smtp_main: SmtpSink,
                   deploy_main: DeploySink) -> dict:
    # --- Email: approval alone must not send; explicit execute must. ---
    email_approval = _create_approval(
        api, "email.send", "Milestone 2 approved email delivery",
        {"to": ["owner@example.test"], "subject": EMAIL_SUBJECT, "body": EMAIL_BODY},
        label="create email approval",
    )
    _require(checks, "no_delivery_on_approval_creation",
             not api.outbox_for(email_approval["id"])
             and not smtp_main.log.records() and not deploy_main.log.records(),
             "outbox rows or sink deliveries exist before approval")
    _require(checks, "approval_payload_hash_present",
             len(str(email_approval.get("payload_sha256", ""))) == 64,
             "approval payload SHA-256 missing")
    _decide(api, email_approval["id"], "approve",
            "Owner approved the exact payload shown.", "approve email")
    email_items = api.outbox_for(email_approval["id"], label="outbox after email approval")
    _require(checks, "approval_creates_single_queued_outbox",
             len(email_items) == 1 and email_items[0].get("status") == "queued",
             f"items={[(i.get('id'), i.get('status')) for i in email_items]}")
    _require(checks, "no_delivery_on_approval_decision",
             not smtp_main.log.records() and not deploy_main.log.records(),
             "sink received a message before outbox execute")
    _decide(api, email_approval["id"], "approve", "duplicate",
            "duplicate email approval", expect=400)

    email_outbox_id = email_items[0]["id"]
    status, body = _execute(api, email_outbox_id, "execute email")
    _require(checks, "email_execute_succeeded",
             status == 200 and body.get("success") is True
             and body.get("status") == "succeeded"
             and (body.get("result") or {}).get("provider") == "smtp",
             f"HTTP {status}: {body}")
    email_records = smtp_main.log.records()
    _require(checks, "email_sink_received_once",
             len(email_records) == 1
             and email_records[0].get("outbox_id") == email_outbox_id,
             f"records={len(email_records)}")

    status, body = _execute(api, email_outbox_id, "duplicate email execute")
    _require(checks, "duplicate_execute_is_idempotent",
             status == 200 and body.get("already_completed") is True
             and len(smtp_main.log.records()) == 1,
             f"HTTP {status}: {body}")

    # --- Deployment: local HTTPS webhook sink. ---
    deploy_payload = {
        "repository": DEPLOY_REPOSITORY,
        "ref": "main",
        "target": "staging",
    }
    deploy_approval = _create_approval(
        api, "website.deploy", "Milestone 2 staging deployment",
        deploy_payload, label="create deploy approval",
    )
    _decide(api, deploy_approval["id"], "approve",
            "Owner approved the staging deployment.", "approve deploy")
    deploy_items = api.outbox_for(deploy_approval["id"], label="outbox after deploy approval")
    _require(checks, "deploy_approval_queued_without_delivery",
             len(deploy_items) == 1 and deploy_items[0].get("status") == "queued"
             and not deploy_main.log.records(),
             f"items={[(i.get('id'), i.get('status')) for i in deploy_items]}")
    deploy_outbox_id = deploy_items[0]["id"]
    status, body = _execute(api, deploy_outbox_id, "execute deploy")
    _require(checks, "deploy_execute_succeeded",
             status == 200 and body.get("success") is True
             and body.get("status") == "succeeded"
             and (body.get("result") or {}).get("provider") == "deployment_webhook",
             f"HTTP {status}: {body}")
    deploy_records = deploy_main.log.records()
    _require(checks, "deploy_sink_received_once",
             len(deploy_records) == 1
             and deploy_records[0].get("body", {}).get("outbox_id") == deploy_outbox_id,
             f"records={len(deploy_records)}")
    status, body = _execute(api, deploy_outbox_id, "duplicate deploy execute")
    _require(checks, "deploy_duplicate_is_idempotent",
             status == 200 and body.get("already_completed") is True
             and len(deploy_main.log.records()) == 1,
             f"HTTP {status}: {body}")

    # --- Reject: no outbox row, no delivery. ---
    reject_approval = _create_approval(
        api, "email.send", "Milestone 2 rejected email",
        {"to": "owner@example.test", "subject": REJECT_SUBJECT, "body": "Never send."},
        label="create rejected approval",
    )
    _decide(api, reject_approval["id"], "reject",
            "Owner rejected this external action.", "reject email")
    _require(checks, "reject_creates_no_outbox_or_delivery",
             not api.outbox_for(reject_approval["id"])
             and not any(REJECT_SUBJECT in str(record.get("subject", ""))
                         for record in smtp_main.log.records()),
             "rejected approval produced an outbox row or sink delivery")
    _decide(api, reject_approval["id"], "reject", "duplicate",
            "duplicate reject", expect=400)

    # --- Expense: manual executor, never an automatic send. ---
    expense_approval = _create_approval(
        api, "expense.purchase", "Milestone 2 manual expense",
        {"vendor": EXPENSE_VENDOR, "amount": 149.5, "currency": "USD"},
        label="create expense approval",
    )
    _decide(api, expense_approval["id"], "approve",
            "Owner approved the expense for manual handling.", "approve expense")
    expense_items = api.outbox_for(expense_approval["id"], label="outbox after expense approval")
    _require(checks, "expense_outbox_queued",
             len(expense_items) == 1 and expense_items[0].get("status") == "queued",
             f"items={[(i.get('id'), i.get('status')) for i in expense_items]}")
    status, body = _execute(api, expense_items[0]["id"], "execute expense")
    expense_after = api.outbox_for(expense_approval["id"], label="outbox after expense execute")
    _require(checks, "expense_awaits_manual_executor",
             status == 202 and body.get("status") == "awaiting_executor"
             and len(expense_after) == 1
             and expense_after[0].get("status") == "awaiting_executor"
             and not expense_after[0].get("external_id")
             and EXPENSE_VENDOR not in json.dumps(smtp_main.log.records()),
             f"HTTP {status}: {body}")

    return {
        "email_outbox_id": email_outbox_id,
        "deploy_outbox_id": deploy_outbox_id,
        "expense_outbox_id": expense_items[0]["id"],
    }


def _negative_missing_and_http(api: Backend, checks: dict,
                               deploy_main: DeploySink):
    missing = _create_approval(
        api, "email.send", "Missing SMTP configuration",
        {"to": "owner@example.test", "subject": MISSING_SUBJECT, "body": "No SMTP."},
        label="create missing-config approval",
    )
    _decide(api, missing["id"], "approve", "approved for negative test",
            "approve missing-config")
    items = api.outbox_for(missing["id"])
    status, body = _execute(api, items[0]["id"], "execute missing-config")
    after = api.outbox_for(missing["id"])[0]
    _require(checks, "missing_config_fails_with_backoff",
             status == 409 and after.get("status") == "failed"
             and int(after.get("attempts") or 0) == 1
             and bool(after.get("next_retry_at"))
             and "SMTP belum dikonfigurasi" in str(after.get("last_error") or ""),
             f"HTTP {status}: {body}; row={after.get('status')}")
    status, _body = _execute(api, items[0]["id"], "early retry missing-config")
    _require(checks, "early_retry_is_refused", status == 409,
             f"early retry returned HTTP {status}")

    deploy = _create_approval(
        api, "website.deploy", "Plain HTTP webhook must fail",
        {"repository": "https://example.test/http-negative.git",
         "ref": "main", "target": "staging"},
        label="create non-HTTPS deploy approval",
    )
    _decide(api, deploy["id"], "approve", "approved for negative test",
            "approve non-HTTPS deploy")
    deploy_item = api.outbox_for(deploy["id"])[0]
    status, body = _execute(api, deploy_item["id"], "execute non-HTTPS deploy")
    deploy_after = api.outbox_for(deploy["id"])[0]
    _require(checks, "non_https_deploy_rejected",
             status == 409 and deploy_after.get("status") == "failed"
             and "HTTPS" in str(deploy_after.get("last_error") or "")
             and deploy_item["id"] not in {
                 str(record.get("outbox_id")) for record in deploy_main.log.records()
             },
             f"HTTP {status}: {body}; row={deploy_after.get('status')}")

    expense = _create_approval(
        api, "expense.purchase", "Negative-db manual expense",
        {"vendor": EXPENSE_VENDOR, "amount": 25, "currency": "USD"},
        label="create negative expense approval",
    )
    _decide(api, expense["id"], "approve", "approved for negative test",
            "approve negative expense")
    expense_item = api.outbox_for(expense["id"])[0]
    status, body = _execute(api, expense_item["id"], "execute negative expense")
    _require(checks, "negative_expense_awaits_executor",
             status == 202 and body.get("status") == "awaiting_executor",
             f"HTTP {status}: {body}")


def _negative_unknown(api: Backend, checks: dict, smtp_unknown: SmtpSink):
    approval = _create_approval(
        api, "email.send", "Uncertain provider outcome",
        {"to": "owner@example.test", "subject": UNKNOWN_SUBJECT,
         "body": "Delivered by the sink but not acknowledged."},
        label="create unknown approval",
    )
    _decide(api, approval["id"], "approve", "approved for unknown test",
            "approve unknown")
    item = api.outbox_for(approval["id"])[0]
    status, body = _execute(api, item["id"], "execute unknown")
    after = api.outbox_for(approval["id"])[0]
    records = smtp_unknown.log.records()
    _require(checks, "unknown_outcome_is_parked",
             status == 409 and after.get("status") == "unknown"
             and len(records) == 1 and records[0].get("outbox_id") == item["id"],
             f"HTTP {status}: {body}; row={after.get('status')} records={len(records)}")
    status, _body = _execute(api, item["id"], "resend unknown")
    _require(checks, "unknown_blocks_duplicate_send",
             status == 409 and len(smtp_unknown.log.records()) == 1,
             f"HTTP {status}; records={len(smtp_unknown.log.records())}")
    status, _body = api.request(
        "POST", f"/api/outbox/{item['id']}/reconcile",
        {"outcome": "succeeded", "note": "", "external_id": ""},
        label="reconcile without note",
    )
    _require(checks, "reconciliation_requires_note", status == 400,
             f"HTTP {status} without a verification note")

    message_id = records[0].get("message_id", "")
    status, body = api.request(
        "POST", f"/api/outbox/{item['id']}/reconcile",
        {"outcome": "succeeded",
         "note": "Local sink JSONL confirms exactly one received message.",
         "external_id": message_id},
        label="reconcile unknown",
    )
    after = api.outbox_for(approval["id"])[0]
    _require(checks, "reconciliation_resolves_without_send",
             status == 200 and after.get("status") == "succeeded"
             and after.get("resolved_by") and after.get("resolution_note")
             and after.get("external_id") == message_id
             and len(smtp_unknown.log.records()) == 1,
             f"HTTP {status}: {body}; row={after.get('status')}")
    status, _body = api.request(
        "POST", f"/api/outbox/{item['id']}/reconcile",
        {"outcome": "failed", "note": "late change"},
        label="reconcile final result",
    )
    _require(checks, "reconciled_result_is_final", status == 400,
             f"HTTP {status} after final result")
    status, body = _execute(api, item["id"], "execute after reconcile")
    _require(checks, "reconciled_duplicate_is_idempotent",
             status == 200 and body.get("already_completed") is True
             and len(smtp_unknown.log.records()) == 1,
             f"HTTP {status}: {body}")


def _negative_exhausted(api: Backend, checks: dict, smtp_exhausted: SmtpSink):
    approval = _create_approval(
        api, "email.send", "Exhausted retries",
        {"to": "owner@example.test", "subject": EXHAUSTED_SUBJECT,
         "body": "Authentication is rejected by the sink."},
        label="create exhausted approval",
    )
    _decide(api, approval["id"], "approve", "approved for exhaustion test",
            "approve exhausted")
    item = api.outbox_for(approval["id"])[0]
    status, body = _execute(api, item["id"], "execute exhausted")
    after = api.outbox_for(approval["id"])[0]
    _require(checks, "exhaustion_stops_retries",
             status == 409 and after.get("status") == "failed"
             and int(after.get("attempts") or 0) == 1
             and not after.get("next_retry_at")
             and not smtp_exhausted.log.records(),
             f"HTTP {status}: {body}; row={after.get('status')}")
    status, _body = _execute(api, item["id"], "resend exhausted")
    _require(checks, "exhausted_resend_is_refused", status == 409,
             f"HTTP {status}")
    status, body = api.request(
        "POST", f"/api/outbox/{item['id']}/requeue", {},
        label="requeue exhausted",
    )
    after = api.outbox_for(approval["id"])[0]
    _require(checks, "requeue_resets_exhausted_item",
             status == 200 and after.get("status") == "queued"
             and int(after.get("attempts") or 0) == 0
             and not after.get("last_error"),
             f"HTTP {status}: {body}; row={after.get('status')}")
    status, _body = api.request(
        "POST", f"/api/outbox/{item['id']}/requeue", {},
        label="requeue non-failed item",
    )
    _require(checks, "requeue_requires_failed_status", status == 400,
             f"HTTP {status}")


def _restart_check(python: str, cycle_dir: Path, env: dict, port: int,
                   expected: dict, checks: dict):
    restarted = Backend(cycle_dir, "main-restarted", python, env, port=port)
    restarted.start()
    try:
        restarted.login("owner", env["BANGKAH_OWNER_PASSWORD"])
        outbox = restarted.get_outbox("outbox after backend restart")
        for name in ("email", "deploy"):
            outbox_id = expected[f"{name}_outbox_id"]
            row = next((item for item in outbox if item.get("id") == outbox_id), None)
            _require(checks, f"{name}_state_survives_restart",
                     bool(row and row.get("status") == "succeeded"
                          and row.get("external_id")),
                     f"{name} outbox row after restart: {row}")
        expense = next(
            (item for item in outbox
             if item.get("id") == expected["expense_outbox_id"]), None)
        _require(checks, "expense_state_survives_restart",
                 bool(expense and expense.get("status") == "awaiting_executor"),
                 f"expense row after restart: {expense}")
        restarted.request(
            "GET", "/api/approvals?status=pending",
            label="approvals after backend restart")
    finally:
        restarted.stop()


def _run_process(command: list[str], cwd: Path, env: dict, log_path: Path) -> int:
    with log_path.open("ab") as log:
        completed = subprocess.run(
            command, cwd=str(cwd), env=env, stdout=log,
            stderr=subprocess.STDOUT, timeout=600, check=False,
        )
    return completed.returncode


def run_cycle(index: int, cycle_dir: Path, python: str) -> dict:
    cycle_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    owner_password = "m2-owner-" + pysecrets.token_hex(12)
    smtp_password = "m2-smtp-" + pysecrets.token_hex(12)
    deploy_token = "m2-deploy-" + pysecrets.token_hex(16)
    checks: dict[str, bool] = {}
    summary: dict = {
        "cycle": index,
        "directory": str(cycle_dir),
        "checks": checks,
        "observations": [],
    }

    main_db = cycle_dir / "main.db"
    negative_db = cycle_dir / "negative.db"
    certs = ensure_test_certificates(cycle_dir / "certs")
    sinks = []
    main_api = None
    try:
        smtp_main = SmtpSink(
            certs["cert_file"], certs["key_file"],
            cycle_dir / "smtp-main.jsonl", SMTP_USER, smtp_password)
        deploy_main = DeploySink(
            certs["cert_file"], certs["key_file"],
            cycle_dir / "deploy-main.jsonl", deploy_token)
        smtp_unknown = SmtpSink(
            certs["cert_file"], certs["key_file"],
            cycle_dir / "smtp-unknown.jsonl", SMTP_USER, smtp_password,
            drop_after_data=True)
        smtp_exhausted = SmtpSink(
            certs["cert_file"], certs["key_file"],
            cycle_dir / "smtp-exhausted.jsonl", SMTP_USER,
            "rejected-" + pysecrets.token_hex(8))
        sinks = [smtp_main, deploy_main, smtp_unknown, smtp_exhausted]

        main_env = _clean_environment()
        main_env.update({
            "BANGKAH_DB_PATH": str(main_db),
            "BANGKAH_OWNER_PASSWORD": owner_password,
            "SMTP_HOST": "127.0.0.1",
            "SMTP_PORT": str(smtp_main.port),
            "SMTP_USERNAME": SMTP_USER,
            "SMTP_PASSWORD": smtp_password,
            "SMTP_FROM": SMTP_FROM,
            "DEPLOY_WEBHOOK_URL": f"https://127.0.0.1:{deploy_main.port}/hook",
            "DEPLOY_WEBHOOK_TOKEN": deploy_token,
            "SSL_CERT_FILE": certs["ca_file"],
            "OUTBOX_MAX_ATTEMPTS": "5",
            "OUTBOX_BACKOFF_SECONDS": "3600",
        })
        main_api = Backend(cycle_dir, "main", python, main_env)
        main_api.start()
        main_api.login("owner", owner_password)
        expected = _main_scenario(main_api, checks, smtp_main, deploy_main)
        main_api.stop()
        summary["observations"].extend(main_api.observations)

        # Negative A: no SMTP configuration and a plain-HTTP deploy webhook.
        negative_a_env = _clean_environment()
        negative_a_env.update({
            "BANGKAH_DB_PATH": str(negative_db),
            "BANGKAH_OWNER_PASSWORD": owner_password,
            "SMTP_HOST": "",
            "SMTP_PORT": "",
            "SMTP_USERNAME": "",
            "SMTP_PASSWORD": "",
            "SMTP_FROM": "",
            "DEPLOY_WEBHOOK_URL": "http://127.0.0.1:9/hook",
            "DEPLOY_WEBHOOK_TOKEN": deploy_token,
            "OUTBOX_MAX_ATTEMPTS": "5",
            "OUTBOX_BACKOFF_SECONDS": "3600",
        })
        negative_a = Backend(cycle_dir, "negative-a", python, negative_a_env)
        negative_a.start()
        try:
            negative_a.login("owner", owner_password)
            _negative_missing_and_http(negative_a, checks, deploy_main)
            summary["observations"].extend(negative_a.observations)
        finally:
            negative_a.stop()

        # Negative B: sink accepts DATA but never acknowledges it.
        negative_b_env = _clean_environment()
        negative_b_env.update({
            "BANGKAH_DB_PATH": str(negative_db),
            "BANGKAH_OWNER_PASSWORD": owner_password,
            "SMTP_HOST": "127.0.0.1",
            "SMTP_PORT": str(smtp_unknown.port),
            "SMTP_USERNAME": SMTP_USER,
            "SMTP_PASSWORD": smtp_password,
            "SMTP_FROM": SMTP_FROM,
            "DEPLOY_WEBHOOK_URL": "",
            "DEPLOY_WEBHOOK_TOKEN": "",
            "SSL_CERT_FILE": certs["ca_file"],
            "OUTBOX_MAX_ATTEMPTS": "5",
            "OUTBOX_BACKOFF_SECONDS": "3600",
        })
        negative_b = Backend(cycle_dir, "negative-b", python, negative_b_env)
        negative_b.start()
        try:
            negative_b.login("owner", owner_password)
            _negative_unknown(negative_b, checks, smtp_unknown)
            summary["observations"].extend(negative_b.observations)
        finally:
            negative_b.stop()

        # Negative C: SMTP authentication is rejected and attempts are capped.
        negative_c_env = _clean_environment()
        negative_c_env.update({
            "BANGKAH_DB_PATH": str(negative_db),
            "BANGKAH_OWNER_PASSWORD": owner_password,
            "SMTP_HOST": "127.0.0.1",
            "SMTP_PORT": str(smtp_exhausted.port),
            "SMTP_USERNAME": SMTP_USER,
            "SMTP_PASSWORD": smtp_password,
            "SMTP_FROM": SMTP_FROM,
            "DEPLOY_WEBHOOK_URL": "",
            "DEPLOY_WEBHOOK_TOKEN": "",
            "SSL_CERT_FILE": certs["ca_file"],
            "OUTBOX_MAX_ATTEMPTS": "1",
            "OUTBOX_BACKOFF_SECONDS": "3600",
        })
        negative_c = Backend(cycle_dir, "negative-c", python, negative_c_env)
        negative_c.start()
        try:
            negative_c.login("owner", owner_password)
            _negative_exhausted(negative_c, checks, smtp_exhausted)
            summary["observations"].extend(negative_c.observations)
        finally:
            negative_c.stop()

        # Restart the real backend against the main database, then prove the
        # state with HTTP and a separate fresh Python process.
        _restart_check(python, cycle_dir, main_env, main_api.port, expected, checks)

        for sink in sinks:
            sink.stop()
        sinks = []

        probe_path = cycle_dir / "state-probe.json"
        probe_log = cycle_dir / "state-probe.log"
        probe_env = _clean_environment()
        probe_code = _run_process(
            [python, "tools/check_milestone2_state.py",
             "--db", str(main_db), "--negative-db", str(negative_db),
             "--json", str(probe_path)],
            BACKEND, probe_env, probe_log,
        )
        probe = json.loads(probe_path.read_text(encoding="utf-8")) \
            if probe_path.is_file() else {}
        _require(checks, "fresh_process_probe",
                 probe_code == 0 and probe.get("all_persisted") is True,
                 f"exit={probe_code} probe={probe.get('checks')}")
        summary["probe"] = probe

        verify_env = _clean_environment()
        verify_env.update({
            "SMTP_PASSWORD": smtp_password,
            "SMTP_USERNAME": SMTP_USER,
            "DEPLOY_WEBHOOK_TOKEN": deploy_token,
            "BANGKAH_OWNER_PASSWORD": owner_password,
        })
        verification_path = cycle_dir / "verification.json"
        verify_log = cycle_dir / "verify.log"
        verify_code = _run_process(
            [python, "tools/verify_milestone2.py",
             "--db", str(main_db),
             "--negative-db", str(negative_db),
             "--smtp-log", str(cycle_dir / "smtp-main.jsonl"),
             "--deploy-log", str(cycle_dir / "deploy-main.jsonl"),
             "--unknown-smtp-log", str(cycle_dir / "smtp-unknown.jsonl"),
             "--exhausted-smtp-log", str(cycle_dir / "smtp-exhausted.jsonl"),
             "--probe-json", str(probe_path),
             "--scan-root", str(cycle_dir),
             "--json-out", str(verification_path)],
            BACKEND, verify_env, verify_log,
        )
        verification = json.loads(verification_path.read_text(encoding="utf-8")) \
            if verification_path.is_file() else {}
        summary["verification"] = verification
        _require(checks, "independent_verifier",
                 verify_code == 0 and verification.get("passed") is True,
                 f"exit={verify_code} checks={verification.get('checks')}")
    except Exception as error:
        summary["error"] = f"{type(error).__name__}: {error}"
        (cycle_dir / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        if main_api is not None:
            main_api.stop()
    finally:
        for sink in sinks:
            try:
                sink.stop()
            except Exception:
                pass
        summary["duration_seconds"] = round(time.monotonic() - started, 2)
        summary["passed"] = bool(checks) and all(checks.values()) and "error" not in summary
        summary["observations"] = summary.get("observations", [])
        (cycle_dir / "observations.json").write_text(
            json.dumps(summary["observations"], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        (cycle_dir / "cycle-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Milestone 2 external-action acceptance cycles.")
    parser.add_argument("--cycles", type=int, default=3,
                        help="required consecutive clean cycles (default: 3)")
    parser.add_argument("--max-attempts", type=int,
                        help="maximum cycles to run; failures reset the streak")
    parser.add_argument("--run-dir", help="directory for logs and databases")
    parser.add_argument("--python", default=sys.executable,
                        help="Python interpreter used for backend subprocesses")
    args = parser.parse_args(argv)

    required = max(1, args.cycles)
    max_attempts = max(required, args.max_attempts or required)
    if args.run_dir:
        run_root = Path(args.run_dir).resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_root = (
            BACKEND / "workspace" / "projects"
            / f"evidence-{datetime.now().strftime('%Y%m%d')}"
            / "milestone2" / "acceptance"
            / f"milestone2-logs-{stamp}"
        )
    run_root.mkdir(parents=True, exist_ok=True)

    print("Milestone 2 acceptance — external actions end-to-end")
    print(f"Root: {run_root}")
    print(f"Required consecutive passes: {required}; max attempts: {max_attempts}")
    print("-" * 72)

    consecutive = 0
    history = []
    attempt = 0
    while consecutive < required and attempt < max_attempts:
        attempt += 1
        cycle_dir = run_root / f"cycle-{attempt:02d}"
        print(f"[cycle {attempt}] {cycle_dir}", flush=True)
        summary = run_cycle(attempt, cycle_dir, args.python)
        history.append(summary)
        if summary.get("passed"):
            consecutive += 1
            print(f"[cycle {attempt}] PASS "
                  f"({summary.get('duration_seconds')}s, streak={consecutive}/{required})")
        else:
            consecutive = 0
            print(f"[cycle {attempt}] FAIL: {summary.get('error', 'check failed')}")
        print("-" * 72, flush=True)

    overall = {
        "required_consecutive": required,
        "attempts": attempt,
        "consecutive_passes": consecutive,
        "passed": consecutive >= required,
        "cycles": [
            {
                "cycle": item.get("cycle"),
                "passed": item.get("passed"),
                "duration_seconds": item.get("duration_seconds"),
                "error": item.get("error"),
            }
            for item in history
        ],
    }
    (run_root / "acceptance-summary.json").write_text(
        json.dumps(overall, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(overall, indent=2))
    print("MILESTONE 2: " + ("PASS" if overall["passed"] else "FAIL"))
    return 0 if overall["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
