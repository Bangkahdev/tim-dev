# Bangkah Company Simulator API Reference

Base URL: `http://127.0.0.1:8765`  
Content type for JSON mutations: `application/json`  
All responses are UTF-8 JSON unless noted.

## Authentication

Every `/api/*` route except `POST /api/auth/login` requires a verified company session:

```http
Authorization: Bearer <session token>
```

- `POST /api/auth/login` with `{"username":"...","password":"..."}` returns `{"success":true,"session":{"token":"...","username":"...","role":"..."}}`.
- `GET /api/auth/me` returns the current user; `POST /api/auth/logout` revokes the session token.
- Missing, invalid, expired, revoked or disabled-account sessions receive `401`. A valid session without the required permission receives `403`.
- There is no anonymous Owner and no implicit loopback bypass.
- Sessions expire after `BANGKAH_SESSION_HOURS` (default 8). Role, employee and department are read from the database on every request, so disabling an account or changing a role takes effect immediately.
- The first owner is created by `ensure_bootstrap_owner()` at server start: it uses `BANGKAH_OWNER_PASSWORD` when set, otherwise generates a password into `backend/data/owner_auth_password.local` (never committed).

A shared `BANGKAH_API_TOKEN` is not an identity by itself. For legacy clients, an operator must explicitly opt in with `BANGKAH_LEGACY_TOKEN_ROLE=owner|secretary|manager|employee|admin`; without it the shared token is rejected.

### Roles and scope

| Role | Summary |
|---|---|
| `owner` | Full access, including approvals, outbox execution/reconciliation and external writes. |
| `secretary` | Company operations, meetings, Papers, approvals (create), audit read; scoped to executive, operations, front office and promotion. |
| `manager` | Task assignment and transitions, meetings, Papers, approvals (create), project runs, audit read; every department except reserved owner-only actions; no external write. |
| `employee` | Read company data, transition own assigned tasks, use the team chat and their workstation; no task creation, audit, outbox or approval access. |
| `admin` | Legacy operations role kept for existing installations; never receives owner-only permissions. |

Department scope is enforced for task assignment/transition, employee listings and the "owner-only" routes. Employees only see their own tasks, their own employee record and projects linked to their assigned tasks.

The backend only binds to loopback. For remote access, place it behind a TLS reverse proxy and preserve the Authorization header. Request bodies are limited to 100 KB. Error responses use `{"error":"..."}` and do not intentionally return environment secrets.

## Read endpoints

| Method / path | Purpose | Response |
|---|---|---|
| `GET /api/status` | Combined live health, legacy office snapshot and company snapshot | `ollama`, `active`, `projects`, `health`, `office`, `company` |
| `GET /api/departments` | Department catalogue | `departments[]` |
| `GET /api/employees` | Employee roster, department and active task | `employees[]` |
| `GET /api/projects` | Latest project state files detected under workspace | `projects[]` |
| `GET /api/tasks` | Persisted tasks with acceptance criteria and evidence | `tasks[]` |
| `GET /api/meetings` | Persisted meetings, attendees, minutes, decisions and follow-ups | `meetings[]` |
| `GET /api/papers[?status=unread]` | Paper inbox | `papers[]` |
| `GET /api/papers/{paper_id}` | One Paper and body | `paper` |
| `GET /api/approvals[?status=pending]` | Approval records including exact review payload and SHA-256 | `approvals[]` |
| `GET /api/outbox` | Approved external action queue and delivery state | `outbox[]` |
| `GET /api/print-jobs` | PDF generation records | `print_jobs[]` |
| `GET /api/print-jobs/{job_id}` | One print job | `print_job` |
| `GET /api/print-jobs/{job_id}/download` | Download generated PDF | `application/pdf` |
| `GET /api/audit?after_id=0&limit=100` | Audit events | `events[]`, `next_after_id` |
| `GET /api/events?after_id=0&limit=100` | Cursor-based event retrieval (polling; not WebSocket) | `events[]`, `next_after_id` |
| `GET /api/usage` | Model usage where provider reports metrics | `usage` with totals and employee metrics |
| `GET /api/office/state` | Legacy office snapshot | Snapshot object |
| `GET /api/office/player` | Saved Owner position | `player` |
| `GET /api/chat/history?channel=team` | Persisted chat history | `channel_id`, `messages[]` |
| `GET /api/knowledge/documents` | Knowledge documents | `documents[]` |
| `GET /api/knowledge/search?q=...` | Knowledge retrieval | `query`, `results[]` |
| `GET /api/workstations` | Workstation catalogue with room and account binding | `workstations[]` each with `account{id,name,role,active,apps}` |
| `GET /api/workstations/{id}` | One workstation summary | `workstation`, `account`, `workspace` |
| `GET /api/desktop/audit?after_id=0&limit=12` | Workstation audit trail | `events[]`, `next_after_id` |
| `GET /api/office/activity?after_id=0&limit=100` | Employee workshift feed (audited events by employees) | `events[]`, `next_after_id`, `summary` |
| `POST /api/office/activity/tick` | Manual workshift tick | `{"success", "activity"}` |

