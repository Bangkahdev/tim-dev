# Milestone 2 Playbook — External Actions End-to-End

This playbook defines the acceptance contract for the external-action chain:
**immutable approval → outbox → explicit execute → verified delivery**. The
executed evidence is recorded in **[`MILESTONE-2-EVIDENCE.md`](MILESTONE-2-EVIDENCE.md)**.

## Honesty boundary

Milestone 2 is tested against **local test providers only**:

- a local SMTP sink that speaks STARTTLS and AUTH PLAIN;
- a local HTTPS webhook sink for website deployment.

The real `core.action_adapters` code path is exercised unchanged, but **no real
email provider, public website host, or external deployment service is
contacted**. This milestone does not claim production delivery, provider
deliverability, or cloud-model execution.

## Goal

Prove that the Owner approval boundary is real and one-way:

1. Creating an approval stores the exact canonical payload and its SHA-256, but
   creates no outbox item and sends nothing.
2. Approving the approval creates exactly one queued outbox item, but still
   sends nothing.
3. Only an explicit `POST /api/outbox/{id}/execute` invokes the adapter.
4. A second execute is idempotent for a succeeded item and never delivers twice.
5. Rejecting an approval creates no outbox item and delivers nothing.
6. `expense.purchase` has no automatic adapter and remains `awaiting_executor`.
7. An uncertain provider result is parked as `unknown`, cannot be resent, and is
   resolved only by an explicit reconciliation with a verification note.
8. A definitive failure schedules exponential backoff; an exhausted item stops,
   refuses resends, and requires a manual requeue.
9. A deployment webhook that is not HTTPS is rejected before any network call.
10. The whole set succeeds **three consecutive times** with fresh databases and
    retained logs. Any failure resets the consecutive count to zero.

## Required chain contract

| Step | API | Required result |
|---|---|---|
| Create approval | `POST /api/approvals` | `201`, canonical payload + SHA-256, no outbox row, no delivery |
| Reject | `POST /api/approvals/{id}/reject` | `200`, no outbox row, no delivery |
| Approve | `POST /api/approvals/{id}/approve` | `200`, exactly one `queued` outbox row, no delivery |
| Execute email | `POST /api/outbox/{id}/execute` | `200`, `succeeded`, SMTP external id, one sink record |
| Execute deployment | `POST /api/outbox/{id}/execute` | `200`, `succeeded`, deployment id, one sink record |
| Execute expense | `POST /api/outbox/{id}/execute` | `202`, `awaiting_executor`, no external id |
| Duplicate execute | `POST /api/outbox/{id}/execute` | `200` with `already_completed`; no second sink record |
| Unknown outcome | execute | `409`, `unknown`, one sink record, resend refused |
| Reconcile | `POST /api/outbox/{id}/reconcile` | note required; `succeeded`/`failed` final; no resend |
| Exhausted | execute with capped attempts | `409`, `failed`, no retry time, resend refused |
| Requeue | `POST /api/outbox/{id}/requeue` | `200`, `queued`, attempts reset to 0 |
| Non-HTTPS deploy | execute | `409`, `failed`, no network call |

Approval payload JSON is canonicalized with sorted keys and compact separators,
SHA-256 hashed, and protected by the `approval_payload_immutable` SQLite trigger.
Credentials are read from the backend environment and are **never** placed in
approval payloads, outbox results, audit events, or sink logs.

## Local sinks

`backend/tools/external_sinks.py` provides:

- **`SmtpSink`**: minimal ESMTP server with STARTTLS, AUTH PLAIN, and DATA. It
  writes JSONL evidence with the outbox id, Message-ID, sender, recipients,
  subject, body, authenticated user, and raw message SHA-256.
- **`DeploySink`**: HTTPS `POST /hook` server that requires the bearer token and
  records the idempotency key, request body, deployment id, and only a SHA-256 of
  the `Authorization` header — never the raw token.
- **`ensure_test_certificates`**: throwaway CA and loopback server certificate
  (SAN `DNS:localhost,IP:127.0.0.1`) generated with OpenSSL. The backend trusts
  the CA through `SSL_CERT_FILE`.

