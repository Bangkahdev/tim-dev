"""Controlled real-agent Milestone 1 runner.

This path is for operator/external-sandbox use with real CrewAI + cloud models.
It creates task/evidence records through CompanyOperations, runs the real agent
against the exact run project directory, verifies with the independent Owner
verifier, and records a report Paper/PrintJob. It never claims NFR-SEC-09/10
without external sandbox evidence.

For automated tests in this repo, use a mocked LLM/factory; do not run real
cloud agents in CI-like environments without credentials and sandbox evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.business_cycle import CrewAIAgentWorker, DeterministicWorker  # noqa: E402
from core.company_operations import CompanyOperations  # noqa: E402
from core.office_store import BASE_DIR, OfficeStore  # noqa: E402
from core.sandbox_exec import ensure_sandbox_canaries, sandbox_required  # noqa: E402
from tools.verify_milestone1 import verify as owner_verify  # noqa: E402


WORDCOUNT_COMMAND = (
    "Build a small Python CLI utility `wordcount` that reports lines, words, "
    "and characters for a file or stdin, with tests and a README"
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run one controlled real-agent Milestone 1 attempt.")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--external-sandbox", required=True, help="evidence note: image/cmd + isolation proof")
    parser.add_argument("--allow-unverified-real", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not sandbox_required() and not args.allow_unverified_real:
        print("ERROR: BANGKAH_SANDBOX_REQUIRED=1 is required for --worker/real agent runs.", file=sys.stderr)
        return 2

    project_dir = Path(args.project_dir).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db).resolve()
    ops = CompanyOperations(OfficeStore(db_path))
    try:
        canary = ensure_sandbox_canaries(
            project_dir,
            audit=lambda t, a, d, e: ops.store.add_event(t, a, d, e),
        )
        (project_dir / "artifacts").mkdir(exist_ok=True)
        (project_dir / "artifacts" / "sandbox-canary.json").write_text(json.dumps(canary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        if sandbox_required() and not canary.get("ok"):
            print(json.dumps({"ok": False, "stage": "sandbox_canary", "canary": canary}, indent=2), file=sys.stderr)
            return 2

        tasks = []
        for emp, label in [("coo", "Requirements and plan"), ("architect", "Architecture and file layout"), ("backend", "Implementation"), ("qa", "Automated tests"), ("lead", "QA review and final report")]:
            task = ops.create_task(title=f"{label}: {args.project_key}", description=WORDCOUNT_COMMAND, assignee_id=emp, priority="high", project_key=args.project_key, actor="lead")
            ops.transition_task(task["id"], "in_progress", actor=emp)
            tasks.append(task)

        worker = CrewAIAgentWorker() if not args.allow_unverified_real else DeterministicWorker()
        spec = (BASE_DIR.parent / "docs" / "specs" / "wordcount-behavior.md").resolve()
        produced = worker.produce(project_dir, WORDCOUNT_COMMAND, spec)

        v = owner_verify(db_path, args.project_key, project_dir)
        (project_dir / "artifacts" / "owner-verifier.json").write_text(json.dumps(v, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        passed = bool(v.get("checks", {}).get("OVERALL_VERIFIABLE"))
        for task in tasks:
            if passed:
                ops.transition_task(task["id"], "completed", evidence=[{"type": "real_agent" if worker.mode == "crewai_real" else "integration", "reference": str(project_dir), "note": json.dumps({"produced": produced, "external_sandbox": args.external_sandbox}, default=str)[:900]}], actor=task["assignee_id"])
            else:
                try:
                    ops.transition_task(task["id"], "blocked", note="owner verifier failed", actor=task["assignee_id"])
                except Exception:
                    pass
        paper = ops.create_paper(f"Final Report: {args.project_key}", f"# Real Agent Report\n\nProject: {project_dir}\nExternal sandbox: {args.external_sandbox}\nVerifier overall: {passed}\n", paper_type="report", origin="engineering", priority="high", related_task_id=tasks[-1]["id"])
        job = ops.create_print_job(paper["id"])
        ops.store.add_event("paper_delivered", "front_office", f"Report {paper['id']} delivered to the owner tray.", paper["id"])
        print(json.dumps({"ok": passed, "paper_id": paper["id"], "print_job_id": job["id"], "canary": canary, "verifier": v, "project_dir": str(project_dir)}, indent=2, ensure_ascii=False, default=str))
        return 0 if passed else 1
    finally:
        ops.close()


if __name__ == "__main__":
    raise SystemExit(main())
