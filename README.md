# Bangkah Company Simulator — Final Desktop MVP 1.0

**Native Godot 4 headquarters · Third-person default · Optional first-person · Python operations backend**

Bangkah Company Simulator is a walkable 3D headquarters for a single human Owner and an AI-operated software company. The office is the primary interface: the Owner walks through reception and departments, meets the team, opens physical workstation panels, creates company tasks, records meetings, reviews company documents, and approves external actions.

This release is the **Final Desktop MVP 1.0** for the single-Owner local desktop scope. It is not a declaration that every requirement in the broader SRS v1.3 is complete. The exact implemented scope, remaining integration requirements, and unverified runtime checks are documented below and in `docs/FINAL-ACCEPTANCE.md`.

## Included in this release

### 3D headquarters

- Native Godot 4 project with a walkable single-floor headquarters, reception, Owner Suite, Secretary desk, Engineering departments, Boardroom, Archive / Print room, Promotion Studio, Lounge and Pantry.
- Third-person Owner avatar camera by default. Press `V` to switch to first-person; mouse wheel adjusts third-person camera distance.
- WASD / arrow movement, Shift sprint, Space jump, mouse look and contextual `E` interaction.
- Role-aware NPC routines and reception desk activity. The backend's employee status remains authoritative for work poses.
- NPC local separation, obstacle probes and route recovery using authored waypoints.
- Local Boardroom preview with seated participants, alternating speaking/listening gestures and return routes. This visual preview is separate from persisted backend meetings.
- Optional GLB character slots under `godot/assets/characters/`. Procedural humanoids remain the fallback; no third-party rigged models are bundled.
- Physical workstation slice: the Owner desk (`OWNER-PC-001`) opens **Bangkah OS** through the real backend — workstation login (PBKDF2 accounts, login throttling, 8-hour sessions), a Files sandbox folder per workstation, an argv-only sandbox Terminal, truthful Infrastructure status, and a Company summary. Employee workstations are catalogued but their accounts stay inactive; the backend refuses their logins honestly. See `docs/WORKSTATION-AND-DESKTOP.md`.

### Company operations backend

- Persistent departments, employee roster, task lifecycle and completion evidence.
- Persistent meetings with scheduled / in-progress / completed / cancelled states, minutes, decisions and follow-ups.
- Paper inbox with read / deferred / archived states and generated PDF print jobs.
- Immutable approval payloads with SHA-256 integrity checks.
- Approval-to-outbox workflow for outbound email and website deployment.
- SMTP TLS email adapter and HTTPS deployment webhook adapter, both disabled until credentials / endpoint are configured.
- Explicit manual handling for purchases. The application never records a purchase as completed merely because approval was granted.
- Audit events, cursor-based event retrieval and model usage summaries when the provider reports token metrics.
- Optional bearer-token authentication for every API endpoint. The backend binds to loopback only; remote access should pass through a TLS reverse proxy.

## Quick start

### Requirements

- Godot 4.3 or later for the 3D client.
- Python 3.10+ for the backend. Use a Python version supported by the installed CrewAI dependency.
- Ollama with a compatible model, or a supported cloud provider API key, only when AI responses / coding agents are needed.

### Windows

1. Extract the ZIP to a writable directory.
2. Run `start_backend.bat` once. It creates `backend/.venv`, installs requirements, and creates `backend/.env.example` as `backend/.env` on first run.
3. Edit `backend/.env` to configure the model provider. Keep the console open while using the game.
4. Open Godot Project Manager and import `godot/project.godot`.
5. Press `F5` to run the headquarters.
6. The default API address is `http://127.0.0.1:8765`.

### Linux

```bash
chmod +x start_backend.sh run_godot.sh
./start_backend.sh
```

After the backend creates `backend/.env`, edit the model/provider settings and run `./start_backend.sh` again. Import `godot/project.godot` in Godot and press `F5`.

The 3D office remains explorable when the backend is offline. Company data and operations are marked unavailable until the backend reconnects.

## Controls

| Input | Action |
|---|---|
| `W A S D` / Arrow keys | Walk |
| `Shift` | Sprint |
| `Space` | Jump |
| Mouse | Look around |
| `E` | Interact with the focused nearby employee / office object |
| `E` at the Owner desk | Sit down at OWNER-PC-001 and open Bangkah OS |
| `Esc` while in Bangkah OS | Stand up and return to the office (session stays until `LOGOUT`) |
| `V` | Toggle third-person / first-person |
| Mouse wheel | Adjust third-person camera distance |
| `Esc` | Release mouse cursor / close applicable panel |
| Left click | Capture mouse again |
| `F1` | Company overview |
| `F2` | Owner inbox / Paper |
| `F3` | Projects and tasks |
| `F4` | Team and employees |

Supporting panels are secondary to the 3D world and are opened from the relevant workstation / physical interaction point or shortcut.

## Core work cycle

1. Owner creates a task and assigns an employee / priority.
2. Task moves through a validated state transition: pending → in progress → blocked / completed / failed / cancelled as permitted.
3. Completion requires at least one evidence reference (commit, pull request, build, QA report, or documented verification).
4. Owner schedules and runs a meeting; minutes are required to complete it. Decisions and follow-ups are saved with the meeting.
5. Documents can be created in Paper, marked read, and rendered to PDF. The PDF can be saved to the local computer from the Archive page.
6. Outbound email / deployment requests are stored as immutable approvals. The exact payload and hash are shown before the Owner approves or rejects them.
7. Approval creates an outbox item. A separate Owner action is required to execute it. Unknown remote outcomes are not retried automatically.

## Backend configuration

