"""Local web office for the AI Coding Factory."""

from __future__ import annotations

import json
import mimetypes
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import hmac
import os

from config import make_llm, model_for
from main import AICodingFactory, LOG_DIR, WORKSPACE, check_ollama
from core.employee_health import EMPLOYEES, get_health_snapshot, record_activity
from core.office_store import STORE
from core.office_tools import TOOLS
from core.orchestrator import ORCHESTRATOR
from core.knowledge_base import KNOWLEDGE
from core.company_operations import OPS
from core.workstations import DESKTOP, DesktopAuthError, DesktopError
from core.employee_activity import EmployeeActivityEngine
from core.domain_service import DomainService
from core.infra_service import INFRA
from core.ftp_service import FTP
from core.mail_service import MAIL
from core.network_service import NETWORK

ACTIVITY = EmployeeActivityEngine()
DOMAIN = DomainService()
from core.action_adapters import execute_outbox, AdapterError

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
HOST = os.getenv("BANGKAH_HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT = int(os.getenv("BANGKAH_PORT", "8765"))
API_AUTH_TOKEN = os.getenv("BANGKAH_API_TOKEN", "").strip()
RUN_LOCK = threading.Lock()
ACTIVE = {"running": False, "command": "", "started_at": None, "error": None}
CHAT_HISTORY = []
CHAT_LOCK = threading.Lock()
EMPLOYEE_CHAT_HISTORY = {employee_id: [] for employee_id in EMPLOYEES}
EMPLOYEE_CHAT_ACTIVE = {}
EMPLOYEE_CHAT_LOCK = threading.Lock()
EMPLOYEE_CHAT_STATE_LOCK = threading.Lock()
OLLAMA_CACHE = {"checked_at": 0, "result": (False, "Belum diperiksa.")}
OLLAMA_LOCK = threading.Lock()


def cached_ollama_status():
    with OLLAMA_LOCK:
        if time.monotonic() - OLLAMA_CACHE["checked_at"] > 20:
            OLLAMA_CACHE["result"] = check_ollama()
            OLLAMA_CACHE["checked_at"] = time.monotonic()
        return OLLAMA_CACHE["result"]


def latest_project_state():
    projects = []
    for state_file in WORKSPACE.glob("*/.factory/state.json"):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            state["directory"] = str(state_file.parent.parent)
            projects.append(state)
        except (OSError, json.JSONDecodeError):
            continue
    projects.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return projects


def read_activity(limit=120):
    path = LOG_DIR / "factory.log"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-limit:]


# ------------------------------------------------------------
# Percakapan: prompt dan pembersih format
# ------------------------------------------------------------

CHAT_STYLE_RULES = (
    "Aturan menjawab:\n"
    "- Tulis teks biasa seperti pesan chat. Jangan pakai markdown: "
    "tanpa tanda bintang, tanpa tanda #, tanpa huruf tebal, tanpa daftar berpoin.\n"
    "- Bahasa Indonesia yang santai tapi sopan, seperti rekan kerja.\n"
    "- Panjang jawaban mengikuti pesan owner. Sapaan dibalas satu atau dua kalimat pendek.\n"
    "- Jangan menjelaskan peranmu sendiri dan jangan mengulang kata-kata owner atau instruksi ini.\n"
    "- Tanyakan paling banyak satu pertanyaan dalam satu balasan, hanya yang paling penting.\n"
    "- Jangan mengaku sudah mengerjakan sesuatu dan jangan mengarang fakta.\n"
)

LEAD_CHAT_SYSTEM = (
    "Kamu Arman, Lead Manager di sebuah kantor AI yang membuat aplikasi. "
    "Kamu sedang mengobrol langsung dengan owner, yaitu pemilik proyek. "
    "Tim yang bisa kamu arahkan: COO, System Architect, Backend, API, Frontend, dan QA.\n\n"
    + CHAT_STYLE_RULES +
    "- Jangan menyebut pembagian tugas tim sebelum owner menjelaskan proyeknya.\n"
    "- Setelah kebutuhan cukup jelas, ringkas dalam beberapa kalimat biasa, "
    "sebutkan siapa mengerjakan apa, lalu bilang owner bisa menekan tombol mulai kalau sudah setuju.\n\n"
    "Contoh percakapan yang baik:\n"
    "Owner: Halo\n"
    "Kamu: Halo! Ada yang mau kita buat hari ini?\n"
    "Owner: Aku mau bikin aplikasi catatan keuangan\n"
    "Kamu: Seru, aplikasi catatan keuangan ya. Untuk pemakaian pribadi atau buat dipakai banyak orang?"
)


