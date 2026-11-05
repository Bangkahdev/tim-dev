# Bangkah Headquarters — Environment v0.3

The 3D headquarters is the primary playable interface. The game starts inside the office, not in a dashboard. The default camera is first-person; `V` switches to an over-the-shoulder third-person follow camera for avatar and room inspection.

## Building footprint

- Main floor: approximately **84 m × 80 m**.
- Single-storey walkable headquarters with a glazed facade, south-facing entry canopy, exterior sign and landscaped arrival area.
- Interior offices use framed glass partitions with door openings.
- Suspended acoustic ceiling panels, HVAC return grilles, linear ceiling lights and lobby pendants are present.

## Ground-floor departments

| Zone | Main contents |
|---|---|
| Owner Suite | Executive desk, multi-monitor setup, guest sofa, coffee table, strategy shelf, physical incoming-paper tray |
| Executive Secretary | Secretary workstation, agenda pinboard, paper tray, credenza and file storage |
| Engineering Leadership | Arman and Sinta workstations, sprint / kanban board |
| System Architecture | Raka workstation, architecture display wall |
| Frontend / Design Studio | Dira workstation, design workstation, UI moodboard |
| Quality Assurance Lab | Tika workstation, automated-test station, device test bench |
| Backend Engineering | Bima workstation, service-monitoring desk, server cabinet |
| Boardroom | Long conference table, ten chairs, large display, whiteboard and credenza |
| Reception / Lobby | Mira's reception counter, check-in monitor, visitor seating, directory display and feature wall |
| API / Infrastructure Lab | Naya workstation, server racks and API topology board |
| Archive / Print Room | Archive shelves, report shelves, printer, paper output and checkout counter |
| Promotion Studio | Three reserved desks for Promotion Manager, Content Writer and Social Media roles; kept empty until backend agents are provisioned |
| Staff Lounge | Sofas, coffee table, rug and plants |
| Pantry | Counter run, upper cabinets, sink, coffee machine, microwave, fridge and island seating |

## Character behavior

- Seven engineering employees use department workstations.
- Mira is placed behind the reception counter facing visitors.
- A separate Secretary character slot and desk are included as a visual placeholder. It is not registered as a backend employee and does not claim to perform work yet.
- When a backend employee record reports `working`, the employee returns to their workstation and uses a seated typing pose. The visual pose does not create or alter backend status.
- Idle employees use short, role-specific ambient routes within their department. These are waypoint-based; NavigationMesh, dynamic obstacle avoidance and crowd avoidance are not implemented.
- Employee floating nameplates are hidden by default. Names are shown by interaction prompts and office signage.

## Physical interactions

- Owner computer: opens the Company Command Center panel prototype.
- Owner paper tray: opens the document inbox prototype.
- Secretary desk: opens the agenda prototype.
- Boardroom: opens the meeting prototype.
- Printer: currently provides an interaction prompt; PrintJob and PDF generation await the SRS v1.3 backend API.
- Archive: opens the archive prototype.
- Reception desk / Mira, coffee station and lounge provide local interactions.

## Implementation note

The environment uses native Godot geometry and generated materials in `godot/scripts/office_environment.gd`; there is no external asset-pack dependency. Characters are procedural interim meshes with improved proportions, not rigged GLB models. Rendering, collision, camera composition and frame rate must be verified in Godot 4.3+ before acceptance.
