"""Local delivery sinks for Milestone 2 acceptance.

These are *test* providers, not production services:

- an SMTP sink that speaks enough ESMTP (STARTTLS, AUTH PLAIN, DATA) for the
  real ``core.action_adapters._send_email`` path;
- an HTTPS webhook sink that accepts the real deployment adapter request.

Both write JSONL evidence. Credentials are never written to the logs; the
deployment sink records only a SHA-256 of the Authorization header.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import socket
import ssl
import subprocess
import threading
import uuid
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha256(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


class JsonlLog:
    """Append-only JSONL evidence log with a lock."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, record: dict):
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        items = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return items


def ensure_test_certificates(directory: str | Path) -> dict:
    """Create a throwaway CA and a loopback server certificate with OpenSSL.

    Returns paths to the CA bundle (for ``SSL_CERT_FILE``), server certificate
    and server key. The certificate SAN covers ``localhost`` and 127.0.0.1.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    ca_key = directory / "ca.key"
    ca_pem = directory / "ca.pem"
    server_key = directory / "server.key"
    server_pem = directory / "server.pem"
    server_csr = directory / "server.csr"
    ext_file = directory / "server.ext"
    ext_file.write_text(
        "subjectAltName=DNS:localhost,IP:127.0.0.1\n"
        "keyUsage=digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n",
        encoding="utf-8",
    )

    def run(*args):
        completed = subprocess.run(
            ["openssl", *args], capture_output=True, text=True, timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"openssl {' '.join(args)} failed: {completed.stderr.strip()}"
            )
        return completed

    run(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(ca_key), "-out", str(ca_pem), "-days", "2",
        "-subj", "/CN=Bangkah Milestone 2 Test CA",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
    )
    run(
        "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(server_key), "-out", str(server_csr),
        "-subj", "/CN=localhost",
    )
    run(
        "x509", "-req", "-in", str(server_csr),
        "-CA", str(ca_pem), "-CAkey", str(ca_key), "-CAcreateserial",
        "-out", str(server_pem), "-days", "2", "-sha256",
        "-extfile", str(ext_file),
    )
    return {
        "ca_file": str(ca_pem),
        "cert_file": str(server_pem),
        "key_file": str(server_key),
    }


class SmtpSink:
    """Minimal ESMTP server with STARTTLS + AUTH PLAIN for tests."""

    def __init__(self, cert_file: str, key_file: str, log_path: str | Path,
                 username: str, password: str, drop_after_data: bool = False):
        self.username = username
        self.password = password
        self.drop_after_data = bool(drop_after_data)
        self.log = JsonlLog(log_path)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(cert_file, key_file)
        sink = self

        import socketserver

        class Handler(socketserver.StreamRequestHandler):
            def _reply(self, line: str):
                self.wfile.write((line + "\r\n").encode("utf-8"))
                self.wfile.flush()

            def _read_line(self) -> str:
                raw = self.rfile.readline(65536)
                if not raw:
                    raise EOFError
                return raw.decode("utf-8", "replace").rstrip("\r\n")

            def _ehlo(self):
                self._reply("250-localhost")
                if not self.tls_active:
                    self._reply("250-STARTTLS")
                self._reply("250-AUTH PLAIN")
                self._reply("250 SIZE 10485760")

            def _auth_plain(self, argument: str):
                encoded = argument.strip()
                if not encoded:
                    self._reply("334 ")
                    encoded = self._read_line().strip()
                try:
                    decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
                    _authzid, authcid, password = decoded.split("\0", 2)
                except Exception:
                    self._reply("535 5.7.8 Authentication credentials invalid")
                    return
                if hmac.compare_digest(authcid, sink.username) and \
                        hmac.compare_digest(password, sink.password):
                    self.authenticated = authcid
                    self._reply("235 2.7.0 Authentication successful")
                else:
                    self._reply("535 5.7.8 Authentication credentials invalid")

            def _upgrade_tls(self):
                self._reply("220 2.0.0 Ready to start TLS")
                self.connection = sink.context.wrap_socket(
                    self.connection, server_side=True,
                )
                self.rfile = self.connection.makefile("rb")
                self.wfile = self.connection.makefile("wb")
                self.tls_active = True
                self.authenticated = None
                self.mail_from = None
                self.rcpt_to = []

            def _record_message(self, raw: bytes):
                parsed = BytesParser(policy=policy.default).parsebytes(raw)
                body = ""
                try:
                    if parsed.is_multipart():
                        for part in parsed.walk():
                            if part.get_content_type() == "text/plain":
                                body = str(part.get_content())
                                break
                    else:
                        body = str(parsed.get_content())
                except Exception:
                    payload = parsed.get_payload(decode=True) or b""
                    body = payload.decode("utf-8", "replace")
                recipients = [addr for _name, addr in getaddresses(parsed.get_all("To", []))]
                sink.log.write({
                    "kind": "smtp",
                    "received_at": _now(),
                    "outbox_id": str(parsed.get("X-Bangkah-Outbox-ID", "")),
                    "message_id": str(parsed.get("Message-ID", "")),
                    "from": str(parsed.get("From", "")),
                    "to": recipients,
                    "subject": str(parsed.get("Subject", "")),
                    "body": body,
                    "authenticated_user": self.authenticated,
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                })

            def handle(self):
                self.tls_active = False
                self.authenticated = None
                self.mail_from = None
                self.rcpt_to = []
                try:
                    self._reply("220 localhost Milestone2 SMTP sink")
                    while True:
                        try:
                            line = self._read_line()
                        except EOFError:
                            break
                        if not line:
                            self._reply("500 5.5.2 Empty command")
                            continue
                        parts = line.split(" ", 1)
                        command = parts[0].upper()
                        argument = parts[1] if len(parts) > 1 else ""
                        if command in ("EHLO", "HELO"):
                            if command == "EHLO":
                                self._ehlo()
                            else:
                                self._reply("250 localhost")
                        elif command == "STARTTLS":
                            if self.tls_active:
                                self._reply("503 5.5.1 TLS already active")
                            else:
                                self._upgrade_tls()
                        elif command == "AUTH":
                            if self.authenticated:
                                self._reply("503 5.5.1 Already authenticated")
                            elif argument.upper().startswith("PLAIN"):
                                self._auth_plain(argument[5:].strip())
                            else:
                                self._reply("504 5.5.4 Unsupported authentication mechanism")
                        elif command == "MAIL":
                            if not self.authenticated:
                                self._reply("530 5.7.0 Authentication required")
                            else:
                                self.mail_from = argument
                                self.rcpt_to = []
                                self._reply("250 2.1.0 OK")
                        elif command == "RCPT":
                            if not self.mail_from:
                                self._reply("503 5.5.1 MAIL first")
                            else:
                                self.rcpt_to.append(argument)
                                self._reply("250 2.1.5 OK")
                        elif command == "DATA":
                            if not self.rcpt_to:
                                self._reply("503 5.5.1 RCPT first")
                                continue
                            self._reply("354 End data with <CR><LF>.<CR><LF>")
                            chunks = []
                            while True:
                                try:
                                    data_line = self.rfile.readline(65536)
                                except EOFError:
                                    data_line = b""
                                if not data_line:
                                    break
                                if data_line in (b".\r\n", b".\n"):
                                    break
                                if data_line.startswith(b".."):
                                    data_line = data_line[1:]
                                chunks.append(data_line)
                            raw = b"".join(chunks)
                            self._record_message(raw)
                            if sink.drop_after_data:
                                # Simulate a provider that accepted DATA but lost the
                                # connection before the final acknowledgement. The
                                # sender must park the item as UNKNOWN.
                                try:
                                    self.connection.close()
                                except OSError:
                                    pass
                                return
                            self._reply("250 2.0.0 OK")
                            self.mail_from = None
                            self.rcpt_to = []
                        elif command == "RSET":
                            self.mail_from = None
                            self.rcpt_to = []
                            self._reply("250 2.0.0 OK")
                        elif command == "NOOP":
                            self._reply("250 2.0.0 OK")
                        elif command == "QUIT":
                            self._reply("221 2.0.0 Bye")
                            break
                        else:
                            self._reply("502 5.5.2 Command not implemented")
                except (ConnectionError, ssl.SSLError, OSError):
                    pass
                finally:
                    try:
                        self.connection.close()
                    except OSError:
                        pass

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.allow_reuse_address = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True,
            name="milestone2-smtp-sink",
        )
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class DeploySink:
    """HTTPS webhook sink for the real deployment adapter (POST /hook)."""

    def __init__(self, cert_file: str, key_file: str, log_path: str | Path,
                 token: str, path: str = "/hook"):
        self.token = token
        self.path = path
        self.log = JsonlLog(log_path)
        sink = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "Milestone2DeploySink/1.0"

            def log_message(self, fmt, *args):
                return

            def _send(self, status: int, payload: dict, extra: dict | None = None):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != sink.path:
                    self._send(404, {"error": "not found"})
                    return
                supplied = self.headers.get("Authorization", "")
                expected = f"Bearer {sink.token}"
                if not hmac.compare_digest(supplied, expected):
                    self._send(401, {"error": "unauthorized"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length <= 0 or length > 1_000_000:
                    self._send(400, {"error": "invalid body length"})
                    return
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._send(400, {"error": "invalid json"})
                    return
                deployment_id = "DEP-" + uuid.uuid4().hex[:12].upper()
                sink.log.write({
                    "kind": "deploy",
                    "received_at": _now(),
                    "path": self.path,
                    "authorization_sha256": _sha256(supplied),
                    "idempotency_key": self.headers.get("Idempotency-Key", ""),
                    "content_type": self.headers.get("Content-Type", ""),
                    "body": body,
                    "deployment_id": deployment_id,
                })
                self._send(200, {"accepted": True}, {"X-Deployment-ID": deployment_id})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_file, key_file)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True,
            name="milestone2-deploy-sink",
        )
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


def wait_for_port(host: str, port: int, timeout: float = 20.0) -> bool:
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.05)
    return False
