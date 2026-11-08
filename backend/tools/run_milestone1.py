"""Milestone 1 acceptance runner — wordcount pilot, 3 CONSECUTIVE passes.

Honest gates:
- Pilot: wordcount CLI (machine-checkable). Each run uses a CLEAN workspace dir and
  (with --isolated-db) a fresh DB. Logs kept for every attempt including failures.
- Any failure resets the consecutive counter to 0 (record root cause, fix, restart).
- Sandbox FS/network isolation (NFR-SEC-09/10) is NOT met by in-process guards; the
  runner reports it as FAIL/WARN honestly unless run in an external disposable
  VM/container (record that). Do not claim it passed without evidence.
- Independent Owner verifier (tools/verify_milestone1.py) runs hidden tests the
  agents never see and inspects DB/artifacts. Agents do not judge themselves.
- One manual Godot check per run remains: character status, tray, paper match
  backend records (reported as MANUAL).

Usage:
    python tools/run_milestone1.py [--cycles 3] [--db PATH] [--workspace DIR]
                                    [--isolated-db] [--external-sandbox NOTE]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.business_cycle import BusinessCycle, CrewAIAgentWorker, DeterministicWorker, check_rbac_and_approval  # noqa: E402
from core.company_operations import CompanyOperations  # noqa: E402
from core.office_store import BASE_DIR, OfficeStore  # noqa: E402
from tools.verify_milestone1 import verify as owner_verify  # noqa: E402


SANDBOX_CHECK_MARKER = "fs_network_isolation_NFR_SEC_09_10"
MANUAL_CHECK = "manual.godot_status_tray_paper_match_backend"


def _hard_failures(checks: dict, failures: list[str]) -> list[str]:
    """Return checks that must fail the attempt.

    Sandbox isolation is an operator-evidence item: the in-process cycle and the
    independent verifier cannot inspect the host wrapper. The runner records it
    from ``--external-sandbox`` plus the mandatory preflight canaries, so those
    keys never hard-fail by themselves. A missing external note already appends
    an explicit failure string. The Godot check is manual by design.
    """
    hard = [
        key
        for key, value in checks.items()
        if value is False
        and key != MANUAL_CHECK
        and SANDBOX_CHECK_MARKER not in key
    ]
    hard.extend(failures)
    return hard


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run Milestone 1 (wordcount) with consecutive gating.")
    parser.add_argument("--cycles", type=int, default=3, help="consecutive passes required (default: 3)")
    parser.add_argument("--db", help="SQLite database path (ignored with --isolated-db per run)")
    parser.add_argument("--workspace", help="workspace root for pilot projects (each run gets a fresh subdir)")
    parser.add_argument("--isolated-db", action="store_true", help="fresh DB per run (recommended for clean data)")
    parser.add_argument("--external-sandbox", default="", help="note/evidence that pilot ran in disposable VM/container providing FS+network isolation")
    parser.add_argument("--worker", choices=["deterministic", "real"], default="deterministic", help="deterministic=backend integration fixture (NOT real Milestone 1). real=CrewAI/cloud AgentWorker (requires deps+model+external sandbox).")
    parser.add_argument("--allow-unverified-real", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--max-attempts", type=int, default=20, help="safety cap on total attempts")
    args = parser.parse_args(argv)

    if args.worker == "real" and not args.allow_unverified_real:
        from core.sandbox_exec import sandbox_required
        if not sandbox_required():
            print("ERROR: --worker real requires BANGKAH_SANDBOX_REQUIRED=1 (and a validated external sandbox wrapper).", file=sys.stderr)
            return 2
        if not args.external_sandbox.strip():
            print("ERROR: --worker real requires --external-sandbox evidence (image/wrapper + isolation proof).", file=sys.stderr)
            return 2

    workspace = Path(args.workspace) if args.workspace else (BASE_DIR / "workspace" / "projects")
    workspace.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = workspace / f"milestone1-logs-{stamp}"
    log_dir.mkdir(parents=True, exist_ok=True)

    sandbox_preflight = None
    if args.worker == "real" and not args.allow_unverified_real:
        from core.sandbox_exec import ensure_sandbox_canaries
        preflight_dir = log_dir / "_sandbox_preflight"
        preflight_dir.mkdir(parents=True, exist_ok=True)
        try:
            sandbox_preflight = ensure_sandbox_canaries(preflight_dir, force=True)
        except Exception as error:
            print(f"ERROR: sandbox preflight failed: {type(error).__name__}: {error}", file=sys.stderr)
            return 2
        if not sandbox_preflight.get("ok"):
            print(f"ERROR: sandbox canaries did not prove FS+network isolation: {sandbox_preflight}", file=sys.stderr)
            return 2
        print(f"Sandbox preflight: FS isolated={sandbox_preflight.get('fs_isolated')} network isolated={sandbox_preflight.get('network_isolated')}")

    required = max(1, args.cycles)
    consecutive = 0
    attempt = 0
    all_attempts = []
    worker_mode = "deterministic_integration" if args.worker == "deterministic" else "crewai_real"
    print(f"Milestone 1 (wordcount) — require {required} CONSECUTIVE passes")
    print(f"Worker        : {worker_mode}{'  [BACKEND INTEGRATION FIXTURE, NOT REAL MILESTONE 1]' if args.worker == 'deterministic' else ''}")
    print(f"Workspace root: {workspace}")
    print(f"Logs          : {log_dir}")
    print(f"External sandbox note: {args.external_sandbox or '(none — FS/network isolation NOT evidenced)'}")
    print("-" * 72)

    while consecutive < required and attempt < args.max_attempts:
        attempt += 1
        run_n = consecutive + 1
        project_key = f"milestone1-wordcount-{stamp}-a{attempt}-r{run_n}"
        run_ws = workspace / project_key  # clean dir per run (BusinessCycle creates it)
        db_path = (log_dir / f"{project_key}.db") if (args.isolated_db or not args.db) else Path(args.db)
        ops = CompanyOperations(OfficeStore(Path(db_path)))
        command = (
            "Build a small Python CLI utility `wordcount` that reports lines, words, "
            "and characters for a file or stdin, with tests and a README"
        )
        print(f"[attempt {attempt}] target consecutive {run_n}/{required} key={project_key}")
        attempt_log = {"attempt": attempt, "consecutive_target": run_n, "project_key": project_key,
                       "worker": worker_mode, "db": str(db_path), "workspace": str(run_ws), "checks": {}, "failures": []}
        try:
            worker = DeterministicWorker() if args.worker == "deterministic" else CrewAIAgentWorker()
            result = BusinessCycle(ops, workspace_root=workspace, worker=worker).run(command, project_key)
            attempt_log["result"] = {k: v for k, v in result.items() if k != "checks"}
            attempt_log["checks"].update(result.get("checks", {}))
            if args.worker == "deterministic":
                attempt_log["checks"]["milestone1.real_agent_worker"] = False
                attempt_log["failures"].append("deterministic worker is a backend integration fixture, not a real Milestone 1 agent run")
            else:
                attempt_log["checks"]["milestone1.real_agent_worker"] = True

            # Owner independent verifier (hidden tests, DB/artifacts). Agents never judge themselves.
            v = owner_verify(db_path, project_key, result["project_dir"])
            attempt_log["independent_verifier"] = v
            for k, val in v["checks"].items():
                attempt_log["checks"][f"verify.{k}"] = val

            # Fresh-process restart probe: after Paper delivery, reopen the run
            # DB in a NEW interpreter. This is stronger than the in-process
            # store reopen inside BusinessCycle and directly matches the
            # playbook's "restart after Paper" requirement.
            probe_path = Path(__file__).resolve().parent / "check_persisted_state.py"
            probe = subprocess.run(
                [sys.executable, str(probe_path), "--db", str(db_path),
                 "--project-key", project_key],
                capture_output=True, text=True, timeout=60,
            )
            try:
                probe_json = json.loads(probe.stdout)
            except Exception:
                probe_json = {
                    "checks": {"all_persisted": False},
                    "error": (probe.stderr or probe.stdout or "empty probe output")[-1500:],
                }
            attempt_log["restart_process_probe"] = probe_json
            attempt_log["checks"]["restart.fresh_process_persistence"] = bool(
                probe_json.get("checks", {}).get("all_persisted")
            )

            # honest sandbox status
            if args.external_sandbox:
                attempt_log["checks"]["sandbox.fs_network_isolation_NFR_SEC_09_10"] = True
                attempt_log["sandbox_evidence"] = args.external_sandbox
            else:
                attempt_log["checks"]["sandbox.fs_network_isolation_NFR_SEC_09_10"] = False
                attempt_log["failures"].append("sandbox FS/network isolation (NFR-SEC-09/10) NOT evidenced; run in disposable VM/container or implement isolation")

            attempt_log["checks"]["manual.godot_status_tray_paper_match_backend"] = "MANUAL_REQUIRED"
        except Exception as error:
            attempt_log["failures"].append(f"exception: {type(error).__name__}: {error}")
            attempt_log["traceback"] = traceback.format_exc()
            print(f"  FAILED: {error}")
        finally:
            try:
                ops.close()
            except Exception:
                pass

        hard_fail = _hard_failures(attempt_log["checks"], attempt_log["failures"])
        attempt_log["hard_failures"] = hard_fail
        passed = len(hard_fail) == 0 and attempt_log["checks"].get("verify.OVERALL_VERIFIABLE") is True
        real_pass = (
            passed
            and args.worker == "real"
            and bool(args.external_sandbox)
            and bool((sandbox_preflight or {}).get("ok"))
        )

        attempt_log["passed_verifiable"] = passed
        attempt_log["passed_real_milestone1"] = real_pass
        (log_dir / f"{project_key}.json").write_text(json.dumps(attempt_log, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        for name, val in sorted(attempt_log["checks"].items()):
            tag = "PASS" if val is True else ("MANUAL" if val == "MANUAL_REQUIRED" else "FAIL")
            print(f"  [{tag}] {name}")
        if args.worker == "deterministic":
            print("  [NOTE] deterministic worker used — backend integration fixture only; does NOT satisfy real Milestone 1.")
        if passed and not args.external_sandbox:
            print("  [NOTE] verifiable checks passed but sandbox FS/network isolation NOT evidenced — do not claim SRS sandbox met.")
        if passed and args.external_sandbox:
            print(f"  [NOTE] external sandbox recorded: {args.external_sandbox}")

        all_attempts.append(attempt_log)
        if passed:
            consecutive += 1
            print(f"  => consecutive {consecutive}/{required}")
        else:
            print(f"  => FAILURE resets consecutive count (was {consecutive}); fix root cause, record change, restart from 1.")
            consecutive = 0
        print("-" * 72)

    print("Static acceptance checks (RBAC/approval boundary)")
    static_ops = CompanyOperations(OfficeStore(Path(args.db) if args.db and not args.isolated_db else (log_dir / "static.db")))
    static = check_rbac_and_approval(static_ops)
    static_ok = all(static.values())
    for name, passed in static.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    try:
        static_ops.close()
    except Exception:
        pass

    summary = {"required_consecutive": required, "achieved_consecutive": consecutive,
               "attempts": attempt,
               "passed": consecutive >= required and static_ok and real_pass,
               "passed_verifiable_only": consecutive >= required and static_ok and not real_pass,
               "worker": worker_mode, "real_agent_worker": args.worker == "real",
               "external_sandbox": args.external_sandbox,
               "sandbox_preflight": sandbox_preflight,
               "logs": str(log_dir), "static": static}
    (log_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("-" * 72)
    if summary["passed"]:
        print("MILESTONE 1: PASS (consecutive + real agent + verifiable + external sandbox evidenced)")
        return 0
    if summary["passed_verifiable_only"]:
        print("MILESTONE 1: INCOMPLETE — not a real pass. Deterministic/integration run or missing external sandbox evidence.")
        return 2
    print("MILESTONE 1: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
