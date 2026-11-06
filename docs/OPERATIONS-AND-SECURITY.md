# Operations and Security

## Local deployment model

The supported release topology is one Owner desktop running the Godot client and a Python backend bound to `127.0.0.1:8765`. SQLite stores office and company operation records under `backend/data/`. Generated PDF files are stored under `backend/data/prints/`. Agent logs, reports and workspaces remain under the backend directory and are excluded from the release ZIP.

The backend refuses direct non-loopback binding. Every `/api/*` route except `/api/auth/login` requires a company session; place an HTTPS reverse proxy in front of remote access and forward the `Authorization` header with request size / rate limits. Never expose the Python HTTP server directly on a public interface.

## First run

1. Run `start_backend.bat` or `start_backend.sh` from the extracted project root.
2. The start script creates a virtual environment and installs `backend/requirements.txt`.
3. On first launch, `backend/.env.example` is copied to `backend/.env`; configure model variables and provider keys.
4. Start the backend again. Keep its console open. On an empty database the server creates the first `owner` account: it uses `BANGKAH_OWNER_PASSWORD` if set, otherwise writes a generated password to `backend/data/owner_auth_password.local`.
5. Launch `godot/project.godot` in Godot 4.3+. The web UI shows a login gate and stores only the session token.
6. Log in through `POST /api/auth/login` (or the UI). There is no anonymous access and no implicit Owner identity.

## Accounts, sessions and roles

- Passwords are hashed with bcrypt. Sessions are random 32-byte tokens; only server-side state decides validity. Sessions expire after `BANGKAH_SESSION_HOURS` (default 8), can be revoked, and are rejected when the account is disabled.
- Roles: `owner`, `secretary`, `manager`, `employee` (plus legacy `admin` with operations rights but no owner-only permissions).
- Authorization combines role permission, department scope, task assignment/ownership, project access and approval authority. `POST /api/approvals/{id}/approve|reject` is owner-only, and the reviewer is the authenticated session user.
- Actions are attributed to the authenticated user. Request body fields such as `actor` are ignored.
- Manage accounts with `core.auth.sessions.create_user`, `set_user_enabled` and `set_user_role`. Employee accounts can be linked to a roster id and department.

## Secrets

- Keep provider keys, SMTP credentials and deployment tokens only in `backend/.env` or a stronger secret store used by the host.
- Do not paste secrets into chat, Paper, approval payloads, knowledge documents, task evidence or source code.
- `.env`, SQLite databases, generated PDFs, logs, reports, workspaces and `owner_auth_password.local` are gitignored and excluded from the release archive.
- The Godot client keeps the API/session credential in memory only.
- A shared `BANGKAH_API_TOKEN` is not accepted as an identity unless the operator sets `BANGKAH_LEGACY_TOKEN_ROLE` explicitly. Prefer real sessions.

## External action safety

External side effects follow a three-step process:

1. A request is stored as an approval with a canonical immutable payload and SHA-256 digest.
2. The Owner reviews the exact payload in the game and approves or rejects it.
3. An approved request creates an outbox item. A separate explicit Owner action starts execution.

Email uses SMTP with TLS. The deployment adapter only accepts an HTTPS webhook URL and sends a bearer token plus an idempotency key. The webhook provider must honor that idempotency key to prevent duplicate deployment requests. Purchase actions are never auto-completed; they are marked `awaiting_executor` for manual handling.

If a remote connection ends after a provider may have accepted a request, the outbox is marked `unknown`. The system never auto-retries an unknown result. The operator inspects the provider and calls `POST /api/outbox/{id}/reconcile` with the verified outcome and a note; reconciliation records the decision without re-sending and a `succeeded` result is final.

A definitive failure is retryable with exponential backoff. `OUTBOX_MAX_ATTEMPTS` (default 5), `OUTBOX_BACKOFF_SECONDS` (default 30) and `OUTBOX_BACKOFF_MAX_SECONDS` (default 3600) control the policy. `next_retry_at` is stored on the item, an early execution is refused, and `POST /api/outbox/retry-due` runs only items whose window has elapsed. Once attempts are exhausted the item stops retrying and must be reconciled or explicitly requeued with `POST /api/outbox/{id}/requeue`. Every execution, scheduled retry, reconciliation and requeue is written to the audit trail.

## Data and recovery

- Back up `backend/data/` while the backend is stopped. It contains the SQLite database and generated PDF files.
- Back up `backend/workspace/`, `backend/reports/` and `backend/logs/` separately if project source and run history should be retained.
- Do not replace the whole data directory with an older backup while the application is running.
- Audit events are append-oriented records. Database backups are still required; this local release does not replicate to a remote store.

## Model privacy and costs

A local Ollama model keeps prompts on the local machine, subject to the configured model/runtime. A cloud model provider receives prompts and relevant context and may incur token charges. Set model provider, model name and repair-round limits deliberately. Model token totals may be unavailable if the provider does not expose usage metadata.

## Security boundary and known gaps

- This is a local single-company MVP. It now has real logins, short-lived revocable sessions and role/department enforcement, but it is not a hardened internet-facing multi-tenant service.
- Account administration is local (`create_user`, `set_user_enabled`, `set_user_role`); there is no public user-management HTTP API yet.
- There is no full subprocess/container sandbox or per-agent filesystem/network isolation in this release.
- RAG content is context, not authorization. Tool allowlists in the legacy Orchestrator remain the control point for tool invocation.
- Email and deployment adapters are opt-in and require real provider credentials. The package contains no credentials and has not sent a real message or deployment.
- The Boardroom 3D meeting preview is cosmetic; persisted meetings are created and completed through the company operations UI/API.
