# SRS v1.3 Traceability — Final Desktop MVP 1.0

This matrix records the delivered implementation, not an assertion that the entire v1.3 specification has passed acceptance. `Runtime unverified` means the source is present but the Godot binary was not available for scene execution in the build environment.

| SRS area | Final Desktop MVP 1.0 coverage | Status |
|---|---|---|
| WLD-01 | Third-person default, optional first-person, WASD, sprint, jump, mouse and interaction focus | Implemented in source; runtime unverified |
| WLD-02 | Player / environment collision bodies and physical rooms | Implemented in source; runtime unverified |
| WLD-03 | Role waypoints, local separation, obstacle probes and stuck recovery; no global NavigationMesh | Partial |
| WLD-04 | Backend employee state is authoritative for working pose; idle/completed ambient routines remain non-task | Partial; NPC movement is not persisted |
| WLD-05 | Owner player save/load through existing office API | Partial / legacy state contract |
| WLD-06 | Office exploration remains usable offline | Implemented in source; runtime unverified |
| WLD-07 | Company hours, dynamic day/night simulation and calendar | Not implemented |
| WLD-08 | Owner position persisted periodically; no durable NPC transform stream | Partial |
| OBJ-01 | Owner computer opens operational company overview with database snapshot | Implemented in client source; runtime unverified |
| OBJ-02 | Persisted meeting agenda, start, completion, minutes, decisions, follow-ups; separate visual Boardroom preview | Implemented backend + client workflow; visual/runtime unverified |
| OBJ-03 | Pantry interaction is local / visual | Partial |
| OBJ-04 | Paper-based PDF PrintJob and client download; no spooler to a physical printer | Implemented PDF workflow; physical printer not implemented |
| OBJ-05 | Knowledge archive and print history | Partial / read-oriented archive |
| OBJ-07 | Secretary visual panel; commands route to Lead Manager Arman; no separate Secretary AI agent | Partial |
| OBJ-09 | Owner movement / office interaction posts to legacy API | Partial / legacy endpoint |
| OBJ-10 / PAP | Persisted Paper inbox, read state, approval link, PDF print job | Implemented basic local workflow |
| ORG | Department catalogue and employee mapping returned by backend; current roster is seeded/static | Partial; no organization CRUD |
| CMD-06 / CMD-07 | Existing Orchestrator, RAG and OfficeTools allowlist retained | Partial; no new per-agent capability engine or sandbox |
| PRJ-10–13 | Task create, transition validation, acceptance criteria and evidence requirement for completion | Implemented basic backend workflow |
| APR-01–11 | Approval payload hash / immutability, review, outbox, SMTP / HTTPS webhook adapters, unknown result boundary | Implemented basic local workflow; no complete remote reconciliation |
| CCC | Company overview, tasks, team, Paper inbox, meetings, approvals and archive panels | Implemented in client source; runtime unverified |
| SYN-01–09 | Status polling and cursor-based HTTP event retrieval | Partial; no WebSocket replay/ack protocol |
| NFR-SEC | .env secrets, loopback bind, optional bearer token on all API paths, approval gates | Partial; no short-lived Owner session or process sandbox |
| NFR-PRF-01 | Project uses GL Compatibility, frame cap 120 and basic NPC workload | Unverified; no hardware benchmark |

## Acceptance boundaries

- 56 backend unit tests pass. HTTP smoke tests exercise the local API without invoking a live LLM provider.
- Godot GDScript parsing/runtime, rendering, physics, camera clipping, GLB animation and FPS have not been run in the build environment.
- No licensed / third-party rigged GLB assets are bundled. Procedural character fallbacks remain.
- NPC navigation uses authored waypoints plus local steering, not NavigationAgent3D / NavigationMesh.
- Local visual meeting animation is not the persisted meeting record. The company UI/API writes the actual record.
- SMTP and deployment require user-owned credentials / endpoint configuration. No live external action has been executed during build validation.
- Purchases remain manual. `unknown` outbox results require operator reconciliation and are not retried automatically.

Full SRS v1.3 acceptance still requires the outstanding items above and the desktop checklist in `FINAL-ACCEPTANCE.md`.
