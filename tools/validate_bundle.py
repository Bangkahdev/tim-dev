#!/usr/bin/env python3
"""Static sanity checks for the Bangkah Godot delivery bundle."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
errors: list[str] = []

if not (GODOT / "project.godot").is_file():
    errors.append("Missing godot/project.godot")
if not (GODOT / "scenes/main.tscn").is_file():
    errors.append("Missing godot/scenes/main.tscn")

# Resolve res:// preloads and script references from Godot source files.
for file in list((GODOT / "scripts").glob("*.gd")) + list((GODOT / "scenes").glob("*.tscn")):
    source = file.read_text(encoding="utf-8")
    refs = re.findall(r'res://([^"\']+)', source)
    for ref in refs:
        target = GODOT / ref
        if not target.exists():
            errors.append(f"Broken resource reference in {file.relative_to(ROOT)}: res://{ref}")

# Ensure the docs needed to run/review the project are present.
required_docs = [
    "README.md",
    "VERSION",
    "docs/API-REFERENCE.md",
    "docs/OPERATIONS-AND-SECURITY.md",
    "docs/FINAL-ACCEPTANCE.md",
    "docs/ARCHITECTURE.md",
    "docs/ENVIRONMENT-DESIGN.md",
    "docs/CONTROLS-AND-CAMERA.md",
    "docs/VISUAL-STYLE-GUIDE.md",
    "docs/BACKEND-INTEGRATION.md",
    "docs/SRS-V1.3-TRACEABILITY.md",
    "docs/MILESTONE-1-PLAYBOOK.md",
    "docs/TESTING-AND-RELEASE.md",
    "docs/ASSET-REGISTER.md",
    "docs/NPC-BEHAVIOR.md",
    "docs/MEETING-PHASE.md",
    "docs/PHASE-V0.5-REPORT.md",
    "godot/assets/characters/README.md",
    "backend/core/company_operations.py",
    "backend/core/action_adapters.py",
    "backend/tests/test_company_operations.py",
]
for rel in required_docs:
    if not (ROOT / rel).is_file():
        errors.append(f"Missing documentation: {rel}")


# Protect the behavior/authority contract and visible-player default.
npc_source = (GODOT / "scripts/npc.gd").read_text(encoding="utf-8")
main_source = (GODOT / "scripts/main.gd").read_text(encoding="utf-8")
player_source = (GODOT / "scripts/player.gd").read_text(encoding="utf-8")
if 'elif office_status in ["idle", "completed"]:' not in npc_source:
    errors.append("NPC ambient routines must only run for idle/completed backend states")
if 'var working := office_status == "working" and not walking' not in npc_source:
    errors.append("NPC working pose must remain tied to backend-confirmed working status")
if 'receptionist.trigger_greeting()' not in main_source:
    errors.append("Reception interaction must trigger the receptionist greeting routine")
if '_set_view_mode("third_person")' not in player_source:
    errors.append("Owner avatar must be visible by default in third-person mode")
if 'func begin_local_meeting' not in npc_source or 'func end_local_meeting' not in npc_source:
    errors.append("NPC local meeting lifecycle methods are missing")
if 'func _steer_around_obstacles' not in npc_source or 'func _update_stuck_recovery' not in npc_source:
    errors.append("NPC local avoidance and stuck recovery methods are missing")
if 'func _start_local_meeting_preview' not in main_source or 'Simulasi lokal' not in main_source:
    errors.append("Boardroom local preview must be explicit and wired from main.gd")
if '_connection_online and not npc.backend_record_received' not in main_source:
    errors.append("Online meeting attendance must wait for authoritative employee state")
if 'res://assets/characters/' not in (GODOT / "scripts/character_factory.gd").read_text(encoding="utf-8"):
    errors.append("Optional GLB character asset path is missing")

# Ensure the game exposes the persisted task / approval / PDF workflows.
ui_source = (GODOT / "scripts/company_ui.gd").read_text(encoding="utf-8")
if 'func _open_task_evidence_dialog' not in ui_source or '"task_transition"' not in ui_source:
    errors.append("Task transition / evidence UI is missing")
if 'PAYLOAD YANG AKAN DIEKSEKUSI' not in ui_source:
    errors.append("Exact approval payload review is missing")
if 'download_print_job' not in ui_source or 'func _on_print_download_completed' not in main_source:
    errors.append("Paper PDF download flow is missing")

# Private runtime data and real env files must never be shipped.
for pattern in [".env", "*.sqlite", "*.db"]:
    for candidate in ROOT.rglob(pattern):
        if candidate.name == ".env.example":
            continue
        if any(part in {".git", ".godot", ".venv", "__pycache__"} for part in candidate.parts):
            continue
        errors.append(f"Potential private/runtime file in bundle: {candidate.relative_to(ROOT)}")

if errors:
    print("BUNDLE VALIDATION FAILED")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("BUNDLE VALIDATION PASSED")
print("- Godot project and main scene present")
print("- res:// references resolve")
print("- required documentation present")
print("- player/NPC behavior authority checks passed")
print("- meeting preview, waypoint avoidance and optional GLB hooks present")
print("- task evidence, approval payload review and PDF download hooks present")
print("- no private env/database artifacts detected")
