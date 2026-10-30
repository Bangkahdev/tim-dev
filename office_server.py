"""Local web office for the AI Coding Factory."""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from config import make_llm, model_for
from main import AICodingFactory, LOG_DIR, WORKSPACE, check_ollama
from core.employee_health import EMPLOYEES, get_health_snapshot, record_activity

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
HOST = "127.0.0.1"
PORT = 8765
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

    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/api/status":
            projects = latest_project_state()
            latest = projects[0] if projects else None
            with EMPLOYEE_CHAT_STATE_LOCK:
                active_chats = dict(EMPLOYEE_CHAT_ACTIVE)
            self.send_json({
                "ollama": cached_ollama_status(),
                "active": dict(ACTIVE),
                "projects": projects[:10],
                "project": latest,
                "health": get_health_snapshot(),
                "employee_chats": active_chats,
                "activity": read_activity(),
            })
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
        route = urlparse(self.path).path
        if route not in ("/api/command", "/api/chat", "/api/employee-chat"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 20_000:
                self.send_json({"error": "Instruksi terlalu panjang."}, 413)
                return
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            command = str(body.get("command", "")).strip()
            project_name_hint = str(body.get("project_name_hint", "")).strip()
            employee_id = str(body.get("employee_id", "")).strip()
            employee_message = str(body.get("message", "")).strip()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json({"error": "Permintaan tidak valid."}, 400)
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

        def run_factory():
            try:
                AICodingFactory(lambda message: print(message, flush=True)).execute(
                    command,
                    project_name_hint=project_name_hint or None,
                )
            except Exception as error:  # surfaced in the office status instead of disappearing in a worker thread
                ACTIVE["error"] = str(error)
                print(f"[OFFICE ERROR] {error}", flush=True)
            finally:
                ACTIVE["running"] = False
                RUN_LOCK.release()

        threading.Thread(target=run_factory, name="office-project-run", daemon=True).start()
        self.send_json({"accepted": True, "command": command}, 202)

    def handle_chat(self, message):
        if not CHAT_LOCK.acquire(blocking=False):
            self.send_json({"error": "Lead Manager sedang membalas percakapan lain."}, 409)
            return
        try:
            llm = make_llm(model_for("lead"), temperature=0.4)
            messages = (
                [{"role": "system", "content": LEAD_CHAT_SYSTEM}]
                + history_messages(CHAT_HISTORY)
                + [{"role": "user", "content": message}]
            )
            answer = clean_reply(llm.call(messages))
            if not answer:
                raise RuntimeError("Model mengembalikan balasan kosong.")
            record_activity("lead", "idle", "Berdiskusi dengan owner.", llm_usage(llm))
            CHAT_HISTORY.extend([
                {"role": "owner", "content": message},
                {"role": "manager", "content": answer},
            ])
            self.send_json({"reply": answer})
        except Exception as error:
            self.send_json({"error": f"Lead Manager belum dapat membalas: {error}"}, 503)
        finally:
            CHAT_LOCK.release()

    def handle_employee_chat(self, employee_id, message):
        if not EMPLOYEE_CHAT_LOCK.acquire(blocking=False):
            self.send_json({"error": "Karyawan lain sedang membalas. Coba beberapa saat lagi."}, 409)
            return
        employee = EMPLOYEES[employee_id]
        with EMPLOYEE_CHAT_STATE_LOCK:
            EMPLOYEE_CHAT_ACTIVE[employee_id] = {"started_at": datetime.now().isoformat(timespec="seconds")}
        try:
            # employee["model"] sudah string lengkap, mis. "ollama/llama3.2:3b" atau "openai/..."
            llm = make_llm(employee["model"], temperature=0.45)
            projects = latest_project_state()
            project = projects[0] if projects else {}
            current_agent = project.get("agents", {}).get(employee_id, {})
            context = (
                f"proyek terkini {project.get('project', 'belum ada')}, "
                f"fase {project.get('current_phase', 'idle')}, "
                f"tugas terakhirmu: {current_agent.get('detail', 'belum ada tugas tercatat')}"
            )
            history = EMPLOYEE_CHAT_HISTORY[employee_id]
            messages = (
                [{"role": "system", "content": employee_chat_system(employee, context)}]
                + history_messages(history)
                + [{"role": "user", "content": message}]
            )
            reply = clean_reply(llm.call(messages))
            if not reply:
                raise RuntimeError("Model mengembalikan balasan kosong.")
            history.extend([
                {"role": "owner", "content": message},
                {"role": "employee", "content": reply},
            ])
            record_activity(
                employee_id,
                detail=f"Percakapan langsung dengan owner: {message[:100]}",
                usage=llm_usage(llm),
            )
            self.send_json({"reply": reply, "employee": employee})
        except Exception as error:
            self.send_json({"error": f"{employee['name']} belum dapat membalas: {error}"}, 503)
        finally:
            with EMPLOYEE_CHAT_STATE_LOCK:
                EMPLOYEE_CHAT_ACTIVE.pop(employee_id, None)
            EMPLOYEE_CHAT_LOCK.release()


if __name__ == "__main__":
    print(f"AI Coding Office is ready at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), OfficeHandler).serve_forever()