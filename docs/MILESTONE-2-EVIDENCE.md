# Milestone 2 Evidence — External Actions End-to-End, Three Consecutive Passes

**Date:** 2026-11-19
**Status:** **PASS for the local end-to-end acceptance set.** Approval → outbox →
explicit execute → verified delivery is proven against local test providers.
This is **not** a real email-provider or public deployment-provider run (see
"Honesty boundary").

## Honesty boundary

The acceptance run uses the unchanged production code path
(`core.action_adapters`) but talks only to local test providers:

- a local SMTP sink with STARTTLS and AUTH PLAIN;
- a local HTTPS webhook deployment sink;
- a throwaway OpenSSL CA/server certificate trusted through `SSL_CERT_FILE`.

No real email provider, public website host, or external deployment service is
contacted. This milestone does not claim provider deliverability, production
hosting, or cloud-model execution.

## Environment

- Linux host (Bangkah v1.3 local desktop environment), no Docker/Podman.
- Python **3.12.16** (uv-managed interpreter:
  `/home/atha/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12`).
- Backend started as real `office_server.py` subprocesses with
  `PYTHONPATH=.pylibs:.`.
- CrewAI/OpenTelemetry telemetry disabled for subprocesses to keep startup
  deterministic and offline.
- Acceptance run directory on tmpfs (`/tmp/opencode/...`) because the repository
  lives on a slow USB drive; the USB run stalled in kernel I/O wait (see
  "Exploratory failure and fix").
- Per-cycle credentials (owner password, SMTP password, deployment token) are
  randomly generated; no secret is reused across cycles.

## Command

Run from `backend/`:

```bash
PYTHONPATH=.pylibs:. python3.12 tools/run_milestone2.py \
  --cycles 3 --max-attempts 6 \
  --run-dir /tmp/opencode/m2-acceptance-final-20261119
```

The runner starts a fresh backend and fresh SQLite databases per scenario,
exercises the chain over HTTP, restarts the backend, runs a fresh-process
persistence probe (`tools/check_milestone2_state.py`), and then runs the
independent verifier (`tools/verify_milestone2.py`) in another process. A cycle
passes only when all runner checks, the restarted-state check, the probe, and
the independent verifier pass. Any failure resets the consecutive streak.

## Result

```
Required consecutive passes: 3; max attempts: 6
[cycle 1] PASS (16.43s, streak=1/3)
[cycle 2] PASS (16.0s,  streak=2/3)
[cycle 3] PASS (17.02s, streak=3/3)
MILESTONE 2: PASS
```

| Cycle | Duration | Runner checks | Independent verifier | Restart probe | Main events | SMTP main / deploy / unknown / exhausted |
|---|---|---|---|---|---|---|
| 1 | 16.43 s | 33/33 | 22/22 | all persisted | 18 | 1 / 1 / 1 / 0 |
| 2 | 16.00 s | 33/33 | 22/22 | all persisted | 18 | 1 / 1 / 1 / 0 |
| 3 | 17.02 s | 33/33 | 22/22 | all persisted | 18 | 1 / 1 / 1 / 0 |

The exact 1/1/1/0 sink counts are deliberate: one approved email, one approved
deployment, one uncertain delivery (unknown scenario), and **zero** deliveries
for the rejected, missing-configuration, plain-HTTP, and exhausted scenarios.

## Per-cycle evidence

Payload hashes are identical across the three cycles for the same canonical
payload, which shows deterministic canonicalization and hashing:

| Payload | SHA-256 |
|---|---|
| Approved email (`M2-SMTP-OK: approved project update`) | `779249887edeb8187f3600742611407a00c524c61c75c8220b6535a084c513e3` |
| Approved deployment (`https://example.test/milestone2-site.git`) | `d4321f21b757092fe45713a6c39b5c5947b66b101a46d77c8a30b0566a53e8d7` |
| Rejected email (`M2-REJECT-NO-SEND: must never be delivered`) | `0b9a68a8028b17eb38efb37d83f5bf47949ff345a076f671d05b7f83d411a144` |
| Manual expense (`M2 Local Supplies`) | `6fb1741442bf294e2d537687cc35e9413031213f07f44f7a1d79a95c30918a30` |

