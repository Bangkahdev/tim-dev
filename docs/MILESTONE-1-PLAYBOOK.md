# Milestone 1 Playbook â€” One Real Business Cycle (wordcount pilot)

This is the implementation and acceptance playbook for the v1.3 milestone. **Pilot chosen: `wordcount` CLI** (machine-checkable exit codes/output; a static landing page is too subjective for evidence). The latest executed evidence is recorded in **[`MILESTONE-1-EVIDENCE.md`](MILESTONE-1-EVIDENCE.md)**.

**Honesty boundary:** A deterministic in-process run (`core.business_cycle.BusinessCycle`) that writes fixed pilot files and executes the verifier is a **backend integration test**, not a real Milestone 1 pass. Milestone 1 is satisfied only when a real `AgentWorker` (CrewAI/cloud model or an explicitly documented equivalent) receives the behavior spec, writes `wordcount` from `docs/specs/wordcount-behavior.md` without seeing hidden tests, tests run in an enforced external sandbox, the independent Owner verifier passes, and the cycle succeeds **3 consecutive times** with clean workspace/DB, logs, and a restart-after-Paper case.

### Focused real-agent worker (implementation note)

`CrewAIAgentWorker` in `backend/core/business_cycle.py` is the real-agent boundary used by `tools/run_milestone1.py --worker real`. It runs CrewAI tasks per file with an implementer role and a QA role, plus an advisory lead review. Every returned file is validated (Python AST parse plus required public API), written through `safe_project_path`, and then the public unittest command and a spec-derived probe are executed through `run_sandboxed`. Real failure output is fed back for repair rounds. Hidden verifier cases are never given to any agent. LLM inference is an API call made by the orchestrator process; every execution of agent-produced code (tests and probe commands) runs inside the configured sandbox with only the project directory mounted and networking disabled. If the agent-written `tests/test_wordcount.py` fails validation, the worker installs a deterministic public-spec test scaffold and records `tests_source` in its returned metadata; the `wordcount` implementation files remain agent-generated.

## Goal

Complete one small real software project from Owner instruction to reviewable deliverable, with **no manual intervention except required Owner approval**. Repeat successfully **three consecutive times** (see definition below).

## Consecutive-run definition (strict)

- **Any failure resets the consecutive count to 0.** Fix the root cause, record what changed, then restart the count from run 1.
- **Clean directory and data for each run.** Each run uses a fresh project key/workspace directory and (for independent verification runs) a fresh DB or clearly isolated run data. Do **not** reuse a contaminated workspace.
- **Keep logs for every attempt, including failures.** `tools/run_milestone1.py` / `tools/verify_milestone1.py` write per-attempt logs; retain them.

## Required sequence

1. Owner sends a request to Secretary or directly to a division manager.
2. Secretary / Orchestrator creates a validated plan and proposal.
3. Owner approves the internal coding pipeline where required.
4. Manager decomposes work into tasks with acceptance criteria and dependencies.
5. Backend assigns tasks to employees with role-scoped tool permissions.
6. Agents run in an **enforced sandbox** (see sandbox status) and produce files + test output.
7. QA executes tests and stores evidence.
8. **Backend validates evidence and sets task/project state** â€” but task completion evidence is currently validated as a **non-empty reference/note** (not an independent execution check). Therefore the **Owner independent verifier** (`backend/tools/verify_milestone1.py`) MUST run its own hidden tests and inspect DB/artifacts; agents must **not** judge their own work.
9. Worker creates a final report Paper and PrintJob.
10. Employee prints and physically delivers the report to Owner tray (animation follows persisted events).
11. Owner reviews evidence, decision is persisted and audited.
12. **Explicit restart step (at least once per acceptance set):** after the Paper is sent/delivered, stop/restart the backend/store process, then verify evidence, Paper, PrintJob, and Owner decision are still complete/intact.

## Pilot spec (`wordcount`)

Use the agent-facing spec as the single source of truth: **[`docs/specs/wordcount-behavior.md`](specs/wordcount-behavior.md)**.

