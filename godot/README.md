# Godot Client

Open `project.godot` in Godot 4.3+ and press F5.

## Cameras

- Third-person is the default (`OfficePlayer`); press `V` to switch to first-person and press `V` again to return.
- Mouse movement looks around in both modes.
- Mouse wheel zoom works only in third-person mode.

## Input

WASD / arrows: move · Shift: sprint · Space: jump · E: interact · Esc: release cursor · V: camera · F1–F4: supporting company panels.

## v0.5 meeting and character pipeline

- Use the physical Boardroom interaction (`E`) to start the local meeting movement preview. The preview does not persist a meeting or create backend artifacts.
- NPC movement combines authored door waypoints with local separation and obstacle probes. It is a lightweight steering layer, not global NavigationMesh pathfinding.
- Optional rigged models can be placed in `assets/characters/<employee_id>.glb`. Each model should expose a compatible `AnimationPlayer`; procedural models remain the fallback. See `assets/characters/README.md`.

## Key files

- `scripts/main.gd`: scene orchestration, legacy API requests, HUD, interaction focus.
- `scripts/player.gd`: first-person / third-person controller and interaction signals.
- `scripts/character_factory.gd`: GLB loader with procedural humanoid fallback.
- `scripts/npc.gd`: employee state, GLB/procedural animation, ambient routes, local avoidance and meeting state.
- `scripts/office_environment.gd`: building shell, rooms, furniture, ceiling, lighting and landscape.
- `scripts/company_ui.gd`: supporting in-world business UI. Demo data is labeled.

## Important

The Python backend remains the source of truth. Paper Workflow, transactional approvals/outbox, Owner session auth, sandbox enforcement and WebSocket replay from SRS v1.3 are not implemented in this client package. See `../docs/BACKEND-INTEGRATION.md` and `../docs/SRS-V1.3-TRACEABILITY.md`.
