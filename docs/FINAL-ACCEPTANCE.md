# Final Desktop MVP 1.0 — Acceptance Record

## Release definition

This is the final delivered **local single-Owner desktop MVP** for Bangkah Company Simulator. It includes the Godot walkable HQ, Python backend, persistent company-operation workflows, approval/outbox boundary, Paper-to-PDF flow, API reference, operations guide, unit tests and release scripts.

It is not certified as full SRS v1.3 compliance. The scope below separates implementation from runtime verification and externally configured behavior.

## Delivered and automated verification

| Area | Evidence | Result |
|---|---|---|
| Company departments / employee mapping | `backend/tests/test_company_operations.py` | Passed |
| Task state machine and evidence gate | `backend/tests/test_company_operations.py` | Passed |
| Meeting lifecycle, minutes, decisions and follow-ups | `backend/tests/test_company_operations.py` | Passed |
| Paper lifecycle and PDF generation | ReportLab PDF signature test | Passed |
| Immutable approval payload and SHA-256 check | SQLite trigger and integrity tests | Passed |
| Approval-to-outbox creation and one-way review | Unit tests | Passed |
| Outbox claim, unknown state and manual purchase boundary | Unit tests | Passed |
| SMTP TLS adapter | Mocked SMTP adapter tests | Passed |
| Deployment HTTPS validation | Adapter tests | Passed |
| Workstation catalogue, login, throttle, session lifetime | `backend/tests/test_workstations.py` | Passed |
| Workstation sandbox filesystem, argv terminal, audit honesty | `backend/tests/test_workstations.py` | Passed |
| Employee workstation accounts, activation gate and credential provision | `backend/tests/test_workstations.py` | Passed |
| Employee workshift engine: login, files, audit feed, duty window | `backend/tests/test_employee_activity.py` | Passed |
| Python syntax compilation | `python -m compileall -q backend` | Passed |
| Backend unit suite | `python -m pytest -q` | 85 passed |
| HTTP route integration | Isolated local HTTP smoke test | Passed |
| Workstation desktop live HTTP check | `backend/tools/check_desktop_api.py` | 21/21 passed |
| Godot headless boot and workstation UI state machine | `godot/scripts/workstation_ui_check.gd` (Godot 4.7.2 headless) | 22/22 passed |
| Static Godot resource references / docs / package hygiene | `python tools/validate_bundle.py` | Passed |

The HTTP smoke test uses a fake `crewai` import because the exercised endpoints do not call the LLM. It does not prove a real provider has been configured or that coding agents can complete an external project. SMTP and deployment adapter tests use mocks / configuration validation; no real email or website deployment was triggered. The desktop HTTP runtime check runs the real server routes over loopback, including the employee workshift tick and audited feed; the Godot script validates the client state machine against recorded real-backend response shapes because the build sandbox blocks Godot-to-loopback sockets (details in `docs/WORKSTATION-AND-DESKTOP.md`).

## Manual desktop acceptance still required

Godot itself is now available in the build environment (4.7.2 headless), and the automated headless checks above already cover script parsing, scene boot and the workstation state machine. The interactive checks below — rendering, input feel, animation timing, FPS — still require the target desktop and remain **not marked passed**.

- [ ] Project imports in Godot 4.3+ with no script parse or resource errors.
- [ ] Main scene starts in third-person with the Owner avatar visible.
- [ ] `V` switches first-person / third-person, camera collision and mouse look behave correctly.
- [ ] WASD, sprint, jump, `E`, `Esc` and cursor recapture work.
- [ ] Owner can reach reception, each department, boardroom, archive and pantry without clipping through walls or furniture.
- [ ] NPC waypoint routines do not repeatedly overlap, oscillate or walk through closed partitions.
- [ ] Working / blocked / failed states follow backend status and do not get overwritten by ambient routines.
- [ ] Local Boardroom preview completes and returns participants without changing persisted meeting status.
- [ ] Company UI can create, start, block, resume, cancel and complete tasks; completion rejects missing evidence.
- [ ] Meeting UI can schedule, start, cancel and complete; minutes, decisions and follow-ups persist after restart.
- [ ] Paper creation, review and PDF print job work; a PDF can be downloaded and opened from the client.
- [ ] Approval UI exposes the exact payload and hash before decision; reject does not create an outbox item.
- [ ] Approve creates one outbox item; explicit execution sends only after approval.
- [ ] API token protects GET, POST and PDF download routes when configured.
- [ ] Owner walks to a workstation desk, presses `E`, sits with the sit animation and the camera lands on the monitor.
- [ ] Bangkah OS login accepts the Owner password once and refuses a wrong password with the backend message; fails and throttle states surface honestly.
- [ ] Employee desks open Bangkah OS too; the login account is prefilled per desk and the dock follows the account's apps (employee: files/terminal/company only).
- [ ] Files lists the seeded sandbox folder, opens README.md and saves an edited file (write appears in the workstation audit).
- [ ] Terminal accepts builtin commands, echoes output/exit codes and refuses shell chaining / path traversal.
- [ ] Infrastructure shows `ABSENT` for unconfigured SMTP / deploy / API token and `DNS tidak dikelola` for the domain.
- [ ] `ESC` stands the Owner up with the stand-up animation, restores the office HUD; sitting again resumes the session; `LOGOUT` closes it for real.
- [ ] With the backend running during office hours, employees appear logged-in at their desks working; polling `/api/office/activity` shows `employee_work` units appearing for them.
- [ ] Offline exploration remains usable and business actions clearly report the unavailable backend.
- [ ] FPS and 1% low are measured in reception, Engineering and boardroom with hardware / renderer recorded.

## Known implementation boundaries

- Procedural humanoid meshes are used by default. Optional GLB loaders are included, but external rigged character assets are not bundled.
- NPC pathing uses authored waypoints with local steering, not a complete NavigationAgent3D / NavigationMesh crowd system.
- The local 3D Boardroom preview is visual; the separate meeting records are the persisted business record.
- The event feed uses cursor-based HTTP polling. No WebSocket replay/reconnect endpoint is included.
- Owner identity is a single local Owner. Workstation desktop sessions exist for physical stations (logout closes them), but there is no general web account system or multi-user RBAC.
- Task completion evidence is validated as a non-empty reference and note object; the backend does not fetch or independently verify an external Git / CI URL.
- SMTP / webhook integrations require configuration and provider-side testing. No credentials or real provider state are included in the archive.
- Purchases remain manual; no payment provider is integrated.
- Full process/container sandboxing and formal per-agent egress restrictions remain outside this MVP.

## Release packaging checklist

- [x] `.env.example` is included.
- [x] Real `.env` and credentials are excluded.
- [x] Local database and generated print files are excluded.
- [x] Python cache and pytest cache are excluded.
- [x] Godot project, scripts, docs, tests and launch scripts are included.
- [x] Root README and API / operations docs describe the actual release boundary.
- [ ] Target-machine runtime checklist above completed by Owner before production use.
