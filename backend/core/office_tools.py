"""Validated action layer used by the API now and agents in the next phase."""
from .office_store import STORE, BASE_DIR
from datetime import datetime


class OfficeTools:
    def __init__(self, store=STORE):
        self.store = store

    def execute(self, action: str, arguments: dict, actor="owner"):
        args = arguments if isinstance(arguments, dict) else {}
        if action == "move_employee":
            return self.store.move_employee(args.get("employee_id", ""), args.get("room_id", ""), actor)
        if action == "move_all_employees":
            return self.store.move_all(args.get("room_id", ""), actor)
        if action == "create_task":
            return self.store.create_task(args.get("title", ""), args.get("description", ""),
                                          args.get("assignee_id"), args.get("priority", "normal"), actor)
        if action == "update_task":
            return self.store.update_task(args.get("task_id", ""), args.get("status", ""), actor)
        if action == "create_meeting":
            return self.store.create_meeting(args.get("title", ""), args.get("attendee_ids", []),
                                             args.get("agenda", ""), args.get("room_id", "meeting"), actor)
        if action == "generate_weekly_report":
            days = args.get("days", 7)
            if not isinstance(days, int) or not 1 <= days <= 90:
                raise ValueError("Rentang laporan harus 1 sampai 90 hari.")
            report = self.store.weekly_report(days)
            report_dir = BASE_DIR / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            filename = f"weekly-report-{datetime.now().astimezone():%Y%m%d-%H%M%S}.md"
            lines = [
                f"# Laporan Aktivitas {days} Hari Terakhir",
                "",
                f"Dibuat: {report['generated_at']}",
                f"Mulai: {report['since']}",
                "",
                "## Ringkasan",
                f"- Aktivitas tercatat: {report['summary']['events']}",
                f"- Tugas dibuat: {report['summary']['tasks_created']}",
                "- Status tugas: " + (", ".join(f"{k}: {v}" for k, v in report['summary']['task_status'].items()) or "Belum ada"),
                "",
                "## Daftar Tugas",
            ]
            if report["tasks"]:
                lines.extend(f"- **{t['title']}** — {t['status']} (assignee: {t['assignee_id'] or 'belum ditentukan'})" for t in report["tasks"])
            else:
                lines.append("Belum ada tugas pada periode ini.")
            lines += ["", "## Aktivitas"]
            if report["events"]:
                lines.extend(f"- {e['created_at']} · {e['actor']} · {e['detail']}" for e in report["events"])
            else:
                lines.append("Belum ada aktivitas pada periode ini.")
            path = report_dir / filename
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            report["report_path"] = str(path)
            return report
        raise ValueError("Aksi kantor tidak tersedia.")


TOOLS = OfficeTools()
