"""End-to-end Godot Owner session-login check.

Starts the real office_server handler on a throwaway loopback port with a fresh
SQLite database and a generated Owner password, then runs the headless Godot
check in ``godot/scripts/auth_login_check.gd``. The Godot check drives the real
settings form, logs in through ``/api/auth/login``, calls ``/api/auth/me`` with
the returned session token, logs out through ``/api/auth/logout``, and verifies
the old token is revoked (401).

Usage (from backend/):
    PYTHONPATH=.pylibs:. python3.12 tools/check_godot_auth.py

Exit code 0 means the Godot login/logout flow passed. The test database lives
under ``backend/workspace/`` and is removed on success. No production database,
Owner password, legacy token, or cloud credential is touched.
"""
from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
GODOT_DIR = REPO / "godot"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(BACKEND / ".pylibs") not in sys.path:
    sys.path.insert(0, str(BACKEND / ".pylibs"))

# Configure the server before importing office_server so its module-level STORE
# points at a throwaway database. Empty strings win over developer .env values
# because load_dotenv() does not override existing environment variables.
_WORK_ROOT = BACKEND / "workspace"
_WORK_ROOT.mkdir(parents=True, exist_ok=True)
_TMP = Path(tempfile.mkdtemp(prefix="godot-auth-check-", dir=_WORK_ROOT))
_PASSWORD = secrets.token_urlsafe(18)
os.environ["BANGKAH_DB_PATH"] = str(_TMP / "office.db")
os.environ["BANGKAH_OWNER_PASSWORD"] = _PASSWORD
os.environ["BANGKAH_SESSION_HOURS"] = "1"
os.environ["BANGKAH_API_TOKEN"] = ""
os.environ["BANGKAH_LEGACY_TOKEN_ROLE"] = ""

import office_server  # noqa: E402
from core.auth.sessions import ensure_bootstrap_owner  # noqa: E402


def _godot_binary() -> str | None:
    candidate = os.getenv("GODOT_BIN", "").strip()
    if candidate:
        return candidate
    candidate = shutil.which("godot") or shutil.which("godot4")
    if candidate:
        return candidate
    fallback = Path.home() / ".local" / "bin" / "godot"
    return str(fallback) if fallback.is_file() else None


def main() -> int:
    godot = _godot_binary()
    if not godot:
        print("GODOT-AUTH-CHECK: SKIP (godot binary not found; set GODOT_BIN)")
        shutil.rmtree(_TMP, ignore_errors=True)
        return 0

    ensure_bootstrap_owner()
    server = ThreadingHTTPServer(("127.0.0.1", 0), office_server.OfficeHandler)
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = os.environ.copy()
    env.update({
        "BANGKAH_TEST_URL": base,
        "BANGKAH_TEST_USER": "owner",
        "BANGKAH_TEST_PASSWORD": _PASSWORD,
    })
    try:
        result = subprocess.run(
            [godot, "--headless", "--path", str(GODOT_DIR),
             "--script", "res://scripts/auth_login_check.gd"],
            capture_output=True, text=True, timeout=180, env=env,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip()[-3000:])
    passed = result.returncode == 0 and "AUTH-CHECK: PASS" in (result.stdout or "")
    print(f"GODOT-AUTH-CHECK: {'PASS' if passed else 'FAIL'}")
    if passed:
        shutil.rmtree(_TMP, ignore_errors=True)
    else:
        print(f"Evidence kept at: {_TMP}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
