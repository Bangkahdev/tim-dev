#!/usr/bin/env python3
"""Owner-controlled independent Milestone 1 verifier (agents never see hidden tests).

- Runs a HIDDEN test suite against the produced wordcount project with
  owner-computed expected values (lines = newline count + (1 if non-empty and no
  trailing newline else 0), words = whitespace split, chars = character count,
  not bytes). Cases: normal file, empty file, stdin, missing file/arg (exit 2,
  stderr message), UTF-8 multibyte.
- Checks agent-reported test exit codes/artifacts.
- Reads DB and artifacts and prints PASS/FAIL per criterion with evidence.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.company_operations import CompanyOperations  # noqa: E402
from core.office_store import OfficeStore  # noqa: E402


def expected(text: str) -> dict:
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    words = len(text.split())
    return {"lines": lines, "words": words, "chars": len(text)}


def _parse_output(out: str):
    # accept `lines=N words=N characters=N <name>` or close variants
    import re
    m = re.search(r"lines\s*[:=]\s*(\d+).*?words\s*[:=]\s*(\d+).*?(?:characters|chars)\s*[:=]\s*(\d+)", out, re.I | re.S)
    if not m:
        return None
    return {"lines": int(m.group(1)), "words": int(m.group(2)), "chars": int(m.group(3))}


def run_cli(project_dir: Path, args, stdin_text=None):
    # try `python -m wordcount <file|->` then `python -m wordcount.cli`
    for mod in ("wordcount", "wordcount.cli"):
        cmd = [sys.executable, "-m", mod] + list(args)
        try:
            cp = subprocess.run(cmd, cwd=project_dir, input=stdin_text, text=True, capture_output=True, timeout=30)
        except Exception as e:
            return None, -1, str(e), "", str(e)
        # if module missing, try next; ModuleNotFoundError in stderr
        if cp.returncode != 0 and "No module named" in (cp.stderr or "") and "wordcount" in (cp.stderr or ""):
            continue
        return mod, cp.returncode, (cp.stdout or "") + (cp.stderr or ""), cp.stdout, cp.stderr
    return None, -1, "no runnable wordcount module", "", "no runnable wordcount module"


def hidden_tests(project_dir: Path):
    cases = []
    def add(name, ok, detail):
        cases.append({"name": name, "pass": bool(ok), "detail": detail})
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # normal file
        text = "hello world\nsecond line\n"
        f = td / "normal.txt"; f.write_text(text, encoding="utf-8")
        mod, rc, _, out, err = run_cli(project_dir, [str(f)])
        exp = expected(text); got = _parse_output(out or "")
        add("hidden.normal_file", rc == 0 and got == exp, f"rc={rc} expected={exp} got={got} out={out!r}")
        # empty file
        text = ""; f = td / "empty.txt"; f.write_text(text, encoding="utf-8")
        mod, rc, _, out, err = run_cli(project_dir, [str(f)])
        exp = expected(text); got = _parse_output(out or "")
        add("hidden.empty_file", rc == 0 and got == exp, f"rc={rc} expected={exp} got={got} out={out!r}")
        # stdin
        text = "alpha beta\ngamma\n"
        mod, rc, _, out, err = run_cli(project_dir, ["-"], stdin_text=text)
        exp = expected(text); got = _parse_output(out or "")
        add("hidden.stdin", rc == 0 and got == exp, f"rc={rc} expected={exp} got={got} out={out!r}")
        # missing file/arg -> exit 2, stderr message
        mod, rc, _, out, err = run_cli(project_dir, [str(td / "nope-missing.txt")])
        add("hidden.missing_file_exit2", rc == 2 and bool((err or "").strip() or (out or "").strip()),
            f"rc={rc} stderr={err!r} out={out!r}")
        mod, rc, _, out, err = run_cli(project_dir, [])
        add("hidden.missing_arg_exit2", rc == 2 and bool((err or "").strip() or (out or "").strip()),
            f"rc={rc} stderr={err!r} out={out!r}")
        # UTF-8 multibyte (chars are characters, not bytes)
        text = "halo café\nこんにちは 世界\n"
        f = td / "utf8.txt"; f.write_text(text, encoding="utf-8")
        mod, rc, _, out, err = run_cli(project_dir, [str(f)])
        exp = expected(text); got = _parse_output(out or "")
        add("hidden.utf8_multibyte_chars", rc == 0 and got == exp, f"rc={rc} expected(chars,not bytes)={exp} got={got} out={out!r}")
    return cases


def verify(db_path, project_key, project_dir):
    checks = {}
    details = {}
    project_dir = Path(project_dir)

    # artifacts present
    for rel in ("README.md", "QA-REPORT.md", "MANAGER-REVIEW.md", "artifacts/test-output.txt"):
        ok = (project_dir / rel).is_file()
        checks[f"artifact.{rel}"] = ok
        details[f"artifact.{rel}"] = str(project_dir / rel)

    # hidden tests (owner-computed) - agents never see these
    ht = hidden_tests(project_dir)
    for c in ht:
        checks[c["name"]] = c["pass"]
        details[c["name"]] = c["detail"]
    checks["hidden.all_pass"] = all(c["pass"] for c in ht)

    # DB/artifact inspection
    try:
        ops = CompanyOperations(OfficeStore(Path(db_path)))
        tasks = [t for t in ops.tasks() if str(t.get("project_key") or "") == project_key]
        checks["db.tasks_present"] = len(tasks) >= 1
        details["db.tasks_present"] = f"count={len(tasks)}"
        checks["db.tasks_completed_with_evidence"] = bool(tasks) and all(t.get("status") == "completed" and t.get("evidence") for t in tasks)
        details["db.tasks_completed_with_evidence"] = [(t["id"], t.get("status"), len(t.get("evidence") or [])) for t in tasks]

        title = f"Final Report: {project_key}"
        paper = None
        with ops._db() as db:
            row = db.execute("SELECT * FROM paper_records WHERE title=? ORDER BY created_at DESC LIMIT 1", (title,)).fetchone()
            paper = dict(row) if row else None
        checks["db.final_report_paper"] = bool(paper)
        details["db.final_report_paper"] = (paper or {}).get("id")
        checks["db.owner_decision_audited"] = False
        checks["db.print_job_completed"] = False
        if paper:
            with ops._db() as db:
                dec = db.execute("SELECT 1 FROM events WHERE event_type='owner_decision' AND entity_id=? LIMIT 1", (paper["id"],)).fetchone()
                pj = db.execute("SELECT * FROM print_jobs WHERE paper_id=? ORDER BY created_at DESC LIMIT 1", (paper["id"],)).fetchone()
            checks["db.owner_decision_audited"] = bool(dec)
            if pj:
                checks["db.print_job_completed"] = pj["status"] == "completed"
                details["db.print_job_completed"] = dict(pj)
        ops.close()
    except Exception as e:
        checks["db.inspect_error"] = False
        details["db.inspect_error"] = str(e)

    # sandbox honest status (NOT claimed met)
    checks["sandbox.fs_network_isolation_NFR_SEC_09_10"] = False
    details["sandbox.fs_network_isolation_NFR_SEC_09_10"] = "NOT MET: only env filter/exec allowlist/shell=False/timeout/cwd. FS+network isolation requires VM/container or implementation; run pilot in disposable VM/container and record external sandbox."

    ok = all(v for k, v in checks.items() if k != "sandbox.fs_network_isolation_NFR_SEC_09_10") and checks.get("hidden.all_pass") and checks.get("db.tasks_completed_with_evidence")
    # note: overall pass for the *verifiable* criteria; sandbox remains an explicit unmet/externally-evidenced item
    checks["OVERALL_VERIFIABLE"] = bool(ok)
    return {"checks": checks, "details": details}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Owner independent Milestone 1 verifier (hidden tests).")
    ap.add_argument("--db", required=True)
    ap.add_argument("--project-key", required=True)
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args(argv)
    res = verify(args.db, args.project_key, args.project_dir)
    for name, passed in res["checks"].items():
        tag = "PASS" if passed else "FAIL"
        ev = res["details"].get(name, "")
        print(f"  [{tag}] {name} :: {ev}")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if res["checks"].get("OVERALL_VERIFIABLE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
