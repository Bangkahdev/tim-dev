"""Aplikasi HTTP/WebSocket Bangkah Company Simulator.

Menjaga kompatibilitas endpoint kantor lama sambil menambahkan API domain:
organisasi, task, rapat, persetujuan, paper, audit, usage, dan event realtime.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import (
    audit, auth, chat, conversation, db, emailer, events, knowledge, meetings,
    monitor, org, papers, projects as project_service, reports, secretary,
    settings, tasks, tools, website,
)
from .db import fetch_all, fetch_one, json_dump, json_load, now

WEB_DIR = settings.BASE_DIR / "web"
RUN_LOCK = threading.Lock()
LLM_LOCK = threading.Lock()
ACTIVE = {"running": False, "command": "", "started_at": None, "error": None}
EMPLOYEE_CHAT_ACTIVE: dict[str, dict[str, Any]] = {}
STATE_LOCK = threading.Lock()
EMAIL_SYNC_STOP = threading.Event()
_OLLAMA_CACHE: dict[str, Any] = {"checked_at": 0.0, "result": [False, "Belum diperiksa."]}


def _init() -> None:
    db.init_db(db.active_path())


_init()


def _email_sync_worker() -> None:
    """Tarik email masuk secara berkala (EML-02) bila akun dikonfigurasi."""
    interval = max(60, settings.EMAIL_SYNC_MINUTES * 60)
    while not EMAIL_SYNC_STOP.wait(interval):
        if not settings.EMAIL_IMAP_HOST:
            continue
        try:
            with db.transaction() as conn:
                emailer.sync_inbox(conn)
        except Exception:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    _init()
    events.attach_loop(asyncio.get_running_loop())
    EMAIL_SYNC_STOP.clear()
    worker = None
    if settings.EMAIL_IMAP_HOST and settings.EMAIL_SYNC_MINUTES > 0:
        worker = threading.Thread(target=_email_sync_worker, name="email-sync", daemon=True)
        worker.start()
    try:
        yield
    finally:
        EMAIL_SYNC_STOP.set()


app = FastAPI(title="Bangkah Company Simulator", version="1.0.0", lifespan=lifespan)


# ------------------------------------------------------------
# Middleware dan penanganan error
# ------------------------------------------------------------

@app.middleware("http")
async def guard_requests(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and int(length) > settings.MAX_REQUEST_BYTES:
        return JSONResponse({"error": "Permintaan terlalu besar."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _error_response(error: Exception) -> JSONResponse:
    status = getattr(error, "status_code", 400)
    return JSONResponse({"error": str(error)}, status_code=status)


async def _domain_error(_: Request, error: Exception):
    if isinstance(error, tools.PermissionDenied):
        actor = getattr(error, "actor", "unknown")
        tool_name = getattr(error, "tool_name", "unknown")
        try:
            with db.transaction() as conn:
                audit.log(
                    conn, actor=actor, actor_kind="employee", action="tool.denied",
                    detail=json_dump({"tool": tool_name, "source": "http"}),
                    ref_type="tool", ref_id=tool_name,
                )
        except Exception:
            pass
    return _error_response(error)


async def _value_error(_: Request, error: Exception):
    return JSONResponse({"error": str(error)}, status_code=400)


for _error_type in (
    tasks.TaskError, papers.PaperError, tools.ToolError,
    meetings.MeetingError, monitor.MonitorError,
    emailer.EmailError, website.WebsiteError, knowledge.KnowledgeError,
):
    app.add_exception_handler(_error_type, _domain_error)
app.add_exception_handler(ValueError, _value_error)


# ------------------------------------------------------------
# Autentikasi sesi Owner
# ------------------------------------------------------------

def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def require_owner(request: Request) -> str:
    token = _bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="Sesi Owner diperlukan.")
    with db.transaction() as conn:
        row = auth.verify_token(conn, token)
    if not row:
        raise HTTPException(status_code=401, detail="Sesi Owner tidak sah atau kedaluwarsa.")
    return token


def _is_local(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


class SessionRequest(BaseModel):
    api_auth_token: str | None = None


class OwnerSessionResponse(BaseModel):
    token: str
    expires_at: str
    hours: int


@app.post("/api/session", response_model=OwnerSessionResponse)
def create_session(request: Request, payload: SessionRequest | None = None):
    if not _is_local(request):
        raise HTTPException(status_code=403, detail="Sesi lokal hanya dapat diterbitkan dari mesin Owner.")
    candidate = payload.api_auth_token if payload else None
    if not auth.token_matches_config(candidate):
        raise HTTPException(status_code=401, detail="Token API tidak sah.")
    with db.transaction() as conn:
        session = auth.create_session(conn)
        audit.log(
            conn, actor="owner", actor_kind="owner", action="owner.session_issued",
            detail="Sesi Owner diterbitkan untuk klien lokal.",
        )
    return session


@app.post("/api/session/logout")
def logout(token: str = Depends(require_owner)):
    with db.transaction() as conn:
        auth.revoke(conn, token)
        audit.log(conn, actor="owner", actor_kind="owner", action="owner.session_revoked", detail="Sesi dicabut.")
    return {"ok": True}


# ------------------------------------------------------------
# Status kantor (kompatibel dengan UI lama)
# ------------------------------------------------------------

def _cached_ollama() -> list[Any]:
    with STATE_LOCK:
        if settings.env_bool("BANGKAH_SKIP_MODEL_CHECK"):
            return [False, "Pemeriksaan model dilewati."]
        if time.monotonic() - _OLLAMA_CACHE["checked_at"] > 20:
            try:
                from main import check_ollama

                _OLLAMA_CACHE["result"] = list(check_ollama())
            except Exception as error:  # pragma: no cover - lingkungan tanpa model
                _OLLAMA_CACHE["result"] = [False, f"Pemeriksaan model gagal: {error}"]
            _OLLAMA_CACHE["checked_at"] = time.monotonic()
        return _OLLAMA_CACHE["result"]


def _projects() -> list[dict[str, Any]]:
    result = []
    for state_file in settings.WORKSPACE_DIR.glob("*/.factory/state.json"):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            state["directory"] = str(state_file.parent.parent)
            result.append(state)
        except (OSError, json.JSONDecodeError):
            continue
    result.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return result


def _activity(limit: int = 120) -> list[str]:
    path = settings.BASE_DIR / "logs" / "factory.log"
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except OSError:
        return []


def _health() -> dict[str, Any]:
    try:
        from core.employee_health import get_health_snapshot

        return get_health_snapshot()
    except Exception:
        return {"employees": {}}


@app.get("/api/status")
def status():
    projects = _projects()
    with db.connection() as conn:
        summary = _company_summary(conn)
        employee_rows = org.employee_states(conn)
        tray = papers.tray_summary(conn)
        summary["pending_papers"] = tray["pending"]
        summary["paper_tray"] = {
            "limit": tray["limit"],
            "overflow": tray["overflow"],
        }
        papers_list = tray["papers"]
    with STATE_LOCK:
        active = dict(ACTIVE)
        employee_chats = dict(EMPLOYEE_CHAT_ACTIVE)
    return {
        "ollama": _cached_ollama(),
        "active": active,
        "projects": projects[:10],
        "project": projects[0] if projects else None,
        "health": _health(),
        "employee_chats": employee_chats,
        "activity": _activity(),
        "summary": summary,
        "employees": employee_rows,
        "papers": papers_list,
        "pending_papers": tray["pending"],
        "paper_tray": {
            "limit": tray["limit"],
            "overflow": tray["overflow"],
        },
        "server_time": now(),
    }


def _company_summary(conn) -> dict[str, Any]:
    from .orchestrator import company_status

    return company_status(conn)


@app.get("/api/command-center")
def command_center():
    with db.connection() as conn:
        summary = _company_summary(conn)
        summary["tasks_overdue"] = tasks.overdue_tasks(conn)
        project_rows = fetch_all(conn, "SELECT * FROM projects ORDER BY created_at DESC")
        for row in project_rows:
            counts = fetch_one(
                conn,
                "SELECT COUNT(*) AS total, SUM(status = 'COMPLETED') AS done FROM tasks WHERE project_id = ?",
                (row["id"],),
            )
            row["task_total"] = int(counts["total"] or 0) if counts else 0
            row["task_done"] = int(counts["done"] or 0) if counts else 0
        usage = reports.usage_summary(conn)
        tray = papers.tray_summary(conn)
        summary["pending_papers"] = tray["pending"]
        return {
            "summary": summary,
            "papers": tray["papers"],
            "paper_tray": {
                "pending": tray["pending"],
                "limit": tray["limit"],
                "overflow": tray["overflow"],
                "overflow_papers": tray["overflow_papers"],
                "summary_sheet": tray["summary_sheet"],
            },
            "projects": project_rows,
            "tasks": tasks.list_tasks(conn, limit=200),
            "employees": org.employee_states(conn),
            "usage": usage["by_employee"],
            "usage_summary": usage,
            "division_performance": reports.division_performance(conn),
            "activity": reports.activity(conn, limit=30),
            "generated_at": now(),
        }


# ------------------------------------------------------------
# Organisasi
# ------------------------------------------------------------

class DepartmentCreate(BaseModel):
    name: str
    manager_id: str | None = None
    room: str = ""


class EmployeeCreate(BaseModel):
    name: str
    title: str
    department_id: str
    manager_id: str | None = None
    model: str | None = None
    skills: list[str] = []
    tool_permissions: list[str] = []
    room: str = ""
    desk: str = ""
    avatar: str = "🧑‍💼"


class EmployeeUpdate(BaseModel):
    name: str | None = None
    title: str | None = None
    department_id: str | None = None
    manager_id: str | None = None
    model: str | None = None
    skills: list[str] | None = None
    tool_permissions: list[str] | None = None
    room: str | None = None
    desk: str | None = None
    avatar: str | None = None
    active: bool | None = None


@app.get("/api/departments")
def departments():
    with db.connection() as conn:
        return {"departments": org.list_departments(conn)}


@app.post("/api/departments", status_code=201)
def create_department(payload: DepartmentCreate, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        department = org.create_department(conn, name=payload.name, manager_id=payload.manager_id, room=payload.room)
    return {"department": department}


@app.get("/api/employees")
def employees(active_only: bool = False):
    with db.connection() as conn:
        return {"employees": org.list_employees(conn, active_only=active_only)}


@app.post("/api/employees", status_code=201)
def create_employee(payload: EmployeeCreate, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        employee = org.create_employee(conn, **payload.model_dump())
    return {"employee": employee}


@app.patch("/api/employees/{employee_id}")
def update_employee(employee_id: str, payload: EmployeeUpdate, _: str = Depends(require_owner)):
    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    with db.transaction() as conn:
        employee = org.update_employee(conn, employee_id, changes)
    return {"employee": employee}


class EmployeeStateRequest(BaseModel):
    room: str | None = None
    activity: str = "idle"
    source: str = "task"


@app.post("/api/employees/{employee_id}/state")
def employee_state(employee_id: str, payload: EmployeeStateRequest, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        state = org.set_employee_state(conn, employee_id, room=payload.room, activity=payload.activity, source=payload.source)
    return {"state": state}


@app.get("/api/employees/{employee_id}/monitor")
def employee_monitor(employee_id: str, _: str = Depends(require_owner)):
    with db.connection() as conn:
        return {"monitor": monitor.employee_monitor(conn, employee_id)}


# ------------------------------------------------------------
# Proyek dan task
# ------------------------------------------------------------

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    assignee: str | None = None
    project_id: str | None = None
    priority: str = "normal"
    kind: str = "code"
    depends_on: list[str] = []
    acceptance_criteria: list[str] = []
    due_at: str | None = None


class TaskTransitionRequest(BaseModel):
    to_status: str
    actor: str = "owner"
    actor_kind: str = "owner"
    note: str = ""
    evidence: dict[str, Any] | None = None


class ProjectCreate(BaseModel):
    name: str
    department_id: str = "engineering"
    deliverable: str = ""


class ProjectComplete(BaseModel):
    note: str = ""
    force: bool = False


@app.get("/api/projects")
def projects(status: str | None = None, department_id: str | None = None, limit: int = 200):
    with db.connection() as conn:
        rows = project_service.list_projects(conn, status=status, department_id=department_id, limit=limit)
        active = project_service.active_count(conn)
    return {
        "projects": rows,
        "active": active,
        "max_concurrent": settings.MAX_CONCURRENT_PROJECTS,
    }


@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectCreate, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        result = tools.execute(
            conn, actor="owner", tool_name="create_project",
            args={"name": payload.name, "department_id": payload.department_id, "deliverable": payload.deliverable},
        )
    return result


@app.post("/api/projects/{project_id}/request-start", status_code=201)
def request_project_start(project_id: str, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        try:
            return project_service.request_start(conn, project_id, requester="owner")
        except project_service.ProjectError as error:
            raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@app.post("/api/projects/{project_id}/complete")
def complete_project(project_id: str, payload: ProjectComplete | None = None, _: str = Depends(require_owner)):
    body = payload or ProjectComplete()
    with db.transaction() as conn:
        try:
            return project_service.complete_project(
                conn, project_id, actor="owner", note=body.note, force=body.force
            )
        except project_service.ProjectError as error:
            raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@app.post("/api/projects/{project_id}/fail")
def fail_project(project_id: str, payload: ProjectComplete | None = None, _: str = Depends(require_owner)):
    body = payload or ProjectComplete()
    with db.transaction() as conn:
        try:
            return project_service.fail_project(conn, project_id, actor="owner", reason=body.note)
        except project_service.ProjectError as error:
            raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@app.get("/api/projects/{project_id}/report")
def project_report(project_id: str):
    with db.connection() as conn:
        try:
            markdown = reports.project_markdown(conn, project_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
    return {"project_id": project_id, "markdown": markdown}


@app.post("/api/projects/{project_id}/report/export")
def export_project_report(project_id: str, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        try:
            return reports.export_project(conn, project_id, actor="owner")
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/tasks")
def list_tasks(
    status: str | None = None,
    assignee: str | None = None,
    project_id: str | None = None,
    limit: int = 100,
):
    with db.connection() as conn:
        rows = tasks.list_tasks(conn, status=status, assignee=assignee, project_id=project_id, limit=limit)
        overdue = {row["id"] for row in tasks.overdue_tasks(conn)}
    for row in rows:
        row["overdue"] = row["id"] in overdue
    return {"tasks": rows}


@app.post("/api/tasks", status_code=201)
def create_task(payload: TaskCreate, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        task = tasks.create_task(conn, created_by="owner", actor_kind="owner", **payload.model_dump())
    return {"task": task}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    with db.connection() as conn:
        task = tasks.get_task(conn, task_id)
        transitions = fetch_all(
            conn, "SELECT * FROM task_transitions WHERE task_id = ? ORDER BY id ASC", (task_id,)
        )
    return {"task": task, "transitions": transitions}


@app.post("/api/tasks/{task_id}/transition")
def transition_task(task_id: str, payload: TaskTransitionRequest, _: str = Depends(require_owner)):
    kind = payload.actor_kind
    if payload.actor == "owner":
        kind = "owner"
    with db.transaction() as conn:
        task = tasks.transition(
            conn,
            task_id=task_id,
            to_status=payload.to_status,
            actor=payload.actor,
            actor_kind=kind,
            note=payload.note,
            evidence=payload.evidence,
        )
    return {"task": task}


# ------------------------------------------------------------
# Rapat
# ------------------------------------------------------------

class MeetingCreate(BaseModel):
    title: str
    agenda: str = ""
    participants: list[str] = []
    room: str = "ruang_rapat"
    scheduled_at: str | None = None
    run_now: bool = False
    rounds: int | None = None


class MeetingInterjection(BaseModel):
    content: str


@app.get("/api/meetings")
def list_meetings():
    with db.connection() as conn:
        rows = fetch_all(conn, "SELECT * FROM meetings ORDER BY COALESCE(scheduled_at, created_at) ASC")
    for row in rows:
        row["participants"] = json_load(row.get("participants"), [])
        row["transcript"] = json_load(row.get("transcript"), [])
        row["decisions"] = json_load(row.get("decisions"), [])
    return {"meetings": rows}


@app.get("/api/meetings/{meeting_id}")
def meeting_detail(meeting_id: str):
    with db.connection() as conn:
        row = fetch_one(conn, "SELECT * FROM meetings WHERE id = ?", (meeting_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Rapat tidak ditemukan.")
    row["participants"] = json_load(row.get("participants"), [])
    row["transcript"] = json_load(row.get("transcript"), [])
    row["decisions"] = json_load(row.get("decisions"), [])
    return {"meeting": row}


@app.post("/api/meetings", status_code=201)
def create_meeting(payload: MeetingCreate, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        result = tools.execute(conn, actor="owner", tool_name="create_meeting", args=payload.model_dump())
    return result


@app.post("/api/meetings/{meeting_id}/run")
def run_meeting(meeting_id: str, rounds: int | None = None, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        result = tools.execute(
            conn, actor="owner", tool_name="run_meeting",
            args={"meeting_id": meeting_id, "rounds": rounds},
        )
    return result


@app.post("/api/meetings/{meeting_id}/interject")
def interject_meeting(meeting_id: str, payload: MeetingInterjection, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        meeting = meetings.interject(conn, meeting_id, payload.content, actor="owner")
    return {"meeting": meeting}


# ------------------------------------------------------------
# Persetujuan dan Paper
# ------------------------------------------------------------

class PaperDecision(BaseModel):
    decision: str
    note: str = ""


class PaperRevise(BaseModel):
    payload: dict[str, Any]
    summary: str


@app.get("/api/papers")
def list_papers(delivery_status: str | None = None, tray_only: bool = False, limit: int = 100):
    with db.connection() as conn:
        if tray_only:
            tray = papers.tray_summary(conn, limit=limit)
            return {
                "papers": tray["papers"],
                "pending": tray["pending"],
                "limit": tray["limit"],
                "overflow": tray["overflow"],
                "overflow_papers": tray["overflow_papers"],
                "summary_sheet": tray["summary_sheet"],
            }
        rows = papers.list_papers(conn, delivery_status=delivery_status, limit=limit)
        pending = papers.pending_count(conn)
    return {"papers": rows, "pending": pending}


@app.get("/api/papers/{paper_id}")
def paper_detail(paper_id: str):
    with db.connection() as conn:
        paper = papers.get_paper(conn, paper_id)
        pdf = papers.pdf_path(conn, paper_id)
        approval = papers.get_approval(conn, paper["approval_id"]) if paper.get("approval_id") else None
    paper["pdf_path"] = str(pdf) if pdf else None
    paper["approval"] = approval
    return {"paper": paper}


@app.post("/api/papers/{paper_id}/print")
def print_paper(paper_id: str, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        result = papers.print_paper(conn, paper_id, actor="owner")
    return result


@app.post("/api/papers/{paper_id}/deliver")
def deliver_paper(paper_id: str, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        paper = papers.deliver_paper(conn, paper_id, actor="owner")
    return {"paper": paper}


@app.post("/api/papers/{paper_id}/decision")
def decide_paper(paper_id: str, payload: PaperDecision, _: str = Depends(require_owner)):
    failure: Exception | None = None
    paper = None
    with db.transaction() as conn:
        try:
            paper = papers.decide_paper(
                conn, paper_id, decision=payload.decision, actor="owner", actor_kind="owner", note=payload.note
            )
        except papers.PaperError as error:
            failure = error
    if failure:
        raise HTTPException(status_code=getattr(failure, "status_code", 409), detail=str(failure))
    _reflect_decision(paper)
    execution = _execute_approval(paper.get("approval_id")) if paper["review_status"] == "APPROVED" else None
    return {"paper": paper, "execution": execution}


@app.post("/api/papers/{paper_id}/revise", status_code=201)
def revise_paper(paper_id: str, payload: PaperRevise, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        old = papers.get_paper(conn, paper_id)
        old_approval = papers.get_approval(conn, old["approval_id"]) if old.get("approval_id") else None
        paper = papers.revise_paper(conn, paper_id, payload=payload.payload, summary=payload.summary, actor=old["creator"])
        if old_approval and paper.get("approval_id"):
            if old_approval["type"] == "email":
                emailer.reattach_revision(conn, old["approval_id"], paper["approval_id"], payload.payload)
            elif old_approval["type"] == "website":
                website.reattach_revision(conn, old["approval_id"], paper["approval_id"], payload.payload)
        papers.print_paper(conn, paper["id"], actor=old["creator"])
        paper = papers.deliver_paper(conn, paper["id"], actor=old["creator"])
    return {"paper": paper}


@app.get("/api/papers/{paper_id}/pdf")
def paper_pdf(paper_id: str, _: str = Depends(require_owner)):
    with db.connection() as conn:
        path = papers.pdf_path(conn, paper_id)
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="PDF belum tersedia.")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.get("/api/approvals")
def approvals():
    with db.connection() as conn:
        rows = fetch_all(
            conn,
            """
            SELECT a.*, p.id AS paper_id, p.delivery_status, p.review_status
            FROM approvals a LEFT JOIN papers p ON p.approval_id = a.id
            ORDER BY a.created_at DESC LIMIT 200
            """,
        )
    for row in rows:
        row["payload"] = json_load(row.get("payload"), {})
    return {"approvals": rows}


@app.post("/api/approvals/{approval_id}/approve")
def approve(approval_id: str, payload: PaperDecision | None = None, _: str = Depends(require_owner)):
    return _decide_approval(approval_id, "APPROVED", payload.note if payload else "")


@app.post("/api/approvals/{approval_id}/reject")
def reject(approval_id: str, payload: PaperDecision | None = None, _: str = Depends(require_owner)):
    return _decide_approval(approval_id, "REJECTED", payload.note if payload else "")


def _decide_approval(approval_id: str, decision: str, note: str) -> dict[str, Any]:
    with db.connection() as conn:
        row = fetch_one(conn, "SELECT id FROM papers WHERE approval_id = ? ORDER BY version DESC LIMIT 1", (approval_id,))
    if not row:
        raise HTTPException(status_code=409, detail="Persetujuan ini tidak memiliki dokumen proposal (Paper).")
    failure: Exception | None = None
    paper = None
    with db.transaction() as conn:
        try:
            paper = papers.decide_paper(conn, row["id"], decision=decision, actor="owner", actor_kind="owner", note=note)
        except papers.PaperError as error:
            failure = error
    if failure:
        raise HTTPException(status_code=getattr(failure, "status_code", 409), detail=str(failure))
    _reflect_decision(paper)
    execution = _execute_approval(paper.get("approval_id")) if paper["review_status"] == "APPROVED" else None
    return {"paper": paper, "execution": execution}


def _reflect_decision(paper: dict[str, Any]) -> None:
    """Cerminkan penolakan/revisi ke outbox domain, bukan hanya ke Paper."""
    approval_id = paper.get("approval_id")
    review = paper.get("review_status")
    if not approval_id or review not in ("REJECTED", "REVISION_REQUESTED"):
        return
    with db.transaction() as conn:
        emailer.set_status_by_approval(conn, approval_id, review)
        website.set_status_by_approval(conn, approval_id, review)


def _execute_approval(approval_id: str | None) -> dict[str, Any] | None:
    """Pekerja outbox: eksekusi aksi eksternal setelah persetujuan Owner (APR-10)."""
    if not approval_id:
        return None
    try:
        with db.transaction() as conn:
            approval = papers.get_approval(conn, approval_id)
            if approval["status"] != "APPROVED":
                return None
            if approval["type"] == "email":
                return {"type": "email", "result": emailer.send_approved(conn, approval_id)}
            if approval["type"] == "website":
                return {"type": "website", "result": website.publish_approved(conn, approval_id)}
            if approval["type"] == "project_start":
                if papers.claim_execution(conn, approval_id, "project") is None:
                    return None
                project_id = approval["payload"].get("project_id")
                result = project_service.enqueue(conn, project_id, actor="owner")
                papers.finish_execution(conn, approval_id, status="SUCCEEDED", result="project_started")
                return {"type": "project_start", "result": result}
    except Exception as error:
        try:
            with db.transaction() as conn:
                audit.log(
                    conn, actor="executor", actor_kind="backend", action="approval.execution_error",
                    detail=json_dump({"approval_id": approval_id, "error": str(error)[:300]}),
                    ref_type="approval", ref_id=approval_id,
                )
        except Exception:
            pass
        return {"error": str(error)}
    return None


@app.post("/api/approvals/{approval_id}/execute")
def execute_approval(approval_id: str, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        approval = papers.get_approval(conn, approval_id)
    if approval["status"] != "APPROVED":
        raise HTTPException(status_code=409, detail="Persetujuan belum disetujui Owner.")
    return {"execution": _execute_approval(approval_id)}


# ------------------------------------------------------------
# Email: inbox, outbox, dan sinkronisasi (EML)
# ------------------------------------------------------------

class EmailDraftRequest(BaseModel):
    to: str
    subject: str
    body: str = ""
    attachments: list[str] = []
    task_id: str | None = None


@app.get("/api/inbox")
def inbox(limit: int = 50):
    with db.connection() as conn:
        return {"messages": emailer.list_inbox(conn, limit=limit), "warning": emailer.UNTRUSTED_WARNING}


@app.post("/api/inbox/sync")
def inbox_sync(limit: int = 20, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        messages = emailer.sync_inbox(conn, limit=limit)
    return {"messages": messages, "warning": emailer.UNTRUSTED_WARNING}


@app.get("/api/outbox")
def outbox(limit: int = 50):
    with db.connection() as conn:
        return {"messages": emailer.list_outbox(conn, limit=limit)}


@app.post("/api/outbox", status_code=201)
def create_outbox(payload: EmailDraftRequest, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        result = emailer.create_draft(
            conn,
            to=payload.to,
            subject=payload.subject,
            body=payload.body,
            attachments=payload.attachments,
            requester="owner",
            task_id=payload.task_id,
        )
    return result


@app.post("/api/outbox/process")
def process_outbox(_: str = Depends(require_owner)):
    with db.transaction() as conn:
        return {"messages": emailer.process_outbox(conn)}


# ------------------------------------------------------------
# Website: paket rilis, publikasi, rollback (WEB)
# ------------------------------------------------------------

class WebsitePackageRequest(BaseModel):
    summary: str
    diff: str
    task_id: str | None = None


@app.get("/api/website/deployments")
def website_deployments(limit: int = 50):
    with db.connection() as conn:
        return {"deployments": website.list_deployments(conn, limit=limit)}


@app.post("/api/website/deployments", status_code=201)
def create_website_deployment(payload: WebsitePackageRequest, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        result = website.create_deployment(
            conn,
            summary=payload.summary,
            diff=payload.diff,
            requester="owner",
            task_id=payload.task_id,
        )
    return result


@app.get("/api/website/deployments/{release_id}")
def website_deployment(release_id: str):
    with db.connection() as conn:
        return {"deployment": website.get_deployment(conn, release_id)}


@app.post("/api/website/deployments/{release_id}/publish")
def publish_website(release_id: str, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        deployment = website.publish(conn, release_id, actor="owner")
    return {"deployment": deployment}


@app.post("/api/website/deployments/{release_id}/rollback")
def rollback_website(release_id: str, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        deployment = website.rollback(conn, release_id, actor="owner")
    return {"deployment": deployment}


@app.get("/api/website/deployments/{release_id}/reconcile")
def reconcile_website(release_id: str):
    with db.connection() as conn:
        return website.reconcile(conn, release_id)


# ------------------------------------------------------------
# Sekretaris
# ------------------------------------------------------------

class SecretaryCommand(BaseModel):
    text: str
    preview: bool = False


@app.post("/api/secretary/command")
def secretary_command(payload: SecretaryCommand, _: str = Depends(require_owner)):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Perintah tidak boleh kosong.")
    with db.transaction() as conn:
        result = secretary.handle_command(conn, payload.text, preview=payload.preview)
    return result


@app.get("/api/secretary/agenda")
def secretary_agenda():
    with db.connection() as conn:
        return secretary.agenda(conn)


# ------------------------------------------------------------
# Audit, usage, knowledge
# ------------------------------------------------------------

@app.get("/api/audit")
def audit_entries(
    limit: int = 50,
    action: str | None = None,
    actor: str | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    before_id: int | None = None,
):
    with db.connection() as conn:
        rows = audit.list_entries(
            conn, limit=limit, action=action, actor=actor, ref_type=ref_type, ref_id=ref_id, before_id=before_id
        )
    return {"entries": rows}


@app.get("/api/usage")
def usage(days: int = 30):
    with db.connection() as conn:
        return reports.usage_summary(conn, days=days)


class UsageRecordRequest(BaseModel):
    employee_id: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int | None = None
    estimated_cost: float = 0.0
    project_id: str | None = None


@app.post("/api/usage/record", status_code=201)
def record_usage(payload: UsageRecordRequest, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        try:
            return reports.record_usage(conn, actor="owner", **payload.model_dump())
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/activity")
def activity(
    department_id: str | None = None,
    employee_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
):
    with db.connection() as conn:
        return {
            "entries": reports.activity(
                conn,
                department_id=department_id,
                employee_id=employee_id,
                action=action,
                limit=limit,
            )
        }


@app.get("/api/reports/divisions")
def division_reports():
    with db.connection() as conn:
        return {"divisions": reports.division_performance(conn)}


@app.get("/api/reports/divisions/{department_id}")
def division_report(department_id: str):
    with db.connection() as conn:
        try:
            markdown = reports.division_markdown(conn, department_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
    return {"department_id": department_id, "markdown": markdown}


@app.post("/api/reports/divisions/{department_id}/export")
def export_division_report(department_id: str, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        try:
            return reports.export_division(conn, department_id, actor="owner")
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(settings.BASE_DIR))
    except ValueError:
        return str(path)


def _knowledge_documents() -> list[dict[str, Any]]:
    documents = []
    for root in (settings.DOCS_DIR, settings.REPORT_DIR):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            if knowledge.file_has_secrets(path):
                continue
            documents.append({
                "path": _display_path(path),
                "size": path.stat().st_size,
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
            })
    return documents


class KnowledgeDocument(BaseModel):
    name: str
    content: str


@app.get("/api/knowledge/documents")
def knowledge_documents():
    return {"documents": _knowledge_documents()}


@app.post("/api/knowledge/documents", status_code=201)
def add_knowledge_document(payload: KnowledgeDocument, _: str = Depends(require_owner)):
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", payload.name).strip(".-") or "dokumen.md"
    if not name.lower().endswith((".md", ".txt", ".json")):
        name += ".md"
    knowledge.assert_safe(payload.content)
    target = settings.DOCS_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    with db.transaction() as conn:
        audit.log(
            conn, actor="owner", actor_kind="owner", action="knowledge.document_added",
            detail=str({"path": _display_path(target)}),
            ref_type="knowledge", ref_id=name,
        )
    return {"document": {"path": _display_path(target), "size": target.stat().st_size}}


@app.get("/api/knowledge/search")
def knowledge_search(q: str = Query("", min_length=0)):
    with db.transaction() as conn:
        result = tools.execute(conn, actor="owner", tool_name="search_knowledge", args={"query": q})
    return result


# ------------------------------------------------------------
# Event realtime
# ------------------------------------------------------------

@app.get("/api/events")
def event_replay(last_event_id: int = 0, limit: int = 1000):
    with db.connection() as conn:
        return events.replay(conn, last_event_id, limit)


class EventAck(BaseModel):
    client_id: str
    event_id: int


@app.post("/api/events/ack")
def event_ack(payload: EventAck, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        events.ack(conn, payload.client_id, payload.event_id)
    return {"ok": True}


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket, last_event_id: int = 0):
    await websocket.accept()
    with db.connection() as conn:
        replay = events.replay(conn, last_event_id)
    if replay["snapshot_required"]:
        await websocket.send_json({"type": "snapshot_required", "latest_id": replay["latest_id"]})
    else:
        for event in replay["events"]:
            await websocket.send_json(event)
    subscription_id, queue = events.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                with db.connection() as conn:
                    latest = events.latest_id(conn)
                await websocket.send_json({"type": "ping", "latest_id": latest})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        events.unsubscribe(subscription_id)


# ------------------------------------------------------------
# Kantor: state pemain, aksi objek, chat legacy
# ------------------------------------------------------------

class PlayerStateRequest(BaseModel):
    x: float = 0
    y: float = 0
    z: float = 0
    room: str = "owner_room"
    activity: str = "idle"


class OfficeAction(BaseModel):
    action: str
    object: str = ""
    room: str = ""
    payload: dict[str, Any] = {}


@app.get("/api/office/state")
def office_state():
    with db.connection() as conn:
        player = fetch_one(conn, "SELECT * FROM player_state WHERE id = 1") or {}
        employees = org.employee_states(conn)
        rooms = fetch_all(conn, "SELECT id, name, room, manager_id FROM departments")
        interactions = fetch_all(conn, "SELECT * FROM interactions ORDER BY created_at DESC LIMIT 100")
    return {
        "player": player,
        "employees": employees,
        "rooms": rooms,
        "interactables": [
            {"id": "computer_owner", "name": "Komputer Owner", "room": "owner_room", "action": "open_command_center"},
            {"id": "secretary_desk", "name": "Meja Sekretaris", "room": "front_office", "action": "open_agenda"},
            {"id": "tray_owner", "name": "Tray Meja Owner", "room": "owner_room", "action": "open_tray"},
            {"id": "printer", "name": "Printer Kantor", "room": "front_office", "action": "print"},
            {"id": "archive", "name": "Rak Arsip", "room": "front_office", "action": "open_archive"},
            {"id": "coffee", "name": "Mesin Kopi", "room": "pantry", "action": "coffee"},
            {"id": "meeting_table", "name": "Meja Rapat", "room": "ruang_rapat", "action": "meeting"},
        ],
        "interactions": interactions,
    }


@app.get("/api/office/player")
def get_player():
    with db.connection() as conn:
        return {"player": fetch_one(conn, "SELECT * FROM player_state WHERE id = 1") or {}}


@app.post("/api/office/player")
def save_player(payload: PlayerStateRequest, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO player_state (id, x, y, z, room, activity, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                x = excluded.x, y = excluded.y, z = excluded.z,
                room = excluded.room, activity = excluded.activity, updated_at = excluded.updated_at
            """,
            (payload.x, payload.y, payload.z, payload.room, payload.activity, now()),
        )
        events.publish(conn, "player.state", "owner", payload.model_dump())
    return {"ok": True}


