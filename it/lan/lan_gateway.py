#!/usr/bin/env python3
"""Gateway LAN untuk API kantor Bangkah.

Backend Python sengaja hanya bind ke 127.0.0.1. Gateway ini menjadi satu-satunya
pintu masuk dari jaringan kantor, hanya menerima alamat IP privat, dan dapat
menyisipkan bearer token backend secara otomatis.

Pemakaian:
    python3 lan_gateway.py --listen 0.0.0.0:8081 \
        --upstream 127.0.0.1:8765 --token "$BANGKAH_API_TOKEN"
"""
from __future__ import annotations

import argparse
import http.client
import ipaddress
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def is_private_client(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "BangkahLANGateway/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401
        print(f"[LAN] {self.client_address[0]} {fmt % args}", flush=True)

    def _reject_external(self) -> bool:
        if is_private_client(self.client_address[0]):
            return False
        self.send_error(403, "Hanya jaringan kantor yang diizinkan.")
        return True

    def _proxy(self) -> None:
        if self._reject_external():
            return

        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else None

        upstream = self.server.upstream  # type: ignore[attr-defined]
        token = self.server.upstream_token  # type: ignore[attr-defined]

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP
        }
        headers["host"] = upstream
        headers["x-forwarded-for"] = self.client_address[0]
        headers["x-forwarded-proto"] = "http"
        if token and "authorization" not in {key.lower() for key in headers}:
            headers["authorization"] = f"Bearer {token}"

        connection = http.client.HTTPConnection(upstream, timeout=120)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()

            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() in HOP_BY_HOP:
                    continue
                self.send_header(key, value)
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except (ConnectionError, socket.timeout, http.client.HTTPException) as error:
            self.send_error(502, f"Backend tidak dapat dihubungi: {error}")
        finally:
            connection.close()

    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_PATCH = _proxy
    do_DELETE = _proxy
    do_HEAD = _proxy
    do_OPTIONS = _proxy


def parse_address(value: str) -> tuple[str, int]:
    if ":" not in value:
        return value, 80
    host, port = value.rsplit(":", 1)
    return host, int(port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gateway LAN untuk backend Bangkah")
    parser.add_argument("--listen", default="0.0.0.0:8081")
    parser.add_argument("--upstream", default="127.0.0.1:8765")
    parser.add_argument("--token", default="", help="Bearer token backend (opsional)")
    args = parser.parse_args()

    listen_host, listen_port = parse_address(args.listen)
    upstream_host, upstream_port = parse_address(args.upstream)

    server = ThreadingHTTPServer((listen_host, listen_port), GatewayHandler)
    server.upstream = f"{upstream_host}:{upstream_port}"  # type: ignore[attr-defined]
    server.upstream_token = args.token.strip()  # type: ignore[attr-defined]

    print("=" * 72)
    print("  Bangkah LAN Gateway")
    print(f"  http://{listen_host}:{listen_port}  ->  http://{upstream_host}:{upstream_port}")
    print("  Hanya menerima alamat IP privat / loopback.")
    print("  Tekan Ctrl+C untuk berhenti.")
    print("=" * 72)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Gateway dihentikan.")
        server.server_close()


if __name__ == "__main__":
    main()
