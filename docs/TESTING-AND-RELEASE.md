# Testing and Release — Final Desktop MVP 1.0

## Automated checks

Run from repository root:

```bash
python -m compileall -q backend
python tools/validate_bundle.py
cd backend
python -m pytest -q
```

The security-hardening test run returned **125 passed**. `backend/tests/conftest.py` points `BANGKAH_DB_PATH` at a temporary database before any backend import, so the suite never touches real company data. Authentication tests install `bcrypt` from `backend/requirements.txt` (`pip install -r backend/requirements.txt`); if `bcrypt` is missing the auth tests fail with `ModuleNotFoundError`, which is an environment problem rather than an implementation result.

The HTTP integration tests start the real handler on an ephemeral loopback port and cover anonymous access, invalid/expired/revoked/disabled sessions, all four roles, department scope, task ownership, unauthorized approvals, actor spoofing, legacy-token migration, login/logout and domain routing. A separate HTTP smoke test exercises company workflows with a fake `crewai` import because those data APIs do not invoke the model.

## Desktop runtime acceptance

Open `godot/project.godot` in Godot 4.3+ and complete every checklist item in `FINAL-ACCEPTANCE.md`. The build environment used to create this package has no Godot executable, so GDScript parsing, scene execution, physics, rendering, camera behavior, GLB import and performance have not been verified here.

## Provider acceptance

- [ ] Run a real local Ollama model or cloud LLM provider and validate chat / agent pipeline behavior.
- [ ] Configure a test SMTP account and send a test message only after explicit Owner approval and outbox execution.
- [ ] Configure a staging HTTPS deployment webhook and confirm it honors the `Idempotency-Key` header.
- [ ] Test a provider timeout and reconcile `unknown` status without duplicate sends.
- [ ] Confirm any real company domain, email sender identity and deployment destination are owned / authorized by the Owner.

These actions need the Owner's own model and service credentials. No credentials are included or fabricated.

## Package hygiene

- Keep `.env`, database files, generated PDFs, logs, reports, workspace files and Python caches out of release ZIPs.
- Include `.env.example`, Python requirements, unit tests, Godot project, docs and launch scripts.
- Re-run `python tools/validate_bundle.py` against the extracted archive.
- Do not describe the product as full SRS v1.3 compliant until remaining traceability items and Godot / provider acceptance checks have passed.