- `python -m wordcount <path|->` (module `wordcount`; `wordcount.cli`/`__main__` acceptable). UTF-8. stdin name `-`.
- Success output (stdout): a single line with clearly labeled parseable counts for `lines`, `words`, `characters` plus the input name, e.g. `lines=2 words=4 characters=24 <name>`.
- Exit `0` on success; `2` on missing argument or missing/unreadable file, with a human-readable error on stderr.
- Counting: `characters` = Unicode character count (not bytes); `words` = whitespace-delimited tokens (`str.split()`); `lines` = newline count plus 1 for a non-empty text that does not end with a newline, else 0 for empty text.
- Deliverables: `wordcount/` package (`core.py` with `count_text(text) -> {lines,words,characters}` plus `cli.py`/`__main__`), `README.md`, `tests/test_wordcount.py` (normal file, empty file, stdin `-`, missing file/arg), `artifacts/test-output.txt`.
- Created in a **dedicated workspace** (e.g. `backend/workspace/projects/milestone1-wordcount-runN/`), **never** a production or personal directory. The Owner verifier runs hidden cases agents do not see.

## Required evidence (per run)

- Source files / commit reference.
- Test command and exit code.
- Test output artifact.
- QA report.
- Manager review.
- Final project report.
- Paper record and generated PDF.
- PrintJob and delivery event.
- Owner decision and audit record.

## Sandbox & hidden-test operational notes (pre-run)

- **VM/network (point 1):** Sekretaris/Lead/QA may need cloud model APIs. A *fully* network-isolated VM kills the cycle. Use a disposable VM/container whose firewall allows **only** the model API hosts (+ DNS) and record that exact allowlist in `--external-sandbox`; **or** isolate only the **agent subprocess** (e.g. run agent command in a container `--network none` with only the project dir mounted). `core.sandbox_exec.wrap_argv` is wired into `run_sandboxed` (backend/core), the CrewAI tool `Run Project Command` (backend/main.py), and the desktop terminal external binary path (backend/core/workstations.py) when `BANGKAH_SANDBOX_CMD` is set. `enforce_sandbox` itself now runs the cached canaries whenever `BANGKAH_SANDBOX_REQUIRED=1`, so a caller cannot bypass the isolation check by using only that function. Never claim NFR-SEC-09/10 without evidence.
- **Hidden tests (point 2):** without FS sandbox, agents could read the verifier. Run/keep `backend/tools/verify_milestone1.py` (and its hidden case list) **outside the agent-visible project tree** or execute it as a different OS user/path not mounted into the agent workspace; ensure RAG indexing (`docs/`, `reports/`, `workspace/projects/`, `core/`, `web/`) does **not** expose `tools/` hidden-case inputs. `core/business_cycle.py` and `docs/MILESTONE-1-PLAYBOOK.md` are excluded from agent RAG seeding, and old `workspace/projects/milestone1*` pilot outputs are excluded because they contain the deterministic reference answer. The `wordcount` spec given to agents must be behavior-only, not the verifier contents. The verifier executes every hidden-test CLI call through `enforce_sandbox`, so under `BANGKAH_SANDBOX_REQUIRED=1` a missing/broken wrapper fails closed; fixture files are created inside a temporary `.owner-verify-*` directory in the project tree so they remain visible under a project-only mount, then removed.
- **Verify the verifier (point 3):** keep `backend/tests/test_verify_milestone1_whitebox.py` passing (correct impl PASS; byte-vs-char, off-by-one lines, no-trailing-newline/single-line/whitespace/CRLF cases, missing-file-exit-0, no-stdin FAIL) before trusting Milestone 1 results.
- **Host sandbox example (validated):** on Linux without Docker, bubblewrap can provide the same contract. Example wrapper prefix (keep the `{project_dir}` token):
  `bwrap --unshare-net --die-with-parent --ro-bind /usr /usr --ro-bind <python-runtime> <python-runtime> --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib64 /lib64 --ro-bind /etc /etc --proc /proc --dev /dev --tmpfs /tmp --bind {project_dir} /work --chdir /work --setenv PATH /usr/bin:/bin --setenv HOME /tmp`.
  `tools/run_milestone1.py --worker real` runs canaries first and refuses to start unless a sentinel outside `/work` is unreadable, outbound TCP is blocked inside the sandbox, and the **same probe succeeds outside the sandbox** (control). If the host itself cannot reach the probe target, the result is inconclusive and fails closed.
- **Docker wrapper example:**
  `export BANGKAH_SANDBOX_CMD='docker run --rm --network none -v {project_dir}:/work -w /work <image>'`
  The image must contain Python and `pytest`. Before trusting a run, execute manual probes from inside the wrapper and keep the transcript: reading a host file outside `/work` must fail, and `curl`/outbound TCP must fail.
- **Canary limits (point 4):** the wrapper is operator-controlled, so a wrapper that fabricates `{"ok": true, "leaked": false}` can pass the canary without providing any isolation. Canaries are supporting evidence, **not standalone proof**. NFR-SEC-09/10 evidence must include recorded manual probes from inside the real container/VM (outside-file read fails; outbound network fails), stored with the run logs.

