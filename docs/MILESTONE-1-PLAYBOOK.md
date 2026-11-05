# Milestone 1 Playbook — One Real Business Cycle

This is the implementation and acceptance playbook for the v1.3 milestone. It is not yet a completed workflow in v0.5.

## Goal

Complete one small real software project from Owner instruction to reviewable deliverable, with no manual intervention except required Owner approval. Repeat successfully three times.

## Required sequence

1. Owner sends a request to Secretary or directly to a division manager.
2. Secretary / Orchestrator creates a validated plan and proposal.
3. Owner approves the internal coding pipeline where required.
4. Manager decomposes work into tasks with acceptance criteria and dependencies.
5. Backend assigns tasks to employees with role-scoped tool permissions.
6. Agents run in an enforced sandbox, produce files and test output.
7. QA executes tests and stores evidence.
8. Backend validates evidence and sets task/project state.
9. Worker creates a final report Paper and PrintJob.
10. Employee prints and physically delivers the report to Owner tray (animation follows persisted events).
11. Owner reviews evidence, decision is persisted and audited.

## Minimal pilot project

Use a project small enough to validate the complete pipeline, for example:

- A static company landing page with 3–4 sections and responsive layout; or
- A small Python CLI utility with tests and README.

The pilot must be created in a dedicated workspace, not directly in a production website or personal system directory.

## Required evidence

- Source files / commit reference.
- Test command and exit code.
- Test output artifact.
- QA report.
- Manager review.
- Final project report.
- Paper record and generated PDF.
- PrintJob and delivery event.
- Owner decision and audit record.

## Acceptance checks

- Same Task cannot reach COMPLETED without validated evidence.
- Invalid state transitions are rejected.
- Employee tool calls outside permissions are rejected by backend.
- Agent subprocess cannot access files outside project workspace or arbitrary internet.
- Owner approval is immutable, single-use and hash-bound.
- Paper cannot appear/disappear in the 3D tray without backend record/event.
- Duplicate events do not create duplicate animations or duplicate decisions.
- Restart does not lose task evidence, Paper, PrintJob or Owner decision.
- Character status in Godot matches backend task/session state.
- All decisions are present in the audit trail.
- Full cycle succeeds three consecutive times.

## Not part of this milestone

Email delivery, public website deployment, marketing automation, parallel projects, advanced NPC pathfinding and visual polish. These are later phases after the internal workflow is proven.