@app.post("/api/office/action")
def office_action(payload: OfficeAction, _: str = Depends(require_owner)):
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO world_events (at, type, actor, object, room, payload) VALUES (?, ?, 'owner', ?, ?, ?)",
            (now(), f"object.{payload.action}", payload.object, payload.room, json_dump(payload.payload)),
        )
        audit.log(
            conn, actor="owner", actor_kind="owner", action="object.interaction",
            detail=str({"action": payload.action, "object": payload.object, "room": payload.room}),
            ref_type="object", ref_id=payload.object,
        )
        events.publish(conn, "office.action", "owner", payload.model_dump())
        summary = secretary.daily_summary(conn)
    return {"ok": True, "summary": summary}


class ChatRequest(BaseModel):
    command: str = ""
    message: str = ""


@app.get("/api/chat/history")
def chat_history(
    employee_id: str | None = None,
    thread_type: str | None = None,
    thread_id: str | None = None,
    limit: int = 50,
):
    if employee_id:
        thread_type, thread_id = "employee", employee_id
    thread_type = thread_type or "lead"
    thread_id = thread_id or ("owner-lead" if thread_type == "lead" else "owner-secretary")
    with db.connection() as conn:
        rows = chat.history(conn, thread_type=thread_type, thread_id=thread_id, limit=limit)
    return {"messages": rows}


