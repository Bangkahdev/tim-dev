# Environment Design — Bangkah Headquarters

## Design intent

The headquarters is the main product interface. It should read as a real, contemporary Indonesian technology company: human-scale proportions, clear circulation, functional room groupings, glass privacy partitions, acoustic ceiling, understated signage and neutral material palette. It is not an isometric board, floating dashboard or cartoon diorama.

## Building envelope

| Property | Target |
|---|---|
| Footprint | Approx. 84 m × 80 m |
| Floors | One in v0.5 |
| Clear interior height | Approx. 3.8–4.0 m |
| Structure | Concrete / painted wall perimeter, glass facade and framed glass office partitions |
| Roof treatment | Suspended acoustic ceiling panels, HVAC grilles and linear/recessed office lighting |
| Entry | South-facing glazed double door with canopy and landscaped approach |
| Render mode | Godot GL Compatibility |

## Space program

| Space | Main elements | Physical interaction |
|---|---|---|
| Main entrance | Glazed doors, canopy, approach path, company sign | Enter office |
| Reception / lobby | Reception counter, check-in monitor, visitor seating, wayfinding | Talk to Mira |
| Owner Suite | Executive desk, dual monitors, guest seating, tray | Open Company Command Center / paper tray |
| Executive Secretary | Secretary desk, agenda board, credenza | Open agenda prototype |
| Engineering Leadership | Arman and Sinta desks, sprint board | Talk to employees |
| System Architecture | Raka workstation, architecture wall | Talk to employee |
| Frontend / Design | Dira workstation and design board | Talk to employee |
| QA Lab | Tika workstation, test bench and device screens | Talk to employee |
| Backend Engineering | Bima workstation, service display and rack | Talk to employee |
| API / Infrastructure | Naya workstation, server racks and topology wall | Talk to employee |
| Boardroom | Long table, meeting chairs, large display, whiteboard | Open meeting prototype |
| Archive / Print | Shelves, report racks, printer and checkout desk | Open archive / printer prompt |
| Promotion Studio | Reserved manager/content/social desks | Reserved until agents are provisioned |
| Staff Lounge | Sofa groups, rug, coffee table, plants | Local lounge interaction |
| Pantry | Counter, cabinets, sink, coffee, microwave and fridge | Coffee interaction |

## Circulation

- The lobby forms the public front-of-house.
- A central corridor distributes access to the north executive wing, central engineering spaces and south support rooms.
- Department doors are sized for NPC and Owner movement.
- Glass partitions preserve visual connection while communicating room boundaries.
- Keep the central path free of furniture; avoid routing NPCs through desk clusters.

## Interaction placement

Interactable points are configured in `godot/scripts/main.gd` and use the same world coordinate system as the environment. The focus test checks range and camera direction. Remove visual floating markers; the contextual prompt is enough.

| ID | Intended location |
|---|---|
| `reception` | Front side of Mira's reception counter |
| `computer` | Owner workstation |
| `owner_tray` | Physical incoming-paper tray on Owner desk |
| `secretary_desk` | Secretary's agenda workstation |
| `meeting` | Boardroom entrance / table edge |
| `printer` | Print station in Archive / Print Room |
| `coffee` | Pantry coffee machine |
| `lounge` | Staff Lounge seating zone |
| `archive` | Archive checkout counter |

## Coordinate and layout ownership

- World geometry is authored in `godot/scripts/office_environment.gd`.
- Room centers and employee home coordinates are currently defined in `godot/scripts/main.gd`.
- Employee ambient routes are defined in `_ambient_plans_for()` in `main.gd` and consumed by `godot/scripts/npc.gd`.
- Do not independently move furniture, employee home positions and interaction points without checking all three files.

## Visual QA checklist

- A person at 1.66 m eye height can read reception signage and room labels.
- Doors and corridor clearances feel plausible at 1.0× scale.
- The reception desk does not block the visitor path.
- No workstation, plant or chair intersects the intended NPC route.
- Glass is visible through highlights and mullions but does not become an opaque black wall.
- Ceiling lights do not clip through panels.
- The Owner tray and printer are visually identifiable from a few metres away.
- The office remains readable in first-person and third-person camera modes.
