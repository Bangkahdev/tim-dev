# NPC Behavior Model — v0.5

This document describes client-side animation and ambient movement. It does not replace the backend employee/task state machine.

## Authority boundary

`office_status` is populated from backend employee records. Online meeting attendance waits for the first employee record; the client does not assume an uninitialized employee is idle. Offline mode is explicitly local/demo behavior. Ambient actions and the local boardroom preview never create tasks or promote employees to `working`. A work/typing pose is shown only when the backend reports `working`. If an attendee changes to a backend-owned status other than `idle`/`completed` during a local meeting preview, the backend state wins and the character leaves the meeting.

## Employee state behavior

| Backend status | Character behavior |
|---|---|
| `working` | Returns to assigned workstation, then holds the procedural typing pose or matching GLB clip. |
| `idle` | Performs a role-specific ambient visit, pauses, then returns home. |
| `completed` | Review/idle posture and non-task ambient routine. |
| `talking` / `listening` | Stops ambient movement and uses a restrained conversation gesture. |
| `failed` / `blocked` | Stops ambient movement and uses a concerned/thinking pose. |

## Movement and local avoidance

The movement state is `home → outbound → at_destination → returning → home`. Ambient destinations are role-specific. During movement, NPCs use local separation from other office NPCs, short forward physics rays against static collision geometry, side probes to select a clearer direction, and a stuck timer to alternate avoidance bias. Boardroom routes use authored waypoints through the doors in the existing floor plan.

This is **local steering and waypoint navigation**, not NavigationAgent3D, NavigationMesh pathfinding or a global crowd simulation. It improves predictable short routes, but complex dynamic obstacles and dense crowds still require runtime testing and a later navigation pass.

## Boardroom preview

When the Owner uses the physical Boardroom interaction, up to seven employees with backend status `idle` or `completed` are invited to a timed local visual preview. Attendees walk to authored chairs, face the table, and alternate between speaking and listening gestures. The preview ends automatically and attendees return along the saved route. If the backend changes an attendee to a non-idle/non-completed state, that employee leaves the preview.

The preview is not a persisted meeting. It does not create transcripts, minutes, decisions, tasks, approvals or audit events. Those require the future backend meeting lifecycle API. See `MEETING-PHASE.md`.

## Character asset pipeline

`CharacterFactory` first checks `res://assets/characters/<employee_id>.glb`. If a matching GLB scene imports with a `Node3D` root, it is loaded with a compatible `AnimationPlayer`; otherwise the procedural interim model is used. The client looks for common aliases for idle, walk, type, talk, listen, write and phone clips. See `../godot/assets/characters/README.md`. No external character assets are bundled in this release.

## Receptionist routine

Mira remains at the front desk and alternates between keyboard entry, visitor-log writing, phone confirmation, list review and greeting. Pressing `E` at reception triggers a short greeting. This is an ambient front-desk routine, not a backend employee task.

## Manual validation

1. Start the game offline and verify the world remains explorable.
2. Walk to Mira and press `E`; confirm the greeting and return to front-desk routine.
3. Start the legacy backend and mark an employee `working`; confirm the employee returns to the workstation and uses the work pose.
4. Mark the employee `idle`; confirm ambient routines resume.
5. Trigger `talking`, `listening`, `failed` and `blocked`; confirm ambient movement stops.
6. Trigger the local boardroom preview and verify door waypoints, seating, speaking turns and return paths.
7. Change one meeting attendee to `working`; confirm the server-owned state wins.
8. Test hallway crowd avoidance and inspect any stuck/oscillating route.
9. Verify the Owner in third-person and first-person modes.

## Known limits

- Default characters remain procedural meshes because no third-party rigged character assets are bundled.
- GLB loading and clip alias playback are implemented as an asset slot, but not runtime-verified in this environment.
- Avoidance is local and waypoint-based; it is not full NavigationMesh pathfinding.
- Ambient and local meeting preview state are not persisted.
- Godot runtime parsing, rendering, collision, camera, animation and FPS require editor playtesting.
