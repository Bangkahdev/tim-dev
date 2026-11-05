# Backend Integration — Final Desktop MVP 1.0

## Authority boundary

Godot is the presentation, player-control and interaction client. Python / SQLite are authoritative for employee records, task states, meeting records, Paper, approvals, outbox, generated PDF jobs, knowledge documents and audit events. The client may animate from backend snapshots but may not declare a task completed, approve a request, or report an external side effect as successful before the API reports the persisted outcome.

## Connected operations

| Endpoint | Client use | Status |
|---|---|---|
| `GET /api/status` | Poll office + company snapshot | Connected |
| `GET /api/office/player` | Load Owner position | Connected |
| `POST /api/office/player` | Save Owner position / supported interaction | Connected |
| `POST /api/room-chat` | Employee conversation | Connected for supported employees |
| `POST /api/tasks` | Create company task | Connected |
| `POST /api/tasks/{id}/transition` | Start / block / resume / cancel / complete with evidence | Connected |
| `POST /api/meetings` | Create agenda | Connected |
| `POST /api/meetings/{id}/start|complete|cancel` | Persist meeting state, minutes, decisions, follow-ups | Connected |
| `POST /api/papers` | Create Paper | Connected |
| `POST /api/papers/{id}/review` | Mark read / defer / archive | Connected for read action in current UI; API accepts the supported statuses |
| `POST /api/print-jobs` | Render PDF from Paper | Connected |
| `GET /api/print-jobs/{id}/download` | Download saved PDF to local user folder | Connected |
| `POST /api/approvals` | Create immutable approval request | Connected |
| `POST /api/approvals/{id}/approve|reject` | Owner decision | Connected |
| `POST /api/outbox/{id}/execute` | Explicitly execute approved action | Connected |
| `GET /api/events?after_id=...` | Read audit event cursor | API available; client snapshot still polls |
| `GET /api/usage` | Read usage metrics | API available; overview shows totals when available |

See `API-REFERENCE.md` for request contracts.

## External action adapters

- Email uses SMTP TLS and is only invoked through an approved outbox item.
- Website deployment calls a configured HTTPS webhook with bearer token and idempotency key.
- Purchase requests require approval but remain `awaiting_executor` for manual handling.
- Provider uncertainty transitions to `unknown`; the client does not automatically retry unknown delivery.
- No SMTP account, deployment webhook or financial provider credentials are included in the package.

## Authentication and network

`BANGKAH_API_TOKEN` is optional for the loopback-only local desktop instance. When configured, every `/api/*` GET and POST request including PDF download requires `Authorization: Bearer ...`. The Godot settings panel accepts the token into memory for the current session and never writes it to disk. The Python server refuses direct non-loopback binding. For remote access, keep the service on loopback and place a TLS reverse proxy in front of it.

## Still outside this release

- Owner account bootstrap, short-lived sessions, session revocation, multi-user roles and dynamic organization CRUD.
- WebSocket event replay, acknowledgements and reconnect snapshots. `/api/events` is cursor-based HTTP polling.
- Full NavigationAgent3D / NavigationMesh navigation and persistent NPC movement state.
- Full backend-enforced agent tool capabilities beyond the existing Orchestrator / OfficeTools allowlist.
- Container / OS process sandbox, per-agent egress proxy and strong workspace isolation.
- Independent verification of external task evidence references.
- Deployment completion reconciliation, active commit validation, automatic rollback and external provider polling.
- Purchase / payment adapter.

Do not read a documented SRS requirement as implemented unless the table above, code and tests support it. This release is an auditable local MVP, not SRS v1.3 certification.
