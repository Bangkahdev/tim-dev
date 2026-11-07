#!/usr/bin/env python3
"""LAN pass-through gateway for the Bangkah office API.

The backend binds to loopback only. This gateway is the controlled entry point
from the office LAN: it accepts private/loopback clients, forwards requests to
the loopback backend, and forwards ``Authorization`` as-is without injecting or
storing credentials.

Security notes:
- This gateway speaks plain HTTP. Passwords and session tokens traverse the LAN
  unencrypted. Place it behind TLS (for example Caddy) before real use.
- ``X-Forwarded-For`` is overwritten with the real client IP so spoofed client
  headers cannot pass through. The backend must trust that header only when the
  direct peer is loopback (this gateway).
- ``Authorization`` is never logged.
"""
from __future__ import annotations

import argparse
import http.client
import ipaddress
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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

DEFAULT_MAX_BODY = 1_048_576  # 1 MiB
DEFAULT_TIMEOUT = 120


def is_private_client(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "BangkahLANGateway/2.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401
        # Never include request headers (Authorization) in logs.
        print(f"[LAN] {self.client_address[0]} {self.command} {self.path} {fmt % args}", flush=True)

    def _reject_external(self) -> bool:
        if is_private_client(self.client_address[0]):
            return False
        self.send_error(403, "Only office LAN or loopback clients are allowed.")
        return True

    def _read_body(self) -> bytes | None:
        length_raw = self.headers.get("content-length")
        if length_raw is None:
            return None
        try:
            length = int(length_raw)
        except ValueError:
            self.send_error(400, "Invalid Content-Length.")
            return b""
        if length < 0:
            self.send_error(400, "Invalid Content-Length.")
            return b""
        max_body = int(getattr(self.server, "max_body", DEFAULT_MAX_BODY))
        if length > max_body:
            self.send_error(413, "Request body too large.")
            return b""
        return self.rfile.read(length) if length else b""

    def _proxy(self) -> None:
        if self._reject_external():
            return

        body = self._read_body()
        if body == b"" and self.headers.get("content-length") and self.command in {"POST", "PUT", "PATCH"}:
            # An error response was already sent for an invalid/oversized body.
            return

        upstream = self.server.upstream  # type: ignore[attr-defined]
        timeout = int(getattr(self.server, "upstream_timeout", DEFAULT_TIMEOUT))

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP and key.lower() != "x-forwarded-for"
        }
        headers["Host"] = upstream
        # Overwrite, never forward client-supplied X-Forwarded-For.
        headers["X-Forwarded-For"] = self.client_address[0]
        headers["X-Forwarded-Proto"] = "http"
        # Forward Authorization only when the client sent it; never inject.

        connection = http.client.HTTPConnection(upstream, timeout=timeout)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()

            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() in HOP_BY_HOP:
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except (ConnectionError, OSError, http.client.HTTPException) as error:
            self.send_error(502, f"Backend unavailable: {type(error).__name__}")
        finally:
            connection.close()

    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_PATCH = _proxy
    do_DELETE = _proxy
    do_HEAD = _proxy
    do_OPTIONS = _proxy


def parse_address(value: str, default_port: int) -> tuple[str, int]:
    if ":" not in value:
        return value, default_port
    host, port = value.rsplit(":", 1)
    return host, int(port)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pass-through LAN gateway for the Bangkah office API")
    parser.add_argument("--listen", default="0.0.0.0:8081")
    parser.add_argument("--upstream", default="127.0.0.1:8765")
    parser.add_argument("--max-body", type=int, default=DEFAULT_MAX_BODY)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    listen_host, listen_port = parse_address(args.listen, 8081)
    upstream_host, upstream_port = parse_address(args.upstream, 8765)

    server = ThreadingHTTPServer((listen_host, listen_port), GatewayHandler)
    server.upstream = f"{upstream_host}:{upstream_port}"  # type: ignore[attr-defined]
    server.max_body = max(0, int(args.max_body))  # type: ignore[attr-defined]
    server.upstream_timeout = max(1, int(args.timeout))  # type: ignore[attr-defined]

    print("=" * 72, flush=True)
    print("  Bangkah LAN Gateway (pass-through)", flush=True)
    print(f"  http://{listen_host}:{listen_port}  ->  http://{upstream_host}:{upstream_port}", flush=True)
    print("  Accepts private/loopback clients only. Authorization is forwarded as-is; never injected.", flush=True)
    print("  X-Forwarded-For is overwritten with the real client IP.", flush=True)
    print("  WARNING: Plain HTTP. Passwords/session tokens are UNENCRYPTED on the LAN.", flush=True)
    print("  Require TLS (for example, Caddy reverse proxy) before real use.", flush=True)
    print("=" * 72, flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Gateway stopped.", flush=True)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
