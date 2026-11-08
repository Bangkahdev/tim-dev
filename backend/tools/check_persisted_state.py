#!/usr/bin/env python3
"""Fresh-process persistence probe for Milestone 1 evidence.

Run this in a NEW Python process after a cycle (simulating a backend/store
restart) to prove that task evidence, the final report Paper, its PrintJob, the
delivery event and the owner decision survive across process boundaries.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.company_operations import CompanyOperations  # noqa: E402
from core.office_store import OfficeStore  # noqa: E402


def check_persisted_state(db_path, project_key: str) -> dict:
    ops = CompanyOperations(OfficeStore(Path(db_path)))
    try:
        tasks = [t for t in ops.tasks() if str(t.get("project_key") or "") == project_key]
        title = f"Final Report: {project_key}"
        with ops._db() as db:
            row = db.execute(
                "SELECT * FROM paper_records WHERE title=? ORDER BY created_at DESC LIMIT 1",
                (title,),
            ).fetchone()
            paper = dict(row) if row else None
            job = None
            delivered = False
            decision = False
            if paper:
                job_row = db.execute(
                    "SELECT * FROM print_jobs WHERE paper_id=? ORDER BY created_at DESC LIMIT 1",
                    (paper["id"],),
                ).fetchone()
                job = dict(job_row) if job_row else None
                delivered = db.execute(
                    "SELECT 1 FROM events WHERE event_type='paper_delivered' AND entity_id=? LIMIT 1",
                    (paper["id"],),
                ).fetchone() is not None
                decision = db.execute(
                    "SELECT 1 FROM events WHERE event_type='owner_decision' AND entity_id=? LIMIT 1",
                    (paper["id"],),
                ).fetchone() is not None

        checks = {
            "tasks_present": len(tasks) >= 1,
            "tasks_completed_with_evidence": bool(tasks)
            and all(t.get("status") == "completed" and t.get("evidence") for t in tasks),
            "final_report_paper": bool(paper),
            "print_job_completed": bool(job) and job.get("status") == "completed",
            "paper_delivered_event": delivered,
            "owner_decision_audited": decision,
        }
        checks["all_persisted"] = all(checks.values())
        return {
            "project_key": project_key,
            "db": str(db_path),
            "tasks": len(tasks),
            "evidence_rows": sum(len(t.get("evidence") or []) for t in tasks),
            "paper_id": (paper or {}).get("id"),
            "print_job_id": (job or {}).get("id"),
            "checks": checks,
        }
    finally:
        ops.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify Milestone 1 state from a fresh process.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args(argv)

    result = check_persisted_state(args.db, args.project_key)
    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["checks"]["all_persisted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
