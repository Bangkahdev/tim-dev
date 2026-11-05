> **Status dokumen:** Bagian implementasi 2.5D / Three.js di bawah adalah catatan sejarah dan referensi untuk prototype lama. Client 3D utama saat ini adalah Godot di `godot/` (first-person default, third-person toggle dengan `V`). Gunakan dokumentasi root `docs/` dan `README.md` sebagai arahan implementasi aktif.

# Bangkah Company Simulator: Product and Technical Direction

## Product definition

Bangkah is a real company workspace presented through a living office simulation. The office is the interaction layer, not a substitute for the company's actual systems. Projects, source files, tasks, meetings, decisions, reports, and archives must remain real records in the backend.

The owner joins the same world as a controllable character. AI employees are represented as autonomous characters whose movement and activity reflect server-side work events. A visual animation must never imply that work happened when no corresponding event or artifact exists.

## Current prototype boundary

The current build is a 2.5D isometric prototype. It provides:

- A large isometric office illustration with independent employee characters.
- Hover-only room names, occupancy labels, employee names, and idle activity labels.
- Click-to-move and WASD/arrow-key movement for the Owner avatar.
- `E` interactions for a workstation, coffee station, meeting room, lounge, and company archive point.
- Persistent owner coordinates, current room, activity, and interaction events in SQLite.
- Existing AI employee state, tasks, meetings, messages, activity events, workspaces, and generated reports.

The 2.5D scene remains available as the legacy Virtual Office. A separate playable 3D preview is now implemented with Three.js: a cutaway HQ floor, third-person Owner camera, procedural characters, a receptionist, keyboard/touch controls, obstacle collision, grid-based NPC routing, ambient NPC routines, and existing Office API integration. This is an early 3D prototype, not a production game client.

## Simulator interaction model

| World object | Interaction | Real application destination |
| --- | --- | --- |
| Workstation | Sit / use computer | Project workspace, source files, tasks, terminal and QA results |
| Meeting table | Join meeting | Meeting record, agenda, attendees, minutes and decisions |
| Coffee station | Make coffee | Owner character action and office event |
| Lounge | Sit / rest | Owner presence and activity event |
| Archive shelves | Open archive | Historical projects, deliverables, reports, decisions and releases |
| Employee avatar | Talk / assign work | Persistent direct or group chat and Orchestrator tools |

## Company data model to grow toward

- `Company`: Bangkah identity, departments, policies and operating hours.
- `Employee`: AI employee profile, role, model, skills, permissions and avatar.
- `Player`: human owner identity, avatar appearance, world position and inventory/cosmetics.
- `Room` and `Interactable`: walkable areas, workstations, meeting tables, coffee machines and archives.
- `Project`: real project identity, repository/workspace path, status, owner and deliverables.
- `Task`: assignee, dependency, priority, status, evidence and acceptance criteria.
- `Meeting`: participants, agenda, transcript, decisions and follow-up tasks.
- `Artifact`: source files, builds, test results, documents and release packages.
- `ArchiveRecord`: immutable links to completed project snapshots, reports and decisions.
- `WorldEvent`: movement, conversations, work sessions, object interactions and project events.

## Recommended full 3D direction

Move the renderer to a dedicated WebGL client (Three.js or Babylon.js) with GLB/glTF character and furniture assets. Keep the office API and company data model independent from the renderer so a future game client can replace the 2.5D scene without changing how projects and agents work.

The full 3D layer should add:

1. A walkable floor mesh and collision geometry for walls, desks and partitions.
2. A navigation mesh for AI employee pathfinding; agents should route around furniture and doors.
3. A third-person follow camera, keyboard movement, pointer/touch controls and avatar customization.
4. Character animation states: idle, walk, run, sit, type, talk, listen, drink, carry and interact.
5. Server-authoritative player and employee positions, with interpolation for smooth movement.
6. Interaction points attached to actual objects. A workstation action opens a real project; it must not just play a typing animation.
7. Realtime world events over WebSocket so agent conversations, meetings and task changes update the room.

## Trust and realism rules

- An employee is `working` only while a real task or work session is active.
- A conversation bubble appears only from a persisted chat/interaction event.
- A character may walk to a desk only when a real task or user command assigned that destination.
- A completed project archive points to immutable deliverables, test evidence and a final report.
- Idle animations are cosmetic and must not be represented as work activity.
- Owner movement and object interactions are saved to the company event log.

## Suggested delivery phases

### Phase A — Current 2.5D interaction foundation

Finish reliable movement, owner interactions, hover-only labels, status synchronization, and persistence. Add automated tests around world coordinates and interaction events.

### Phase B — Real office operations

Make workstations open actual project workspaces, meeting tables create and join real meetings, and archive shelves open project histories and artifacts. Add project-level permissions and audit trails.

### Phase C — 3D character and world client

**Prototype milestone delivered:** a separate Three.js 3D world with procedural characters and furniture, third-person camera, basic collisions, grid-based NPC pathfinding, a reception lobby, ambient routines, and Office API polling. The 2.5D renderer remains available as a fallback.

Remaining work for production quality:
- Replace procedural character meshes with optimized, rigged GLB assets and authored animation clips.
- Replace the simple obstacle grid with a proper collision/physics layer and baked navigation mesh.
- Add floor selection, stairs/elevators, accessibility options, mobile camera gestures and configurable key bindings.
- Move status updates from polling to WebSocket events and interpolate network-authoritative positions.
- Add asset bundling/local hosting so the 3D client works without an external CDN dependency.

### Phase D — Persistent company simulator

Add avatar customization, multiplayer owner presence, role/department permissions, scheduled office events, archive snapshots, and deployment for multiple authorized users.
