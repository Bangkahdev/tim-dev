"""Local web office for the AI Coding Factory."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from crewai import Agent, Crew, Process, Task

from main import AICodingFactory, LOG_DIR, MODEL_MANAGER, OLLAMA_URL, WORKSPACE, LLM, check_ollama

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
HOST = "127.0.0.1"
PORT = 8765
RUN_LOCK = threading.Lock()
ACTIVE = {"running": False, "command": "", "started_at": None, "error": None}
CHAT_HISTORY = []
CHAT_LOCK = threading.Lock()
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
            self.send_json({
                "ollama": cached_ollama_status(),
                "active": dict(ACTIVE),
                "projects": projects[:10],
                "project": latest,
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
        if route not in ("/api/command", "/api/chat"):
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
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json({"error": "Permintaan tidak valid."}, 400)
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
            llm = LLM(model=MODEL_MANAGER, base_url=OLLAMA_URL, temperature=0.35)
            lead = Agent(
                role="Lead Manager / AI CTO",
                goal="Berdiskusi dengan owner, memahami tujuan dan batasan, lalu menyepakati rencana kerja yang bisa didelegasikan kepada tim.",
                backstory="Anda memimpin kantor berisi COO, System Architect, Backend Developer, API Specialist, Frontend Developer, dan QA Engineer. Saat berdiskusi, jangan mengklaim pekerjaan telah dimulai. Tanyakan hanya hal penting yang belum jelas, rangkum kebutuhan, dan beri rancangan pembagian kerja yang mudah dipahami. Owner akan menekan tombol mulai setelah menyetujui arahan.",
                llm=llm,
                allow_delegation=False,
                verbose=False,
            )
            transcript = "\n".join(
                f"{item['role'].upper()}: {item['content']}" for item in CHAT_HISTORY[-12:]
            )
            task = Task(
                description=(
                    "Percakapan dengan owner (pesan terbaru di bagian akhir):\n"
                    f"{transcript}\nOWNER: {message}\n\n"
                    "Balas dalam Bahasa Indonesia dengan nada manager yang jelas dan kolaboratif. "
                    "Tanggapi konteks sebelumnya, jelaskan pemahamanmu, beri saran pembagian kerja bila sudah cukup jelas, "
                    "dan ajukan maksimal dua pertanyaan penting bila masih ada keputusan yang perlu owner tentukan. "
                    "Jangan mengaku sudah menjalankan tugas."
                ),
                expected_output="Balasan diskusi dari Lead Manager beserta pemahaman dan rencana kerja sementara.",
                agent=lead,
            )
            answer = str(Crew(agents=[lead], tasks=[task], process=Process.sequential, verbose=False).kickoff())
            CHAT_HISTORY.extend([{"role": "owner", "content": message}, {"role": "manager", "content": answer}])
            self.send_json({"reply": answer})
        except Exception as error:
            self.send_json({"error": f"Lead Manager belum dapat membalas: {error}"}, 503)
        finally:
            CHAT_LOCK.release()


if __name__ == "__main__":
    print(f"AI Coding Office is ready at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), OfficeHandler).serve_forever()
