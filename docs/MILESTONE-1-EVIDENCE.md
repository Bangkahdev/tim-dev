# Milestone 1 Evidence — Real Agent, Three Consecutive Passes

## Latest acceptance run — 2026-11-19

**Status: PASS for the machine-verifiable acceptance set.** This is a real CrewAI
agent run against a real local model (Ollama), executed inside a real
filesystem/network sandbox (bubblewrap). It is not a cloud-model run and does not
include the manual Godot visual check (see “Not claimed”).

### Environment

- Linux host `bangkah`; Docker is installed but the daemon could not start
  because the host iptables/nftables NAT chain is broken
  (`nat-PREROUTING`/`docker-bridges` missing). Sandbox was therefore provided by
  **bubblewrap 0.13.1**, which the playbook explicitly accepts as an equivalent
  OS sandbox.
- **Python 3.12.16** (uv-managed interpreter).
- **CrewAI 1.15.34** (real package from `backend/.pylibs`) and **Ollama
  `qwen2.5-coder:7b`** for the implementer, QA, and advisory lead roles.
- Cloud API keys in `backend/.env` are empty; this is the documented local-model
  equivalent for this environment. No cloud tokens were consumed.
- Sandbox wrapper: `/usr/bin/bwrap --unshare-net --die-with-parent` with only the
  project directory writable at `/work`, read-only system/runtime mounts, and a
  tmpfs `/tmp`.
- Preflight canaries: **filesystem isolated = true**, **network isolated =
  true**, **outside-sandbox control probe reachable = true**.
- Manual isolation probes (recorded):
  `backend/workspace/projects/sandbox-manual-evidence-20261119-033948.txt`.
  Outside project read fails, outbound TCP/DNS fails, project read succeeds, and
  the same TCP control succeeds outside the sandbox.

### Command

Run from `backend/`:

```bash
export BANGKAH_SANDBOX_REQUIRED=1
export BANGKAH_SANDBOX_CMD='/usr/bin/bwrap --unshare-net --die-with-parent \
  --ro-bind /usr /usr \
  --ro-bind /home/atha/.local/share/uv/python /home/atha/.local/share/uv/python \
  --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
  --ro-bind /etc /etc --proc /proc --dev /dev --tmpfs /tmp \
  --bind {project_dir} /work --chdir /work \
  --setenv PATH /usr/bin:/bin --setenv HOME /tmp \
  --setenv PYTHONDONTWRITEBYTECODE 1'
export MODEL_MANAGER=ollama/qwen2.5-coder:7b
export MODEL_CODER=ollama/qwen2.5-coder:7b
export MODEL_SPECIALIST=ollama/qwen2.5-coder:7b
export MODEL_BACKEND=ollama/qwen2.5-coder:7b
export MODEL_QA=ollama/qwen2.5-coder:7b
export MODEL_LEAD=ollama/qwen2.5-coder:7b
export PYTHONPATH=.pylibs:.
PY=/home/atha/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12

"$PY" tools/run_milestone1.py \
  --cycles 3 --isolated-db --max-attempts 12 \
  --worker real \
  --external-sandbox 'bwrap 0.13.1: --unshare-net, project-only bind at /work, ro system/runtime mounts, tmpfs /tmp; manual probes: backend/workspace/projects/sandbox-manual-evidence-20261119-033948.txt; Docker daemon unavailable on host (iptables nat-PREROUTING failure)'
```

The `BANGKAH_SANDBOX_*` variables are exported explicitly because
`tools/run_milestone1.py` checks `sandbox_required()` before the CrewAI worker
imports `config.py` (which is what loads `.env`). `.env` also contains the same
values for normal backend operation.

### Result

`summary.json`:

```json
{
  "required_consecutive": 3,
  "achieved_consecutive": 3,
  "attempts": 3,
  "passed": true,
  "passed_verifiable_only": false,
  "worker": "crewai_real",
  "real_agent_worker": true
}
```

Every attempt used a fresh project directory and a fresh isolated SQLite DB.
No repair loop was needed: **3 attempts total**, all three passed on the first
try.

