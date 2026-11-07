# Milestone 1 Playbook â€” One Real Business Cycle (wordcount pilot)

This is the implementation and acceptance playbook for the v1.3 milestone. **Pilot chosen: `wordcount` CLI** (machine-checkable exit codes/output; a static landing page is too subjective for evidence).

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

- `python -m wordcount <file|->` (or equivalent documented CLI) prints `lines words chars <name>` (UTF-8; stdin name `-` or `<stdin>`). Exit `0` ok, `2` missing arg/file, message to stderr.
- `README.md` and `tests/test_wordcount.py` (pytest/unittest as chosen) covering at minimum: normal file, empty file, stdin, missing file/arg.
- Created in a **dedicated workspace** (e.g. `backend/workspace/projects/milestone1-wordcount-runN/`), **never** a production or personal directory.

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

- **VM/network (point 1):** Sekretaris/Lead/QA may need cloud model APIs. A *fully* network-isolated VM kills the cycle. Use a disposable VM/container whose firewall allows **only** the model API hosts (+ DNS) and record that exact allowlist in `--external-sandbox`; **or** isolate only the **agent subprocess** (e.g. run agent command in a container `--network none` with only the project dir mounted) — this requires new subprocess-isolation code (current `run_sandboxed`/worker has no such hook). Never claim NFR-SEC-09/10 without evidence.
- **Hidden tests (point 2):** without FS sandbox, agents could read the verifier. Run/keep `backend/tools/verify_milestone1.py` (and its hidden case list) **outside the agent-visible project tree** or execute it as a different OS user/path not mounted into the agent workspace; ensure RAG indexing (`docs/`, `reports/`, `workspace/projects/`) does **not** expose `tools/` hidden-case inputs. The `wordcount` spec given to agents must be behavior-only, not the verifier contents.
- **Verify the verifier (point 3):** keep `backend/tests/test_verify_milestone1_whitebox.py` passing (correct impl PASS; byte-vs-char, off-by-one lines, missing-file-exit-0, no-stdin FAIL) before trusting Milestone 1 results.

## Acceptance checks

- Same Task cannot reach `COMPLETED` without validated evidence (backend gate: non-empty evidence; **independent verifier** re-checks by running hidden tests).
- Invalid state transitions are rejected.
- Employee tool calls outside permissions are rejected by backend.
- **Sandbox (HONEST STATUS â€” NOT YET MET for NFR-SEC-09/10):** current controls are env filtering, executable allowlist, `shell=False`, timeout, and working-directory scoping. **Filesystem confinement and network egress restriction are NOT implemented.** Do **NOT** mark this criterion passed until OS/container/VM-level filesystem + network isolation is enforced and evidenced. Options: run the pilot inside a disposable VM/container and record that system sandbox is external, **or** implement minimal FS/network sandbox first. Automated checks may only report path/executable-process-level guards as *partial*.
- Owner approval is immutable, single-use and hash-bound.
- Paper cannot appear/disappear in the 3D tray without backend record/event.
- Duplicate events do not create duplicate animations or duplicate decisions.
- **Restart does not lose** task evidence, Paper, PrintJob or Owner decision (verified by explicit restart step).
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
