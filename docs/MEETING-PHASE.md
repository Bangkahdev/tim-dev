# Local Boardroom Meeting Phase

## User flow

1. Walk to the physical Boardroom interaction point.
2. Look toward the boardroom prompt and press `E`.
3. Eligible idle/completed Engineering employees follow role-aware corridor waypoints to available chairs.
4. Attendees face the table and switch between speaking and listening gestures.
5. After the local preview ends, attendees return along their recorded route to their own workstation.

## Attendance and authority

- Only employees whose current backend status is `idle` or `completed` can join the visual preview.
- While the client is online, an employee must have a backend record received before the client can treat its initial status as eligible. Offline mode may use the local demo defaults.
- Employees marked `working`, `failed`, `blocked`, `talking` or `listening` are not pulled from their current backend-owned state.
- If a backend update changes an attendee to a non-idle/non-completed state during the preview, that employee exits the preview and follows the saved return route.
- The Owner remains player-controlled. The preview does not move the Owner automatically.

## Explicit prototype boundary

This phase is a **local visual meeting preview only**. It does not call a new meeting API and does not create a persisted meeting, transcript, minutes, decision, task, approval or audit event. The existing Meetings UI remains labeled as preview data. Do not represent the preview as a real company meeting until the backend meeting lifecycle endpoints and event persistence are implemented.

## Navigation implementation

The meeting uses authored corridor/door waypoints based on the current floor plan, then a short chair approach. Each NPC also applies local separation against other NPCs, forward physics ray checks against static geometry, side selection around obstacles, and a stuck timeout that flips the preferred avoidance side. This is a lightweight steering layer, **not** a NavigationMesh or globally optimal pathfinder.

## Manual acceptance

- Start offline and interact with the Boardroom. At least two idle employees should begin moving toward the meeting room.
- Confirm each employee uses the opening for their room rather than walking through a glass partition.
- Confirm seated characters face the table and speaking gestures rotate among seated participants.
- Keep one employee marked `working` in the backend; that character must remain assigned to its workstation and not attend.
- Change an attendee to `working` during the preview; the local meeting state must release that character and return it to its workstation.
- After the preview ends, all attendees should return without becoming `working` unless the backend says so.
- Inspect NPC crowd movement at corridor doorways for overlap, oscillation and blocked routes.