| # | Project key | Hidden tests | Verifier overall | Fresh-process restart | Sandbox canary | Paper | PrintJob | `tests_source` | Repair rounds |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `milestone1-wordcount-20261119-034217-a1-r1` | 11/11 | PASS | PASS | FS+net PASS | `PAP-5731D880F7E5` | `PRN-CB6B75236850` | `None` (agent tests passed) | `None` |
| 2 | `milestone1-wordcount-20261119-034217-a2-r2` | 11/11 | PASS | PASS | FS+net PASS | `PAP-5E9583817A8F` | `PRN-05CB4AB0174A` | `None` (agent tests passed) | `None` |
| 3 | `milestone1-wordcount-20261119-034217-a3-r3` | 11/11 | PASS | PASS | FS+net PASS | `PAP-353900131A5C` | `PRN-C5063D06620E` | `None` (agent tests passed) | `None` |

Each attempt passed:

- `verify.hidden.all_pass` — normal file, empty file, stdin `-`, no trailing
  newline, single line without newline, lone `"\n"`, repeated whitespace/tabs,
  CRLF, missing file exit 2, missing argument exit 2, UTF-8 character (not byte)
  count.
- `verify.OVERALL_VERIFIABLE` — DB tasks/evidence, final-report Paper, completed
  PrintJob, delivered event, audited owner decision, and required artifacts.
- `restart.fresh_process_persistence` — a **new Python process**
  (`tools/check_persisted_state.py`) reopened the run DB after Paper delivery and
  found the completed tasks/evidence, Paper, PrintJob, delivery event, and owner
  decision.
- `sandbox.fs_network_isolation_NFR_SEC_09_10` — active wrapper plus canaries
  proving both filesystem confinement and blocked egress.
- RBAC/approval static checks: employee cannot reach owner routes, approval is
  hash-bound, payload is immutable, approval is single-use.

**Honest note on `verify.sandbox.fs_network_isolation_NFR_SEC_09_10`:** the
independent verifier deliberately reports this key as `False` because it cannot
inspect the host-level wrapper. The runner records the operator evidence from
`--external-sandbox` plus the mandatory preflight canaries and manual probes.
This is the documented, honest split; it is not a hidden failure.

### Test suite

`backend/workspace/pytest-full-20261119-034311.log`:

```text
214 passed in 105.39s (0:01:45)
```

This includes the sandbox fail-closed tests, the new control-probe semantics, the
verifier whitebox mutants, the Milestone 2 acceptance verifier tests, and the
business-cycle integration test fixed to disable a developer `.env` sandbox for
its “in-process guards alone” assertion.

### Evidence locations

- Acceptance root:
  `backend/workspace/projects/milestone1-logs-20261119-034217/`
  - `summary.json`
  - per-attempt `*.json` and `*.db`
  - `static.db`, `prints/`, `_sandbox_preflight/`
- Generated project dirs:
  `backend/workspace/projects/milestone1-wordcount-20261119-034217-a1-r1/`,
  `...-a2-r2/`, `...-a3-r3/`
- Console log:
  `backend/workspace/projects/milestone1-console-20261119-034217.log`
- Manual isolation probe transcript:
  `backend/workspace/projects/sandbox-manual-evidence-20261119-033948.txt`
- Full test log:
  `backend/workspace/pytest-full-20261119-034311.log`

## Previous acceptance run — 2026-11-08

The earlier run used the same local Ollama/CrewAI path and bubblewrap. It passed
3/3 consecutive cycles with `qwen2.5-coder:7b`, but the agent-written test file
was rejected in every attempt, so the worker installed the deterministic
public-spec test scaffold (`tests_source=worker_spec_scaffold_after_agent_tests_failed`,
`repair_rounds=1`). The 2026-11-19 run above is stronger: the agent's own tests
passed and no scaffold or repair round was needed.

Historical evidence is under
`backend/workspace/projects/evidence-20261108/` (acceptance, single-pass, and
exploratory runs) and `backend/workspace/archives/` (old deterministic
workspaces). The advisory lead review in that run returned `STATUS: FAIL`; it was
factually contradicted by the delivered files and executed tests and remains
advisory by design, not an acceptance gate.

## Not claimed

- **Cloud-model execution:** no cloud keys were configured; this evidence is a
  local Ollama/CrewAI run. The local model is the explicitly documented
  equivalent for this environment.
- **Docker execution:** the Docker daemon is unavailable on this host because of
  an iptables/nftables NAT initialization failure. The sandbox evidence is from
  bubblewrap, not Docker.
- **Manual Godot check:** character status, tray, and Paper matching backend
  records remain `MANUAL_REQUIRED`. The automated runner records this as manual
  and does not claim it.
- **Godot visual polish:** the uncommitted office/city visual changes are outside
  Milestone 1 scope.
