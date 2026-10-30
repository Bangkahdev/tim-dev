
from crewai import Task, Crew, Process

from core.task_router import TaskRouter
from core.employee_health import record_activity


class LeadManager:

    def __init__(self, agents, logger, state):

        self.agents = agents
        self.logger = logger
        self.state = state

        self.router = TaskRouter(agents)

    def log(self, message):

        self.logger.log(
            "[LEAD MANAGER] " + message
        )

    def assign_agent(self, issue):

        agent, routing = self.router.get_agent(issue)

        name = routing["agent"]

        self.log(
            f"Masalah dialihkan ke {name.upper()}"
        )

        self.state.add_history(
            "lead_manager",
            "assign_issue",
            f"Assigned to {name}: {issue[:500]}"
        )

        self.state.set_agent(
            name,
            "working",
            issue[:500]
        )

        return agent, name

    def repair_issue(self, issue):

        agent, name = self.assign_agent(issue)

        repair_task = Task(
            description=f"""
            Anda menerima tugas perbaikan dari Lead Manager.

            MASALAH:
            {issue}

            TANGGUNG JAWAB:
            1. Periksa file proyek yang relevan.
            2. Cari akar penyebab masalah.
            3. Perbaiki file yang bermasalah.
            4. Jangan merusak fitur yang sudah berjalan.
            5. Jalankan pengujian yang relevan.
            6. Laporkan perubahan yang dilakukan.

            Anda wajib menggunakan tools untuk
            membaca dan mengubah file nyata.

            Jangan mengklaim berhasil tanpa bukti.
            """,
            expected_output="""
            Laporan perbaikan:
            - Penyebab masalah
            - File yang diperbaiki
            - Perubahan kode
            - Hasil pengujian
            """,
            agent=agent
        )

        try:

            crew = Crew(
                agents=[agent],
                tasks=[repair_task],
                process=Process.sequential,
                verbose=True
            )

            result = crew.kickoff()
            record_activity(name, "completed", "Menyelesaikan tugas perbaikan.", getattr(result, "token_usage", None) or getattr(crew, "usage_metrics", None))

            self.state.set_agent(
                name,
                "completed",
                str(result)[:1000]
            )

            self.state.add_history(
                name,
                "repair_completed",
                str(result)[:2000]
            )

            self.log(
                f"{name.upper()} telah menyelesaikan tugas perbaikan."
            )

            return str(result)

        except Exception as error:

            record_activity(name, "failed", str(error))

            self.state.set_agent(
                name,
                "failed",
                str(error)
            )

            self.log(
                f"Gagal memperbaiki masalah: {error}"
            )

            raise

    def review_qa(self, qa_result):

        review_task = Task(
            description=f"""
            Anda adalah Lead Manager dan AI CTO.

            Berikut laporan QA:

            {qa_result}

            Analisis laporan ini.

            Tentukan:
            1. Apakah ada bug?
            2. Apa penyebabnya?
            3. File apa yang perlu diperbaiki?
            4. Departemen mana yang bertanggung jawab?
            5. Apakah perlu pengujian ulang?

            Format jawaban:

            STATUS: PASS atau FAIL

            ISSUES:
            - Masalah yang ditemukan

            ROOT_CAUSE:
            - Penyebab masalah

            REPAIR_PLAN:
            - Instruksi perbaikan

            Jika tidak ada masalah, tuliskan:

            STATUS: PASS
            ISSUES: NONE
            """,
            expected_output=(
                "Keputusan Lead Manager beserta "
                "diagnosis dan instruksi perbaikan."
            ),
            agent=self.agents["lead"]
        )

        crew = Crew(
            agents=[self.agents["lead"]],
            tasks=[review_task],
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()
        record_activity("lead", "completed", "Meninjau hasil QA dan menentukan tindak lanjut.", getattr(result, "token_usage", None) or getattr(crew, "usage_metrics", None))
        return str(result)

    def get_project_status(self):

        snapshot = self.state.get_snapshot()

        self.log(
            f"Status proyek: {snapshot['status']}"
        )

        for name, info in snapshot["agents"].items():

            self.log(
                f"{name}: {info['status']}"
            )

        return snapshot
