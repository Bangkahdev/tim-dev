"""Live HTTP runtime check for the workstation / Bangkah OS endpoints.

Runs office_server on a throwaway loopback port and exercises the real routes
with real authentication, terminal, sandbox filesystem and audit behavior.
Leaves no orphan files and does not touch the production owner password.

Usage (from backend/):
    .venv/Scripts/python tools/check_desktop_api.py

Exit code 0 means every check passed.
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import office_server  # noqa: E402

PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"
results = []


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("X-Desktop-Session", token)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def check(name, condition, detail=""):
    results.append((name, bool(condition), detail))
    print(("PASS " if condition else "FAIL ") + name + (" :: " + detail if detail and not condition else ""))


def owner_password():
    env = os.getenv("BANGKAH_OWNER_PASSWORD", "").strip()
    if env:
        return env
    path = BACKEND / "data" / "owner_credentials.local"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OWNER_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Owner password not found")


server = ThreadingHTTPServer(("127.0.0.1", PORT), office_server.OfficeHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    status, body = call("GET", "/api/workstations")
    check("GET /api/workstations", status == 200 and len(body.get("workstations", [])) == 8,
          f"status={status} count={len(body.get('workstations', []))}")

    status, body = call("GET", "/api/workstations/OWNER-PC-001")
    check("GET /api/workstations/OWNER-PC-001",
          status == 200 and body["workstation"]["account_id"] == "owner", f"status={status}")

    status, body = call("POST", "/api/workstations/OWNER-PC-001/login",
                        {"account_id": "owner", "password": "definitely-wrong"})
    check("login rejects wrong password", status == 400, f"status={status}")

    status, body = call("POST", "/api/workstations/OWNER-PC-001/login",
                        {"account_id": "owner", "password": owner_password()})
    token = body.get("token") if isinstance(body, dict) else None
    check("owner login", status == 201 and bool(token) and body.get("apps") ==
          ["files", "terminal", "infrastructure", "company"], f"status={status}")
    if not token:
        raise SystemExit(1)

    status, body = call("GET", "/api/desktop/session", token=token)
    check("GET /api/desktop/session", status == 200 and body["session"]["account"]["id"] == "owner",
          f"status={status}")

    status, body = call("POST", "/api/terminal/exec", {"command": "ls"}, token=token)
    check("terminal ls", status == 200 and "README.md" in body.get("stdout", ""), f"status={status}")

    status, body = call("POST", "/api/terminal/exec", {"command": "whoami"}, token=token)
    check("terminal whoami", status == 200 and body.get("stdout", "").strip() == "owner",
          f"status={status}")

    status, body = call("POST", "/api/terminal/exec", {"command": "ls; whoami"}, token=token)
    check("terminal rejects shell chaining", status == 400, f"status={status}")

    status, body = call("POST", "/api/terminal/exec", {"command": "cat ../company.db"}, token=token)
    check("terminal rejects traversal", status == 400, f"status={status}")

    status, body = call("GET", "/api/desktop/files?path=.", token=token)
    names = {item["name"] for item in body.get("entries", [])}
    check("GET /api/desktop/files", status == 200 and "README.md" in names and "docs" in names,
          f"status={status}")

    status, body = call("POST", "/api/desktop/files/write",
                        {"path": "runtime-check.md", "content": "# Runtime check\n"}, token=token)
    check("write sandbox file", status == 200, f"status={status}")

    status, body = call("GET", "/api/desktop/files/content?path=runtime-check.md", token=token)
    check("read sandbox file", status == 200 and "Runtime check" in body["file"]["content"],
          f"status={status}")

    status, body = call("GET", "/api/desktop/system", token=token)
    integrations = body.get("integrations", {})
    system_dm = integrations.get("domain", {}).get("dns_managed")
    dm_status, dm_body = call("GET", "/api/domain/state")
    check("system info domain consistent with domain service",
          status == 200 and dm_status == 200
          and system_dm == bool(dm_body.get("internal_dns_managed")),
          f"status={status} system={system_dm} domain={dm_body.get('internal_dns_managed')}")

    # ---- Domain & DNS internal (Slice B) ----
    joined_before = dm_body.get("joined_count", 0)
    joined_ids_before = {c["workstation_id"] for c in dm_body.get("joined_computers", [])}

    target = "PC-QA-001" if "PC-QA-001" not in joined_ids_before else "PC-FE-001"
    status, body = call("POST", "/api/domain/join",
                        {"workstation_id": target, "actor": "owner"})
    domain_join = body.get("domain", {})
    check("domain join workstation",
          status == 201 and domain_join.get("workstation_id") == target,
          f"status={status}")

    status, body = call("GET", "/api/domain/state")
    check("domain state after join",
          status == 200 and body.get("internal_dns_managed") is True
          and body.get("joined_count") >= joined_before + 1
          and target in {c["workstation_id"] for c in body.get("joined_computers", [])},
          f"status={status} body={body}")

    status, body = call("GET", "/api/domain/dns/lookup?name=%s.bangkah.my.id" % target)
    check("dns lookup found",
          status == 200 and body.get("found") is True
          and body["record"]["value"] == "127.0.0.1",
          f"status={status} body={body}")

    status, body = call("GET", "/api/domain/dns/lookup?name=tidakada.bangkah.my.id")
    check("dns lookup not found", status == 404, f"status={status}")

    status, body = call("GET", "/api/domain/dns/records")
    check("dns records list",
          status == 200 and len(body.get("records", [])) >= 10,
          f"status={status}")

    status, body = call("POST", "/api/domain/dns/record",
                        {"name": "apps.bangkah.my.id", "type": "CNAME",
                         "value": "dc.bangkah.my.id", "actor": "owner"})
    check("dns record added", status == 201 and body.get("record", {}).get("type") == "CNAME",
          f"status={status}")

    status, body = call("GET", "/api/desktop/system", token=token)
    check("system info domain managed after join",
          status == 200 and body.get("integrations", {}).get("domain", {}).get("dns_managed") is True,
          f"status={status}")

    status, body = call("GET", "/api/desktop/audit", token=token)
    kinds = {event["event_type"] for event in body.get("events", [])}
    check("audit trail", status == 200 and "terminal_exec" in kinds and "desktop_file_write" in kinds,
          f"status={status} kinds={sorted(kinds)}")

    status, body = call("POST", "/api/desktop/session/close", {}, token=token)
    check("close session", status == 200 and body.get("closed") is True, f"status={status}")

    status, body = call("GET", "/api/desktop/session", token=token)
    check("closed session rejected", status == 401, f"status={status}")

    status, body = call("GET", "/api/desktop/session")
    check("missing session rejected", status == 401, f"status={status}")

    # ---- Employee activity engine (real posts, no mocks) ----
    status, body = call("GET", "/api/workstations")
    stations = {item["id"]: item for item in body.get("workstations", [])}
    station = stations.get("PC-BE-001", {})
    account = station.get("account", {})
    check("employee workstation carries account info",
          status == 200 and account.get("id") == "backend" and account.get("role") == "employee",
          f"status={status}")

    status, body = call("POST", "/api/office/activity/tick",
                        {"force": True, "ignore_window": True})
    tick = body.get("activity", {})
    check("activity tick runs", status == 200 and tick.get("enabled") is True,
          f"status={status} enabled={tick.get('enabled')}")

    status, body = call("GET", "/api/office/activity?limit=100")
    summary = body.get("summary", {})
    employees = summary.get("employees", [])
    kinds = {event["event_type"] for event in body.get("events", [])}
    check("activity feed has employee events",
          status == 200 and "employee_work" in kinds,
          f"status={status}")
    check("activity summary covers roster",
          status == 200 and len(employees) == 7,
          f"status={status} employees={len(employees)}")

    for row in body.get("events", []):
        if row["event_type"] == "employee_work":
            break
finally:
    server.shutdown()
    server.server_close()
    target = BACKEND / "workspace" / "desktop" / "OWNER-PC-001" / "runtime-check.md"
    if target.is_file():
        target.unlink()

failed = [name for name, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} runtime checks passed")
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
