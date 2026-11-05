import os
import re
import sys
import json
import shlex
import queue
import threading
import subprocess
import traceback
import urllib.request

from pathlib import Path
from datetime import datetime

from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Button, RichLog
from textual.containers import Horizontal

from config import (
    OLLAMA_URL,
    MAX_REPAIR_ROUNDS,
    COMMAND_TIMEOUT,
    GROUP_MODELS,
    model_for,
    make_llm,
    required_local_models,
    missing_api_keys,
)
from core.project_state import ProjectState
from core.lead_manager import LeadManager
from core.employee_health import EMPLOYEES, record_activity
from core.office_store import STORE


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

WORKSPACE = BASE_DIR / "workspace" / "projects"
LOG_DIR = BASE_DIR / "logs"
REPORT_DIR = BASE_DIR / "reports"

# Dipertahankan agar kode lama yang mengimpor nama ini tetap jalan.
MODEL_MANAGER = GROUP_MODELS["MANAGER"]
MODEL_CODER = GROUP_MODELS["CODER"]
MODEL_SPECIALIST = GROUP_MODELS["SPECIALIST"]

MAX_FILE_SIZE = 1_000_000

for directory in (WORKSPACE, LOG_DIR, REPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOGGING
# ============================================================

class ProjectLogger:

    def __init__(self, callback):
        self.callback = callback
        self.lock = threading.RLock()

    def log(self, message):

        timestamp = datetime.now().strftime("%H:%M:%S")

        message = f"[{timestamp}] {message}"

        with self.lock:

            self.callback(message)

            with open(
                LOG_DIR / "factory.log",
                "a",
                encoding="utf-8"
            ) as file:

                file.write(message + "\n")


# ============================================================
# PROJECT NAME
# ============================================================

def create_project_name(command):

    name = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "-",
        command.lower()
    ).strip("-")

    return name[:45] or "new-project"


# ============================================================
# SAFE FILESYSTEM
# ============================================================

def safe_project_path(root, relative_path):

    root = Path(root).resolve()

    target = (root / relative_path).resolve()

    if target != root and root not in target.parents:

        raise ValueError(
            "Akses ditolak: path keluar dari workspace."
        )

    current = root

    for part in Path(relative_path).parts:

        if part in ("", "."):
            continue

        if part == "..":
            raise ValueError("Path traversal ditolak.")

        current = current / part

        if current.is_symlink():
            raise ValueError("Symbolic link tidak diizinkan.")

    return target


# ============================================================
# PROJECT TOOLS
# ============================================================

