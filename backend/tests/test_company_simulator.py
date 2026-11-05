from pathlib import Path
import re
import tempfile

from core.office_store import OfficeStore

ROOT = Path(__file__).resolve().parents[1]


def test_room_and_employee_labels_are_hover_only():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "#overview .floor-plan .office-zone>b" in html
    assert "#wholeOffice .floor-plan .office-zone:hover>b" in html
    assert "#overview .employee-sprite .activity-tag" in html
    assert "#wholeOffice .employee-sprite:hover .activity-tag" in html


def test_owner_avatar_has_walk_and_interaction_controls():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "owner-avatar-model" in html
    assert "owner-controls-hint" in html
    assert "function bindOwnerControls()" in html
    assert "function interactOwner()" in html
    for action in ("computer", "coffee", "meeting", "lounge", "archive"):
        assert f"id:'{action}'" in html


def test_simulator_camera_supports_pan_zoom_reset():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "function applyOfficeCamera()" in html
    assert "function resetOfficeCamera()" in html
    assert "canvas.addEventListener('wheel'" in html
    assert "pointermove" in html


def test_owner_player_state_and_interaction_are_persisted():
    with tempfile.TemporaryDirectory() as tmp:
        store = OfficeStore(Path(tmp) / "office.db")
        moved = store.update_owner_player(52, 82, "lounge", "walking")
        assert moved["room_id"] == "lounge"
        action = store.interact_owner("computer", 52, 39, "architect")
        assert action["activity"] == "working"
        events = store.snapshot()["events"]
        assert any(e["event_type"] == "owner_moved" for e in events)
        assert any(e["event_type"] == "owner_interaction" and e["entity_id"] == "computer" for e in events)


def test_real_3d_avatar_assets_are_present_for_agents_and_owner():
    avatars = ROOT / "web" / "assets" / "avatars"
    for name in ("lead", "coo", "architect", "backend", "api", "frontend", "qa", "owner"):
        asset = avatars / f"{name}.webp"
        assert asset.is_file() and asset.stat().st_size > 5_000
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'src="/assets/avatars/${a.id}.webp"' in html
    assert 'src="/assets/avatars/owner.webp"' in html
    assert "ownerInteractionCard" in html


def test_idle_employee_activity_is_not_randomly_simulated():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "Math.floor(Date.now()/10000" not in html
    assert "const s=agentStatus(a),state=s==='working'" in html


def test_owner_player_api_routes_are_wired_in_the_server():
    server = (ROOT / "office_server.py").read_text(encoding="utf-8")
    assert 'route == "/api/office/player"' in server
    assert '"/api/office/player"' in server
    assert 'STORE.owner_player_state()' in server
    assert 'STORE.update_owner_player(' in server
    assert 'STORE.interact_owner(' in server


def test_playable_3d_company_simulator_is_integrated():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = ROOT / "web" / "assets" / "company-simulator-3d.js"
    assert 'data-view="simulator3d"' in html
    assert 'id="company3dCanvas"' in html
    assert 'type="module" src="/assets/company-simulator-3d.js"' in html
    assert script.is_file() and script.stat().st_size > 10_000
    js = script.read_text(encoding="utf-8")
    for feature in ("PerspectiveCamera", "requestPointerLock", "pathfind", "stationByEmployee", "/api/status", "/api/office/player"):
        assert feature in js
    assert "receptionist" in js and "Receptionist" in js


def test_3d_simulator_does_not_fake_employee_work_status():
    js = (ROOT / "web" / "assets" / "company-simulator-3d.js").read_text(encoding="utf-8")
    assert "npc.record?.status==='working'" in js
    assert "setNpcTarget(npc,item,'walking')" in js
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "tidak mengubah status pekerjaan" in readme
