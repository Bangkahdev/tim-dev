# Changelog

## Employee workshift slice — staffed workstations

- Activated the seven employee workstation accounts (`lead`, `coo`, `architect`, `backend`, `api`, `frontend`, `qa`) bound 1:1 to their desks. Passwords are provisioned into `backend/data/employee_credentials.local`, the same local-secret pattern as the Owner credentials; `BANGKAH_EMPLOYEE_ACCOUNTS=0` freezes back to Owner-only login.
- Added the workshift engine `core/employee_activity.py`: at shift start every employee logs into their own workstation through the same public login path, and the engine produces one role-specific audited work unit per tick (code files, endpoint contracts, ADRs, component stubs, QA reports, standup notes, project updates), referencing the latest open task assigned to them. Employees interacting in the 3D office (talking/listening) are preserved; sessions close at shift end. Config: `BANGKAH_EMPLOYEE_ACTIVITY`, `BANGKAH_EMPLOYEE_DUTY_HOURS` (default 9-17), `BANGKAH_EMPLOYEE_TICK_SECONDS` (default 20).
- Added `GET /api/office/activity` (audited feed + summary) and `POST /api/office/activity/tick` (manual `force` / `ignore_window` tick), plus `activity_engine` in `/api/status`.
- Extended `/api/workstations` to carry each workstation's bound `account` (`id`/`name`/`role`/`active`/`apps`, and `list_accounts()` with no password data).
- Godot: all seven employee desks are proper `workstation` interactables with seat/camera transforms (seat = P + (0, 0.05, 1.55), camera = seat + (0, 1.22, -0.2), target = P + (0, 1.35, -0.44) when the desk rotation is 0 as for every mapped desk), prompts name the workstation, and the login account is prefilled per desk. The dock follows session apps (employee: files/terminal/company only).
- Validation: 12 new activity tests plus 2 replaced workstation tests (suite now 85 passed), `backend/tools/check_desktop_api.py` 21/21, `godot/scripts/workstation_ui_check.gd` 22/22.

## Workstation slice — physical workstation and Bangkah OS

- Added eight catalogued physical workstations in the backend. The Owner station `OWNER-PC-001` opens Bangkah OS in-game; employee station accounts stay inactive and their logins are refused honestly until activation.
- Added PBKDF2 (240k) workstation accounts, 5-per-60s login throttle, 8-hour desktop sessions (configurable), and one-time session tokens (only SHA-256 stored server-side).
- Added a per-workstation sandbox filesystem in `backend/workspace/desktop/<id>/` with listing, read and write constrained to that folder.
- Added an argv-only sandbox terminal (`pwd whoami date ls cat head tail wc grep find help`) with no host shell, fixed size/output limits and a deny-by-default external-binary allowlist (`BANGKAH_TERMINAL_ALLOWED_BINARIES`).
- Added truthful `/api/desktop/system` integration rows (SMTP, deploy webhook, API token, domain with `dns_managed`/`email_provisioned` left `false` until actually managed).
- Added the workstation desktop API routes and audited workstation events (`GET /api/desktop/audit`, plus `GET /api/workstations` catalogue routes).
- Added the Godot flow: walk to the Owner desk, `E` to sit with sit animation and workstation camera, login UI, Files / Terminal / Infrastructure / Company apps, `ESC` to stand up with the session preserved until `LOGOUT`.
- Validation: 15 new workstation tests (suite now 71 passed), `backend/tools/check_desktop_api.py` live HTTP checks 17/17, `godot/scripts/workstation_ui_check.gd` headless UI checks 20/20.

## Final Desktop MVP 1.0

- Reframed the deliverable as a complete local single-Owner desktop MVP rather than another visual-only phase.
- Added persistent backend APIs for departments, employees, projects, tasks, meetings, Papers, approvals, outbox, print jobs, audit events and model usage.
- Added task state transition validation and a completion evidence gate.
- Added meeting lifecycle with persisted minutes, decisions and follow-up records.
- Added Paper inbox lifecycle and ReportLab PDF print jobs with client download-to-user-folder support.
- Added immutable approval payloads with SHA-256 integrity checks, exact payload display in the Owner UI, one-way approval decisions and explicit outbox execution.
- Added optional SMTP TLS email and HTTPS deployment webhook adapters; provider uncertainty is marked `unknown`, and purchase execution remains manual.
- Added API bearer authentication for all `/api/*` GET / POST / download routes when configured; Python server is loopback-only and remote deployment requires TLS reverse proxy.
- Added model usage summary when the provider exposes token metrics.
- Added task lifecycle actions, evidence entry, meeting cancellation, minutes / decisions / follow-ups and PDF download controls to the Godot UI.
- Updated API reference, operations/security, final acceptance and SRS traceability documents.

## v0.5 — Boardroom and NPC movement phase

- Added local Boardroom visual preview with route-aware attendees, seat assignment, speaking/listening gestures and return paths.
- Added local crowd separation, obstacle probes, side selection and stuck-route recovery to waypoint movement.
- Added optional GLB character loading with procedural fallback.

## v0.4 — Character-led simulation and NPC routines

- Third-person over-the-shoulder camera became the default; first-person remains available with `V`.
- Added role-based ambient routines, procedural head aim / blink / breathing and receptionist front-desk cycles.
- Kept backend status authoritative for working poses.

## v0.3 — Realistic camera and office pass

- Added first-person view, optional third-person follow camera, minimal HUD and contextual interaction prompt.
- Improved procedural character shape and office ceiling / lighting detail.

## v0.2 — Expanded HQ environment

- Expanded reception, Owner Suite, Secretary office, Engineering, Boardroom, Archive / Print, Pantry and Lounge areas.

## v0.1 — Native Godot foundation

- Initial Godot 4 environment and player / NPC foundation preserving the Python AI Office backend.
