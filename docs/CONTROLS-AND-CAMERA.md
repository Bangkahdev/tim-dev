# Controls and Camera

## Camera modes

### Third-person follow camera (default)

- The Owner avatar remains visible in an over-the-shoulder view while walking.
- Follow camera uses a SpringArm3D to reduce camera clipping against walls.
- Mouse wheel zooms the follow camera between configured limits.
- Camera pitch is clamped so the player can inspect the office without flipping the view.

### First-person

- Toggle with `V`.
- Camera height: 1.66 m above player origin.
- Field of view: 76 degrees.
- The full-body mesh is hidden to avoid clipping into the camera.
- Subtle sleeve/hand meshes are attached to the camera as a restrained viewmodel.
- Walking head-bob is small and disabled while stationary.

## Input map

| Input | Behavior |
|---|---|
| W / Up | Forward |
| S / Down | Backward |
| A / Left | Strafe left |
| D / Right | Strafe right |
| Shift | Sprint |
| Space | Jump |
| Mouse movement | Look / aim |
| E | Interact |
| V | Switch camera mode |
| Mouse wheel | Zoom third-person camera |
| Esc | Release mouse |
| Left click | Re-capture mouse |
| F1 | Overview panel |
| F2 | Owner documents panel prototype |
| F3 | Projects panel prototype |
| F4 | Team panel prototype |

## Interaction focus

The game does not show a permanent marker above every object. A target becomes interactable when it is within approximately 3.25 m and inside the camera's forward view cone. The HUD then presents a contextual `E` prompt. The backend remains the authority for task and employee state.

## Input lock

When a company panel or employee conversation is open:

- Player movement is disabled.
- Mouse cursor is released for UI operation.
- Closing the panel re-captures the mouse.

## Tuning values

The primary settings live in `godot/scripts/player.gd`: `walk_speed`, `sprint_speed`, `jump_velocity`, `mouse_sensitivity`, `eye_height`, camera FOV, spring length and pitch clamps. Test both camera modes after changing any of these values.