def create_project_tools(project_dir, logger):

    project_dir = Path(project_dir).resolve()

    project_dir.mkdir(parents=True, exist_ok=True)

    @tool("Read Project File")
    def read_project_file(path: str) -> str:
        """Membaca isi file proyek berdasarkan path relatif."""

        try:

            target = safe_project_path(
                project_dir,
                path
            )

            if not target.is_file():
                return "File tidak ditemukan."

            if target.stat().st_size > MAX_FILE_SIZE:
                return "File terlalu besar."

            return target.read_text(
                encoding="utf-8"
            )

        except Exception as error:

            return f"ERROR: {error}"

    @tool("Write Project File")
    def write_project_file(path: str, content: str) -> str:
        """Membuat atau memperbarui file proyek."""

        try:

            target = safe_project_path(
                project_dir,
                path
            )

            if target.is_symlink():
                return "Symbolic link ditolak."

            target.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            target.write_text(
                content,
                encoding="utf-8"
            )

            logger.log(
                f"[FILE] Menulis: {path}"
            )

            return f"File berhasil disimpan: {path}"

        except Exception as error:

            return f"ERROR: {error}"

    @tool("List Project Files")
    def list_project_files(path: str = ".") -> str:
        """Melihat daftar file dalam proyek."""

        try:

            target = safe_project_path(
                project_dir,
                path
            )

            if not target.exists():
                return "Direktori tidak ditemukan."

            results = []

            ignored = {
                ".git",
                ".venv",
                "venv",
                "node_modules",
                "__pycache__",
                ".factory"
            }

            for item in sorted(target.rglob("*")):

                if any(
                    part in ignored
                    for part in item.relative_to(project_dir).parts
                ):
                    continue

                relative = item.relative_to(project_dir)

                prefix = (
                    "[DIR]"
                    if item.is_dir()
                    else "[FILE]"
                )

                results.append(
                    f"{prefix} {relative}"
                )

                if len(results) >= 300:
                    results.append("Batas daftar tercapai.")
                    break

            return "\n".join(results) or "Proyek kosong."

        except Exception as error:

            return f"ERROR: {error}"

    @tool("Run Project Command")
    def run_project_command(command: str) -> str:
        """
        Menjalankan perintah proyek tanpa shell.

        Hanya executable yang diizinkan.
        Jangan gunakan untuk perintah sistem.
        """

        try:

            args = shlex.split(command)

            if not args:
                return "Perintah kosong."

            executable = Path(args[0]).name.lower()

            allowed = {
                "python",
                "python3",
                "pytest",
                "node",
                "npm",
                "npx",
                "git",
                "uv"
            }

            if executable not in allowed:
                return (
                    f"Executable tidak diizinkan: {executable}"
                )

            forbidden = {
                "rm",
                "rmdir",
                "del",
                "format",
                "shutdown",
                "reboot",
                "sudo",
                "su",
                "chmod",
                "chown",
                "mkfs"
            }

            if any(
                Path(arg).name.lower() in forbidden
                for arg in args
            ):
                return "Perintah berbahaya ditolak."

            for arg in args:

                if ".." in Path(arg).parts:
                    return "Path traversal ditolak."

            logger.log(
                f"[TERMINAL] $ {command}"
            )

            result = subprocess.run(
                args,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT,
                shell=False,
                env={
                    **os.environ,
                    "PYTHONUNBUFFERED": "1"
                }
            )

            output = (
                result.stdout or ""
            ) + (
                result.stderr or ""
            )

            return (
                f"EXIT CODE: {result.returncode}\n"
                f"OUTPUT:\n{output[-12000:]}"
            )

        except subprocess.TimeoutExpired:

            return "ERROR: Command timeout."

        except Exception as error:

            return f"ERROR: {error}"

    @tool("Inspect Project")
    def inspect_project() -> str:
        """Memeriksa file aktual proyek."""

        files = []

        ignored = {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".factory"
        }

        for item in project_dir.rglob("*"):

            if not item.is_file():
                continue

            if any(
                part in ignored
                for part in item.relative_to(project_dir).parts
            ):
                continue

            files.append(
                str(item.relative_to(project_dir))
            )

        return json.dumps(
            {
                "directory": str(project_dir),
                "file_count": len(files),
                "files": files[:300]
            },
            indent=2
        )

    return [
        read_project_file,
        write_project_file,
        list_project_files,
        run_project_command,
        inspect_project
    ]


# ============================================================
# MODEL CONNECTION CHECK (Ollama + API key cloud)
# ============================================================

def check_ollama():
    """Memeriksa kesiapan model sesuai .env.

    Nama fungsi dipertahankan agar office_server.py tetap kompatibel.
    - Model ollama/... : Ollama harus hidup dan model terpasang.
    - Model cloud      : API key provider harus terisi.
    """

    try:

        missing_keys = missing_api_keys()

        if missing_keys:

            return (
                False,
                "API key belum diisi di .env: " +
                ", ".join(missing_keys)
            )

        required = required_local_models()

        if not required:

            return (
                True,
                "Semua model memakai cloud. "
                "Ollama tidak diperlukan."
            )

        with urllib.request.urlopen(
            OLLAMA_URL,
            timeout=5
        ) as response:

            if response.status != 200:
                return False, "Ollama tidak merespons."

        with urllib.request.urlopen(
            OLLAMA_URL + "/api/tags",
            timeout=5
        ) as response:

            data = json.loads(
                response.read().decode()
            )

        installed = {
            model["name"]
            for model in data.get("models", [])
        }

        missing = [
            model
            for model in required
            if model not in installed
        ]

        if missing:

            return (
                False,
                "Model belum tersedia di Ollama: " +
                ", ".join(missing)
            )

        return True, "Model siap digunakan."

    except Exception as error:

        return False, str(error)


# ============================================================
# AI CODING FACTORY ENGINE
# ============================================================