Copy `backend/.env.example` to `backend/.env` if the start script has not already done so. Configure the model variables relevant to your provider. Model usage can remain unavailable when the provider does not expose token metrics; the UI will show that as unavailable rather than inventing a number.

Optional external integrations:

| Variables | Purpose | Safety boundary |
|---|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | Outbound email | SMTP with TLS; only via approved outbox execution |
| `DEPLOY_WEBHOOK_URL`, `DEPLOY_WEBHOOK_TOKEN` | Website deployment trigger | HTTPS only; only via approved outbox execution |
| `BANGKAH_API_TOKEN` | Protect all API reads and writes | Bearer token; kept in game memory for the current session |
| `BANGKAH_HOST`, `BANGKAH_PORT` | Local API bind | Host must remain loopback; default port 8765 |
| `BANGKAH_OWNER_PASSWORD` | Owner workstation password for Bangkah OS | Generated into `backend/data/owner_credentials.local` when left empty; never committed |
| `BANGKAH_DESKTOP_SESSION_HOURS` | Desktop session lifetime in hours | Default 8 |
| `BANGKAH_TERMINAL_ALLOWED_BINARIES` | Allowlist for external terminal binaries | Empty = builtin commands only; argv-resolved paths, no shell metacharacters |
| `BANGKAH_DOMAIN` | Company domain shown in system info | DNS / email state is reported honestly as unmanaged |

External email and deployment are intentionally not preconfigured. Do not put passwords, provider tokens or private keys in Paper content, chat messages, approval payloads or source files. Put secrets only in `backend/.env`, which is excluded from the release package and version control.

For remote access, keep the Python service bound to `127.0.0.1`, configure `BANGKAH_API_TOKEN`, and expose the API through a TLS reverse proxy. Do not expose the plain HTTP backend directly to a network.

## Documentation

- `docs/API-REFERENCE.md` — API routes, request fields and response behavior.
- `docs/WORKSTATION-AND-DESKTOP.md` — workstation slice, Bangkah OS apps, sandbox terminal and audit design.
- `docs/OPERATIONS-AND-SECURITY.md` — setup, secrets, networking and external action safety.
- `docs/FINAL-ACCEPTANCE.md` — delivered scope, automated test evidence and manual runtime acceptance checklist.
- `docs/SRS-V1.3-TRACEABILITY.md` — requirement coverage and gaps.
- `docs/BACKEND-INTEGRATION.md` — Godot / Python boundaries and data flow.
- `docs/ARCHITECTURE.md` — system architecture.
- `docs/ENVIRONMENT-DESIGN.md` — office layout, room program and interaction design.
- `docs/CONTROLS-AND-CAMERA.md` — player movement and camera.
- `docs/NPC-BEHAVIOR.md` — NPC state authority, role routines and movement.
- `docs/VISUAL-STYLE-GUIDE.md` — material, lighting, model and interface direction.
- `docs/ASSET-REGISTER.md` — included assets and external asset policy.
- `docs/CHANGELOG.md` — release history.

## Project structure

```text
Bangkah-Godot-Company-Simulator/
├── godot/                    # Native Godot 4 game client
│   ├── scenes/
│   ├── scripts/
│   └── assets/characters/    # Optional user-supplied GLB slots
├── backend/                  # Python API, agent factory and SQLite workflows
│   ├── core/
│   ├── tests/
│   ├── .env.example
│   └── office_server.py
├── docs/                     # Operations, design and acceptance documentation
├── design-preview/           # Concept-art and floor-plan preview
├── tools/                    # Bundle validation
├── start_backend.bat
├── start_backend.sh
├── run_godot.bat
└── run_godot.sh
```

## Validation and honest limitations

- Backend unit suite: **71 tests passed** in the latest full run (the workstation slice added 15 tests to the previous 56).
- Python compile check: passed.
- Live desktop/workstation HTTP runtime check: `backend/tools/check_desktop_api.py` executes the real routes with real authentication, terminal and sandbox filesystem behavior — **17/17 checks passed**.
- Headless Godot runtime checks on the build machine (Godot 4.7.2): main scene boots without script errors, and `godot/scripts/workstation_ui_check.gd` drives the workstation sit/login/OS/stand-up state machine — **20/20 checks passed**.
- HTTP API smoke test: status, usage, tasks, evidence-required completion, meetings, Paper, PDF download, approvals, outbox, audit cursor and authenticated API access passed using an isolated test server. LLM/provider calls were not invoked by that smoke test.
- Static bundle validation: passed after runtime data and local secrets were removed.
- **Automated caveat recorded during the build:** the build sandbox blocks Godot's loopback TCP connections (an environment-level network rule; Godot could still reach external hosts). Desktop HTTP responses were therefore validated in Godot against recorded real-backend payloads while live HTTP was proven by the Python runtime check. Run the interactive workstation flow once on the target machine as part of `docs/FINAL-ACCEPTANCE.md`.
- Rigged GLB characters are supported by the loader but not bundled. Character visuals currently use procedural meshes.
- Employee workstation accounts exist in the catalogue but are inactive; activating them (account + app set + sandbox seed) is the next slice, and the architecture is shared with OWNER-PC-001.
- NPC navigation is waypoint-based local steering, not full NavigationAgent3D / NavigationMesh pathfinding.
- The Boardroom world preview is visual only. Persisted agenda / minutes / decisions are created through Company UI and backend records.
- Deployment reconciliation / rollback, automated purchase execution, and full production telemetry are outside this Desktop MVP release.

This release is a complete **local single-Owner desktop MVP** with an auditable operations backend. It is not a claim of full SRS v1.3 certification or production readiness without target-machine Godot acceptance testing and real provider configuration.