@app.post("/api/chat")
def lead_chat(payload: ChatRequest, _: str = Depends(require_owner)):
    message = (payload.command or payload.message).strip()
    if not message:
        raise HTTPException(status_code=400, detail="Tulis pesan untuk Lead Manager.")
    if not LLM_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Lead Manager sedang membalas percakapan lain.")
    try:
        with db.transaction() as conn:
            result = conversation.lead_reply(conn, message)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Lead Manager belum dapat membalas: {error}")
    finally:
        LLM_LOCK.release()
    return result


class EmployeeChatRequest(BaseModel):
    employee_id: str
    message: str


@app.post("/api/employee-chat")
def employee_chat(payload: EmployeeChatRequest, _: str = Depends(require_owner)):
    employee = None
    with db.connection() as conn:
        employee = org.get_employee(conn, payload.employee_id)
    if not employee or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Karyawan atau pesan tidak valid.")
    with STATE_LOCK:
        EMPLOYEE_CHAT_ACTIVE[payload.employee_id] = {"started_at": now()}
    try:
        with db.transaction() as conn:
            result = conversation.employee_reply(conn, payload.employee_id, payload.message.strip())
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"{employee['name']} belum dapat membalas: {error}")
    finally:
        with STATE_LOCK:
            EMPLOYEE_CHAT_ACTIVE.pop(payload.employee_id, None)
    return result


