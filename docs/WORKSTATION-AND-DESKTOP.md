# Workstation and Bangkah OS

The office floor is now also a real computer. A physical workstation in a room is backed by the Python backend: logging in starts a desktop session, and the mission-control-style reading of office state (`F1`–`F4`) can still be used alongside the First-Person `Bangkah OS` that company state renders through. No office state is invented in the client: everything shown comes from `/api/workstations*`, `/api/desktop*` and `/api/terminal/exec`.

Scope honesty: in this slice only **OWNER-PC-001** (Owner Suite) opens Bangkah OS. The other seven catalogued workstations render on the desk map, but their employee accounts are still inactive, so a login attempt there is refused honestly by the backend ("account inactive") instead of pretending to work. The architecture is shared, so activating an employee account plus an OS app set is a data change, not a rewrite.

## Interaction flow (OWNER-PC-001)

1. The Owner walks to the desk in the Owner Suite. The prompt shows `E — Duduk di workstation OWNER-PC-001` when in range.
2. Press `E`: the player character walks/teleports to the seat, plays a sit animation, the third-person camera tweens (0.55s) to the workstation camera looking at the monitor, and Bangkah OS appears over the office view. The HUD is hidden while seated.
3. Bangkah OS shows the workstation login (account prefilled with `owner`, password field). Login talks only to `/api/workstations/OWNER-PC-001/login`.
4. After a successful login the OS view shows the four apps: **Files**, **Terminal**, **Infrastructure**, **Company**.
5. `ESC` (or `TUTUP ESC`) stands the Owner up, restores the player camera and HUD, and hides the OS. The desktop session token is intentionally kept in the client, so standing up and sitting down again resumes the session (the login view re-shows only when there is no session). **NOT** written: entering the desktop does not log anyone out; only `LOGOUT` releases the backend session immediately and is audit-recorded.
6. While the OS is open, gameplay input is suppressed: no movement, no saving the player position, no chat, no F-panel hotkeys; `ESC` order is chat close → company panel close → desktop close.

## Backend model (`backend/core/workstations.py`)

- `workstation_catalog` — eight stations seeded with room and account binding, from `OWNER-PC-001` to `PC-QA-001`.
- Logged-in accounts live in `workstation_accounts`. Owner password: generated on first start into `backend/data/owner_credentials.local` (never committed) or provided through `BANGKAH_OWNER_PASSWORD`. Hashes use PBKDF2-SHA256 with 240,000 iterations; created at import time by a singleton, not configurable by the client.
- Login throttle: at most 5 failed attempts per workstation+account within 60 seconds; success clears the counter. Session default duration comes from `BANGKAH_DESKTOP_SESSION_HOURS` (default 8).
- Session tokens are returned once in the 201 body; only their SHA-256 is stored with the session so the DB leak does not expose a live token. All desktop routes take `X-Desktop-Session: <token>`; the standard `Authorization: Bearer` remains fully independent.
- Workstation sandbox filesystem in `backend/workspace/desktop/<WORKSTATION_ID>/` seeded with README/notes/docs on first use. File listing, read, and write are constrained to that directory (traversal rejected; a write is stored with the workstation id + file path in the audit).
- Terminal is a *builtin only*, argv-based interpreter (`pwd whoami date ls cat head tail wc grep find help`). There is no host shell; per-command characters 500, 6, bytes per file 65536 and per-file output caps 16 kB characters. External binaries are off until `BANGKAH_TERMINAL_ALLOWED_BINARIES` names them (resolved full paths, argv execution, no shell metacharacters). Shell chaining / metacharacters are refused outright.
- `system_info` reports truthful integration state: marks SMTP, deploy webhook and API token config as absent or present, and reports the domain row (`BANGKAH_DOMAIN`, default `bangkah.my.id`) with `dns_managed: false` / `email_provisioned: false` rather than inventing bought DNS.
- Every login, file write, terminal command, session close, and loss writes to the company audit trail (`workstation_*` events) with actor, workstation and detail, reachable through `/api/desktop/audit`.

## API surface

