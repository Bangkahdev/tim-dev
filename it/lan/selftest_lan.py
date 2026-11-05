#!/usr/bin/env python3
"""Tes cepat layanan jaringan kantor Bangkah.

Pemakaian:
    python3 selftest_lan.py [ip]

Tanpa argumen, IP kantor dideteksi otomatis.
"""
from __future__ import annotations

import socket
import sys
import urllib.request


def detect_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def check_http(label: str, url: str, silent_body: bool = False) -> None:
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            print(f"[+] {label}: HTTP {response.status}")
            if not silent_body:
                body = response.read(200)
                print(f"       {body[:200]!r}")
    except Exception as error:  # noqa: BLE001
        print(f"[!] {label}: {error}")


def check_port(label: str, host: str, port: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=8):
            print(f"[+] {label}: port {port} terbuka.")
    except Exception as error:  # noqa: BLE001
        print(f"[!] {label}: {error}")


def main() -> None:
    ip = sys.argv[1] if len(sys.argv) > 1 else detect_ip()
    print(f"\nMenguji layanan pada {ip}\n")

    check_http("Portal intranet", f"http://{ip}:8080/", silent_body=True)
    check_http("Portal health", f"http://{ip}:8080/health", silent_body=True)
    check_http("Gateway office API", f"http://{ip}:8081/api/status", silent_body=True)
    check_http("Backend langsung", "http://127.0.0.1:8765/api/status", silent_body=True)
    check_port("FTPS", ip, 2121)

    print("\nSelesai.")


if __name__ == "__main__":
    main()