### Cycle 1

| Item | ID | Outcome |
|---|---|---|
| Email approval | `APR-BE0931584D8F` | approved |
| Email outbox | `OUT-A4A485A2AB97` | `succeeded`, external id `<179503128140.26027.9359220661728028216.out-a4a485a2ab97@example.test>` |
| Deployment approval | `APR-FB2CB75BADFB` | approved |
| Deployment outbox | `OUT-2A753B5854A9` | `succeeded`, external id `DEP-E25B3314365F` |
| Rejected email | `APR-F52C80EF93CA` | rejected, no outbox row, no delivery |
| Expense outbox | `OUT-9A1AD29DF6FA` | `awaiting_executor`, no external id |
| Missing-config email | `OUT-92DA5A40DE6C` | `failed`, attempts 1, backoff scheduled |
| Plain-HTTP deployment | `OUT-6AE4949A28FD` | `failed` ("wajib menggunakan HTTPS"), no network call |
| Uncertain email | `OUT-AA8A8471BADE` | `unknown` → reconciled `succeeded` by `owner`, sink message id used as external id |
| Exhausted email | `OUT-96EAD0254490` | `failed` after attempt 1 → requeued to `queued`, attempts 0 |

### Cycle 2

| Item | ID | Outcome |
|---|---|---|
| Email approval | `APR-C97D38C315EA` | approved |
| Email outbox | `OUT-BCF909D2AF7B` | `succeeded`, external id `<179503129775.26312.8173814965880387103.out-bcf909d2af7b@example.test>` |
| Deployment approval | `APR-9F5B4117A2E2` | approved |
| Deployment outbox | `OUT-F6CFA5612415` | `succeeded`, external id `DEP-8244588B6440` |
| Rejected email | `APR-5341BEA603DC` | rejected, no outbox row, no delivery |
| Expense outbox | `OUT-B159F6275D7D` | `awaiting_executor`, no external id |
| Missing-config email | `OUT-0E57C70469A6` | `failed`, attempts 1, backoff scheduled |
| Plain-HTTP deployment | `OUT-63FB6DD725A2` | `failed`, no network call |
| Uncertain email | `OUT-5F3FA98E1266` | `unknown` → reconciled `succeeded` by `owner` |
| Exhausted email | `OUT-2C5805A7D172` | `failed` → requeued `queued`, attempts 0 |

### Cycle 3

| Item | ID | Outcome |
|---|---|---|
| Email approval | `APR-09513AABFD2D` | approved |
| Email outbox | `OUT-05A6046AC7B9` | `succeeded`, external id `<179503131378.26603.5794095682888727322.out-05a6046ac7b9@example.test>` |
| Deployment approval | `APR-8E8EE93BBDB7` | approved |
| Deployment outbox | `OUT-C00267A61500` | `succeeded`, external id `DEP-4340388BA484` |
| Rejected email | `APR-F1AFA26AEDAD` | rejected, no outbox row, no delivery |
| Expense outbox | `OUT-480209181775` | `awaiting_executor`, no external id |
| Missing-config email | `OUT-A8F4D339AF57` | `failed`, attempts 1, backoff scheduled |
| Plain-HTTP deployment | `OUT-B2ADF514BC96` | `failed`, no network call |
| Uncertain email | `OUT-A96FC520E41B` | `unknown` → reconciled `succeeded` by `owner` |
| Exhausted email | `OUT-373AB576367C` | `failed` → requeued `queued`, attempts 0 |

## Independent verifier checks (22/22 every cycle)

The verifier reads the SQLite databases and both sink JSONL logs directly; the
runner observations are not accepted as proof. It recomputes every approval hash
from the stored canonical JSON and performs a rolled-back no-op update to prove
the `approval_payload_immutable` trigger actually fires.