class AICodingFactory:

    def __init__(self, callback):

        self.logger = ProjectLogger(callback)

        self.state = None
        self.lead_manager = None
        self.agent_keys = {}

    # --------------------------------------------------------
    # CREATE AGENTS
    # --------------------------------------------------------

    def create_agents(self, tools):

        agents = {}

        agents["lead"] = Agent(
            role="Lead Manager / AI CTO",

            goal=(
                "Menjadi satu-satunya penanggung jawab "
                "proyek dan pemimpin seluruh departemen."
            ),

            backstory=(
                "Anda adalah AI CTO profesional. "
                "Anda menerima instruksi dari pemilik, "
                "mengawasi seluruh agen, mengambil keputusan, "
                "menyelesaikan masalah, dan memberikan "
                "laporan akhir kepada pemilik."
            ),

            llm=make_llm(model_for("lead")),
            tools=tools,
            allow_delegation=False,
            verbose=True
        )

        agents["coo"] = Agent(
            role="COO / Project Manager",

            goal=(
                "Menganalisis kebutuhan, membuat rencana "
                "dan mengatur prioritas proyek."
            ),

            backstory=(
                "Anda bertanggung jawab atas perencanaan "
                "dan koordinasi proyek."
            ),

            llm=make_llm(model_for("coo")),
            tools=tools,
            allow_delegation=False,
            verbose=True
        )

        agents["architect"] = Agent(
            role="System Architect",

            goal=(
                "Merancang arsitektur dan struktur aplikasi."
            ),

            backstory=(
                "Anda ahli system architecture, database, "
                "integrasi, dan desain aplikasi."
            ),

            llm=make_llm(model_for("architect")),
            tools=tools,
            allow_delegation=False,
            verbose=True
        )

        agents["backend"] = Agent(
            role="Backend Developer",

            goal=(
                "Membangun backend, database, "
                "dan business logic."
            ),

            backstory=(
                "Anda developer backend profesional. "
                "Anda harus membuat file proyek nyata."
            ),

            llm=make_llm(model_for("backend")),
            tools=tools,
            allow_delegation=False,
            verbose=True
        )

        agents["api"] = Agent(
            role="API Specialist",

            goal=(
                "Membangun routing, API, "
                "middleware dan dokumentasi."
            ),

            backstory=(
                "Anda ahli REST API dan integrasi sistem."
            ),

            llm=make_llm(model_for("api")),
            tools=tools,
            allow_delegation=False,
            verbose=True
        )

        agents["frontend"] = Agent(
            role="Frontend Developer",

            goal=(
                "Membangun UI, UX dan integrasi frontend."
            ),

            backstory=(
                "Anda ahli HTML, CSS, JavaScript, React "
                "dan antarmuka modern."
            ),

            llm=make_llm(model_for("frontend")),
            tools=tools,
            allow_delegation=False,
            verbose=True
        )

        agents["qa"] = Agent(
            role="QA Engineer",

            goal=(
                "Menguji aplikasi, menemukan bug, "
                "dan memastikan kualitas kode."
            ),

            backstory=(
                "Anda QA profesional. Jangan pernah "
                "mengklaim PASS tanpa bukti pengujian."
            ),

            llm=make_llm(model_for("qa")),
            tools=tools,
            allow_delegation=False,
            verbose=True
        )

        self.agent_keys = {id(agent): name for name, agent in agents.items()}
        return agents

    # --------------------------------------------------------
    # CREW EXECUTION
    # --------------------------------------------------------

    def run_phase(self, agents, tasks):
        result = None
        for task in tasks:
            agent = task.agent
            agent_key = self.agent_keys.get(id(agent), "lead")
            detail = task.description.strip().splitlines()[0][:180]
            self.state.set_agent(agent_key, "working", detail)
            record_activity(agent_key, "working", detail)
            try:
                STORE.set_employee_status(agent_key, "working", detail, actor="workflow")
                if agent_key != "lead":
                    employee_row = next((x for x in STORE.snapshot()["employees"] if x["id"] == agent_key), None)
                    STORE.record_interaction("lead", agent_key, detail, (employee_row or {}).get("room_id"), "task_assignment", 90)
            except Exception as office_error:
                self.logger.log(f"[OFFICE SYNC] {office_error}")
            self.logger.log(f"[AGENT] {agent_key} memulai tugas.")
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=True
            )
            try:
                result = crew.kickoff()
            except Exception as error:
                self.state.set_agent(agent_key, "failed", str(error)[:400])
                record_activity(agent_key, "failed", str(error)[:240])
                try:
                    STORE.set_employee_status(agent_key, "failed", str(error)[:240], actor="workflow")
                except Exception:
                    pass
                raise
            usage = getattr(result, "token_usage", None) or getattr(crew, "usage_metrics", None)
            self.state.set_agent(agent_key, "completed", str(result)[:1000])
            record_activity(agent_key, "completed", detail, usage)
            try:
                STORE.set_employee_status(agent_key, "completed", "Tugas selesai: " + detail, actor="workflow")
                if agent_key != "lead":
                    STORE.record_interaction(agent_key, "lead", str(result)[:350], None, "task_update", 90)
            except Exception as office_error:
                self.logger.log(f"[OFFICE SYNC] {office_error}")
            self.logger.log(f"[AGENT] {agent_key} menyelesaikan tugas.")
        return result

    # --------------------------------------------------------
    # PHASE 1: PLANNING
    # --------------------------------------------------------

    def planning_phase(self, command, agents):

        self.logger.log(
            "[PHASE 1] Perencanaan proyek."
        )

        self.state.update(
            status="running",
            current_phase="planning"
        )

        planning = Task(
            description=f"""
            Instruksi pemilik:

            {command}

            Analisis kebutuhan proyek secara lengkap.

            Tentukan:
            - Jenis aplikasi
            - Fitur utama
            - Teknologi
            - Struktur proyek
            - Database
            - Integrasi
            - Kebutuhan keamanan
            - Urutan pengerjaan

            Jangan membuat asumsi yang bertentangan
            dengan instruksi pemilik.
            """,

            expected_output=(
                "Dokumen kebutuhan dan rencana proyek."
            ),

            agent=agents["coo"]
        )

        architecture = Task(
            description="""
            Buat arsitektur proyek berdasarkan hasil COO.

            Tentukan:
            - Struktur direktori
            - Desain backend
            - Desain frontend
            - Database
            - API
            - Testing

            Buat file ARCHITECTURE.md menggunakan tools.
            """,

            expected_output=(
                "Arsitektur aplikasi dan dokumentasi."
            ),

            agent=agents["architect"],
            context=[planning]
        )

        review = Task(
            description="""
            Tinjau rencana dan arsitektur.

            Pastikan semua kebutuhan pemilik tercakup.

            Berikan arahan kepada tim developer.
            """,

            expected_output=(
                "Persetujuan rencana oleh Lead Manager."
            ),

            agent=agents["lead"],
            context=[planning, architecture]
        )

        result = self.run_phase(
            [
                agents["coo"],
                agents["architect"],
                agents["lead"]
            ],
            [
                planning,
                architecture,
                review
            ]
        )

        self.state.add_history(
            "lead_manager",
            "planning_completed",
            str(result)[:3000]
        )

        return planning, architecture, review

    # --------------------------------------------------------
    # PHASE 2: DEVELOPMENT
    # --------------------------------------------------------

    def development_phase(
        self,
        agents,
        planning,
        architecture,
        review
    ):

        self.logger.log(
            "[PHASE 2] Pengembangan aplikasi."
        )

        self.state.update(
            current_phase="development"
        )

        backend_task = Task(
            description="""
            Bangun backend aplikasi.

            Buat seluruh file yang diperlukan.

            Implementasikan:
            - Business logic
            - Database
            - Model
            - Authentication jika dibutuhkan
            - Configuration
            - Error handling

            Gunakan tools untuk membuat file nyata.
            """,

            expected_output=(
                "Backend aplikasi berhasil dibuat."
            ),

            agent=agents["backend"],

            context=[
                planning,
                architecture,
                review
            ]
        )

        api_task = Task(
            description="""
            Bangun API berdasarkan arsitektur.

            Periksa file backend.

            Buat:
            - Endpoint
            - Routing
            - Middleware
            - Validasi request
            - Dokumentasi API

            Gunakan file tools.
            """,

            expected_output=(
                "API berhasil dibuat dan terintegrasi."
            ),

            agent=agents["api"],

            context=[
                planning,
                architecture,
                backend_task
            ]
        )

        frontend_task = Task(
            description="""
            Bangun frontend aplikasi.

            Buat:
            - Halaman utama
            - Dashboard
            - Komponen UI
            - CSS responsif
            - Navigasi
            - Integrasi API

            Gunakan file tools.
            """,

            expected_output=(
                "Frontend berhasil dibuat."
            ),

            agent=agents["frontend"],

            context=[
                planning,
                architecture,
                backend_task,
                api_task
            ]
        )

        result = self.run_phase(
            [
                agents["backend"],
                agents["api"],
                agents["frontend"]
            ],
            [
                backend_task,
                api_task,
                frontend_task
            ]
        )

        self.state.add_history(
            "development_team",
            "development_completed",
            str(result)[:3000]
        )

        return result

    # --------------------------------------------------------
    # PHASE 3: QA
    # --------------------------------------------------------

    def qa_phase(self, agents):

        self.logger.log(
            "[PHASE 3] QA sedang memeriksa aplikasi."
        )

        self.state.update(
            current_phase="quality_assurance"
        )

        self.state.set_agent(
            "qa",
            "working",
            "Melakukan pemeriksaan proyek."
        )

        qa_task = Task(
            description="""
            Lakukan pemeriksaan proyek secara aktual.

            Periksa:
            1. Struktur file.
            2. File yang kosong.
            3. Kesalahan sintaks.
            4. Dependency.
            5. Database.
            6. Integrasi frontend dan backend.
            7. Test otomatis.

            Jalankan perintah pengujian yang tersedia.

            Jangan menyatakan PASS apabila test
            tidak benar-benar dijalankan.

            Format:

            STATUS: PASS atau FAIL

            ISSUES:
            Daftar masalah.

            FILES:
            File bermasalah.

            TEST_RESULTS:
            Hasil pengujian.
            """,

            expected_output=(
                "Laporan QA lengkap dengan hasil pengujian."
            ),

            agent=agents["qa"]
        )

        result = self.run_phase(
            [agents["qa"]],
            [qa_task]
        )

        self.state.set_agent(
            "qa",
            "completed",
            str(result)[:2000]
        )

        return str(result)

    # --------------------------------------------------------
    # PHASE 4: LEAD REVIEW
    # --------------------------------------------------------

    def lead_review(self, qa_result):

        self.logger.log(
            "[LEAD] Menganalisis laporan QA."
        )

        decision = self.lead_manager.review_qa(
            qa_result
        )

        self.state.add_history(
            "lead_manager",
            "qa_review",
            decision[:3000]
        )

        return decision

    # --------------------------------------------------------
    # PHASE 5: REPAIR
    # --------------------------------------------------------

    def repair_phase(self, decision):

        self.logger.log(
            "[LEAD] Mengaktifkan sistem perbaikan otomatis."
        )

        self.state.increment_repair()

        result = self.lead_manager.repair_issue(
            decision
        )

        self.state.add_history(
            "lead_manager",
            "repair_completed",
            result[:3000]
        )

        return result

    # --------------------------------------------------------
    # PHASE 6: FINAL REPORT
    # --------------------------------------------------------

    def final_report(
        self,
        agents,
        command,
        qa_result,
        decision,
        project_dir
    ):

        self.logger.log(
            "[LEAD] Menyiapkan laporan akhir."
        )

        self.state.update(
            current_phase="final_report"
        )

        inspection_result = json.loads(
            create_project_tools(
                project_dir,
                self.logger
            )[4].run()
        )

        report_task = Task(
            description=f"""
            Buat laporan akhir proyek untuk pemilik.

            INSTRUKSI PEMILIK:
            {command}

            FILE PROYEK AKTUAL:
            {json.dumps(inspection_result, indent=2)}

            LAPORAN QA:
            {qa_result}

            KEPUTUSAN LEAD:
            {decision}

            STATUS:
            {self.state.get_snapshot()['qa_status']}

            Laporan wajib berisi:

            1. Ringkasan proyek.
            2. Fitur yang dibuat.
            3. Teknologi.
            4. Struktur direktori.
            5. Hasil QA.
            6. Bug yang belum selesai.
            7. Cara menjalankan aplikasi.
            8. Rekomendasi selanjutnya.

            Jangan mengklaim fitur selesai tanpa bukti.
            """,

            expected_output="Laporan akhir proyek.",

            agent=agents["lead"]
        )

        result = self.run_phase(
            [agents["lead"]],
            [report_task]
        )

        return str(result)

    # --------------------------------------------------------
    # MAIN EXECUTION
    # --------------------------------------------------------

    def execute(self, command, project_name_hint=None):

        project_name = create_project_name(
            project_name_hint or command
        )

        project_dir = WORKSPACE / project_name

        project_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.logger.log(
            "=" * 55
        )

        self.logger.log(
            "[SYSTEM] AI CODING FACTORY DIMULAI."
        )

        self.logger.log(
            f"[PROJECT] {project_name}"
        )

        self.logger.log(
            f"[WORKSPACE] {project_dir}"
        )

        self.state = ProjectState(
            project_dir
        )

        self.state.update(
            owner_command=command,
            status="running",
            current_phase="initialization",
            qa_status="pending"
        )

        for employee_id in EMPLOYEES:
            self.state.set_agent(employee_id, "idle", "Menunggu arahan berikutnya.")
            record_activity(employee_id, "idle", "Menunggu arahan berikutnya.")
            try:
                STORE.set_employee_status(employee_id, "idle", "Menunggu arahan berikutnya.", actor="workflow")
            except Exception:
                pass

        self.state.add_history(
            "owner",
            "new_project",
            command
        )

        try:

            tools = create_project_tools(
                project_dir,
                self.logger
            )

            agents = self.create_agents(
                tools
            )

            self.lead_manager = LeadManager(
                agents=agents,
                logger=self.logger,
                state=self.state
            )

            # PHASE 1
            planning, architecture, review = (
                self.planning_phase(
                    command,
                    agents
                )
            )

            # PHASE 2
            self.development_phase(
                agents,
                planning,
                architecture,
                review
            )

            # PHASE 3-5
            qa_result = ""
            decision = ""
            qa_passed = False

            for attempt in range(
                MAX_REPAIR_ROUNDS + 1
            ):

                qa_result = self.qa_phase(
                    agents
                )

                decision = self.lead_review(
                    qa_result
                )

                # PASS harus berupa keputusan Lead
                # dan tidak boleh sekaligus FAIL.

                passed = (
                    re.search(
                        r"STATUS\s*:\s*PASS\b",
                        decision,
                        re.IGNORECASE
                    )
                    and not re.search(
                        r"STATUS\s*:\s*FAIL\b",
                        decision,
                        re.IGNORECASE
                    )
                )

                if passed:

                    qa_passed = True

                    self.state.set_qa(
                        "PASS",
                        decision
                    )

                    self.logger.log(
                        "[QA] PASS disetujui Lead Manager."
                    )

                    break

                self.state.set_qa(
                    "FAIL",
                    decision
                )

                if attempt >= MAX_REPAIR_ROUNDS:

                    self.logger.log(
                        "[QA] Batas perbaikan tercapai."
                    )

                    break

                self.repair_phase(
                    decision
                )

            # PHASE 6
            report = self.final_report(
                agents,
                command,
                qa_result,
                decision,
                project_dir
            )

            report_path = (
                REPORT_DIR /
                (
                    f"{project_name}-"
                    f"{datetime.now():%Y%m%d-%H%M%S}.md"
                )
            )

            report_path.write_text(
                report,
                encoding="utf-8"
            )

            self.state.update(
                status=(
                    "completed"
                    if qa_passed
                    else "needs_attention"
                ),
                current_phase="finished",
                last_report=str(report_path),
                qa_status=(
                    "PASS"
                    if qa_passed
                    else "FAIL"
                )
            )

            self.state.add_history(
                "lead_manager",
                "project_finished",
                f"QA: {self.state.get_snapshot()['qa_status']}"
            )

            self.logger.log(
                "========================================"
            )

            self.logger.log(
                "[SUCCESS] PROSES SELESAI."
                if qa_passed
                else "[WARNING] PROYEK MEMERLUKAN PERHATIAN."
            )

            self.logger.log(
                f"[REPORT] {report_path}"
            )

            self.logger.log(
                f"[WORKSPACE] {project_dir}"
            )

            self.logger.log(
                report
            )

        except Exception as error:

            self.state.update(
                status="failed",
                current_phase="error",
                error=str(error)
            )

            self.state.add_history(
                "system",
                "fatal_error",
                str(error)
            )

            self.logger.log(
                f"[FATAL ERROR] {error}"
            )

            self.logger.log(
                traceback.format_exc()
            )

            self.logger.log(
                "[LEAD] Proyek dihentikan. "
                "Periksa log untuk diagnosis."
            )


