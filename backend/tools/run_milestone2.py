"""Milestone 2 acceptance runner — external delivery & reconciliation.

Usage:
    python tools/run_milestone2.py [--db PATH]

Providers are simulated in-process, so no email or deployment is ever sent.
The runner defaults to an isolated temporary database.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.action_adapters as adapters  # noqa: E402
from core.company_operations import CompanyOperations  # noqa: E402
from core.office_store import OfficeStore  # noqa: E402

EMAIL_PAYLOAD = {"to": "owner@example.test", "subject": "Milestone 2", "body": "acceptance"}


def approved_outbox(ops, action_type, payload):
    approval = ops.create_approval(action_type, "Milestone 2 acceptance", payload)
    ops.decide_approval(approval["id"], "approve", "owner", "acceptance run")
    return next(item["id"] for item in ops.list_outbox(200) if item["approval_id"] == approval["id"])


def outbox_row(ops, outbox_id):
    return next(item for item in ops.list_outbox(200) if item["id"] == outbox_id)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the Milestone 2 delivery checks.")
    parser.add_argument("--db", help="SQLite database path (default: temporary)")
    args = parser.parse_args(argv)

    root = Path(args.db).resolve().parent if args.db else Path(tempfile.mkdtemp())
    ops = CompanyOperations(OfficeStore(Path(args.db) if args.db else root / "milestone2.db"))

    original_ops = adapters.OPS
    original_send = adapters._send_email
    saved_env = {key: os.environ.get(key) for key in
                 ("OUTBOX_MAX_ATTEMPTS", "OUTBOX_BACKOFF_SECONDS", "OUTBOX_BACKOFF_MAX_SECONDS")}
    adapters.OPS = ops
    checks = {}

    try:
        # 1. Transient failure schedules exponential backoff.
        os.environ.update({"OUTBOX_MAX_ATTEMPTS": "5", "OUTBOX_BACKOFF_SECONDS": "3600"})
        first = approved_outbox(ops, "email.send", EMAIL_PAYLOAD)
        calls = {"n": 0}

        def flaky(outbox_id, payload):
            calls["n"] += 1
            if calls["n"] == 1:
                raise adapters.AdapterError("simulated transient provider error")
            return {"external_id": "sim-delivered", "provider": "simulated"}

        adapters._send_email = flaky
        try:
            adapters.execute_outbox(first)
        except adapters.AdapterError:
            pass
        row = outbox_row(ops, first)
        checks["failure_schedules_backoff"] = row["status"] == "failed" and bool(row["next_retry_at"])

        # Early retry is refused before the backoff window elapses.
        blocked = False
        try:
            adapters.execute_outbox(first)
        except adapters.AdapterError:
            blocked = True
        checks["early_retry_blocked"] = blocked

        # 2. Due retry executes and succeeds.
        with ops._db() as db:
            db.execute("UPDATE outbox_records SET next_retry_at='2000-01-01T00:00:00+00:00' WHERE id=?",
                       (first,))
        checks["due_item_listed"] = first in [x["id"] for x in ops.list_due_outbox()]
        result = adapters.execute_outbox(first)
        checks["due_retry_succeeds"] = bool(result.get("success")) and outbox_row(ops, first)["status"] == "succeeded"

        # 3. Uncertain delivery is parked as unknown and cannot be resent.
        second = approved_outbox(ops, "email.send", EMAIL_PAYLOAD)

        def uncertain(outbox_id, payload):
            raise adapters.DeliveryUncertain("connection dropped after DATA")

        adapters._send_email = uncertain
        try:
            adapters.execute_outbox(second)
        except adapters.AdapterError:
            pass
        checks["uncertain_marked_unknown"] = outbox_row(ops, second)["status"] == "unknown"
        blocked = False
        try:
            adapters.execute_outbox(second)
        except adapters.AdapterError:
            blocked = True
        checks["unknown_blocks_duplicate_send"] = blocked

        # 4. Operator reconciliation resolves it without re-sending.
        reconciled = ops.reconcile_outbox(second, "succeeded", "Verified in provider dashboard.",
                                          external_id="sim-reconciled", actor="operator")
        checks["reconciliation_resolves"] = (
            reconciled["status"] == "succeeded"
            and reconciled["resolved_by"] == "operator"
            and bool(reconciled["resolution_note"])
        )
        final = False
        try:
            ops.reconcile_outbox(second, "failed", "late change", actor="operator")
        except ValueError:
            final = True
        checks["reconciled_result_is_final"] = final

        # 5. Exhausted retries stop and require manual requeue.
        os.environ["OUTBOX_MAX_ATTEMPTS"] = "1"
        adapters._send_email = lambda outbox_id, payload: (_ for _ in ()).throw(
            adapters.AdapterError("simulated permanent failure"))
        third = approved_outbox(ops, "email.send", EMAIL_PAYLOAD)
        try:
            adapters.execute_outbox(third)
        except adapters.AdapterError:
            pass
        row = outbox_row(ops, third)
        checks["exhausted_has_no_retry"] = row["attempts"] >= 1 and row["next_retry_at"] is None
        blocked = False
        try:
            adapters.execute_outbox(third)
        except adapters.AdapterError:
            blocked = True
        checks["exhausted_blocks_resend"] = blocked
        requeued = ops.requeue_outbox(third, actor="operator")
        checks["requeue_resets_attempts"] = requeued["status"] == "queued" and requeued["attempts"] == 0

        # 6. Audit trail records the reconciliation and the execution start.
        with ops._db() as db:
            kinds = {row["event_type"] for row in db.execute("SELECT event_type FROM events")}
        checks["audit_trail_present"] = {
            "outbox_execution_started", "outbox_reconciled", "outbox_requeued"
        }.issubset(kinds)
    finally:
        adapters.OPS = original_ops
        adapters._send_email = original_send
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print(f"Milestone 2 — external delivery & reconciliation")
    print(f"Database: {ops.db_path}")
    print("-" * 60)
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print("-" * 60)
    if all(checks.values()):
        print("MILESTONE 2: PASS")
        return 0
    print("MILESTONE 2: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