## Workstation desktop sessions (Bangkah OS)

Physical workstations are backed by `backend/core/workstations.py`. Logging in at a workstation starts a desktop session that is separate from the company `Authorization: Bearer` token. `OWNER-PC-001` and all seven employee desks (`PC-MGT-001`, `PC-MGT-002`, `PC-ARC-001`, `PC-BE-001`, `PC-API-001`, `PC-FE-001`, `PC-QA-001`) are active; each employee has a real login at their own desk (credentials in `backend/data/employee_credentials.local` or the shared `BANGKAH_EMPLOYEE_PASSWORD`). `BANGKAH_EMPLOYEE_ACCOUNTS=0` freezes employee logins back to inactive.

`POST /api/workstations/{id}/login`

```json
{"account_id": "owner", "password": "..."}
```

Responds `201` with the one-time session token (only its SHA-256 is stored) plus app list; other codes return `{"error"}` (400 wrong password / inactive account / throttle).

Desktop routes require the header `X-Desktop-Session: <token>`. When `Authorization: Bearer` is configured, both headers are checked:

- `POST /api/desktop/session/close` — logout, audited.
- `GET /api/desktop/session` — current session, account, workstation, apps, expiry.
- `GET /api/desktop/system` — system, sandbox terminal and truthful integration rows (`configured: false` when not configured, `dns_managed: false` / `email_provisioned: false` for the domain).
- `GET /api/desktop/files?path=.` — sandbox directory listing relative to the workstation folder.
- `GET /api/desktop/files/content?path=README.md` — read a text file.
- `POST /api/desktop/files/write` — `{"path": "notes.txt", "content": "..."}`, constrained to the workstation sandbox folder.
- `POST /api/terminal/exec` — `{"command": "ls"}` runs a builtin argv-only command. No host shell shell metacharacters; external binaries run only when allowlisted through `BANGKAH_TERMINAL_ALLOWED_BINARIES`.

Login, file writes, terminal commands and session events are recorded in the company audit trail and surfaced through `GET /api/desktop/audit`.

### Employee workshift engine

Driven by `/api/status` (rate-limited tick, exposed under `activity_engine`) and the manual endpoint:

- `GET /api/office/activity?after_id=0&limit=100` — every audited event whose actor is an employee (`employee_login`, `employee_work`, `desktop_login`, `desktop_file_write`, `terminal_exec`, `desktop_close`, ...) plus a per-employee summary (`units_done`, `units_today`, `last_tick_at`, `last_detail`).
- `POST /api/office/activity/tick` — body `{"force": true, "ignore_window": true}`. `force` bypasses the tick throttle (`BANGKAH_EMPLOYEE_TICK_SECONDS`, default 20); `ignore_window` works outside `BANGKAH_EMPLOYEE_DUTY_HOURS` (default `9-17`). Returns `{"success", "activity"}` with `units[]`, `on_shift[]`, `off_shift[]`, `errors[]`, `overtime` and `skipped`.

Engine state lives in `employee_workshift` (per-employee status, unit counters, day, last detail); employees with live 3D interactions are left alone, and shift end closes sessions. `BANGKAH_EMPLOYEE_ACTIVITY=0` disables the engine.

## Company mutations

All mutations require an authenticated session with the matching permission. The acting user is taken from the session, never from the request body. The backend validates transitions and arguments; the Godot client is not the authority.

### Tasks

`POST /api/tasks`

