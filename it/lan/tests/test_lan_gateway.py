import http.client
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from it.lan.lan_gateway import GatewayHandler, HOP_BY_HOP, is_private_client, parse_address


class _FakeUpstreamHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet
        return

    def do_ANY(self):
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else b""
        state = self.server.state  # type: ignore[attr-defined]
        state["requests"].append({
            "method": self.command,
            "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "body": body.decode("utf-8", "replace"),
        })
        status, payload = state["response"]
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = do_ANY


class _StubWfile:
    def __init__(self):
        self.buf = io.BytesIO()

    def write(self, data):
        self.buf.write(data)

    def flush(self):
        pass


def _make_gateway_handler(server, client_ip, method="GET", path="/api/status", headers=None, body=b""):
    headers = dict(headers or {})
    raw = [f"{method} {path} HTTP/1.1", f"Host: test", f"Content-Length: {len(body)}"]
    for k, v in headers.items():
        raw.append(f"{k}: {v}")
    raw.append("")
    raw.append("")
    request = ("\r\n".join(raw)).encode("latin-1") + body
    handler = GatewayHandler.__new__(GatewayHandler)
    handler.rfile = io.BytesIO(request)
    handler.wfile = _StubWfile()
    handler.client_address = (client_ip, 12345)
    handler.server = server
    handler.close_connection = True
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.command = method
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.headers = http.client.parse_headers(io.BytesIO("\r\n".join(raw[1:]).encode("latin-1")))
    return handler


class LanGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstreamHandler)
        cls.upstream.state = {"requests": [], "response": (200, {"ok": True})}  # type: ignore[attr-defined]
        cls.upstream_port = cls.upstream.server_address[1]
        threading.Thread(target=cls.upstream.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown()
        cls.upstream.server_close()

    def setUp(self):
        self.upstream.state["requests"] = []  # type: ignore[attr-defined]
        self.upstream.state["response"] = (200, {"ok": True})  # type: ignore[attr-defined]
        self.gw = ThreadingHTTPServer.__new__(ThreadingHTTPServer)
        self.gw.upstream = f"127.0.0.1:{self.upstream_port}"  # type: ignore[attr-defined]
        self.gw.max_body = 1024  # type: ignore[attr-defined]
        self.gw.upstream_timeout = 5  # type: ignore[attr-defined]

    def test_authorization_forwarded_intact_and_no_token_injection_without_auth(self):
        h = _make_gateway_handler(self.gw, "192.168.1.20", headers={"Authorization": "Bearer real.session.token"})
        h.handle_one_request()
        req = self.upstream.state["requests"][0]  # type: ignore[attr-defined]
        self.assertEqual(req["headers"].get("Authorization"), "Bearer real.session.token")

        self.upstream.state["requests"] = []  # type: ignore[attr-defined]
        h = _make_gateway_handler(self.gw, "192.168.1.20")
        h.handle_one_request()
        req = self.upstream.state["requests"][0]  # type: ignore[attr-defined]
        self.assertNotIn("Authorization", req["headers"])

    def test_backend_401_is_forwarded(self):
        self.upstream.state["response"] = (401, {"success": False, "error": {"code": "UNAUTHORIZED"}})  # type: ignore[attr-defined]
        h = _make_gateway_handler(self.gw, "10.0.0.5", headers={"Authorization": "Bearer bad"})
        h.handle_one_request()
        out = h.wfile.buf.getvalue()
        self.assertIn(b"401", out.split(b"\r\n", 1)[0])
        self.assertIn(b"UNAUTHORIZED", out)

    def test_external_ip_rejected(self):
        h = _make_gateway_handler(self.gw, "8.8.8.8", headers={"Authorization": "Bearer stolen"})
        h.handle_one_request()
        out = h.wfile.buf.getvalue()
        self.assertIn(b"403", out.split(b"\r\n", 1)[0])
        self.assertEqual(self.upstream.state["requests"], [])  # type: ignore[attr-defined]

    def test_spoofed_x_forwarded_for_from_client_does_not_pass(self):
        h = _make_gateway_handler(
            self.gw, "192.168.1.20",
            headers={"Authorization": "Bearer t", "X-Forwarded-For": "127.0.0.1"},
        )
        h.handle_one_request()
        req = self.upstream.state["requests"][0]  # type: ignore[attr-defined]
        self.assertEqual(req["headers"].get("X-Forwarded-For"), "192.168.1.20")

    def test_body_size_limit(self):
        big = b"x" * 2048
        h = _make_gateway_handler(self.gw, "192.168.1.20", method="POST", path="/api/x",
                                  headers={"Content-Type": "application/json"}, body=big)
        h.handle_one_request()
        out = h.wfile.buf.getvalue()
        self.assertIn(b"413", out.split(b"\r\n", 1)[0])
        self.assertEqual(self.upstream.state["requests"], [])  # type: ignore[attr-defined]

    def test_helpers(self):
        self.assertTrue(is_private_client("10.0.0.1"))
        self.assertTrue(is_private_client("192.168.0.2"))
        self.assertTrue(is_private_client("127.0.0.1"))
        self.assertFalse(is_private_client("8.8.8.8"))
        self.assertEqual(parse_address("0.0.0.0:8081", 80), ("0.0.0.0", 8081))
        self.assertNotIn("authorization", HOP_BY_HOP)  # must be forwarded when present


if __name__ == "__main__":
    unittest.main()