| Route | Auth | Description |
|---|---|---|
| `GET /api/workstations` | none | Catalog + per-room presence, accounts shown as bound state |
| `GET /api/workstations/<id>` | none | Catalog row + account summary + sandbox file count |
| `POST /api/workstations/<id>/login` | none | `{"account_id","password"}` → 201 token + apps; 400 with error otherwise |
| `POST /api/desktop/session/close` | desktop | Logout; audited and stored session invalidated |
| `GET /api/desktop/session` | desktop | Current account, workstation, apps, expiry |
| `GET /api/desktop/system` | desktop | Truthful system + integration + audit-terminal snapshot |
| `GET /api/desktop/files?path=.`, `/api/desktop/files/content?path=`, `POST /api/desktop/files/write` | desktop | Sandbox file manager |
| `POST /api/terminal/exec` | desktop | `{"command"}` → argv-checked builtin execution |
| `GET /api/desktop/audit?after_id=&limit=` | desktop | The workstation audit trail |

Full request/response shapes are in `docs/API-REFERENCE.md` (workstation section).

## Godot client

- `godot/scripts/workstation_sys.gd` — seat camera rig moved to, tweened camera transition between the player camera and the workstation camera, and an `is_active()` guard so gameplay code can bail out while it owns the view.
- `godot/scripts/desktop_ui.gd` (class `BangkahDesktop`) — login/OS view, four apps, Clock, `LOGOUT`, `TUTUP ESC`. Fetches everything through `HTTPRequest` to the same `_server_url` the office game already uses; a 401 tears the session down and shows the login message from the backend verbatim.
- `godot/scripts/player.gd` — `sit_at()`, `stand_up()` and the seated animation variant so sitting is a state, not a fake pose.
- `godot/scripts/main.gd` — registering the OWNER-PC-001 station as interactable with its seat/camera transform, keyboard gating while the OS is open, and ESC priority handling.

Company chart data always stays in the panels (`F1`–`F4` and their workstation buttons); the OS `COMPANY` app intentionally re-opens the real company dashboard instead of re-implementing it, so the reading from `/api/status` is one truth instead of two.

## Validation

- `backend/tests/test_workstations.py` — 15 tests over the catalog, login failure/throttle, session lifetime, token hashing, sandbox path traversal, builtin terminal, audit and integration honesty. **Passed.**
- Whole backend suite — **71 passed** with the workstation tests included.
- `backend/tools/check_desktop_api.py` — 17 live HTTP checks over real routes (wrong password, login, terminal argv rules, traversal, file write/read-back, honest system info, audit kinds, close session, 401 after close). **17/17 PASS**. Run from `backend/`: `.venv/Scripts/python tools/check_desktop_api.py`.
- `godot/scripts/workstation_ui_check.gd` — headless scene load: walk-in, seating, camera rig, login rejection message, rendered session label, files/file/system/audit rendering, terminal echo behavior, 401 teardown, logout, standing back up. **20/20 PASS**. Run from `godot/`: `godot --headless --path . --script res://scripts/workstation_ui_check.gd`.

Environment note recorded at build time: from within the automated build container, Godot → `127.0.0.1` connections were blocked by the sandbox (a process-level network rule, not our code — Godot could reach an external host but not loopback). Desktop HTTP responses were therefore validated with recorded real-backend payloads on the Godot side, and with live HTTP in the Python runtime check. Do the final interactive flow (login → Files → Terminal → Infrastructure → Company → ESC → stand up) on the target Windows machine once, as part of the runtime acceptance checklist in `docs/FINAL-ACCEPTANCE.md`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `BANGKAH_OWNER_PASSWORD` | generated | Owner workstation password; also persisted to `data/owner_credentials.local` when generated |
| `BANGKAH_DESKTOP_SESSION_HOURS` | `8` | Desktop session lifetime |
| `BANGKAH_TERMINAL_ALLOWED_BINARIES` | empty | Allowlisted argv-resolved external binaries (off when empty) |
| `BANGKAH_DOMAIN` | `bangkah.my.id` | Company domain shown in system info; DNS/email state stays honest `false` unless really managed |