```json
{
  "title": "Implement user profile endpoint",
  "description": "Add GET and PATCH profile routes",
  "assignee_id": "backend",
  "priority": "high",
  "project_key": "company-portal",
  "acceptance_criteria": "Routes are covered by tests and API docs"
}
```

`POST /api/tasks/{task_id}/transition`

```json
{
  "status": "completed",
  "note": "Implementation and QA verified",
  "evidence": [
    {"type": "pull_request", "reference": "https://git.example/repo/pull/14", "note": "Tests passed"}
  ]
}
```

Allowed transitions: `pending → in_progress|cancelled`; `in_progress → blocked|completed|failed|cancelled`; `blocked → in_progress|cancelled|failed`; `failed → pending`. Completion requires at least one evidence object with a non-empty reference.

### Meetings

`POST /api/meetings` accepts `title`, `attendee_ids[]`, `agenda`, and `room_id`.

- `POST /api/meetings/{id}/start` changes `scheduled` to `in_progress`.
- `POST /api/meetings/{id}/complete` requires `minutes` and may include `decisions[]` / `followups[]`.
- `POST /api/meetings/{id}/cancel` changes `scheduled` or `in_progress` to `cancelled`.

### Papers and PDF print jobs

`POST /api/papers` accepts `title`, `body`, `paper_type`, `origin`, `priority`, optional `related_task_id`, and optional `approval_id`.

`POST /api/papers/{paper_id}/review` accepts a Paper status such as `read`, `deferred`, or `archived`. A Paper linked to an approval cannot be independently approved/rejected; decide the linked approval instead.

`POST /api/print-jobs` accepts `paper_id` and produces a PDF PrintJob. A completed job can be retrieved from `/api/print-jobs/{id}/download`.

### Approval and outbox

`POST /api/approvals` accepts:

```json
{
  "action_type": "email.send",
  "summary": "Send the approved project status to the client",
  "payload": {
    "to": "client@example.com",
    "subject": "Project status",
    "body": "The reviewed release candidate is ready."
  }
}
```

Supported action types: `email.send`, `website.deploy`, `expense.purchase`.

- `POST /api/approvals/{id}/approve` creates one queued outbox item.
- `POST /api/approvals/{id}/reject` rejects the request.
- `POST /api/outbox/{id}/execute` executes an approved email / deployment adapter. The Owner must explicitly invoke this endpoint after approval. A definitive failure schedules an exponential backoff (`next_retry_at`); an early call is refused.
- `POST /api/outbox/retry-due` executes only failed items whose backoff window has elapsed.
- `POST /api/outbox/{id}/reconcile` accepts `outcome` (`succeeded`/`failed`), `note` (required verification note) and optional `external_id`. It records the verified provider result without re-sending; a succeeded result is final.
- `POST /api/outbox/{id}/requeue` resets an exhausted `failed` item to `queued` for a deliberate fresh run.

Approval payload JSON is canonicalized, SHA-256 hashed and protected by a database trigger against modification. Secrets are rejected from approval payloads. Email and deployment actions require provider configuration. Purchases remain `awaiting_executor` for manual handling. Uncertain provider results become `unknown` and must be reconciled manually before any retry.

Retry policy is configured with `OUTBOX_MAX_ATTEMPTS` (default 5), `OUTBOX_BACKOFF_SECONDS` (default 30) and `OUTBOX_BACKOFF_MAX_SECONDS` (default 3600). Backoff is `base * 2^(attempts-1)`, capped. When attempts are exhausted `next_retry_at` is cleared and execution is refused until an operator reconciles or requeues the item.

## Legacy / agent routes

The pre-existing agent endpoints are preserved:

- `POST /api/command`
- `POST /api/chat`
- `POST /api/employee-chat`
- `POST /api/room-chat`
- `POST /api/office/action`
- `POST /api/office/player`
- `POST /api/knowledge/documents`

These routes continue to use the existing Orchestrator, office tools, CrewAI pipeline and knowledge store. They are not a replacement for approval gates around external actions.

## Important omissions

This release does not expose a WebSocket replay endpoint, full organization CRUD, a task delegation engine, a website rollback API, automated purchasing, or a general plugin registry. `/api/events` is cursor polling, not a WebSocket implementation. Web sessions are separate from workstation desktop sessions (`X-Desktop-Session`), which remain scoped to a physical workstation and its apps.
