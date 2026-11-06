"""Milestone 1 acceptance runner — one real business cycle, three times.

Usage:
    python tools/run_milestone1.py [--cycles 3] [--db PATH] [--workspace DIR]

The runner uses the persisted company backend and the sandboxed worker from
``core.business_cycle``. It exits non-zero if any acceptance check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.business_cycle import BusinessCycle, check_rbac_and_approval  # noqa: E402
from core.company_operations import OPS, CompanyOperations  # noqa: E402
from core.office_store import BASE_DIR, OfficeStore  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the Milestone 1 business cycle.")
    parser.add_argument("--cycles", type=int, default=3, help="number of consecutive cycles (default: 3)")
    parser.add_argument("--db", help="SQLite database path (default: core.office_store.DB_PATH)")
    parser.add_argument("--workspace", help="workspace root for pilot projects")
    args = parser.parse_args(argv)

    if args.db:
        ops = CompanyOperations(OfficeStore(Path(args.db)))
    else:
        ops = OPS
    workspace = Path(args.workspace) if args.workspace else (BASE_DIR / "workspace" / "projects")
    workspace.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    failures = []
    print(f"Milestone 1 — {args.cycles} business cycle(s)")
    print(f"Database : {ops.db_path}")
    print(f"Workspace: {workspace}")
    print("-" * 60)

    for index in range(1, args.cycles + 1):
        project_key = f"milestone1-{stamp}-{index}"
        command = (
            "Build a small Python CLI utility that counts lines, words and "
            "characters, with tests and a README"
        )
        print(f"[cycle {index}/{args.cycles}] {project_key}")
        try:
            result = BusinessCycle(ops, workspace_root=workspace).run(command, project_key)
        except Exception as error:
            failures.append(f"cycle {index}: {type(error).__name__}: {error}")
            print(f"  FAILED: {error}")
            continue
        print(f"  workspace : {result['project_dir']}")
        print(f"  tests     : exit {result['test_exit_code']} ({result['test_output_artifact']})")
        print(f"  paper     : {result['paper_id']}  decision={result['owner_decision']}")
        print(f"  print job : {result['print_job_id']}  pdf={result['pdf_path']}")
        for name, passed in result["checks"].items():
            print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
            if not passed:
                failures.append(f"cycle {index}: {name}")

    print("-" * 60)
    print("Static acceptance checks")
    static = check_rbac_and_approval(ops)
    for name, passed in static.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        if not passed:
            failures.append(name)

    print("-" * 60)
    if failures:
        print("MILESTONE 1: FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("MILESTONE 1: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