## Running the acceptance set (reproducible)

Run from `backend/` with a real model and an evidenced sandbox wrapper:

```bash
export BANGKAH_SANDBOX_REQUIRED=1
export BANGKAH_SANDBOX_CMD='bwrap --unshare-net --die-with-parent --ro-bind /usr /usr ... --bind {project_dir} /work --chdir /work ...'
export MODEL_BACKEND=ollama/qwen2.5-coder:7b   # or cloud provider/model + API key
export MODEL_QA=ollama/qwen2.5-coder:7b
export MODEL_LEAD=ollama/qwen2.5-coder:7b
PYTHONPATH=.pylibs:. python3.12 tools/run_milestone1.py \
  --cycles 3 --isolated-db --workspace /tmp/opencode/m1-real \
  --external-sandbox 'bwrap --unshare-net; canaries prove FS sentinel unreadable and outbound network blocked' \
  --worker real
```

Every attempt gets a fresh `<workspace>/<project-key>/` and, with `--isolated-db`, a fresh DB. `summary.json` must say `"passed": true`; keep the whole log directory, including failed attempts. If a cloud key is unavailable, record the local Ollama model as the explicitly documented equivalent and do not claim a cloud-model run.

## Acceptance checks

- Same Task cannot reach `COMPLETED` without validated evidence (backend gate: non-empty evidence; **independent verifier** re-checks by running hidden tests).
- Invalid state transitions are rejected.
- Employee tool calls outside permissions are rejected by backend.
- **Sandbox (conditional, evidence-based):** `core.sandbox_exec` wraps subprocess argv via `BANGKAH_SANDBOX_CMD` (token `{project_dir}`) and fails closed via `BANGKAH_SANDBOX_REQUIRED=1` in wired execution paths (`main.run_project_command`, workstation external commands, `business_cycle.run_sandboxed`). In required mode `enforce_sandbox` runs the cached canaries itself, so callers cannot bypass them. Wrapping argv is **not** isolation by itself. NFR-SEC-09/10 is claimed for a run **only** when the configured wrapper is a real container/VM or an equivalent OS sandbox (validated here with bubblewrap, `--unshare-net`, read-only system mounts, and only the project directory bound at `/work`), the preflight canaries prove an outside sentinel is unreadable and outbound TCP is blocked inside the sandbox **while the same probe succeeds outside the sandbox**, the recorded manual probes also show an outside-file read and outbound network both fail from inside the wrapper, and the runner records that wrapper as `--external-sandbox` evidence. If the control probe cannot reach the target, the canary is inconclusive and fails closed. Canary JSON is operator-controlled and can be fabricated, so canaries alone are not proof. Without those conditions the runner reports isolation as not evidenced; path/executable guards alone remain *partial*.
- Owner approval is immutable, single-use and hash-bound.
- Paper cannot appear/disappear in the 3D tray without backend record/event.
- Duplicate events do not create duplicate animations or duplicate decisions.
- **Restart does not lose** task evidence, Paper, PrintJob or Owner decision (verified by explicit restart step). `tools/run_milestone1.py` additionally starts a **fresh Python process** (`tools/check_persisted_state.py`) against the run DB after Paper delivery and records `restart.fresh_process_persistence` in the attempt log.
- Character status in Godot matches backend task/session state â€” **one manual check per run** (status/character, tray, paper match backend records). Other verification from backend data.
- All decisions are present in the audit trail.
- Full cycle succeeds **three consecutive times** (per definition above).

## Independent Owner verifier (agents never see hidden tests)

`backend/tools/verify_milestone1.py` is the Owner-controlled verifier. It:
- contains a **hidden test suite** (never shown to agents) with owner-computed expected values: `lines = newline count + (1 if non-empty and no trailing newline else 0)`, `words = whitespace split length`, `chars = character count (not bytes)`; cases: normal file, empty file, stdin, missing file/arg (exit 2, message to stderr), UTF-8 multibyte.
- runs those tests itself for each run and checks exit codes.
- reads the database and artifacts and prints **PASS/FAIL per criterion with evidence**.

Run: `python backend/tools/verify_milestone1.py --db <path> --project-key <key> --project-dir <dir>` (and the consecutive runner integrates it).

## Not part of this milestone

Email delivery, public website deployment, marketing automation, parallel projects, advanced NPC pathfinding and visual polish. These are later phases after the internal workflow is proven.
