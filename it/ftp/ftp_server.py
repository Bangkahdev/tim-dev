#!/usr/bin/env python3
"""Server FTPS perusahaan Bangkah.

Dijalankan di jaringan kantor (LAN). Setiap anggota tim mendapat akun dan
folder sendiri. Akun owner dan team mendapat akses ke folder bersama.

Pemakaian:
    python3 ftp_server.py --setup     # buat users.json + folder + sertifikat
    python3 ftp_server.py             # jalankan server
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Dukungan disk tanpa symlink (exFAT/USB): paket dapat berada di .pylibs.
PYLIBS = BASE_DIR / ".pylibs"
if str(PYLIBS) not in sys.path and (PYLIBS / "pyftpdlib").exists():
    sys.path.insert(0, str(PYLIBS))
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_USERS = BASE_DIR / "users.json"
DEFAULT_SHARE = BASE_DIR / "share"
CERT_DIR = BASE_DIR / "certs"

EMPLOYEES = [
    ("owner", "Owner / Founder", True),
    ("arman", "Lead Manager", False),
    ("sinta", "COO / Project Manager", False),
    ("raka", "System Architect", False),
    ("bima", "Backend Developer", False),
    ("naya", "API Specialist", False),
    ("dira", "Frontend Developer", False),
    ("tika", "QA Engineer", False),
    ("mira", "Receptionist", False),
]

DEFAULT_CONFIG_DATA = {
    "host": "0.0.0.0",
    "port": 2121,
    "passive_ports": [30000, 30009],
    "share_dir": "share",
    "users_file": "users.json",
    "tls": {
        "enabled": True,
        "certfile": "certs/ftp.crt",
        "keyfile": "certs/ftp.key",
    },
    "banner": "Bangkah Company FTPS - authorized users only.",
}


def ensure_config() -> dict:
    if DEFAULT_CONFIG.exists():
        return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    DEFAULT_CONFIG.write_text(json.dumps(DEFAULT_CONFIG_DATA, indent=2) + "\n", encoding="utf-8")
    print(f"[+] Dibuat {DEFAULT_CONFIG}")
    return dict(DEFAULT_CONFIG_DATA)


def generate_password(length: int = 20) -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_certificate(config: dict) -> None:
    tls = config.get("tls", {})
    certfile = BASE_DIR / tls.get("certfile", "certs/ftp.crt")
    keyfile = BASE_DIR / tls.get("keyfile", "certs/ftp.key")
    if certfile.exists() and keyfile.exists():
        print("[=] Sertifikat TLS sudah ada.")
        return

    if not shutil.which("openssl"):
        print("[!] openssl tidak ditemukan. FTPS dinonaktifkan; isi tls.enabled=false.")
        tls["enabled"] = False
        return

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "825",
            "-keyout",
            str(keyfile),
            "-out",
            str(certfile),
            "-subj",
            "/CN=bangkah.lan/O=Bangkah Company",
            "-addext",
            "subjectAltName=DNS:bangkah.lan,DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.chmod(keyfile, 0o600)
    print(f"[+] Sertifikat TLS dibuat: {certfile}")


def setup_accounts(config: dict) -> None:
    users_path = BASE_DIR / config.get("users_file", "users.json")
    share_dir = BASE_DIR / config.get("share_dir", "share")
    share_dir.mkdir(parents=True, exist_ok=True)
    (share_dir / "team").mkdir(exist_ok=True)
    (share_dir / "public").mkdir(exist_ok=True)

    accounts: dict[str, dict] = {}
    if users_path.exists():
        accounts = json.loads(users_path.read_text(encoding="utf-8"))

    print("\nAkun FTP perusahaan")
    print("=" * 78)
    print(f"{'USER':<12} {'PERAN':<25} {'KATA SANDI':<22} HOME")
    print("-" * 78)

    for username, role, is_owner in EMPLOYEES:
        home = share_dir if is_owner else share_dir / username
        home.mkdir(exist_ok=True)
        if username not in accounts:
            accounts[username] = {
                "password": generate_password(),
                "role": role,
                "home": str(home.relative_to(BASE_DIR)),
                "permissions": "elradfmwMT",
            }
        account = accounts[username]
        print(f"{username:<12} {role:<25} {account['password']:<22} {account['home']}")

    if "team" not in accounts:
        accounts["team"] = {
            "password": generate_password(),
            "role": "Shared team folder",
            "home": str((share_dir / "team").relative_to(BASE_DIR)),
            "permissions": "elradfmwMT",
        }
    team = accounts["team"]
    print(f"{'team':<12} {'Folder bersama':<25} {team['password']:<22} {team['home']}")
    print("=" * 78 + "\n")

    users_path.write_text(json.dumps(accounts, indent=2) + "\n", encoding="utf-8")
    os.chmod(users_path, stat.S_IRUSR | stat.S_IWUSR)
    print(f"[+] Kredensial disimpan di {users_path} (chmod 600). Jangan bagikan file ini.")
    print("[!] FTPS memakai sertifikat self-signed. Di FileZilla/WinSCP pilih")
    print("    'Trust this certificate' saat koneksi pertama.")


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def run_server(config: dict) -> None:
    try:
        from pyftpdlib.authorizers import DummyAuthorizer
        from pyftpdlib.handlers import FTPHandler, TLS_FTPHandler
        from pyftpdlib.servers import FTPServer
    except ImportError:
        sys.exit(
            "pyftpdlib belum terpasang.\n"
            "Jalankan: python3 -m pip install --user pyftpdlib\n"
            "atau gunakan ./start_ftp.sh yang membuat virtualenv otomatis."
        )

    users_path = BASE_DIR / config.get("users_file", "users.json")
    if not users_path.exists():
        sys.exit("users.json belum ada. Jalankan: python3 ftp_server.py --setup")

    accounts = json.loads(users_path.read_text(encoding="utf-8"))
    authorizer = DummyAuthorizer()
    for username, account in accounts.items():
        home = (BASE_DIR / account["home"]).resolve()
        home.mkdir(parents=True, exist_ok=True)
        authorizer.add_user(
            username,
            account["password"],
            str(home),
            perm=account.get("permissions", "elradfmwMT"),
        )

    tls = config.get("tls", {})
    certfile = BASE_DIR / tls.get("certfile", "certs/ftp.crt")
    keyfile = BASE_DIR / tls.get("keyfile", "certs/ftp.key")

    if tls.get("enabled") and certfile.exists() and keyfile.exists():
        handler = TLS_FTPHandler
        handler.certfile = str(certfile)
        handler.keyfile = str(keyfile)
        handler.tls_control_required = True
        handler.tls_data_required = True
        scheme = "ftps"
    else:
        handler = FTPHandler
        scheme = "ftp"
        print("[!] PERINGATAN: TLS tidak aktif. Gunakan hanya di jaringan tepercaya.")

    handler.authorizer = authorizer
    handler.passive_ports = range(
        int(config.get("passive_ports", [30000, 30009])[0]),
        int(config.get("passive_ports", [30000, 30009])[1]) + 1,
    )
    handler.banner = config.get("banner", "Bangkah Company FTPS ready.")

    host = config.get("host", "0.0.0.0")
    port = int(config.get("port", 2121))
    server = FTPServer((host, port), handler)

    print("=" * 72)
    print("  Bangkah Company File Server")
    print(f"  {scheme.upper()}://{lan_ip()}:{port}")
    print(f"  Bind: {host}:{port} · Passive ports: {handler.passive_ports}")
    print(f"  Folder: {BASE_DIR / config.get('share_dir', 'share')}")
    print("  Tekan Ctrl+C untuk berhenti.")
    print("=" * 72)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Server dihentikan.")
        server.close_all()


def main() -> None:
    global DEFAULT_CONFIG

    parser = argparse.ArgumentParser(description="Bangkah Company FTPS server")
    parser.add_argument("--setup", action="store_true", help="buat akun, folder, dan sertifikat")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    DEFAULT_CONFIG = Path(args.config)
    config = ensure_config()

    if args.setup:
        generate_certificate(config)
        setup_accounts(config)
        print("[+] Setup selesai. Jalankan server dengan: python3 ftp_server.py")
        return

    if config.get("tls", {}).get("enabled") and not (CERT_DIR / "ftp.crt").exists():
        print("[!] Sertifikat belum ada. Jalankan --setup terlebih dahulu.")
    run_server(config)


if __name__ == "__main__":
    main()