class RoomChatRequest(BaseModel):
    room: str
    message: str


@app.post("/api/room-chat")
def room_chat(payload: RoomChatRequest, _: str = Depends(require_owner)):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Pesan kosong.")
    try:
        with db.transaction() as conn:
            result = conversation.room_reply(conn, payload.room, payload.message.strip())
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Ruangan belum dapat membalas: {error}")
    return result


# ------------------------------------------------------------
# Pipeline coding legacy
# ------------------------------------------------------------

class CommandRequest(BaseModel):
    command: str
    project_name_hint: str | None = None


@app.post("/api/command", status_code=202)
def run_command(payload: CommandRequest, _: str = Depends(require_owner)):
    command = payload.command.strip()
    if not command:
        raise HTTPException(status_code=400, detail="Tulis instruksi untuk tim.")
    if not RUN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Masih ada pekerjaan yang berjalan.")
    with STATE_LOCK:
        ACTIVE.update(running=True, command=command, started_at=now(), error=None)
    with db.transaction() as conn:
        audit.log(
            conn, actor="owner", actor_kind="owner", action="pipeline.started",
            detail=str({"command": command[:500], "hint": payload.project_name_hint}),
            ref_type="pipeline", ref_id="legacy",
        )

    def worker() -> None:
        try:
            from main import AICodingFactory

            AICodingFactory(lambda message: print(message, flush=True)).execute(
                command, project_name_hint=payload.project_name_hint or None
            )
        except Exception as error:
            with STATE_LOCK:
                ACTIVE["error"] = str(error)
            print(f"[OFFICE ERROR] {error}", flush=True)
        finally:
            with STATE_LOCK:
                ACTIVE["running"] = False
            RUN_LOCK.release()

    threading.Thread(target=worker, name="office-project-run", daemon=True).start()
    return {"accepted": True, "command": command}


# ------------------------------------------------------------
# UI statis
# ------------------------------------------------------------

@app.get("/")
def index():
    path = WEB_DIR / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="UI kantor tidak ditemukan.")
    return FileResponse(path, media_type="text/html; charset=utf-8")


@app.get("/healthz")
def healthz():
    return {"ok": True, "time": now()}


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)
