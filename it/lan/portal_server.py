#!/usr/bin/env python3
"""Portal jaringan kantor Bangkah (LAN).

Halaman ringkas berisi tautan layanan perusahaan, direktori tim, dan status
koneksi. Dijalankan di port 8080 pada jaringan kantor.
"""
from __future__ import annotations

import argparse
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROSTER_FILE = BASE_DIR.parent / "company.json"

DEFAULT_ROSTER = {
    "company": "Bangkah",
    "domain": "bangkah.web.id",
    "employees": [
        {"name": "Owner", "role": "Founder & CEO", "email": "owner@bangkah.web.id"},
        {"name": "Arman", "role": "Lead Manager", "email": "arman@bangkah.web.id"},
        {"name": "Sinta", "role": "COO / Project Manager", "email": "sinta@bangkah.web.id"},
        {"name": "Raka", "role": "System Architect", "email": "raka@bangkah.web.id"},
        {"name": "Bima", "role": "Backend Developer", "email": "bima@bangkah.web.id"},
        {"name": "Naya", "role": "API Specialist", "email": "naya@bangkah.web.id"},
        {"name": "Dira", "role": "Frontend Developer", "email": "dira@bangkah.web.id"},
        {"name": "Tika", "role": "QA Engineer", "email": "tika@bangkah.web.id"},
        {"name": "Mira", "role": "Receptionist", "email": "mira@bangkah.web.id"},
    ],
}


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def load_roster() -> dict:
    if ROSTER_FILE.exists():
        try:
            return json.loads(ROSTER_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return DEFAULT_ROSTER


def render(host: str) -> str:
    roster = load_roster()
    employees = roster.get("employees", DEFAULT_ROSTER["employees"])
    cards = "\n".join(
        f"""<a class="person" href="mailto:{employee['email']}">
              <span class="avatar">{employee['name'][0]}</span>
              <span><strong>{employee['name']}</strong><small>{employee['role']}</small>
              <em>{employee['email']}</em></span>
            </a>"""
        for employee in employees
    )
    return f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Bangkah · Intranet</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%2346c08a'/%3E%3Ctext x='32' y='45' text-anchor='middle' font-size='40' font-family='sans-serif' font-weight='bold' fill='%2308130d'%3EB%3C/text%3E%3C/svg%3E" />
<style>
  :root {{ color-scheme: dark; --bg:#0f1418; --panel:#131b21; --border:#26333d; --text:#dfe7ec; --muted:#8fa2ae; --primary:#46c08a; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }}
  header {{ padding:26px 22px; border-bottom:1px solid var(--border); background:linear-gradient(135deg,rgba(70,192,138,.12),transparent 55%); }}
  .wrap {{ max-width:1050px; margin:0 auto; }}
  .brand {{ display:flex; align-items:center; gap:12px; }}
  .logo {{ width:42px;height:42px;border-radius:11px;background:var(--primary);color:#08130d;display:grid;place-items:center;font-size:22px;font-weight:800; }}
  .brand h1 {{ margin:0; font-size:22px; }}
  .brand p {{ margin:2px 0 0; color:var(--muted); font-size:12px; letter-spacing:.14em; text-transform:uppercase; }}
  main {{ max-width:1050px; margin:0 auto; padding:22px; }}
  h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.12em; color:var(--muted); margin:26px 0 12px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }}
  a.service {{ display:flex; flex-direction:column; gap:6px; padding:16px; border:1px solid var(--border); border-radius:12px; background:var(--panel); color:var(--text); text-decoration:none; transition:.15s; }}
  a.service:hover {{ border-color:var(--primary); transform:translateY(-1px); }}
  a.service strong {{ font-size:15px; }}
  a.service span {{ color:var(--muted); font-size:12px; overflow-wrap:anywhere; }}
  a.service .dot {{ width:8px;height:8px;border-radius:50%;background:var(--primary);display:inline-block;margin-right:6px; }}
  .people {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:10px; }}
  .person {{ display:flex; gap:11px; align-items:center; padding:12px 14px; border:1px solid var(--border); border-radius:11px; background:var(--panel); color:var(--text); text-decoration:none; }}
  .person:hover {{ border-color:var(--primary); }}
  .avatar {{ width:36px;height:36px;border-radius:9px;background:rgba(70,192,138,.14);color:var(--primary);display:grid;place-items:center;font-weight:700;flex-shrink:0; }}
  .person strong {{ display:block; font-size:14px; }}
  .person small {{ display:block; color:var(--muted); font-size:11px; }}
  .person em {{ display:block; color:var(--primary); font-style:normal; font-size:11px; margin-top:2px; }}
  .note {{ border:1px solid var(--border); border-radius:12px; background:var(--panel); padding:14px 16px; color:var(--muted); font-size:12px; line-height:1.6; }}
  footer {{ max-width:1050px; margin:0 auto; padding:8px 22px 30px; color:var(--muted); font-size:11px; }}
  code {{ background:#0b1115; border:1px solid var(--border); border-radius:5px; padding:1px 5px; font-size:11px; }}
</style>
</head>
<body>
<header><div class="wrap"><div class="brand"><div class="logo">B</div><div><h1>Bangkah Intranet</h1><p>Jaringan kantor · {host}</p></div></div></div></header>
<main>
  <h2>Layanan</h2>
  <div class="grid">
    <a class="service" href="https://bangkah.web.id"><strong><span class="dot"></span>Website perusahaan</strong><span>https://bangkah.web.id</span></a>
    <a class="service" href="https://mail.bangkah.web.id"><strong><span class="dot"></span>Mail perusahaan</strong><span>https://mail.bangkah.web.id</span></a>
    <a class="service" href="https://files.bangkah.web.id"><strong><span class="dot"></span>Portal file (R2)</strong><span>https://files.bangkah.web.id</span></a>
    <a class="service" href="http://{host}:8081"><strong><span class="dot"></span>Office API</strong><span>http://{host}:8081 · LAN gateway</span></a>
    <a class="service" href="ftps://{host}:2121"><strong><span class="dot"></span>FTPS kantor</strong><span>ftps://{host}:2121 · FileZilla/WinSCP</span></a>
    <a class="service" href="http://{host}:8081/api/status"><strong><span class="dot"></span>Status backend</strong><span>http://{host}:8081/api/status</span></a>
  </div>

  <h2>Direktori tim</h2>
  <div class="people">{cards}</div>

  <h2>Catatan jaringan</h2>
  <div class="note">
    Portal ini hanya tersedia di jaringan kantor. Backend hanya mendengarkan di loopback;
    akses LAN melewati gateway di port <code>8081</code>. File server memakai FTPS
    (explicit TLS) di port <code>2121</code>. Jangan membuka port ini ke internet —
    untuk akses jarak jauh gunakan Cloudflare Tunnel atau portal R2.
  </div>
</main>
<footer>Bangkah · {roster.get('domain', 'bangkah.web.id')} · dokumen internal</footer>
</body>
</html>"""


class PortalHandler(BaseHTTPRequestHandler):
    server_version = "BangkahPortal/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            payload = json.dumps({"status": "ok", "service": "bangkah-portal"}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        host = self.headers.get("host", "").split(":")[0] or lan_ip()
        if host in ("localhost", "127.0.0.1", "0.0.0.0"):
            host = lan_ip()
        payload = render(host).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(payload)))
        self.send_header("x-content-type-options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[PORTAL] {self.client_address[0]} {fmt % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Portal intranet Bangkah")
    parser.add_argument("--listen", default="0.0.0.0:8080")
    args = parser.parse_args()

    host, _, port = args.listen.rpartition(":")
    server = ThreadingHTTPServer((host or "0.0.0.0", int(port)), PortalHandler)
    print("=" * 72)
    print("  Bangkah Intranet Portal")
    print(f"  http://{lan_ip()}:{port}")
    print("  Tekan Ctrl+C untuk berhenti.")
    print("=" * 72)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Portal dihentikan.")
        server.server_close()


if __name__ == "__main__":
    main()
