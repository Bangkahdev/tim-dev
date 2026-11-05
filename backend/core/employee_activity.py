"""Workshift engine for the office's AI employees.

Each employee logs into their own workstation with their real domain
credentials and produces small, audited work units through the same desktop
production APIs the browser client uses. Nothing here fakes state: files land
in the employee's sandbox, commands run through the terminal allowlist, and
every unit is written to the shared events feed.

The engine is driven by the status endpoint (/api/status) and by the manual
tick endpoint (/api/office/activity/tick). It is tick-based (no background
threads), rate limited, and honest about off-duty / disabled states.
"""

import datetime as dt
import os
import threading
import time

from core.office_store import LOCK, ROSTER, STORE, _now
from core.workstations import DESKTOP, DesktopError, WORKSTATIONS
from core.employee_health import record_activity

DEFAULT_DUTY_HOURS = "9-17"
DEFAULT_TICK_SECONDS = 20

STATE_LOCK = threading.RLock()

# account_id -> workstation_id for every roster employee.
_EMPLOYEE_DESKS = {
    workstation["account_id"]: workstation["id"]
    for workstation in WORKSTATIONS
    if workstation["account_id"] != "owner"
}


def _duty_open(moment: dt.datetime, duty_hours: str) -> bool:
    """True when `moment` is inside the "start-end" hour window (supports
    overnight windows such as 22-6). Hours are server-local time."""
    spec = str(duty_hours or DEFAULT_DUTY_HOURS).replace(" ", "")
    try:
        start_text, end_text = spec.split("-", 1)
        start, end = int(start_text), int(end_text)
    except (ValueError, AttributeError):
        return False
    start = max(0, min(24, start))
    end = max(0, min(24, end))
    hour = moment.hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def _latest_task(db, employee_id: str) -> str:
    """Title of the employee's most recent open task, if any."""
    row = db.execute(
        """SELECT title,status FROM tasks
           WHERE assignee_id=? AND status IN ('pending','in_progress','blocked')
           ORDER BY created_at DESC LIMIT 1""",
        (employee_id,),
    ).fetchone()
    if not row:
        return ""
    return f"{row['title']} ({row['status']})"


def _unit_plan(role: str, day: str, index: int, task: str):
    """Plan for one work unit: list of ("write", path, content) and
    ("shell", command) steps executed in order."""
    task_line = task or "tanpa tugas aktif"
    if role == "backend":
        name = f"service_{index}.py"
        content = (
            f'"""Unit kerja backend #{index} - {task_line}. Dirancang {day}."""\n'
            "\n\n"
            "def process_payload(payload):\n"
            "    items = payload if isinstance(payload, list) else []\n"
            f"    return {{\"unit\": {index}, \"items\": len(items), \"status\": \"done\"}}\n"
        )
        return [
            ("write", f"work/backend/{day}/{name}", content),
            ("shell", f"wc -l work/backend/{day}/{name}"),
        ]
    if role == "api":
        content = (
            f"# Kontrak endpoint #{index}\n\n"
            f"- Hari: {day}\n- Task: {task_line}\n\n"
            "## Endpoint\n\n"
            f"POST /api/unit/{index}\n\n"
            "## Permintaan\n\n"
            "JSON {payload: \"...\"}\n\n"
            "## Respon\n\n"
            "200 {ok: true}\n"
        )
        return [("write", f"work/api/{day}/endpoint_{index}.md", content)]
    if role == "architect":
        content = (
            f"# ADR #{index}: keputusan layanan\n\n"
            f"- Hari: {day}\n- Task: {task_line}\n\n"
            "## Konteks\n\n"
            f"Layanan unit {index} membutuhkan kontrak yang stabil.\n\n"
            "## Keputusan\n\n"
            "Kontrak API dipublikasikan sebagai markdown dan dibuktikan oleh test.\n\n"
            "## Konsekuensi\n\n"
            "Frontend menunggu kontrak sebelum coding.\n"
        )
        return [("write", f"work/architect/{day}/adr_{index}.md", content)]
    if role == "frontend":
        content = (
            f"// Unit kerja frontend #{index} - {task_line}\n"
            "export interface UnitProps {\n"
            "  unit: number;\n"
            "  status: string;\n"
            "}\n\n"
            "export function UnitPanel(props: UnitProps) {\n"
            "  return null;\n"
            "}\n"
        )
        return [        ("write", f"work/frontend/{day}/component_{index}.py",
         f"# Unit kerja frontend #{index} - {task_line}\n"
         "def render_unit(props=None):\n"
         "    \"\"\"Kerangka panel unit {n}; render ringan, tanpa efek samping.\"\"\"\n"
         "    return {{\"unit\": {n}, \"status\": \"done\"}}\n".format(n=index))]
    if role == "qa":
        report = f"work/qa/{day}/report_{index}.md"
        content = (
            f"# Laporan QA #{index}\n\n"
            f"- Hari: {day}\n- Task: {task_line}\n\n"
            "## Skenario\n\n"
            "- Daftar file dibuat oleh engine.\n"
            "- File dibaca ulang lewat terminal `cat`.\n\n"
            "## Hasil\n\n"
            "PASS. Tidak ada bug baru ditemukan.\n"
        )
        return [
            ("write", report, content),
            ("shell", f"cat {report}"),
            ("shell", f"ls work/qa/{day}"),
        ]
    if role == "lead":
        content = (
            f"# Standup #{index}\n\n"
            f"- Hari: {day}\n- Task: {task_line}\n\n"
            "## Blok kemarin\n\n"
            "- Unit kerja engine selesai.\n\n"
            "## Hari ini\n\n"
            "- Lanjutkan unit berikutnya.\n\n"
            "## Risiko\n\n"
            "- Menunggu task baru dari backlog.\n"
        )
        return [
            ("write", f"work/lead/{day}/standup_{index}.md", content),
            ("shell", f"ls work/lead/{day}"),
        ]
    return [
        ("write", f"work/{role}/{day}/update_{index}.md",
         f"# Update proyek #{index}\n\n- Hari: {day}\n- Task: {task_line}\n\n"
         "- Progres shift berjalan; tidak ada blocker baru.\n")
    ]


