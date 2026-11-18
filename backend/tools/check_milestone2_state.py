#!/usr/bin/env python3
"""Fresh-process persistence probe for Milestone 2.

Run this in a NEW Python process after the acceptance cycle, or after a real
backend restart, to prove that approvals, outbox state, external ids, audit
events and reconciliation results survive across process boundaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.company_operations import CompanyOperations  # noqa: E402
from core.office_store import OfficeStore  # noqa: E402


def _payload(approval: dict) -> dict:
    if isinstance(approval.get("payload"), dict):
        return approval["payload"]
    try:
        value = json.loads(approval.get("payload_json") or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _canonical_payload(approval: dict) -> str:
    stored = approval.get("payload_json")
    if stored is not None:
        return str(stored)
    return json.dumps(_payload(approval), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _outbox_for(outbox: list[dict], approval_id: str) -> list[dict]:
    return [item for item in outbox if item.get("approval_id") == approval_id]


def check_main(db_path: str | Path) -> dict:
    ops = CompanyOperations(OfficeStore(Path(db_path)))
    try:
        approvals = ops.list_approvals(limit=200, include_payload=True)
        outbox = ops.list_outbox(limit=200)
        events = ops.audit(0, 500)
    finally:
        ops.close()

    by_approval = {}
    for item in outbox:
        by_approval.setdefault(str(item.get("approval_id")), []).append(item)

    email_approved = [
        a for a in approvals
        if a.get("action_type") == "email.send" and a.get("status") == "approved"
    ]
    deploy_approved = [
        a for a in approvals
        if a.get("action_type") == "website.deploy" and a.get("status") == "approved"
    ]
    rejected = [a for a in approvals if a.get("status") == "rejected"]
    expense_approved = [
        a for a in approvals
        if a.get("action_type") == "expense.purchase" and a.get("status") == "approved"
    ]

    email_ok = any(
        len(_outbox_for(outbox, a["id"])) == 1
        and _outbox_for(outbox, a["id"])[0].get("status") == "succeeded"
        and bool(_outbox_for(outbox, a["id"])[0].get("external_id"))
        for a in email_approved
    )
    deploy_ok = any(
        len(_outbox_for(outbox, a["id"])) == 1
        and _outbox_for(outbox, a["id"])[0].get("status") == "succeeded"
        and bool(_outbox_for(outbox, a["id"])[0].get("external_id"))
        for a in deploy_approved
    )
    rejected_ok = bool(rejected) and all(
        not _outbox_for(outbox, a["id"]) for a in rejected
    )
    expense_ok = any(
        len(_outbox_for(outbox, a["id"])) == 1
        and _outbox_for(outbox, a["id"])[0].get("status") == "awaiting_executor"
        for a in expense_approved
    )

    hashes_ok = True
    for approval in approvals:
        payload_json = _canonical_payload(approval)
        expected = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        if expected != str(approval.get("payload_sha256") or ""):
            hashes_ok = False
            break

    event_types = {str(e.get("event_type") or "") for e in events}
    audit_ok = {
        "approval_requested",
        "approval_approve",
        "approval_reject",
        "outbox_execution_started",
        "outbox_reconciled",
    }.issubset(event_types)

    counts = {}
    for item in outbox:
        key = str(item.get("approval_id"))
        counts[key] = counts.get(key, 0) + 1
    unique_ok = all(value <= 1 for value in counts.values())

    checks = {
        "email_approved_succeeded": email_ok,
        "deploy_approved_succeeded": deploy_ok,
        "rejected_without_outbox": rejected_ok,
        "expense_awaiting_executor": expense_ok,
        "payload_hashes_valid": hashes_ok,
        "audit_events_present": audit_ok,
        "unique_outbox_per_approval": unique_ok,
    }
    return {
        "db": str(db_path),
        "approvals": len(approvals),
        "outbox": len(outbox),
        "events": len(events),
        "event_types": sorted(event_types),
        "checks": checks,
        "all_persisted": all(checks.values()),
    }


def check_negative(db_path: str | Path) -> dict:
    ops = CompanyOperations(OfficeStore(Path(db_path)))
    try:
        approvals = ops.list_approvals(limit=200, include_payload=True)
        outbox = ops.list_outbox(limit=200)
        events = ops.audit(0, 500)
    finally:
        ops.close()

    by_id = {a["id"]: a for a in approvals}
    items = []
    for item in outbox:
        approval = by_id.get(item.get("approval_id"), {})
        payload = _payload(approval)
        items.append({
            "action_type": item.get("action_type"),
            "status": item.get("status"),
            "attempts": int(item.get("attempts") or 0),
            "next_retry_at": item.get("next_retry_at"),
            "last_error": item.get("last_error"),
            "external_id": item.get("external_id"),
            "resolved_by": item.get("resolved_by"),
            "resolution_note": item.get("resolution_note"),
            "subject": str(payload.get("subject") or ""),
            "vendor": str(payload.get("vendor") or ""),
        })

    def one(predicate):
        return next((item for item in items if predicate(item)), None)

    missing = one(lambda x: x["action_type"] == "email.send"
                  and x["subject"].startswith("Missing config"))
    http_deploy = one(lambda x: x["action_type"] == "website.deploy")
    unknown = one(lambda x: x["action_type"] == "email.send"
                  and x["subject"].startswith("Unknown"))
    exhausted = one(lambda x: x["action_type"] == "email.send"
                    and x["subject"].startswith("Exhausted"))
    expense = one(lambda x: x["action_type"] == "expense.purchase")

    event_types = {str(e.get("event_type") or "") for e in events}
    checks = {
        "negative_failed_backoff": bool(
            missing
            and missing["status"] == "failed"
            and missing["attempts"] == 1
            and missing["next_retry_at"]
            and "SMTP belum dikonfigurasi" in str(missing["last_error"] or "")
        ),
        "negative_http_deploy_rejected": bool(
            http_deploy
            and http_deploy["status"] == "failed"
            and "HTTPS" in str(http_deploy["last_error"] or "")
        ),
        "negative_unknown_reconciled": bool(
            unknown
            and unknown["status"] == "succeeded"
            and unknown["resolved_by"]
            and unknown["resolution_note"]
            and unknown["external_id"]
        ),
        "negative_exhausted_requeued": bool(
            exhausted
            and exhausted["status"] == "queued"
            and exhausted["attempts"] == 0
            and not exhausted["last_error"]
        ),
        "negative_expense_manual": bool(
            expense and expense["status"] == "awaiting_executor"
        ),
        "negative_audit_events": {
            "outbox_retry_scheduled", "outbox_reconciled", "outbox_requeued",
        }.issubset(event_types),
    }
    return {
        "db": str(db_path),
        "approvals": len(approvals),
        "outbox": len(outbox),
        "event_types": sorted(event_types),
        "checks": checks,
        "all_persisted": all(checks.values()),
    }


def check_persisted_state(db_path: str | Path, negative_db: str | Path | None = None) -> dict:
    result = {"main": check_main(db_path)}
    if negative_db:
        result["negative"] = check_negative(negative_db)
        result["checks"] = {
            "main_all_persisted": result["main"]["all_persisted"],
            "negative_all_persisted": result["negative"]["all_persisted"],
        }
        result["all_persisted"] = all(result["checks"].values())
    else:
        result["checks"] = dict(result["main"]["checks"])
        result["all_persisted"] = result["main"]["all_persisted"]
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify Milestone 2 state from a fresh process.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--negative-db")
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args(argv)

    result = check_persisted_state(args.db, args.negative_db)
    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["all_persisted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
