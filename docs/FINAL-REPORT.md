# Final Report — Bangkah Desktop MVP 1.0 (Milestones 1–3)

**Date:** 2026-11-19
**Repo:** https://github.com/Bangkahdev/tim-dev
**Branch:** `main` (origin/main = e325962 after PR #38/39; CHANGELOG commit 76b3088 pending PR #40)

## Summary

| Milestone | Scope | Status | Evidence |
|-----------|-------|--------|----------|
| M1 | Real-agent acceptance (CrewAI + Ollama qwen2.5-coder:7b under bwrap), 3 consecutive passes | **PASS** (3/3, 3 attempts, no repair loop) | `docs/MILESTONE-1-EVIDENCE.md`, `backend/workspace/projects/milestone1-logs-20261119-034217/` |
| M2 | External actions end-to-end (approval → outbox → execute → delivery) | **PASS** (earlier, PR #37) | `docs/MILESTONE-2-EVIDENCE.md` |
| M3 | Godot Owner session login/logout; legacy static token optional, session login default; logout revokes server session | **PASS** (code merged PR #39; docs PR #40 pending CI) | `docs/MILESTONE-3-EVIDENCE.md`, `docs/MILESTONE-3-PLAYBOOK.md` |

### M1 — Real-agent acceptance (locked, do not rerun)

- **3/3 consecutive PASS** in 3 attempts, no repair loop, no scaffold (`tests_source=None`, `repair_rounds=None`).
- Hidden verifier: 11/11 all attempts; independent verifier `OVERALL_VERIFIABLE` PASS.
- Fresh-process restart persistence: PASS (new Python process reopened run DB after Paper delivery).
- Sandbox canaries: FS isolated + network isolated + outside-sandbox control reachable.
- Manual isolation probe transcript: `backend/workspace/projects/sandbox-manual-evidence-20261119-033948.txt`.
- Papers/PrintJobs: `PAP-5731D880F7E5`/`PRN-CB6B75236850`, `PAP-5E9583817A8F`/`PRN-05CB4AB0174A`, `PAP-353900131A5C`/`PRN-C5063D06620E`.
- Full backend suite: **214 passed in 105.39s** (`backend/workspace/pytest-full-20261119-034311.log`).
- PR #38 merged (CI green). Honest note: verifier's `verify.sandbox.fs_network_isolation_NFR_SEC_09_10` key is `False` by design (cannot inspect host wrapper); runner records operator `--external-sandbox` evidence + canaries + manual probes. Docker daemon unavailable on host (iptables/NAT failure); bwrap is the sandbox evidence path.

### M3 — Godot Owner session login/logout

- `godot/scripts/company_ui.gd`: Settings panel drives Owner login via `POST /api/auth/login`; session token held in memory and emitted to `connect_backend_requested`; LOGOUT SESI button calls `POST /api/auth/logout` and emits `disconnect_backend_requested`. Static bearer token kept as explicit loopback-only legacy path behind `BANGKAH_LEGACY_TOKEN_ROLE`.
- `godot/scripts/main.gd`: wires `disconnect_backend_requested` to clear `_api_token` and mark connection offline.
- `godot/scripts/auth_login_check.gd`: headless acceptance — wrong password rejected (401, no session), valid login → `/api/auth/me` 200, logout → old token 401 (revoked).
- `backend/tools/check_godot_auth.py`: starts `office_server` on throwaway port with fresh DB, runs Godot check, cleans up on success. **GODOT-AUTH-CHECK: PASS** (also re-verified after removing `BANGKAH_LEGACY_TOKEN_ROLE=owner` from local `.env`).
- Regression: backend pytest **214 passed**; `workstation_ui_check.gd` failures=0; `feature_v11_check.gd` failures=0; GDScript syntax checks exit 0.
- `BANGKAH_LEGACY_TOKEN_ROLE=owner` removed from local `backend/.env` (gitignored, not committed); session login is the default. `.env.example` and README retain documentation of the optional legacy role.
- PR #39 merged (CI green); PR #40 (CHANGELOG docs) CI running / auto-merge pending.

## Documentation reconciliation

- `docs/MILESTONE-3-PLAYBOOK.md` — M3 acceptance contract, how to run, honesty boundary.
- `docs/MILESTONE-3-EVIDENCE.md` — M3 evidence, per-requirement results, regression checks.
- `docs/CHANGELOG.md` — M1, M3 entries at top.
- `README.md` — Godot headless checks updated to 22/22 workstation + M3 auth_login_check PASS.
- `docs/FINAL-ACCEPTANCE.md` — added M3 row to automated verification table.
- `docs/SRS-V1.3-TRACEABILITY.md` — added M3 note to acceptance boundaries (NFR-SEC session revoke on logout).

## Operator-side items (not executed — require credentials/domain/host access)

1. **Docker host fix:** `docker.service` fails with `iptables ... nat-PREROUTING: CHAIN_ADD failed`. Requires sudo/host firewall/NAT fix before claiming the Docker wrapper path. bwrap is the documented equivalent sandbox; do not silently fall back to no sandbox.
2. **Cloud-model execution:** no cloud keys/tokens configured; local Ollama `qwen2.5-coder:7b` is the documented equivalent. `DAILY_TOKEN_BUDGET` is not implemented (local Ollama has no token cost).
3. **Cloudflare email inbound:** requires Cloudflare account/domain credentials; SMTP adapter tested with mocks only.
4. **Real deployment / public TLS:** requires domain control and TLS reverse proxy; backend binds to loopback only. Deployment webhook adapter validated with mocks/self-signed cert only.
5. **nomic-embed-text:** not installed in Ollama; not used by this MVP.
6. **Manual Godot visual check:** rendering, input feel, animation timing, FPS remain `MANUAL_REQUIRED` (see `docs/FINAL-ACCEPTANCE.md` manual checklist).

## Evidence retention (USB workspace)

- M1 logs: `backend/workspace/projects/milestone1-logs-20261119-034217/` (+ console log, per-attempt DBs, prints, preflight canaries)
- M1 manual probe: `backend/workspace/projects/sandbox-manual-evidence-20261119-033948.txt`
- Full suite log: `backend/workspace/pytest-full-20261119-034311.log`
- M3 evidence dir (kept only on failure): `backend/workspace/godot-auth-check-*` (removed on success)
- M3 pytest log: `backend/workspace/pytest-m3-20261119-035036.log`

## What remains before production use

- Owner completes the `docs/FINAL-ACCEPTANCE.md` target-machine runtime checklist (interactive Godot flow, FPS, etc.).
- Operator resolves the Docker host NAT/iptables issue (or keeps bwrap as sandbox path).
- Operator provisions Cloudflare email, domain, and TLS reverse proxy if remote access is needed.