`drop_after_data=True` makes the SMTP sink accept and log a message but close
before the final `250` acknowledgement. That reproduces a real uncertain
provider outcome without monkeypatching the adapter.

## Running the acceptance set

Run from `backend/`:

```bash
PYTHONPATH=.pylibs:. python3.12 tools/run_milestone2.py --cycles 3
```

Each cycle creates a fresh directory under the gitignored workspace tree with:

- `main.db` and `negative.db`;
- `smtp-main.jsonl`, `deploy-main.jsonl`, `smtp-unknown.jsonl`,
  `smtp-exhausted.jsonl`;
- `server-*.log`, `observations.json`, `cycle-summary.json`;
- `state-probe.json`, `verification.json`, `verify.log`.

The runner:

1. starts the real `office_server.py` as a subprocess per scenario and logs in
   as the owner with a generated password;
2. runs the main email, deployment, reject, and expense flows over HTTP;
3. runs three negative servers against a separate database:
   - **A**: no SMTP configuration and a plain-HTTP deployment webhook;
   - **B**: SMTP sink that drops after DATA (unknown outcome);
   - **C**: SMTP authentication rejected with `OUTBOX_MAX_ATTEMPTS=1`;
4. restarts the main backend against the same database and re-reads state;
5. runs `tools/check_milestone2_state.py` in a **fresh Python process**;
6. stops the backend and runs `tools/verify_milestone2.py` in another fresh
   process. The verifier reads the SQLite databases and sink JSONL logs directly
   (the immutability check is a rolled-back no-op update); runner observations are
   not accepted as proof.

A cycle passes only if every runner check, the restart probe, and the
independent verifier pass. A failed cycle resets the consecutive streak.

## Independent verifier

`backend/tools/verify_milestone2.py` checks, among others:

- every approval hash recomputed from stored canonical JSON;
- the immutability trigger exists and actually aborts a no-op payload update;
- the approved email and deployment each appear exactly once in their sink logs,
  with matching recipients/subject/body, deployment payload hash, deployment id,
  and idempotency key;
- every sink record maps to a `succeeded` outbox row with exactly one
  `outbox_execution_started` event, and every such outbox row has a record;
- the rejected approval has no outbox row and no sink record;
- the expense stays `awaiting_executor` with no external id and no sink record;
- one outbox row per approval;
- required audit event types are present;
- SMTP authentication user and deployment bearer-token hash match configuration;
- configured secrets do not appear anywhere in the database, logs, or
  observations;
- the fresh-process probe reports all persistence checks true;
- the negative database proves backoff, HTTPS rejection, unknown →
  reconciliation, exhaustion → requeue, and manual expense behavior.

## Tests

```bash
cd backend
PYTHONPATH=.pylibs:. python3.12 -m pytest tests ../it --ignore=workspace -q
```

Relevant coverage:

- `tests/test_external_sinks.py` — real SMTP/HTTPS sinks with the real adapters,
  idempotency, unknown outcome, rejected authentication, and plain-HTTP refusal;
- `tests/test_verify_milestone2.py` — verifier whitebox: clean evidence passes;
  duplicate delivery and leaked secrets fail;
- `tests/test_action_adapters.py` — existing adapter unit tests;
- `tests/test_company_operations.py` — approval immutability, outbox, retry,
  reconciliation, and requeue behavior.

## Evidence requirements

For each cycle retain:

- the cycle directory with both databases and all sink JSONL logs;
- `cycle-summary.json`, `observations.json`, and `state-probe.json`;
- `verification.json` and `verify.log` with PASS/FAIL per criterion;
- server logs for every scenario;
- `acceptance-summary.json` with the final consecutive-run result.

Do not reuse a database or sink log across cycles. Keep failed attempts and
record what changed.

## Not part of this milestone

- Real SMTP or deployment provider delivery, provider reputation, or deliverability.
- Production website hosting and rollback.
- Automatic purchasing or payment-provider integration.
- Godot UI wiring for approval screens and visual polish.
- Cloud-model execution and full SRS v1.3 certification.
