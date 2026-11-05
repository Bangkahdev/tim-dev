# System Architecture

## High-level boundary

```text
┌────────────────────────────────────────────────────────────┐
│ Godot 4 Client                                              │
│ First-person / third-person camera · HQ world · HUD · UI    │
└──────────────────────────────┬─────────────────────────────┘
                               │ HTTP today; WebSocket later
                               ▼
┌────────────────────────────────────────────────────────────┐
│ Python AI Office Backend                                   │
│ office_server → API → Orchestrator → OfficeTools / CrewAI   │
│                  │                                          │
│                  ├─ Task / Project / Meeting                │
│                  ├─ Employee / Department / Secretary       │
│                  ├─ Approval / Outbox / Execution           │
│                  ├─ Paper / PrintJob / Audit                 │
│                  └─ RAG / Knowledge                         │
└──────────────────────────────┬─────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
          SQLite + files    LLM provider     External services
          workspace         Ollama/cloud      email / website
```

## Responsibility split

### Godot client

- Render the office world and characters.
- Read keyboard/mouse input and move the Owner.
- Detect focused nearby interaction targets.
- Display read-only backend state and open contextual panels.
- Play visible animations only after receiving trusted backend state/events.
- Remain explorable in offline mode.

Godot must not own task truth, agent permissions, approval state, project lifecycle, email delivery state, website deployment state or audit truth.

### Python backend

- Own the source of truth for employees, departments, projects, tasks, meetings, interactions, papers, approvals and audit.
- Validate natural-language plans and tool calls.
- Enforce per-employee tool permissions.
- Execute code and external actions under explicit policy.
- Write state transitions and durable events.
- Serve snapshots/events to Godot.

### Storage

- SQLite for transactional company state.
- Workspace/repository files for project outputs.
- Append-only audit records for important decisions/actions.
- Bounded WorldEvent and employee/player state for visual synchronization.

## Runtime flow examples

### Owner movement

1. Godot updates local player movement and collision.
2. At a bounded interval, it posts the Owner transform/room state to the existing office endpoint.
3. Backend stores the latest PlayerState.
4. On reconnect, Godot requests a fresh snapshot.

Movement is not an audit event. Only important interactions and decisions are audited.

### Employee work

1. Backend creates or assigns a real Task.
2. Agent worker claims and executes it under backend permission/sandbox rules.
3. Backend validates evidence and task transition.
4. The client receives state/event updates.
5. NPC animation/position reflects the task/session state.

The client must not infer that an employee is working merely because an idle timer or ambient animation is running.

### Paper delivery (future v1.3 integration)

1. Backend creates an immutable Paper record and a PrintJob.
2. PDF is generated and stored.
3. Backend records the print and delivery events.
4. Godot animates the employee carrying the paper only after the delivery event.
5. Owner tray contents are read from backend state.

The full Paper workflow is not implemented by this v0.5 package.

## Current transport status

The client currently uses the legacy HTTP integration for status, player state and employee chat. The v1.3 WebSocket event stream, event replay, acknowledgments, snapshots and authenticated Owner session are not yet wired. Do not present this package as complete v1.3 compliance.