# ============================================================
# TEXTUAL DASHBOARD
# ============================================================

class AIManagerTUI(App):

    TITLE = "AI AUTONOMOUS CODING FACTORY"

    SUBTITLE = "LEAD MANAGER CONTROL CENTER"

    CSS = """
    Screen {
        background: #1e1e2e;
    }

    RichLog {
        background: #181825;
        color: #cdd6f4;
        margin: 1 2;
        border: solid #89b4fa;
    }

    .input-box {
        margin: 1 2;
        dock: bottom;
        height: auto;
    }

    Button {
        background: #89b4fa;
        color: #11111b;
        text-style: bold;
    }

    Button:hover {
        background: #b4befe;
    }

    Input:disabled, Button:disabled {
        background: #313244;
        color: #7f849c;
    }
    """

    BINDINGS = [
        ("q", "quit", "Keluar")
    ]

    def compose(self) -> ComposeResult:

        yield Header(
            show_clock=True
        )

        yield RichLog(
            highlight=False,
            markup=False,
            wrap=True
        )

        with Horizontal(
            classes="input-box"
        ):

            yield Input(
                placeholder="Memeriksa sistem...",
                id="user_command",
                disabled=True
            )

            yield Button(
                "Kirim ke Lead Manager",
                id="btn_submit",
                disabled=True
            )

        yield Footer()

    def on_mount(self):

        self.log_widget = self.query_one(
            RichLog
        )

        self.busy = False

        self.log_widget.write(
            "=" * 55
        )

        self.log_widget.write(
            "AI AUTONOMOUS CODING FACTORY"
        )

        self.log_widget.write(
            "LEAD MANAGER CONTROL CENTER"
        )

        self.log_widget.write(
            "=" * 55
        )

        self.log_widget.write(
            "[SYSTEM] Memeriksa konfigurasi model..."
        )

        threading.Thread(
            target=self.system_check,
            daemon=True
        ).start()

    def system_check(self):

        ready, message = check_ollama()

        self.call_from_thread(
            self.log_widget.write,
            f"[SYSTEM] {message}"
        )

        if ready:

            self.call_from_thread(
                self.enable_interface
            )

    def enable_interface(self):

        input_widget = self.query_one(
            "#user_command",
            Input
        )

        button = self.query_one(
            "#btn_submit",
            Button
        )

        input_widget.placeholder = (
            "Berikan instruksi kepada Lead Manager..."
        )

        input_widget.disabled = False
        button.disabled = False

        input_widget.focus()

        self.busy = False

        self.log_widget.write(
            "[READY] Lead Manager siap."
        )

    def log_from_thread(self, message):

        self.call_from_thread(
            self.log_widget.write,
            str(message)
        )

    def on_button_pressed(self, event):

        if event.button.id == "btn_submit":
            self.process_command()

    def on_input_submitted(self, event):

        self.process_command()

    def process_command(self):

        if self.busy:
            return

        input_widget = self.query_one(
            "#user_command",
            Input
        )

        button = self.query_one(
            "#btn_submit",
            Button
        )

        command = input_widget.value.strip()

        if not command:
            return

        self.busy = True

        self.log_widget.write("")

        self.log_widget.write(
            f"[OWNER] {command}"
        )

        self.log_widget.write(
            "[LEAD] Instruksi diterima."
        )

        input_widget.value = ""

        input_widget.disabled = True
        button.disabled = True

        def worker():

            try:

                factory = AICodingFactory(
                    self.log_from_thread
                )

                factory.execute(
                    command
                )

            except Exception as error:

                self.log_from_thread(
                    f"[SYSTEM ERROR] {error}"
                )

            finally:

                self.call_from_thread(
                    self.enable_interface
                )

        threading.Thread(
            target=worker,
            daemon=True
        ).start()


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

if __name__ == "__main__":

    print(
        "Starting AI Autonomous Coding Factory..."
    )

    app = AIManagerTUI()

    app.run()