def employee_chat_system(employee, context):
    return (
        f"Kamu {employee['name']}, {employee['role']} di sebuah kantor AI yang membuat aplikasi. "
        "Kamu sedang mengobrol langsung dengan owner, yaitu pemilik proyek.\n"
        f"Konteks kantor saat ini: {context}\n\n"
        + CHAT_STYLE_RULES +
        "- Obrolan ini tidak memberimu akses mengubah berkas atau menjalankan pekerjaan. "
        "Kalau owner memberi tugas baru, sampaikan pemahamanmu singkat lalu sarankan "
        "agar arahannya disepakati lewat Lead Manager."
    )


def clean_reply(text):
    """Buang sisa format markdown dan awalan nama dari balasan model."""
    text = str(text or "").replace("\r\n", "\n")
    text = re.sub(r"```[A-Za-z0-9_-]*\n?", "", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "\u2022 ", text, flags=re.M)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(
        r"^\s*(Lead Manager|Manager|Arman|Kamu|Owner)\s*:\s*",
        "",
        text,
        flags=re.I
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def history_messages(history, limit=12):
    """Ubah riwayat jadi pesan chat sungguhan (user/assistant)."""
    messages = []
    for item in history[-limit:]:
        role = "user" if item["role"] == "owner" else "assistant"
        messages.append({"role": role, "content": item["content"]})
    return messages


def llm_usage(llm):
    """Pemakaian token bila library melaporkannya; kalau tidak, None."""
    getter = getattr(llm, "get_token_usage_summary", None)
    if not getter:
        return None
    try:
        return getter()
    except Exception:
        return None


class OfficeHandler(BaseHTTPRequestHandler):
    server_version = "AICodingOffice/1.0"

    def log_message(self, fmt, *args):
        print(f"[{datetime.now():%H:%M:%S}] {fmt % args}")

    def send_json(self, value, status=200):
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Content-Length tidak valid.")
        if length < 0 or length > 100_000:
            raise ValueError("Ukuran permintaan melebihi batas 100 KB.")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Body harus berupa JSON UTF-8 yang valid.") from exc
        if not isinstance(value, dict):
            raise ValueError("Body JSON harus berupa objek.")
        return value

    def _authorize_mutation(self):
        # The default bind is loopback-only. When an explicit token is configured,
        # all mutation calls require it; secrets are never returned by the API.
        if not API_AUTH_TOKEN:
            return True
        supplied = self.headers.get("Authorization", "")
        if supplied.lower().startswith("bearer "):
            supplied = supplied[7:].strip()
        if not hmac.compare_digest(supplied, API_AUTH_TOKEN):
            self.send_json({"error": "Sesi Owner tidak valid atau telah kedaluwarsa."}, 401)
            return False
        return True

    def _api_error(self, error, status=400):
        self.send_json({"error": str(error)}, status)

    def _desktop_token(self):
        return self.headers.get("X-Desktop-Session", "").strip()

    def _desktop_error(self, error):
        if isinstance(error, DesktopAuthError):
            self._api_error(error, 401)
        else:
            self._api_error(error, 400)

    @staticmethod
    def _usage_summary():
        health = get_health_snapshot().get("employees", {})
        keys = ("prompt_tokens", "completion_tokens", "total_tokens", "requests", "tasks_completed", "runtime_seconds")
        totals = {key: 0 for key in keys}
        for metric in health.values():
            for key in keys:
                totals[key] += max(0, int(metric.get(key, 0) or 0))
        return {**totals, "usage_available": any(bool(x.get("usage_available")) for x in health.values())}

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        if route.startswith("/api/") and not self._authorize_mutation():
            return
        if route == "/api/departments":
            self.send_json({"departments": OPS.departments()}); return
        if route == "/api/employees":
            self.send_json({"employees": OPS.employees()}); return
        if route == "/api/projects":
            self.send_json({"projects": latest_project_state()[:100]}); return
        if route == "/api/tasks":
            self.send_json({"tasks": OPS.tasks()}); return
        if route == "/api/meetings":
            self.send_json({"meetings": OPS.meetings()}); return
        if route == "/api/papers":
            self.send_json({"papers": OPS.list_papers(query.get("status", [None])[0])}); return
        if route.startswith("/api/papers/"):
            paper_id = route.rsplit("/", 1)[-1]
            try: self.send_json({"paper": OPS.get_paper(paper_id)})
            except ValueError as error: self._api_error(error, 404)
            return
        if route == "/api/approvals":
            self.send_json({"approvals": OPS.list_approvals(query.get("status", [None])[0], include_payload=True)}); return
        if route == "/api/outbox":
            self.send_json({"outbox": OPS.list_outbox()}); return
        if route == "/api/print-jobs":
            self.send_json({"print_jobs": OPS.list_print_jobs()}); return
        if route == "/api/audit" or route == "/api/events":
            after_id = query.get("after_id", [0])[0]
            limit = query.get("limit", [100])[0]
            events = OPS.audit(after_id, limit)
            try:
                fallback_cursor = int(after_id)
            except (TypeError, ValueError):
                fallback_cursor = 0
            next_cursor = max([int(item["id"]) for item in events] or [fallback_cursor])
            self.send_json({"events": events, "next_after_id": next_cursor}); return
        if route == "/api/usage":
            health = get_health_snapshot().get("employees", {})
            employees = []
            totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                      "requests": 0, "tasks_completed": 0, "runtime_seconds": 0}
            for employee_id, metric in health.items():
                row = {"employee_id": employee_id, "name": metric.get("name", employee_id),
                       "role": metric.get("role", ""), "model": metric.get("model", ""),
                       "status": metric.get("status", "idle"),
                       "usage_available": bool(metric.get("usage_available", False))}
                for key in totals:
                    value = max(0, int(metric.get(key, 0) or 0))
                    row[key] = value
                    totals[key] += value
                row["last_activity_at"] = metric.get("last_activity_at")
                row["last_detail"] = metric.get("last_detail", "")
                employees.append(row)
            self.send_json({"usage": {**totals, "employees": employees,
                "usage_available": any(x.get("usage_available") for x in employees)}}); return
        if route.startswith("/api/print-jobs/") and route.endswith("/download"):
            job_id = route.split("/")[-2]
            try:
                path = OPS.print_file_path(job_id); payload = path.read_bytes()
                self.send_response(200); self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
                self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(payload)
            except ValueError as error: self._api_error(error, 404)
            return
        if route.startswith("/api/print-jobs/"):
            job_id = route.rsplit("/", 1)[-1]
            try: self.send_json({"print_job": OPS.get_print_job(job_id)})
            except ValueError as error: self._api_error(error, 404)
            return
        if route == "/api/workstations":
            self.send_json({"workstations": DESKTOP.list_workstations()})
            return
        if route.startswith("/api/workstations/") and route.count("/") == 3:
            workstation_id = route.rsplit("/", 1)[-1]
            try:
                self.send_json({"workstation": DESKTOP.workstation(workstation_id)})
            except DesktopError as error:
                self._desktop_error(error)
            return
        if route == "/api/domain/state":
            self.send_json(DOMAIN.state())
            return
        if route == "/api/domain/dns/lookup":
            name = query.get("name", [""])[0]
            record = DOMAIN.dns_lookup(name)
            if record is None:
                self.send_json({"name": name, "found": False}, 404)
            else:
                self.send_json({"name": name, "found": True, "record": record})
            return
        if route == "/api/domain/dns/records":
            self.send_json({"records": DOMAIN.dns_records(), "domain": DOMAIN.domain_name})
            return
        if route == "/api/infra/services":
            self.send_json({"services": INFRA.list_services()})
            return
        if route == "/api/ftp/status":
            self.send_json(FTP.health())
            return
        if route == "/api/mail/status":
            self.send_json(MAIL.health())
            return
        if route == "/api/network/networks":
            self.send_json({"networks": NETWORK.list_networks()})
            return
        if route == "/api/network/subnets":
            self.send_json({"subnets": NETWORK.list_subnets()})
            return
        if route == "/api/network/scopes":
            self.send_json({"scopes": NETWORK.list_scopes()})
            return
        if route == "/api/network/leases":
            self.send_json({"leases": NETWORK.list_leases()})
            return
        if route == "/api/network/vpn/peers":
            self.send_json({"peers": NETWORK.list_vpn_peers()})
            return
        if route == "/api/desktop/session":
            try:
                self.send_json({"session": DESKTOP.session_state(self._desktop_token())})
            except DesktopError as error:
                self._desktop_error(error)
            return
        if route == "/api/desktop/system":
            try:
                self.send_json(DESKTOP.system_info(self._desktop_token()))
            except DesktopError as error:
                self._desktop_error(error)
            return
        if route == "/api/desktop/files":
            try:
                self.send_json(DESKTOP.list_files(self._desktop_token(),
                                                   query.get("path", ["."])[0]))
            except DesktopError as error:
                self._desktop_error(error)
            return
        if route == "/api/desktop/files/content":
            try:
                self.send_json({"file": DESKTOP.read_file(self._desktop_token(),
                                                          query.get("path", [""])[0])})
            except DesktopError as error:
                self._desktop_error(error)
            return
        if route == "/api/desktop/audit":
            try:
                self.send_json({"events": DESKTOP.audit(
                    self._desktop_token(),
                    query.get("after_id", [0])[0],
                    query.get("limit", [50])[0])})
            except DesktopError as error:
                self._desktop_error(error)
            return
        if route == "/api/office/state":
            self.send_json(STORE.snapshot())
            return
        if route == "/api/office/activity":
            after_id = query.get("after_id", [0])[0]
            limit = query.get("limit", [100])[0]
            try:
                events = ACTIVITY.feed(after_id, limit)
            except (TypeError, ValueError):
                events = ACTIVITY.feed(0, 100)
            fallback_cursor = int(events[-1]["id"]) if events else 0
            try:
                fallback_cursor = max(fallback_cursor, int(after_id))
            except (TypeError, ValueError):
                pass
            self.send_json({"events": events, "next_after_id": fallback_cursor,
                            "summary": ACTIVITY.summary()})
            return
        if route == "/api/office/player":
            self.send_json({"player": STORE.owner_player_state()})
            return
        if route == "/api/chat/history":
            channel_id = parse_qs(urlparse(self.path).query).get("channel", ["team"])[0]
            try:
                self.send_json({"channel_id": channel_id, "messages": STORE.list_chat_messages(channel_id, 150)})
            except ValueError as error:
                self.send_json({"error": str(error)}, 400)
            return
        if route == "/api/knowledge/documents":
            self.send_json({"documents": KNOWLEDGE.list_documents()})
            return
        if route == "/api/knowledge/search":
            query = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self.send_json({"query": query, "results": KNOWLEDGE.search(query, limit=8)})
            return
        if route == "/api/status":
            projects = latest_project_state()
            latest = projects[0] if projects else None
            with EMPLOYEE_CHAT_STATE_LOCK:
                active_chats = dict(EMPLOYEE_CHAT_ACTIVE)
            try:
                activity_tick = ACTIVITY.tick()
            except Exception as error:
                print(f"[ACTIVITY ENGINE ERROR] {type(error).__name__}: {error}", flush=True)
                activity_tick = {"error": "Engine aktivitas karyawan gagal berjalan."}
            self.send_json({
                "ollama": cached_ollama_status(),
                "active": dict(ACTIVE),
                "projects": projects[:10],
                "project": latest,
                "health": get_health_snapshot(),
                "employee_chats": active_chats,
                "activity": read_activity(),
                "activity_engine": activity_tick,
                "office": STORE.snapshot(),
                "company": {
                    "departments": OPS.departments(),
                    "employees": OPS.employees(),
                    "tasks": OPS.tasks(),
                    "meetings": OPS.meetings(),
                    "papers": OPS.list_papers( limit=100),
                    "approvals": OPS.list_approvals(limit=100, include_payload=True),
                    "outbox": OPS.list_outbox(30),
                    "print_jobs": OPS.list_print_jobs(30),
                    "usage": self._usage_summary(),
                    "knowledge_documents": KNOWLEDGE.list_documents(),
                    "papers_pending": len(OPS.list_papers("unread")),
                    "approvals_pending": len(OPS.list_approvals("pending")),
                },
            })
            return
        if route.startswith("/assets/"):
            asset_root = (WEB_DIR / "assets").resolve()
            relative_name = route.removeprefix("/assets/")
            asset_path = (asset_root / relative_name).resolve()
            try:
                asset_path.relative_to(asset_root)
            except ValueError:
                self.send_error(403, "Invalid asset path")
                return
            if not asset_path.is_file():
                self.send_error(404, "Asset not found")
                return
            try:
                payload = asset_path.read_bytes()
            except OSError:
                self.send_error(404, "Asset not found")
                return
            content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(payload)
            return
        if route in ("/", "/index.html"):
            file_path = WEB_DIR / "index.html"
            try:
                content = file_path.read_bytes()
            except OSError:
                self.send_error(404, "Office UI not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        route = parsed.path
        print(f"[DEBUG DOPOST] route={route}", flush=True)
        if not self._authorize_mutation():
            return
        try:
            body = self._read_json()
        except ValueError as error:
            self.send_json({"error": str(error)}, 400)
            return

        # Workstation desktop. Sessions are separate from the company API token:
        # a login returns an opaque desktop token scoped to one workstation.
        if route.startswith("/api/workstations/") and route.endswith("/login") and route.count("/") == 4:
            workstation_id = route.split("/")[3]
            try:
                session = DESKTOP.login(
                    workstation_id,
                    body.get("account_id", ""),
                    body.get("password", ""),
                )
                self.send_json({"success": True, **session}, 201)
            except DesktopError as error:
                self._desktop_error(error)
            return
        if route == "/api/desktop/session/close":
            try:
                self.send_json(DESKTOP.close_session(self._desktop_token()))
            except DesktopError as error:
                self._desktop_error(error)
            return
        if route == "/api/terminal/exec":
            try:
                self.send_json(DESKTOP.run_command(self._desktop_token(),
                                                   body.get("command", "")))
            except DesktopError as error:
                self._desktop_error(error)
            return
        if route == "/api/desktop/files/write":
            try:
                self.send_json(DESKTOP.write_file(self._desktop_token(),
                                                  body.get("path", ""),
                                                  body.get("content", "")))
            except DesktopError as error:
                self._desktop_error(error)
            return
        if route == "/api/domain/join" and route.count("/") == 2:
            print(f"[DEBUG DOPOST] domain-join branch taken cond={route == '/api/domain/join'} count={route.count('/')}", flush=True)
            workstation_id = str(body.get("workstation_id", "")).strip()
            actor = str(body.get("actor", "system")).strip() or "system"
            try:
                result = DOMAIN.join_domain(workstation_id, actor)
            except ValueError as error:
                self.send_json({"error": str(error)}, 400)
                return
            self.send_json({"success": True, "domain": result}, 201)
            return
        if route == "/api/domain/dns/record" and route.count("/") == 3:
            try:
                result = DOMAIN.add_dns_record(
                    str(body.get("name", "")), str(body.get("type", "A")),
                    str(body.get("value", "")),
                    str(body.get("actor", "system")).strip() or "system")
            except ValueError as error:
                self.send_json({"error": str(error)}, 400)
                return
            self.send_json({"success": True, "record": result}, 201)
            return
        if route == "/api/infra/service/start":
            sid = str(body.get("service_id","")).strip()
            try:
                self.send_json({"service": INFRA.start(sid, str(body.get("actor","system")))})
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
            return
        if route == "/api/infra/service/stop":
            sid = str(body.get("service_id","")).strip()
            self.send_json({"service": INFRA.stop(sid, str(body.get("actor","system")))})
            return
        if route == "/api/ftp/provision":
            u = str(body.get("username","")).strip()
            self.send_json({"path": FTP.provision_home(u)})
            return
        if route == "/api/mail/provision":
            u = str(body.get("username","")).strip()
            self.send_json({"email": MAIL.provision_mailbox(u)})
            return
        if route == "/api/network/subnet":
            self.send_json({"subnet": NETWORK.create_subnet(str(body.get("id","")), str(body.get("network_id","bangkah-net")), str(body.get("name","")), str(body.get("cidr","")), body.get("gateway"), body.get("dns"))}, 201)
            return
        if route == "/api/network/scope":
            self.send_json({"scope": NETWORK.create_scope(str(body.get("id","")), str(body.get("subnet_id","")), str(body.get("name","")), str(body.get("pool_start","")), str(body.get("pool_end","")), int(body.get("lease_seconds",86400)))}, 201)
            return
        if route == "/api/network/lease":
            self.send_json({"lease": NETWORK.allocate_lease(str(body.get("scope_id","")), str(body.get("hostname","")), str(body.get("mac","")), str(body.get("ip","")))}, 201)
            return
        if route == "/api/network/vpn/peer":
            self.send_json({"peer": NETWORK.create_vpn_peer(str(body.get("id","")), str(body.get("username","")), str(body.get("device","")), str(body.get("allowed_ips","")))}, 201)
            return

        # Persisted company workflows. All external side effects are separated
        # into approvals -> outbox -> explicit execute.
        try:
            if route == "/api/tasks":
                item = OPS.create_task(body.get("title", ""), body.get("description", ""),
                    body.get("assignee_id"), body.get("priority", "normal"), body.get("project_key", ""),
                    body.get("acceptance_criteria", ""))
                self.send_json({"success": True, "task": item}, 201); return
            if route.startswith("/api/tasks/") and route.endswith("/transition"):
                task_id = route.split("/")[-2]
                item = OPS.transition_task(task_id, body.get("status", ""), body.get("evidence", []), body.get("note", ""))
                self.send_json({"success": True, "task": item}); return
            if route == "/api/meetings":
                item = OPS.create_meeting(body.get("title", ""), body.get("attendee_ids", []),
                    body.get("agenda", ""), body.get("room_id", "meeting"))
                self.send_json({"success": True, "meeting": item}, 201); return
            if route.startswith("/api/meetings/"):
                parts = route.strip("/").split("/")
                if len(parts) == 4 and parts[3] in ("start", "complete", "cancel"):
                    item = OPS.update_meeting(parts[2], parts[3], body.get("minutes", ""),
                        body.get("decisions", []), body.get("followups", []))
                    self.send_json({"success": True, "meeting": item}); return
            if route == "/api/papers":
                item = OPS.create_paper(body.get("title", ""), body.get("body", ""),
                    body.get("paper_type", "memo"), body.get("origin", "owner"),
                    body.get("priority", "normal"), body.get("related_task_id"), body.get("approval_id"))
                self.send_json({"success": True, "paper": item}, 201); return
            if route.startswith("/api/papers/") and route.endswith("/review"):
                paper_id = route.split("/")[-2]
                item = OPS.update_paper_status(paper_id, body.get("status", "read"))
                self.send_json({"success": True, "paper": item}); return
            if route == "/api/print-jobs":
                item = OPS.create_print_job(body.get("paper_id", ""))
                self.send_json({"success": True, "print_job": item}, 201); return
            if route == "/api/approvals":
                item = OPS.create_approval(body.get("action_type", ""), body.get("summary", ""), body.get("payload", {}))
                self.send_json({"success": True, "approval": item}, 201); return
            if route.startswith("/api/approvals/"):
                parts = route.strip("/").split("/")
                if len(parts) == 4 and parts[3] in ("approve", "reject"):
                    item = OPS.decide_approval(parts[2], parts[3], "owner", body.get("note", ""))
                    self.send_json({"success": True, "approval": item}); return
            if route.startswith("/api/outbox/") and route.endswith("/execute"):
                outbox_id = route.split("/")[-2]
                result = execute_outbox(outbox_id)
                self.send_json(result, 200 if result.get("success") else 202); return
        except ValueError as error:
            self.send_json({"error": str(error)}, 400); return
        except AdapterError as error:
            self.send_json({"error": str(error)}, 409); return
        except Exception as error:
            print(f"[COMPANY API ERROR] {type(error).__name__}: {error}", flush=True)
            self.send_json({"error": "Operasi perusahaan gagal diproses."}, 500); return

        if route not in ("/api/command", "/api/chat", "/api/employee-chat", "/api/room-chat", "/api/office/action", "/api/office/player", "/api/knowledge/documents", "/api/office/activity/tick", "/api/domain/join", "/api/domain/dns/record"):
            self.send_error(404)
            return
        if route == "/api/office/activity/tick":
            force = bool(body.get("force", False))
            ignore_window = bool(body.get("ignore_window", False))
            try:
                result = ACTIVITY.tick(force=force, ignore_window=ignore_window)
                self.send_json({"success": True, "activity": result}, 200)
            except Exception as error:
                print(f"[ACTIVITY ENGINE ERROR] {type(error).__name__}: {error}", flush=True)
                self.send_json({"error": "Engine aktivitas karyawan gagal berjalan."}, 500)
            return
        command = str(body.get("command", "")).strip()
        project_name_hint = str(body.get("project_name_hint", "")).strip()
        employee_id = str(body.get("employee_id", "")).strip()
        employee_message = str(body.get("message", "")).strip()
        channel_id = str(body.get("channel_id", "team")).strip()
        if route == "/api/office/player":
            try:
                if body.get("interaction"):
                    player = STORE.interact_owner(
                        str(body.get("interaction", "")),
                        body.get("x"), body.get("y"), str(body.get("room_id", "corridor"))
                    )
                else:
                    player = STORE.update_owner_player(
                        body.get("x", 50), body.get("y", 90),
                        str(body.get("room_id", "corridor")),
                        str(body.get("activity", "idle"))
                    )
                self.send_json({"success": True, "player": player})
            except ValueError as error:
                self.send_json({"error": str(error)}, 400)
            except Exception as error:
                print(f"[OWNER PLAYER ERROR] {error}", flush=True)
                self.send_json({"error": "Status karakter owner gagal disimpan."}, 500)
            return
        if route == "/api/knowledge/documents":
            try:
                document = KNOWLEDGE.add_document(
                    body.get("title", ""), body.get("content", ""), body.get("source", "manual")
                )
                STORE.add_event("knowledge_document_added", "owner",
                                f"Dokumen knowledge base ditambahkan: {document['title']}", document["id"])
                self.send_json({"success": True, "document": document}, 201)
            except ValueError as error:
                self.send_json({"error": str(error)}, 400)
            except Exception as error:
                print(f"[KNOWLEDGE ERROR] {error}", flush=True)
                self.send_json({"error": "Dokumen gagal diindeks."}, 500)
            return
        if route == "/api/room-chat":
            if not employee_message:
                self.send_json({"error": "Tulis pesan sebelum mengirim."}, 400)
                return
            try:
                STORE.add_chat_message(channel_id, "owner", "Owner", "owner", employee_message)
                if channel_id == "team":
                    result = ORCHESTRATOR.handle_chat(employee_message)
                    reply = str(result.get("reply") or "Pesan diterima tim.")
                    STORE.add_chat_message("team", "lead", "Arman", "agent", reply,
                                           message_type="action_summary" if result.get("actions") else "text",
                                           metadata={"actions": result.get("actions", []), "errors": result.get("errors", [])})
                    STORE.record_interaction("lead", None, reply, None, "group_chat", 90)
                    # Jika perintah memulai rapat, thread rapat akan mengisi balasan anggota.
                    # Untuk obrolan umum, minta setiap spesialis memberi respons singkat.
                    starts_meeting = any(x.get("tool") == "create_meeting" for x in result.get("actions", []))
                    if not starts_meeting and not result.get("requires_approval"):
                        ORCHESTRATOR.start_group_replies(employee_message)
                    self.send_json({"success": True, **result})
                    return

                if channel_id not in EMPLOYEES:
                    self.send_json({"error": "Channel tidak dikenal."}, 400)
                    return
                result = ORCHESTRATOR.handle_employee_chat(channel_id, employee_message)
                employee = EMPLOYEES[channel_id]
                reply = str(result.get("reply") or "Pesan diterima.")
                STORE.add_chat_message(channel_id, channel_id, employee["name"], "agent", reply,
                                       message_type="action_summary" if result.get("actions") else "text",
                                       metadata={"actions": result.get("actions", []), "errors": result.get("errors", [])})
                current = next((x for x in STORE.snapshot()["employees"] if x["id"] == channel_id), None)
                STORE.record_interaction(channel_id, None, reply, (current or {}).get("room_id"), "owner_chat", 60)
                self.send_json({"success": True, **result})
            except Exception as error:
                print(f"[ROOM CHAT ERROR] {error}", flush=True)
                self.send_json({"error": f"Pesan gagal diproses: {error}"}, 503)
            return
        if route == "/api/office/action":
            action = str(body.get("action", "")).strip()
            arguments = body.get("arguments", {})
            if not action or not isinstance(arguments, dict):
                self.send_json({"error": "Aksi atau argumen tidak valid."}, 400)
                return
            try:
                result = TOOLS.execute(action, arguments, actor="owner")
                self.send_json({"success": True, "action": action, "result": result})
            except ValueError as error:
                self.send_json({"error": str(error)}, 400)
            except Exception as error:
                print(f"[OFFICE ACTION ERROR] {error}", flush=True)
                self.send_json({"error": "Aksi kantor gagal dijalankan."}, 500)
            return
        # Chat karyawan memakai field "employee_id" + "message", bukan "command".
        if route == "/api/employee-chat":
            if employee_id not in EMPLOYEES or not employee_message:
                self.send_json({"error": "Karyawan atau pesan tidak valid."}, 400)
                return
            self.handle_employee_chat(employee_id, employee_message)
            return
        if not command:
            self.send_json({"error": "Tulis pesan untuk Lead Manager."}, 400)
            return
        if route == "/api/chat":
            self.handle_chat(command)
            return
        if not RUN_LOCK.acquire(blocking=False):
            self.send_json({"error": "Masih ada pekerjaan yang berjalan."}, 409)
            return

        ACTIVE.update(running=True, command=command, started_at=datetime.now().isoformat(timespec="seconds"), error=None)
        pipeline_task_ids = []
        for task in STORE.snapshot().get("tasks", [])[:6]:
            if task.get("status") == "pending" and task.get("assignee_id"):
                try:
                    STORE.update_task(task["id"], "in_progress", actor="lead")
                    pipeline_task_ids.append(task["id"])
                except ValueError:
                    pass

        def update_pipeline_tasks(status):
            for task_id in pipeline_task_ids:
                try:
                    STORE.update_task(task_id, status, actor="lead")
                except ValueError:
                    pass

        def run_factory():
            try:
                AICodingFactory(lambda message: print(message, flush=True)).execute(
                    command,
                    project_name_hint=project_name_hint or None,
                )
                update_pipeline_tasks("completed")
            except Exception as error:  # surfaced in the office status instead of disappearing in a worker thread
                ACTIVE["error"] = str(error)
                print(f"[OFFICE ERROR] {error}", flush=True)
                update_pipeline_tasks("failed")
            finally:
                ACTIVE["running"] = False
                RUN_LOCK.release()

        threading.Thread(target=run_factory, name="office-project-run", daemon=True).start()
        self.send_json({"accepted": True, "command": command}, 202)

    def handle_chat(self, message):
        if not CHAT_LOCK.acquire(blocking=False):
            self.send_json({"error": "Lead Manager sedang memproses instruksi lain."}, 409)
            return
        try:
            KNOWLEDGE.ensure_seed_documents()
            result = ORCHESTRATOR.handle_chat(message)
            reply = str(result.get("reply") or "Instruksi sudah diproses.")
            CHAT_HISTORY.extend([
                {"role": "owner", "content": message},
                {"role": "manager", "content": reply},
            ])
            STORE.add_event("owner_chat", "owner", message[:900])
            STORE.add_event("lead_chat", "lead", reply[:900])
            record_activity("lead", "idle", "Menganalisis instruksi, mengambil konteks RAG, dan mengorkestrasi tool kantor.")
            self.send_json(result)
        except Exception as error:
            print(f"[ORCHESTRATOR ERROR] {error}", flush=True)
            self.send_json({"error": f"Arman belum dapat menjalankan instruksi: {error}"}, 503)
        finally:
            CHAT_LOCK.release()

    def handle_employee_chat(self, employee_id, message):
        """Compatibility endpoint; delegates to the same action-aware chat pipeline."""
        if not EMPLOYEE_CHAT_LOCK.acquire(blocking=False):
            self.send_json({"error": "Karyawan lain sedang membalas. Coba beberapa saat lagi."}, 409)
            return
        employee = EMPLOYEES[employee_id]
        with EMPLOYEE_CHAT_STATE_LOCK:
            EMPLOYEE_CHAT_ACTIVE[employee_id] = {"started_at": datetime.now().isoformat(timespec="seconds")}
        try:
            STORE.add_chat_message(employee_id, "owner", "Owner", "owner", message)
            result = ORCHESTRATOR.handle_employee_chat(employee_id, message)
            reply = str(result.get("reply") or "Pesan diterima.")
            STORE.add_chat_message(employee_id, employee_id, employee["name"], "agent", reply)
            current = next((x for x in STORE.snapshot()["employees"] if x["id"] == employee_id), None)
            STORE.record_interaction(employee_id, None, reply, (current or {}).get("room_id"), "owner_chat", 60)
            self.send_json(result)
        except Exception as error:
            print(f"[EMPLOYEE CHAT ERROR] {error}", flush=True)
            self.send_json({"error": f"{employee['name']} belum dapat memproses pesan: {error}"}, 503)
        finally:
            with EMPLOYEE_CHAT_STATE_LOCK:
                EMPLOYEE_CHAT_ACTIVE.pop(employee_id, None)
            EMPLOYEE_CHAT_LOCK.release()


if __name__ == "__main__":
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("Direct non-loopback binding is disabled. Keep BANGKAH_HOST on loopback and expose it through a TLS reverse proxy.")
    KNOWLEDGE.ensure_seed_documents()
    print(f"Bangkah AI Office API ready at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), OfficeHandler).serve_forever()