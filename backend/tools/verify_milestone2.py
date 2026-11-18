#!/usr/bin/env python3
"""Independent verifier for Milestone 2 (external actions end-to-end).

The verifier deliberately does not import the application code. It reads each
SQLite database directly (the immutability check performs a rolled-back no-op
update) and reads the local sink JSONL logs, recomputes approval payload hashes
and checks the audit trail. Runner observations are not trusted as proof; they
are only additional context.

Usage (normally invoked by ``tools/run_milestone2.py``)::

    python tools/verify_milestone2.py \
        --db <main.db> --negative-db <negative.db> \
        --smtp-log <smtp-main.jsonl> --deploy-log <deploy-main.jsonl> \
        --unknown-smtp-log <smtp-unknown.jsonl> \
        --exhausted-smtp-log <smtp-exhausted.jsonl> \
        --probe-json <state-probe.json> --scan-root <cycle-dir> \
        --json-out <verification.json>

Exit code 0 means every criterion passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# Scenario markers shared with tools/run_milestone2.py.
EMAIL_SUBJECT = "M2-SMTP-OK: approved project update"
REJECT_SUBJECT = "M2-REJECT-NO-SEND: must never be delivered"
MISSING_SUBJECT = "Missing config"
UNKNOWN_SUBJECT = "Unknown outcome"
EXHAUSTED_SUBJECT = "Exhausted retries"
EXPENSE_VENDOR = "M2 Local Supplies"
DEPLOY_REPOSITORY = "https://example.test/milestone2-site.git"
EMAIL_BODY = "Milestone 2 local SMTP sink delivery.\nSecond line of the approved body."

DEFAULT_SECRET_ENVS = ("SMTP_PASSWORD", "DEPLOY_WEBHOOK_TOKEN", "BANGKAH_OWNER_PASSWORD")


def _sha256(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    return "\n".join(
        line.rstrip()
        for line in str(text).replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    )


def read_jsonl(path: str | Path | None) -> list[dict]:
    if not path:
        return []
    file = Path(path)
    if not file.exists():
        return []
    records = []
    with file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({"kind": "invalid-json", "raw": line[:300]})
    return records


def load_database(db_path: str | Path) -> dict:
    path = Path(db_path)
    if not path.is_file():
        raise SystemExit(f"database not found: {path}")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        approvals = [dict(row) for row in connection.execute(
            "SELECT * FROM approval_records ORDER BY created_at, id")]
        outbox = [dict(row) for row in connection.execute(
            """SELECT o.*, a.payload_json, a.payload_sha256, a.status AS approval_status,
                      a.action_type AS approval_action_type
               FROM outbox_records o JOIN approval_records a ON a.id = o.approval_id
               ORDER BY o.created_at, o.id""")]
        events = [dict(row) for row in connection.execute("SELECT * FROM events ORDER BY id")]
        triggers = [dict(row) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")]
    finally:
        connection.close()
    return {"approvals": approvals, "outbox": outbox, "events": events, "triggers": triggers}


def _payload(row: dict) -> dict:
    try:
        value = json.loads(row.get("payload_json") or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _event_count(events: list[dict], event_type: str, entity_id: str) -> int:
    return sum(
        1 for event in events
        if event.get("event_type") == event_type and str(event.get("entity_id")) == str(entity_id)
    )


def _trigger_enforced(db_path: str | Path, approval_id: str) -> bool:
    """Prove the immutability trigger fires, then roll the no-op update back."""
    connection = sqlite3.connect(str(db_path), timeout=5)
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "UPDATE approval_records SET payload_json=payload_json WHERE id=?",
                (approval_id,),
            )
        except sqlite3.IntegrityError as error:
            connection.rollback()
            return "immutable" in str(error).lower()
        connection.rollback()
        return False
    finally:
        connection.close()


def _by_approval(outbox: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in outbox:
        grouped.setdefault(str(item.get("approval_id")), []).append(item)
    return grouped


def _find_subject(approvals: list[dict], needle: str, action_type: str | None = None) -> list[dict]:
    found = []
    for approval in approvals:
        if action_type and approval.get("action_type") != action_type:
            continue
        payload = _payload(approval)
        if needle.lower() in str(payload.get("subject", "")).lower():
            found.append(approval)
    return found


def _record_outbox_id(record: dict) -> str:
    body = record.get("body") if isinstance(record.get("body"), dict) else {}
    return str(
        record.get("outbox_id")
        or record.get("idempotency_key")
        or body.get("outbox_id")
        or ""
    )


def _sink_ids(records: list[dict]) -> set[str]:
    return {_record_outbox_id(item) for item in records if _record_outbox_id(item)}


def verify_main(db_path: str | Path, smtp_log, deploy_log,
                expected_auth_sha: str | None, expected_smtp_user: str | None,
                probe_json: str | Path | None, scan_files: list[Path],
                secrets: list[tuple[str, str]]) -> tuple[dict, dict]:
    state = load_database(db_path)
    approvals = state["approvals"]
    outbox = state["outbox"]
    events = state["events"]
    grouped = _by_approval(outbox)
    smtp_records = read_jsonl(smtp_log)
    deploy_records = read_jsonl(deploy_log)
    checks: dict[str, bool] = {}
    details: dict[str, str] = {}

    # 1. Immutable approval payloads: hash recomputed from stored canonical JSON,
    #    and the database trigger is both present and enforced.
    bad_hashes = []
    for approval in approvals:
        canonical = str(approval.get("payload_json") or "")
        if _sha256(canonical) != str(approval.get("payload_sha256") or ""):
            bad_hashes.append(approval.get("id"))
    trigger_names = {str(row.get("name")) for row in state["triggers"]}
    trigger_present = "approval_payload_immutable" in trigger_names
    trigger_enforced = bool(approvals) and _trigger_enforced(
        db_path, str(approvals[0].get("id")))
    checks["approval_payload_hash_valid"] = not bad_hashes
    details["approval_payload_hash_valid"] = (
        f"{len(approvals)} payload(s) recomputed; mismatches={bad_hashes}"
    )
    checks["approval_immutability_enforced"] = trigger_present and trigger_enforced
    details["approval_immutability_enforced"] = (
        f"trigger_present={trigger_present} enforced_on_noop_update={trigger_enforced}"
    )

    # 2. Main email delivered exactly once through the SMTP sink, with the
    #    approved payload and no duplicate after a second execute call.
    main_email_outbox = [
        item for item in outbox
        if item.get("action_type") == "email.send"
        and EMAIL_SUBJECT in str(_payload(item).get("subject", ""))
    ]
    main_email_records = [
        record for record in smtp_records
        if EMAIL_SUBJECT in str(record.get("subject", ""))
    ]
    email_ok = False
    email_payload_ok = False
    if len(main_email_outbox) == 1 and len(main_email_records) == 1:
        item = main_email_outbox[0]
        record = main_email_records[0]
        payload = _payload(item)
        email_ok = bool(
            item.get("status") == "succeeded"
            and item.get("external_id")
            and item.get("external_id") == record.get("message_id")
            and record.get("outbox_id") == item.get("id")
        )
        recipients = payload.get("to") if isinstance(payload.get("to"), list) else [payload.get("to")]
        email_payload_ok = bool(
            _normalize(record.get("subject", "")) == _normalize(payload.get("subject", ""))
            and [str(x).strip().lower() for x in record.get("to", [])]
                == [str(x).strip().lower() for x in recipients]
            and _normalize(record.get("body", "")) == _normalize(payload.get("body", ""))
        )
    checks["main_email_delivered_once"] = email_ok
    details["main_email_delivered_once"] = (
        f"outbox={len(main_email_outbox)} sink={len(main_email_records)}"
    )
    checks["main_email_payload_matches"] = email_payload_ok
    details["main_email_payload_matches"] = (
        "subject, recipients and body compared against the approved payload"
    )

    # 3. Main deployment delivered to the HTTPS webhook sink exactly once and
    #    bound to the approval hash and outbox idempotency key.
    deploy_outbox = [
        item for item in outbox
        if item.get("action_type") == "website.deploy"
        and str(_payload(item).get("repository", "")) == DEPLOY_REPOSITORY
    ]
    deploy_sink_records = [
        record for record in deploy_records
        if isinstance(record.get("body"), dict)
        and str(record["body"].get("repository", "")) == DEPLOY_REPOSITORY
    ]
    deploy_ok = False
    deploy_payload_ok = False
    if len(deploy_outbox) == 1 and len(deploy_sink_records) == 1:
        item = deploy_outbox[0]
        record = deploy_sink_records[0]
        body = record["body"]
        payload = _payload(item)
        deploy_ok = bool(
            item.get("status") == "succeeded"
            and record.get("deployment_id")
            and item.get("external_id") == record.get("deployment_id")
            and body.get("outbox_id") == item.get("id")
            and body.get("approval_id") == item.get("approval_id")
        )
        deploy_payload_ok = bool(
            body.get("payload_sha256") == item.get("payload_sha256")
            and body.get("repository") == payload.get("repository")
            and body.get("ref") == payload.get("ref")
            and body.get("target") == payload.get("target")
            and record.get("idempotency_key") == item.get("id")
            and record.get("content_type", "").startswith("application/json")
        )
    checks["main_deploy_delivered_once"] = deploy_ok
    details["main_deploy_delivered_once"] = (
        f"outbox={len(deploy_outbox)} sink={len(deploy_sink_records)}"
    )
    checks["main_deploy_payload_matches"] = deploy_payload_ok
    details["main_deploy_payload_matches"] = (
        "repository, ref, target, payload SHA-256 and idempotency key compared"
    )

    # 4. Delivery can only happen after an explicit execute claim. Every sink
    #    record maps to a succeeded outbox item with exactly one execution-start
    #    event, and no succeeded outbox item is missing its sink record.
    delivered_ids = _sink_ids(smtp_records) | _sink_ids(deploy_records)
    succeeded_ids = {
        str(item.get("id")) for item in outbox
        if item.get("status") == "succeeded"
        and item.get("action_type") in ("email.send", "website.deploy")
    }
    start_counts = {
        str(item.get("id")): _event_count(events, "outbox_execution_started", str(item.get("id")))
        for item in outbox
    }
    checks["deliveries_only_after_execute"] = bool(
        delivered_ids == succeeded_ids
        and all(start_counts.get(outbox_id, 0) == 1 for outbox_id in delivered_ids)
        and all(
            item.get("status") == "succeeded"
            for item in outbox if str(item.get("id")) in delivered_ids
        )
    )
    details["deliveries_only_after_execute"] = (
        f"delivered={sorted(delivered_ids)} succeeded={sorted(succeeded_ids)}"
    )

    record_counts: dict[str, int] = {}
    for record in smtp_records + deploy_records:
        key = _record_outbox_id(record)
        record_counts[key] = record_counts.get(key, 0) + 1
    checks["duplicate_execute_no_second_delivery"] = bool(
        delivered_ids
        and all(record_counts.get(outbox_id) == 1 for outbox_id in delivered_ids)
        and all(start_counts.get(outbox_id) == 1 for outbox_id in delivered_ids)
    )
    details["duplicate_execute_no_second_delivery"] = (
        f"records_per_outbox={record_counts} starts={ {k: start_counts.get(k) for k in delivered_ids} }"
    )

    # 5. Reject creates no outbox row and produces no delivery.
    rejected = [
        approval for approval in approvals
        if approval.get("status") == "rejected"
        and REJECT_SUBJECT in str(_payload(approval).get("subject", ""))
    ]
    reject_leaks = [
        record for record in smtp_records
        if REJECT_SUBJECT in str(record.get("subject", ""))
    ]
    checks["rejected_no_outbox_no_delivery"] = bool(
        rejected
        and all(not grouped.get(str(approval.get("id"))) for approval in rejected)
        and not reject_leaks
        and any(event.get("event_type") == "approval_reject" for event in events)
    )
    details["rejected_no_outbox_no_delivery"] = (
        f"rejected={len(rejected)} outbox_rows="
        f"{sum(len(grouped.get(str(a.get('id')), [])) for a in rejected)} sink_records={len(reject_leaks)}"
    )

    # 6. Expense actions have no automatic adapter and stay awaiting a human.
    expense_items = [
        item for item in outbox
        if item.get("action_type") == "expense.purchase"
        and str(_payload(item).get("vendor", "")) == EXPENSE_VENDOR
    ]
    serialized_sinks = json.dumps(smtp_records + deploy_records, ensure_ascii=False)
    checks["expense_awaiting_executor"] = bool(
        expense_items
        and any(
            item.get("status") == "awaiting_executor"
            and int(item.get("attempts") or 0) >= 1
            and not item.get("external_id")
            for item in expense_items
        )
        and EXPENSE_VENDOR not in serialized_sinks
    )
    details["expense_awaiting_executor"] = (
        f"expense_outbox={[(i.get('id'), i.get('status')) for i in expense_items]}"
    )

    # 7. Exactly one outbox row per decided approval, and a complete audit trail.
    duplicate_approvals = [
        approval_id for approval_id, items in grouped.items() if len(items) > 1
    ]
    checks["unique_outbox_per_approval"] = not duplicate_approvals
    details["unique_outbox_per_approval"] = f"duplicates={duplicate_approvals}"
    event_types = {str(event.get("event_type")) for event in events}
    required_events = {
        "approval_requested", "approval_approve", "approval_reject",
        "outbox_execution_started", "outbox_reconciled",
    }
    checks["audit_trail_present"] = required_events.issubset(event_types)
    details["audit_trail_present"] = (
        f"missing={sorted(required_events - event_types)} total_events={len(events)}"
    )

    # 8. Sink authentication evidence: the SMTP sink saw the configured user and
    #    the deploy sink stored only a hash of the bearer header.
    smtp_auth_ok = bool(
        smtp_records and expected_smtp_user
        and all(record.get("authenticated_user") == expected_smtp_user for record in smtp_records)
    )
    deploy_auth_ok = bool(
        deploy_records
        and all(re.fullmatch(r"[0-9a-f]{64}", str(record.get("authorization_sha256", "")))
                for record in deploy_records)
        and (expected_auth_sha is None
             or all(record.get("authorization_sha256") == expected_auth_sha
                    for record in deploy_records))
    )
    checks["sink_authentication_evidence"] = smtp_auth_ok and deploy_auth_ok
    details["sink_authentication_evidence"] = (
        f"smtp_user_match={smtp_auth_ok} deploy_hash_match={deploy_auth_ok}"
    )

    # 9. Secrets never reach the database, audit trail or sink logs.
    secret_hits = scan_for_secrets(scan_files, secrets)
    checks["secrets_absent_from_artifacts"] = not secret_hits
    details["secrets_absent_from_artifacts"] = (
        "no configured secret value found" if not secret_hits else f"hits={secret_hits}"
    )

    # 10. Fresh-process restart probe independently re-read the same database.
    if probe_json:
        probe_path = Path(probe_json)
        probe = json.loads(probe_path.read_text(encoding="utf-8")) if probe_path.is_file() else {}
        probe_ok = bool(
            probe.get("all_persisted") is True
            and probe.get("checks")
            and all(bool(value) for value in probe.get("checks", {}).values())
        )
    else:
        probe_ok = False
    checks["fresh_process_probe_persisted"] = probe_ok
    details["fresh_process_probe_persisted"] = (
        f"probe={probe_json}" if probe_json else "probe JSON not supplied"
    )
    return checks, details


def verify_negative(db_path: str | Path, smtp_log, unknown_log, exhausted_log,
                    deploy_log, scan_files: list[Path],
                    secrets: list[tuple[str, str]]) -> tuple[dict, dict]:
    state = load_database(db_path)
    approvals = state["approvals"]
    outbox = state["outbox"]
    events = state["events"]
    grouped = _by_approval(outbox)
    unknown_records = read_jsonl(unknown_log)
    exhausted_records = read_jsonl(exhausted_log)
    deploy_records = read_jsonl(deploy_log)
    checks: dict[str, bool] = {}
    details: dict[str, str] = {}

    def item_for(needle: str, action_type: str | None = None) -> dict | None:
        matches = _find_subject(approvals, needle, action_type)
        if not matches:
            return None
        items = grouped.get(str(matches[0].get("id")), [])
        return items[0] if items else None

    # 1. Missing SMTP configuration fails safely and schedules backoff.
    missing = item_for(MISSING_SUBJECT, "email.send")
    checks["negative_missing_config_backoff"] = bool(
        missing
        and missing.get("status") == "failed"
        and int(missing.get("attempts") or 0) == 1
        and missing.get("next_retry_at")
        and "SMTP belum dikonfigurasi" in str(missing.get("last_error") or "")
        and _event_count(events, "outbox_retry_scheduled", str(missing.get("id"))) == 1
    )
    details["negative_missing_config_backoff"] = (
        f"status={missing.get('status')} attempts={missing.get('attempts')} "
        f"next_retry_at={missing.get('next_retry_at')}" if missing else "not found"
    )

    # 2. A plain-HTTP deployment webhook is rejected before any network call.
    http_deploy = None
    for approval in approvals:
        if approval.get("action_type") != "website.deploy":
            continue
        items = grouped.get(str(approval.get("id")), [])
        if items:
            http_deploy = items[0]
            break
    http_deploy_leaks = (
        {str(http_deploy.get("id"))} & _sink_ids(deploy_records) if http_deploy else set()
    )
    checks["negative_http_deploy_rejected"] = bool(
        http_deploy
        and http_deploy.get("status") == "failed"
        and "HTTPS" in str(http_deploy.get("last_error") or "")
        and not http_deploy_leaks
    )
    details["negative_http_deploy_rejected"] = (
        f"status={http_deploy.get('status')} error={http_deploy.get('last_error')}"
        if http_deploy else "not found"
    )

    # 3. An uncertain provider outcome is parked as unknown, cannot be resent,
    #    and is resolved by an explicit operator reconciliation without a send.
    unknown = item_for(UNKNOWN_SUBJECT, "email.send")
    unknown_matches = (
        [record for record in unknown_records
         if str(record.get("outbox_id")) == str(unknown.get("id"))]
        if unknown else []
    )
    checks["negative_unknown_requires_reconciliation"] = bool(
        unknown
        and unknown.get("status") == "succeeded"
        and unknown.get("resolved_by")
        and unknown.get("resolution_note")
        and unknown.get("external_id")
        and len(unknown_matches) == 1
        and unknown.get("external_id") == unknown_matches[0].get("message_id")
        and _event_count(events, "outbox_execution_started", str(unknown.get("id"))) == 1
        and any(
            event.get("event_type") == "outbox_reconciled"
            and str(event.get("entity_id")) == str(unknown.get("id"))
            and "menetapkan hasil" in str(event.get("detail", ""))
            for event in events
        )
    )
    details["negative_unknown_requires_reconciliation"] = (
        f"status={unknown.get('status')} resolved_by={unknown.get('resolved_by')} "
        f"sink_records={len(unknown_matches)}" if unknown else "not found"
    )

    # 4. Exhausted retries stop, block resends and require a manual requeue.
    exhausted = item_for(EXHAUSTED_SUBJECT, "email.send")
    exhausted_leaks = [
        record for record in exhausted_records
        if EXHAUSTED_SUBJECT in str(record.get("subject", ""))
    ]
    checks["negative_exhaustion_requires_requeue"] = bool(
        exhausted
        and exhausted.get("status") == "queued"
        and int(exhausted.get("attempts") or 0) == 0
        and not exhausted.get("last_error")
        and not exhausted_leaks
        and _event_count(events, "outbox_execution_started", str(exhausted.get("id"))) == 1
        and _event_count(events, "outbox_requeued", str(exhausted.get("id"))) == 1
        and any(
            event.get("event_type") == "outbox_reconciled"
            and str(event.get("entity_id")) == str(exhausted.get("id"))
            and "berstatus failed" in str(event.get("detail", ""))
            for event in events
        )
    )
    details["negative_exhaustion_requires_requeue"] = (
        f"status={exhausted.get('status')} attempts={exhausted.get('attempts')} "
        f"sink_records={len(exhausted_leaks)}" if exhausted else "not found"
    )

    # 5. Expense stays manual in the negative database too.
    expense_items = [
        item for item in outbox
        if item.get("action_type") == "expense.purchase"
        and str(_payload(item).get("vendor", "")) == EXPENSE_VENDOR
    ]
    checks["negative_expense_manual"] = bool(
        expense_items
        and all(item.get("status") == "awaiting_executor" for item in expense_items)
    )
    details["negative_expense_manual"] = (
        f"items={[(i.get('id'), i.get('status')) for i in expense_items]}"
    )

    # 6. Negative scenarios never leak into the real sink logs.
    main_smtp_records = read_jsonl(smtp_log)
    main_deploy_records = read_jsonl(deploy_log)
    negative_ids = {str(item.get("id")) for item in outbox}
    markers = (MISSING_SUBJECT, UNKNOWN_SUBJECT, EXHAUSTED_SUBJECT, REJECT_SUBJECT)
    checks["negative_deliveries_isolated"] = bool(
        not (negative_ids & (_sink_ids(main_smtp_records) | _sink_ids(main_deploy_records)))
        and not any(
            marker in str(record.get("subject", ""))
            for record in main_smtp_records
            for marker in markers
        )
        and not exhausted_leaks
    )
    details["negative_deliveries_isolated"] = (
        f"main_smtp_records={len(main_smtp_records)} "
        f"main_deploy_records={len(main_deploy_records)} "
        f"exhausted_sink_records={len(exhausted_records)}"
    )

    secret_hits = scan_for_secrets(scan_files, secrets)
    checks["negative_secrets_absent_from_artifacts"] = not secret_hits
    details["negative_secrets_absent_from_artifacts"] = (
        "no configured secret value found" if not secret_hits else f"hits={secret_hits}"
    )
    return checks, details


def scan_for_secrets(files: list[Path], secrets: list[tuple[str, str]]) -> list[str]:
    hits: list[str] = []
    for file in files:
        file = Path(file)
        if not file.is_file():
            continue
        try:
            if file.stat().st_size > 20 * 1024 * 1024:
                continue
            data = file.read_bytes()
        except OSError:
            continue
        for name, value in secrets:
            if value and value.encode("utf-8") in data:
                hits.append(f"{file.name}:{name}")
    return hits


def _collect_scan_files(explicit: list[str | Path], scan_root: str | Path | None) -> list[Path]:
    files = [Path(path) for path in explicit if path]
    if scan_root:
        root = Path(scan_root)
        if root.is_dir():
            for file in root.rglob("*"):
                if not file.is_file():
                    continue
                if "certs" in file.parts:
                    continue
                if file.suffix in (".key", ".csr", ".ext"):
                    continue
                files.append(file)
    seen = set()
    unique = []
    for file in files:
        key = str(file.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(file)
    return unique


def _secrets_from_env(names: list[str]) -> list[tuple[str, str]]:
    pairs = []
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            pairs.append((name, value))
    return pairs


def verify_all(db_path, negative_db=None, smtp_log=None, deploy_log=None,
               unknown_smtp_log=None, exhausted_smtp_log=None,
               probe_json=None, scan_root=None,
               secret_envs=None, json_out=None,
               deploy_token_env="DEPLOY_WEBHOOK_TOKEN",
               smtp_username_env="SMTP_USERNAME") -> dict:
    secret_envs = list(secret_envs or DEFAULT_SECRET_ENVS)
    secrets = _secrets_from_env(secret_envs)
    deploy_token = os.getenv(deploy_token_env, "").strip()
    expected_auth_sha = _sha256(f"Bearer {deploy_token}") if deploy_token else None
    expected_smtp_user = os.getenv(smtp_username_env, "").strip() or None

    explicit = [db_path, smtp_log, deploy_log, unknown_smtp_log, exhausted_smtp_log]
    scan_files = _collect_scan_files(explicit, scan_root)

    checks, details = verify_main(
        db_path, smtp_log, deploy_log, expected_auth_sha, expected_smtp_user,
        probe_json, scan_files, secrets,
    )
    if negative_db:
        neg_checks, neg_details = verify_negative(
            negative_db, smtp_log, unknown_smtp_log, exhausted_smtp_log, deploy_log,
            scan_files, secrets,
        )
        checks.update(neg_checks)
        details.update(neg_details)

    result = {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "details": details,
        "files": {
            "db": str(db_path),
            "negative_db": str(negative_db) if negative_db else None,
            "smtp_log": str(smtp_log) if smtp_log else None,
            "deploy_log": str(deploy_log) if deploy_log else None,
            "unknown_smtp_log": str(unknown_smtp_log) if unknown_smtp_log else None,
            "exhausted_smtp_log": str(exhausted_smtp_log) if exhausted_smtp_log else None,
        },
    }
    if json_out:
        Path(json_out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Independently verify Milestone 2 evidence.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--negative-db")
    parser.add_argument("--smtp-log")
    parser.add_argument("--deploy-log")
    parser.add_argument("--unknown-smtp-log")
    parser.add_argument("--exhausted-smtp-log")
    parser.add_argument("--probe-json")
    parser.add_argument("--scan-root")
    parser.add_argument("--secret-env", action="append", dest="secret_envs")
    parser.add_argument("--deploy-token-env", default="DEPLOY_WEBHOOK_TOKEN")
    parser.add_argument("--smtp-username-env", default="SMTP_USERNAME")
    parser.add_argument("--json-out")
    args = parser.parse_args(argv)

    result = verify_all(
        args.db, args.negative_db, args.smtp_log, args.deploy_log,
        args.unknown_smtp_log, args.exhausted_smtp_log, args.probe_json,
        args.scan_root, args.secret_envs, args.json_out,
        args.deploy_token_env, args.smtp_username_env,
    )
    print("Milestone 2 independent verification")
    print(f"Database: {args.db}")
    if args.negative_db:
        print(f"Negative database: {args.negative_db}")
    print("-" * 72)
    for name, passed in result["checks"].items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        detail = result["details"].get(name)
        if detail:
            print(f"         {detail}")
    print("-" * 72)
    print("MILESTONE 2 VERIFIER: " + ("PASS" if result["passed"] else "FAIL"))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