1. `approval_payload_hash_valid`
2. `approval_immutability_enforced`
3. `main_email_delivered_once`
4. `main_email_payload_matches` (subject, recipients, body)
5. `main_deploy_delivered_once`
6. `main_deploy_payload_matches` (repository, ref, target, payload SHA-256, idempotency key)
7. `deliveries_only_after_execute`
8. `duplicate_execute_no_second_delivery`
9. `rejected_no_outbox_no_delivery`
10. `expense_awaiting_executor`
11. `unique_outbox_per_approval`
12. `audit_trail_present`
13. `sink_authentication_evidence` (SMTP user; deployment token hash only)
14. `secrets_absent_from_artifacts`
15. `fresh_process_probe_persisted`
16. `negative_missing_config_backoff`
17. `negative_http_deploy_rejected`
18. `negative_unknown_requires_reconciliation`
19. `negative_exhaustion_requires_requeue`
20. `negative_expense_manual`
21. `negative_deliveries_isolated`
22. `negative_secrets_absent_from_artifacts`

The fresh-process probe independently confirmed both databases:
`main_all_persisted: true`, `negative_all_persisted: true`.

## What each negative scenario proves

- **No SMTP configuration** (`negative-a`): execution fails safely with
  `SMTP belum dikonfigurasi`, records attempt 1, and schedules
  `outbox_retry_scheduled`/`next_retry_at`; an early retry is refused with 409.
- **Plain-HTTP deployment webhook** (`negative-a`): rejected with
  `DEPLOY_WEBHOOK_URL wajib menggunakan HTTPS.` before any network connection;
  no sink record exists.
- **Drop after DATA** (`negative-b`): the SMTP sink receives and logs the
  message, then closes before the final `250`. The outbox row becomes `unknown`
  and resend is refused. Only an explicit reconciliation with a verification
  note and the sink message id resolves it, without another send.
- **Rejected SMTP authentication with `OUTBOX_MAX_ATTEMPTS=1`** (`negative-c`):
  the item fails, stops, refuses resends, and requires a manual requeue. The
  requeued row has `status=queued`, `attempts=0`, and no last error; requeueing a
  non-failed item returns 400. The sink received nothing.
- **Reject**: a rejected approval creates no outbox row and no delivery.
- **Expense**: `expense.purchase` has no automatic adapter and stays
  `awaiting_executor` with no external id.

## Automated tests

Full backend suite, from `backend/`:

```bash
PYTHONPATH=.pylibs:. python3.12 -m pytest tests ../it --ignore=workspace -q
```

Result: **207 passed** (85.75 s). This includes the 13 new tests:

- `tests/test_external_sinks.py` — real STARTTLS/AUTH SMTP sink, real HTTPS
  webhook sink, idempotency, drop-after-DATA unknown outcome, rejected
  authentication exhaustion, and plain-HTTP refusal;
- `tests/test_verify_milestone2.py` — verifier whitebox: clean evidence passes,
  duplicate delivery fails, secret leakage fails.

CI's whitebox job also runs both new test files.

## Artifacts

The full run is retained (gitignored workspace evidence tree) at:

```
backend/workspace/projects/evidence-20261119/milestone2/acceptance/
  milestone2-logs-20261119-final-pass/
    acceptance-summary.json
    console.log
    cycle-01/ ... cycle-03/
```

Each cycle directory contains both databases, all four sink JSONL logs, server
logs for every scenario, `observations.json`, `cycle-summary.json`,
`state-probe.json`, `verification.json`, and `verify.log`. Credentials were
randomly generated and the verifier confirmed they do not appear in any
database, log, observation, or sink record; the deployment sink stores only a
SHA-256 of the bearer header.

## Exploratory failure and fix

An earlier acceptance attempt was run directly on the USB workspace
(`.../milestone2-logs-20261119-024043`). Cycle 1 passed in 172 s, but cycles 2
and 3 hit the 90 s backend-startup timeout with empty server logs while the
process was in kernel I/O wait (`blk_mq_get_tag` on the USB device).

Fixes applied before the official run:

- raise the runner's backend-startup timeout to **300 s**;
- disable CrewAI/OpenTelemetry telemetry in subprocess environments;
- run the official acceptance set from tmpfs.

The failed attempt is kept for inspection. Its cycle 1 result was valid, but it
does not count toward the three consecutive passes; the final run above is the
accepted evidence.

## Not claimed

- Real SMTP or deployment-provider delivery, reputation, or deliverability.
- Production website hosting and rollback.
- Automatic purchasing or payment-provider integration.
- Godot approval-screen UI wiring and visual polish.
- Cloud-model execution or full SRS v1.3 certification.