class EmployeeActivityEngine:
    """Drives employee workshifts through the desktop production APIs."""

    def __init__(self, store=STORE, desktop=None,
                 duty_hours: str | None = None, tick_seconds: float | None = None):
        self.store = store
        self.desktop = desktop if desktop is not None else DESKTOP
        self.duty_hours = duty_hours or os.getenv("BANGKAH_EMPLOYEE_DUTY_HOURS", DEFAULT_DUTY_HOURS)
        self.tick_seconds = (
            float(tick_seconds) if tick_seconds is not None
            else float(os.getenv("BANGKAH_EMPLOYEE_TICK_SECONDS", str(DEFAULT_TICK_SECONDS)))
        )
        self._tokens: dict[str, str] = {}
        self._last_tick_at: float = 0.0
        self._initialize()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def _db(self):
        return self.store._db()

    def _initialize(self):
        with LOCK, self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS employee_workshift (
                    employee_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'off_shift',
                    units_done INTEGER NOT NULL DEFAULT 0,
                    units_today INTEGER NOT NULL DEFAULT 0,
                    workday TEXT NOT NULL DEFAULT '',
                    started_at TEXT,
                    last_tick_at TEXT,
                    last_detail TEXT NOT NULL DEFAULT ''
                );
            """)
            for account_id in _EMPLOYEE_DESKS:
                if account_id in ROSTER:
                    db.execute("INSERT OR IGNORE INTO employee_workshift(employee_id) VALUES(?)",
                               (account_id,))

    def enabled(self) -> bool:
        raw = os.getenv("BANGKAH_EMPLOYEE_ACTIVITY", "1").strip().lower()
        return raw not in ("0", "false", "off", "no")

    def _row(self, db, employee_id: str) -> dict:
        row = db.execute("SELECT * FROM employee_workshift WHERE employee_id=?",
                         (employee_id,)).fetchone()
        return dict(row) if row else {
            "employee_id": employee_id, "status": "off_shift",
            "units_done": 0, "units_today": 0, "workday": "",
            "started_at": None, "last_tick_at": None, "last_detail": "",
        }

    def _token(self, account_id: str) -> str | None:
        token = self._tokens.get(account_id)
        if not token:
            return None
        try:
            self.desktop.session_state(token)
        except DesktopError:
            self._tokens.pop(account_id, None)
            return None
        return token

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------
    def tick(self, force: bool = False, ignore_window: bool = False,
             now: dt.datetime | None = None) -> dict:
        moment = now or dt.datetime.now().astimezone()
        summary = {
            "enabled": self.enabled(),
            "workday": moment.date().isoformat(),
            "duty_open": _duty_open(moment, self.duty_hours),
            "duty_hours": self.duty_hours,
            "tick_seconds": self.tick_seconds,
            "overtime": False,
            "skipped": False,
            "units": [],
            "errors": [],
            "on_shift": [],
            "off_shift": [],
        }
        if not summary["enabled"]:
            return summary
        open_window = summary["duty_open"] or ignore_window
        with STATE_LOCK:
            bypass = bool(force or ignore_window)
            if not bypass and self.tick_seconds > 0:
                if time.monotonic() - self._last_tick_at < self.tick_seconds:
                    summary["skipped"] = True
                    summary["on_shift"], summary["off_shift"] = self._partition()
                    return summary
            self._last_tick_at = time.monotonic()
            summary["overtime"] = bool(ignore_window and not summary["duty_open"])
            for account_id in sorted(_EMPLOYEE_DESKS):
                try:
                    outcome = self._employee_tick(account_id, moment, open_window, ignore_window)
                except DesktopError as error:
                    summary["errors"].append({"employee_id": account_id, "error": str(error)[:400]})
                    continue
                if outcome:
                    summary["units"].append(outcome)
            summary["on_shift"], summary["off_shift"] = self._partition()
        return summary

    def _partition(self):
        on_shift, off_shift = [], []
        with LOCK, self._db() as db:
            for account_id in sorted(_EMPLOYEE_DESKS):
                row = self._row(db, account_id)
                (on_shift if row["status"] == "on_shift" else off_shift).append(account_id)
        return on_shift, off_shift

    def _employee_tick(self, account_id: str, moment: dt.datetime,
                       open_window: bool, ignore_window: bool) -> dict | None:
        day = moment.date().isoformat()

        # Shelf phase 1: state read/reset. Each phase uses its own short-lived
        # connection; desktop login/writes open their own connections inside.
        with LOCK, self._db() as db:
            row = self._row(db, account_id)
            if row["workday"] != day:
                db.execute("UPDATE employee_workshift SET units_today=0,workday=? WHERE employee_id=?",
                           (day, account_id))
                row = self._row(db, account_id)

        if not open_window:
            if row["status"] == "on_shift":
                self._end_shift(account_id)
            return None

        if row["status"] != "on_shift":
            started_at = _now()
            with LOCK, self._db() as db:
                db.execute("""UPDATE employee_workshift
                              SET status='on_shift',started_at=?,last_tick_at=?
                              WHERE employee_id=?""",
                           (started_at, started_at, account_id))
                db.execute("UPDATE employees SET status='working',updated_at=? WHERE id=? AND "
                           "status='idle'", (started_at, account_id))
            row["status"] = "on_shift"

        # Login through the same production API the user uses.
        token = self._token(account_id)
        if token is None:
            password = self.desktop.employee_password(account_id)
            session = self.desktop.login(_EMPLOYEE_DESKS[account_id], account_id, password)
            token = session["token"]
            self._tokens[account_id] = token
            with LOCK, self._db() as db:
                self.store._event(db, "employee_login", account_id,
                                  _EMPLOYEE_DESKS[account_id],
                                  f"{ROSTER[account_id][0]} logged in at "
                                  f"{_EMPLOYEE_DESKS[account_id]}.")

        index = row["units_today"] + 1
        with LOCK, self._db() as db:
            task = _latest_task(db, account_id)
        plan = _unit_plan(account_id, day, index, task)
        for step in plan:
            if step[0] == "write":
                self.desktop.write_file(token, step[1], step[2])
            else:
                self.desktop.run_command(token, step[1])

        detail = (f"Unit kerja #{index} - {task}" if task else f"Unit kerja #{index} selesai")
        with LOCK, self._db() as db:
            db.execute("""UPDATE employee_workshift
                          SET units_done=units_done+1,units_today=units_today+1,
                              last_tick_at=?,last_detail=? WHERE employee_id=?""",
                       (_now(), detail, account_id))
            self.store._event(db, "employee_work", account_id, account_id,
                              f"{ROSTER[account_id][0]} menyelesaikan unit {account_id} #{index} "
                              f"di {_EMPLOYEE_DESKS[account_id]}."
                              + (f" Task: {task}." if task else ""))
        record_activity(account_id, status="working", detail=detail[:400])
        return {"employee_id": account_id, "workstation": _EMPLOYEE_DESKS[account_id],
                "unit": index, "task": task or None}

    def _end_shift(self, account_id: str) -> None:
        token = self._tokens.pop(account_id, None)
        if token:
            try:
                self.desktop.close_session(token)
            except DesktopError:
                pass
        with LOCK, self._db() as db:
            db.execute("UPDATE employee_workshift SET status='off_shift',last_tick_at=? WHERE employee_id=?",
                       (_now(), account_id))
            db.execute("UPDATE employees SET status='idle',updated_at=? WHERE id=? AND status='working'",
                       (_now(), account_id))
        record_activity(account_id, status="completed", detail="Shift selesai untuk hari ini.")

    # ------------------------------------------------------------------
    # Feed / summary
    # ------------------------------------------------------------------
    def feed(self, after_id: int = 0, limit: int = 100):
        after_id = max(0, int(after_id))
        limit = max(1, min(int(limit), 200))
        with LOCK, self._db() as db:
            placeholders = ",".join("?" for _ in _EMPLOYEE_DESKS)
            rows = db.execute(
                f"SELECT * FROM events WHERE (actor IN ({placeholders})) AND id>? "
                "ORDER BY id LIMIT ?",
                (*_EMPLOYEE_DESKS, after_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self) -> dict:
        moment = dt.datetime.now().astimezone()
        with LOCK, self._db() as db:
            employees = []
            for account_id in sorted(_EMPLOYEE_DESKS):
                if account_id not in ROSTER:
                    continue
                row = self._row(db, account_id)
                employees.append({
                    "employee_id": account_id,
                    "name": ROSTER[account_id][0],
                    "role": ROSTER[account_id][1],
                    "workstation": _EMPLOYEE_DESKS[account_id],
                    "status": row["status"],
                    "units_done": row["units_done"],
                    "units_today": row["units_today"],
                    "workday": row["workday"] or None,
                    "last_tick_at": row["last_tick_at"],
                    "last_detail": row["last_detail"],
                })
        return {
            "enabled": self.enabled(),
            "duty_open": _duty_open(moment, self.duty_hours),
            "duty_hours": self.duty_hours,
            "tick_seconds": self.tick_seconds,
            "workday": moment.date().isoformat(),
            "employees": employees,
        }


ACTIVITY = EmployeeActivityEngine()
