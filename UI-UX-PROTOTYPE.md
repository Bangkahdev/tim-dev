# UI / UX — v0.3

The main interaction is the 3D headquarters. The user does not start in a dashboard.

## In-world UI

- Minimal HUD: company/location status, a small center reticle, contextual `E` prompt and transient feedback toast.
- Employee names/statuses are not permanently floating above characters.
- Interaction prompts appear only when an object or employee is close and inside the camera view cone.
- Owner computer opens Company Command Center prototype.
- Owner tray opens document reader prototype.
- Secretary desk opens agenda prototype.
- Boardroom opens meetings prototype.
- Archive opens archive prototype.

## Supporting company panels

The `company_ui.gd` panel is an in-world application used at a computer / office object. It is not the home screen. Demo records are labeled `DATA CONTOH` and must not be mistaken for backend records.

## Style

Neutral charcoal / slate surfaces, muted sage accents, restrained amber for attention, lower-radius edges, compact typography and minimal decoration. The environment remains visible behind the UI whenever a panel is not open.

## Preview

Open `design-preview/index.html` for a static environment/design preview. It contains visual-direction concept art and the office floorplan. Concept art is not a Godot gameplay capture.
