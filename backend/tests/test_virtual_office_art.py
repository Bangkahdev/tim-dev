from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def test_isometric_office_asset_is_bundled_and_referenced():
    asset = ROOT / "web" / "assets" / "bangkah-office-isometric.webp"
    assert asset.is_file()
    assert asset.read_bytes()[:4] == b"RIFF"
    assert asset.read_bytes()[8:12] == b"WEBP"
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '/assets/bangkah-office-isometric.webp' in html

def test_all_office_rooms_are_real_interactive_hotspots():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    room_ids = set(re.findall(r'class="office-zone [^"]+" data-room-id="([^"]+)"', html))
    assert room_ids == {
        "owner", "manager", "planning", "architect", "meeting",
        "backend", "api", "frontend", "qa", "lounge", "kitchen"
    }
    assert 'viewBox="0 0 1000 1000"' in html
    assert 'draggable="true"' in html

def test_pixel_agent_animations_and_reduced_motion_exist():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for animation in ("pixelIdle", "pixelWalk", "pixelType", "pixelTalk"):
        assert f"@keyframes {animation}" in html
    assert "prefers-reduced-motion:reduce" in html
    assert "employee-sprite.speaking-server" in html
    assert "employee-sprite.listening" in html
