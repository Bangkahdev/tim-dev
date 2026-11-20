# WS2 Evidence — Quick Security Fixes

**Date:** 2026-11-20
**Status:** **PASS for the WS2 acceptance contract** against a local backend.
This covers error-response hygiene, shared route error handling, persistent
login throttling, and distinct Godot login messages for HTTP 401 and 429.

## Scope and changes

| Item | Change | Files |
| --- | --- | --- |
| Raw error messages | Chat/orchestrator failures now return a generic message plus a `correlation_id`; the exception detail stays on server stdout | `backend/office_server.py` |
| Shared route handling | `infra/service/start|stop`, `ftp/provision`, `mail/provision`, `network/subnet|scope|lease|vpn/peer`: `ValueError` → 400, other exceptions → generic 500 + `correlation_id` | `backend/office_server.py` |
| Persistent login throttle | `_ATTEMPTS` dict replaced by SQLite table `auth_login_attempts`; counters survive process restart | `backend/core/auth/sessions.py` |
| Godot login messages | 401 shows "Username atau kata sandi salah."; 429 shows "Terlalu banyak percobaan login, coba lagi N detik lagi." using `Retry-After` | `godot/scripts/company_ui.gd` |
| Acceptance checks | Fuzz/persistence tests; Godot check asserts both messages | `backend/tests/test_ws2_security_hardening.py`, `godot/scripts/auth_login_check.gd` |

## Evidence

Environment: Linux host, Python 3.12.16 (uv-managed), `PYTHONPATH=.pylibs:.`.
Backend runs as the real `office_server.OfficeHandler` on an ephemeral port.

### Invalid-input fuzz

`tests/test_ws2_security_hardening.py` sends 21 invalid or hostile payloads to
each of the seven POST routes above (147 route/payload subtests total). Every
request returns an HTTP status without a dropped connection, and no response
contains a traceback, `Exception`, `ValueError`, `sqlite3.*`, `File "`, or any
other raw exception marker. Generic 500 responses carry a `correlation_id`.

### Persistent lockout

Five failed logins for one username/IP pair write `count` and `lock_until` to
`auth_login_attempts`. Re-running `sessions._init()` (simulating a backend
restart) does not clear them: the next attempt still raises `LoginThrottled`
with `Retry-After` semantics. A successful login deletes the persisted
counters.

### Godot messages

`tools/check_godot_auth.py` (headless Godot against a temporary local backend):

```text
AUTH-CHECK-DETAIL: Username atau kata sandi salah.
...
AUTH-CHECK-DETAIL: Terlalu banyak percobaan login, coba lagi 899 detik lagi.
GODOT-AUTH-CHECK: PASS
```

`godot/scripts/auth_login_check.gd` also fails if the 401 text is generic or if
the 429 text is missing after the lockout threshold.

### Full regression

Run from `backend/`:

```bash
PYTHONPATH=.pylibs:. python3.12 -m pytest tests ../it --ignore=workspace -q
```

Final tree result:

```text
217 passed, 147 subtests passed in 85.75s (0:01:25)
```

Log: `backend/workspace/pytest-ws2-final-20261120-181148.log`.

Additional Godot checks: `workstation_ui_check.gd` and `feature_v11_check.gd`
both report `RESULT failures=0`; `auth_login_check.gd` and `company_ui.gd`
pass `--check-only` syntax validation.

## Honesty boundary

All checks run against a local backend on loopback. No cloud model, public
deployment, or external mail provider is involved. The manual Godot checklist
(tray/Paper/character status) remains **MANUAL_REQUIRED** under WS8 and is not
claimed here.
