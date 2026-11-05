# Operations and Security

## Local deployment model

The supported release topology is one Owner desktop running the Godot client and a Python backend bound to `127.0.0.1:8765`. SQLite stores office and company operation records under `backend/data/`. Generated PDF files are stored under `backend/data/prints/`. Agent logs, reports and workspaces remain under the backend directory and are excluded from the release ZIP.

The backend refuses direct non-loopback binding. For remote access, keep the process on loopback, configure `BANGKAH_API_TOKEN`, and place an HTTPS reverse proxy in front of it. The proxy must forward the `Authorization` header and should apply request size / rate limits. Never expose the Python HTTP server directly on a public interface.

## First run

1. Run `start_backend.bat` or `start_backend.sh` from the extracted project root.
2. The start script creates a virtual environment and installs `backend/requirements.txt`.
3. On first launch, `backend/.env.example` is copied to `backend/.env`; configure model variables and provider keys.
4. Start the backend again. Keep its console open.
5. Launch `godot/project.godot` in Godot 4.3+.
6. The client initially connects to `http://127.0.0.1:8765`. For token-protected setups, enter the exact `BANGKAH_API_TOKEN` in Settings. The game holds the token in memory only; it is not written to disk.

## Secrets

- Keep provider keys, SMTP credentials and deployment tokens only in `backend/.env` or a stronger secret store used by the host.
- Do not paste secrets into chat, Paper, approval payloads, knowledge documents, task evidence or source code.
- `.env`, SQLite databases, generated PDFs, logs, reports and workspaces are gitignored and excluded from the release archive.
- The game API token is not persisted by the Godot client. Closing the game clears it.
- The backend compares bearer tokens using a constant-time comparison. If configured, the token protects all `/api/*` reads, writes and generated-file downloads.

## External action safety

External side effects follow a three-step process:

1. A request is stored as an approval with a canonical immutable payload and SHA-256 digest.
2. The Owner reviews the exact payload in the game and approves or rejects it.
3. An approved request creates an outbox item. A separate explicit Owner action starts execution.

Email uses SMTP with TLS. The deployment adapter only accepts an HTTPS webhook URL and sends a bearer token plus an idempotency key. The webhook provider must honor that idempotency key to prevent duplicate deployment requests. Purchase actions are never auto-completed; they are marked `awaiting_executor` for manual handling.

If a remote connection ends after a provider may have accepted a request, the outbox is marked `unknown`. The system does not auto-retry an unknown result. The Owner must inspect the provider before deciding how to reconcile it. A failed result is retryable only where the adapter reported a definitive failure before delivery.

## Data and recovery

- Back up `backend/data/` while the backend is stopped. It contains the SQLite database and generated PDF files.
- Back up `backend/workspace/`, `backend/reports/` and `backend/logs/` separately if project source and run history should be retained.
- Do not replace the whole data directory with an older backup while the application is running.
- Audit events are append-oriented records. Database backups are still required; this local release does not replicate to a remote store.

## Model privacy and costs

A local Ollama model keeps prompts on the local machine, subject to the configured model/runtime. A cloud model provider receives prompts and relevant context and may incur token charges. Set model provider, model name and repair-round limits deliberately. Model token totals may be unavailable if the provider does not expose usage metadata.

## Security boundary and known gaps

- This is a single-owner local MVP, not a hardened multi-user service.
- The API bearer token is static configuration, not a short-lived login session with rotation/revocation endpoint.
- There is no full subprocess/container sandbox or per-agent filesystem/network isolation in this release.
- RAG content is context, not authorization. Tool allowlists in the legacy Orchestrator remain the control point for tool invocation.
- Email and deployment adapters are opt-in and require real provider credentials. The package contains no credentials and has not sent a real message or deployment.
- The Boardroom 3D meeting preview is cosmetic; persisted meetings are created and completed through the company operations UI/API.
