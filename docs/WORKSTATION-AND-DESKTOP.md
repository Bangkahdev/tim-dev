# Workstation and Bangkah OS

The office floor is now also a real computer. A physical workstation in a room is backed by the Python backend: logging in starts a desktop session, and the mission-control-style reading of office state (`F1`–`F4`) can still be used alongside the First-Person `Bangkah OS` that company state renders through. No office state is invented in the client: everything shown comes from `/api/workstations*`, `/api/desktop*` and `/api/terminal/exec`.

Scope honesty: **OWNER-PC-001** (Owner Suite) plus all seven employee desks (PC-MGT-001, PC-MGT-002, PC-ARC-001, PC-BE-001, PC-API-001, PC-FE-001, PC-QA-001) open Bangkah OS. Every employee has a real login at their own workstation (employee slice A), and the [workshift engine](#employee-workshift-engine) keeps them on duty writing audited work files.

## Employee workshift engine

Every employee has a persistent domain account bound to exactly one desk (the `employees` roster ids — `lead`, `coo`, `architect`, `backend`, `api`, `frontend`, `qa` — are the workstation account ids). Employee passwords are provisioned into `backend/data/employee_credentials.local`, the same local-secret pattern as the Owner credentials (never committed). `BANGKAH_EMPLOYEE_ACCOUNTS=0` freezes the office back to Owner-only workstation login; `BANGKAH_EMPLOYEE_PASSWORD=<x>` sets one shared password for every employee account.

The engine (`backend/core/employee_activity.py`) runs a real workshift per employee:

- Shift window `BANGKAH_EMPLOYEE_DUTY_HOURS` (default `9-17`, server-local), engine toggle `BANGKAH_EMPLOYEE_ACTIVITY` (default on), tick cadence `BANGKAH_EMPLOYEE_TICK_SECONDS` (default 20).
- At shift start the engine logs the employee into their own workstation through the same public `/api/workstations/<id>/login` production path (it is not a backdoor — the employee login is real and audited as `employee_login`).
- Each tick produces ONE role-specific work unit: backend writes `work/backend/<day>/service_<n>.py`, api writes endpoint contracts, architect writes ADRs, frontend writes component stubs, QA writes reports and then inspects them with terminal `cat`/`ls`, lead writes standup notes, coo writes project updates. Task linkage reads the latest open task assigned to that employee from the `tasks` table and records it in the unit file and the audit event.
- Employees with a live interaction (talking/listening in the 3D office) are left alone — the engine only marks idle employees as `working`, and never flips a talking/listen employee.
- At shift end the engine logs the employee out (`LOGOUT` → `desktop_close` audited) and returns them to `idle`. Sessions lost by restart are re-created on the next tick, so the engine self-heals without manual intervention.

Read it back:

| Route | Description |
|---|---|
| `GET /api/office/activity?after_id=&limit=` | Audited activity feed for all employees + workshift summary |
| `POST /api/office/activity/tick` | `{"force": bool, "ignore_window": bool}` manual tick, used by the Owner console during off-hours; `force` bypasses the rate limit, `ignore_window` works outside the shift window |

The status endpoint (`/api/status`) ticks the engine at its configured cadence and exposes the last tick under `activity_engine`, so the Owner watches work happen just by polling status.

All of it is covered by `backend/tests/test_employee_activity.py` (12 tests: login+files per role, audited events, feed pagination, working status, talking preserved, rate limit, disabled engine, frozen accounts, day-boundary rollover, task linkage, duty-window parsing, shift-end logout) and by the extended `backend/tools/check_desktop_api.py` (21/21 runtime checks including employee workstation account info, tick, feed and summary).

## Interaction flow (Owner Suite)

1. The Owner walks to the desk in the Owner Suite (or any employee desk). The prompt shows `E — Duduk di workstation OWNER-PC-001 (...account...)` when in range.
2. Press `E`: the player character walks/teleports to the seat, plays a sit animation, the third-person camera tweens (0.55s) to the workstation camera looking at the monitor, and Bangkah OS appears over the office view. The HUD is hidden while seated.
3. Bangkah OS shows the workstation login (account prefilled with `owner`, or the employee bound to that desk — e.g. `backend` at Bima's desk). Login talks only to `/api/workstations/<id>/login`.
4. After a successful login the OS view shows the apps the account is permitted (`Files`, `Terminal`, `Company` for employees; all four including `Infrastructure` for the Owner).
5. `ESC` (or `TUTUP ESC`) stands the Owner up, restores the player camera and HUD, and hides the OS. The desktop session token is intentionally kept in the client, so standing up and sitting down again resumes the session (the login view re-shows only when there is no session). **NOT** written: entering the desktop does not log anyone out; only `LOGOUT` releases the backend session immediately and is audit-recorded.
6. While the OS is open, gameplay input is suppressed: no movement, no saving the player position, no chat, no F-panel hotkeys; `ESC` order is chat close → company panel close → desktop close.

## Backend model (`backend/core/workstations.py`)

- `workstation_catalog` — eight stations seeded with room and account binding, from `OWNER-PC-001` to `PC-QA-001`.
- Logged-in accounts live in `workstation_accounts`. Owner password: generated on first start into `backend/data/owner_credentials.local` (never committed) or provided through `BANGKAH_OWNER_PASSWORD`. Employee passwords: generated into `backend/data/employee_credentials.local` or the shared `BANGKAH_EMPLOYEE_PASSWORD`. Hashes use PBKDF2-SHA256 with 240,000 iterations; created at import time by a singleton, not configurable by the client. `/api/workstations` lists each workstation with its bound `account` (`id`/`name`/`role`/`active`/`apps` — never a hash).
- Login throttle: at most 5 failed attempts per workstation+account within 60 seconds; success clears the counter. Session default duration comes from `BANGKAH_DESKTOP_SESSION_HOURS` (default 8).
- Session tokens are returned once in the 201 body; only their SHA-256 is stored with the session so the DB leak does not expose a live token. All desktop routes take `X-Desktop-Session: <token>`; the standard `Authorization: Bearer` remains fully independent.
- Workstation sandbox filesystem in `backend/workspace/desktop/<WORKSTATION_ID>/` seeded with README/notes/docs on first use. File listing, read, and write are constrained to that directory (traversal rejected; a write is stored with the workstation id + file path in the audit).
- Terminal is a *builtin only*, argv-based interpreter (`pwd whoami date ls cat head tail wc grep find help`). There is no host shell; per-command characters 500, 6, bytes per file 65536 and per-file output caps 16 kB characters. External binaries are off until `BANGKAH_TERMINAL_ALLOWED_BINARIES` names them (resolved full paths, argv execution, no shell metacharacters). Shell chaining / metacharacters are refused outright.
- `system_info` reports truthful integration state: marks SMTP, deploy webhook and API token config as absent or present, and reports the domain row (`BANGKAH_DOMAIN`, default `bangkah.my.id`) with `dns_managed: false` / `email_provisioned: false` rather than inventing bought DNS.
- Every login, file write, terminal command, session close, and loss writes to the company audit trail (`workstation_*` events) with actor, workstation and detail, reachable through `/api/desktop/audit`.

## API surface

| `GET /api/workstations` | none | Catalog + per-room presence, each workstation carries its bound `account` (`id`/`name`/`role`/`active`/`apps`) |
| `GET /api/workstations/<id>` | none | Catalog row + account summary + sandbox file count |
| `POST /api/workstations/<id>/login` | none | `{"account_id","password"}` → 201 token + apps; 400 with error otherwise |
| `POST /api/desktop/session/close` | desktop | Logout; audited and stored session invalidated |
| `GET /api/desktop/session` | desktop | Current account, workstation, apps, expiry |
| `GET /api/desktop/system` | desktop | Truthful system + integration + audit-terminal snapshot |
| `GET /api/desktop/files?path=.`, `/api/desktop/files/content?path=`, `POST /api/desktop/files/write` | desktop | Sandbox file manager |
| `POST /api/terminal/exec` | desktop | `{"command"}` → argv-checked builtin execution |
| `GET /api/desktop/audit?after_id=&limit=` | desktop | The workstation audit trail |
| `GET /api/office/activity?after_id=&limit=` | none | Employee workshift feed (`employee_work`, `employee_login`, …) + summary |
| `POST /api/office/activity/tick` | API token | `{"force", "ignore_window"}` manual engine tick |

Full request/response shapes are in `docs/API-REFERENCE.md` (workstation section).

## Godot client

- `godot/scripts/workstation_sys.gd` — seat camera rig moved to, tweened camera transition between the player camera and the workstation camera, and an `is_active()` guard so gameplay code can bail out while it owns the view.
- `godot/scripts/desktop_ui.gd` (class `BangkahDesktop`) — login/OS view, four apps, Clock, `LOGOUT`, `TUTUP ESC`. Fetches everything through `HTTPRequest` to the same `_server_url` the office game already uses; a 401 tears the session down and shows the login message from the backend verbatim.
- `godot/scripts/player.gd` — `sit_at()`, `stand_up()` and the seated animation variant so sitting is a state, not a fake pose.
- `godot/scripts/main.gd` — registering all eight stations as interactables with seat/camera transforms (seat = P + (0, 0.05, 1.55), camera = seat + (0, 1.22, -0.2), target = P + (0, 1.35, -0.44) when desk rotation is 0 as for every mapped desk), keyboard gating while the OS is open, and ESC priority handling.
- `godot/scripts/desktop_ui.gd` `open_for(..., account_hint)` prefills the login account and `_apply_session` filters the dock by the session apps, so employee OS shows files/terminal/company only.

Company chart data always stays in the panels (`F1`–`F4` and their workstation buttons); the OS `COMPANY` app intentionally re-opens the real company dashboard instead of re-implementing it, so the reading from `/api/status` is one truth instead of two.

## Validation

- `backend/tests/test_workstations.py` — 17 tests over the catalog, login failure/throttle, session lifetime, token hashing, sandbox path traversal, builtin terminal, audit, account activation, env freeze, and credentials file. **Passed.**
- `backend/tests/test_employee_activity.py` — 12 tests over the workshift engine. **Passed.**
- Whole backend suite — **85 passed** (71 workstation-slice tests + 14 tests added/updated in this slice: 12 activity + 2 adjusted workstation tests).
- `backend/tools/check_desktop_api.py` — 21 live HTTP checks over real routes (wrong password, login, terminal argv rules, traversal, file write/read-back, honest system info, audit kinds, close session, 401 after close, employee workstation account info, activity tick/feed/summary). **21/21 PASS**. Run from `backend/`: `.venv/Scripts/python tools/check_desktop_api.py`.
- `godot/scripts/workstation_ui_check.gd` — headless scene load: walk-in, seating, camera rig, login rejection message, rendered session label, owner vs employee dock apps, employee account prefill, files/file/system/audit rendering, terminal echo behavior, 401 teardown, logout, standing back up. **22/22 PASS**. Run from `godot/`: `godot --headless --path . --script res://scripts/workstation_ui_check.gd`.

Environment note recorded at build time: from within the automated build container, Godot → `127.0.0.1` connections were blocked by the sandbox (a process-level network rule, not our code — Godot could reach an external host but not loopback). Desktop HTTP responses were therefore validated with recorded real-backend payloads on the Godot side, and with live HTTP in the Python runtime check. Do the final interactive flow (login → Files → Terminal → Infrastructure → Company → ESC → stand up) on the target Windows machine once, as part of the runtime acceptance checklist in `docs/FINAL-ACCEPTANCE.md`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `BANGKAH_OWNER_PASSWORD` | generated | Owner workstation password; also persisted to `data/owner_credentials.local` when generated |
| `BANGKAH_DESKTOP_SESSION_HOURS` | `8` | Desktop session lifetime |
| `BANGKAH_TERMINAL_ALLOWED_BINARIES` | empty | Allowlisted argv-resolved external binaries (off when empty) |
| `BANGKAH_DOMAIN` | `bangkah.my.id` | Company domain shown in system info; DNS/email state stays honest `false` unless really managed |
