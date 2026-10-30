"""Persistent local health metrics for the office's AI employees."""

import json
import threading
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
HEALTH_FILE = BASE_DIR / "logs" / "employee_health.json"
LOCK = threading.RLock()

EMPLOYEES = {
    "lead": {"name": "Arman", "role": "Lead Manager", "model": "qwen2.5-coder:1.5b"},
    "coo": {"name": "Sinta", "role": "COO / Project Manager", "model": "qwen2.5-coder:1.5b"},
    "architect": {"name": "Raka", "role": "System Architect", "model": "qwen2.5-coder:1.5b"},
    "backend": {"name": "Bima", "role": "Backend Developer", "model": "qwen2.5-coder:1.5b"},
    "api": {"name": "Naya", "role": "API Specialist", "model": "llama3.2:3b"},
    "frontend": {"name": "Dira", "role": "Frontend Developer", "model": "qwen2.5-coder:1.5b"},
    "qa": {"name": "Tika", "role": "QA Engineer", "model": "llama3.2:3b"},
}


def _empty_employee(employee_id):
    return {
        **EMPLOYEES[employee_id],
        "status": "idle",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "requests": 0,
        "tasks_completed": 0,
        "usage_available": False,
        "runtime_seconds": 0,
        "current_started_at": None,
        "last_duration_seconds": 0,
        "last_activity_at": None,
        "last_detail": "Belum ada aktivitas tercatat.",
        "events": [],
    }


def _load():
    try:
        data = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    employees = data.get("employees", {})
    for employee_id in EMPLOYEES:
        base = _empty_employee(employee_id)
        base.update(employees.get(employee_id, {}))
        base.update(EMPLOYEES[employee_id])
        employees[employee_id] = base
    return {"employees": employees}


def _number(metrics, *keys):
    for key in keys:
        value = metrics.get(key)
        if value is not None:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                continue
    return 0


def record_activity(employee_id, status=None, detail=None, usage=None):
    if employee_id not in EMPLOYEES:
        return
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOCK:
        data = _load()
        employee = data["employees"][employee_id]
        duration = 0
        if status == "working":
            employee["current_started_at"] = timestamp
        elif status in ("completed", "failed") and employee.get("current_started_at"):
            try:
                started = datetime.fromisoformat(employee["current_started_at"])
                duration = max(0, int((datetime.fromisoformat(timestamp) - started).total_seconds()))
            except (TypeError, ValueError):
                duration = 0
            employee["runtime_seconds"] += duration
            employee["last_duration_seconds"] = duration
            employee["current_started_at"] = None
        if usage is not None:
            if hasattr(usage, "model_dump"):
                usage = usage.model_dump()
            elif not isinstance(usage, dict):
                try:
                    usage = vars(usage)
                except TypeError:
                    usage = {}
            prompt = _number(usage, "prompt_tokens", "input_tokens")
            completion = _number(usage, "completion_tokens", "output_tokens")
            total = _number(usage, "total_tokens") or prompt + completion
            requests = _number(usage, "successful_requests", "requests")
            employee["usage_available"] = employee["usage_available"] or any(
                key in usage for key in (
                    "prompt_tokens", "input_tokens", "completion_tokens",
                    "output_tokens", "total_tokens"
                )
            )
            employee["prompt_tokens"] += prompt
            employee["completion_tokens"] += completion
            employee["total_tokens"] += total
            employee["requests"] += requests
        if status:
            employee["status"] = status
            if status == "completed":
                employee["tasks_completed"] += 1
        employee["last_activity_at"] = timestamp
        if detail:
            employee["last_detail"] = detail[:400]
        employee["events"].append({
            "at": timestamp,
            "status": status or employee["status"],
            "detail": (detail or "Aktivitas model tercatat.")[:240],
            "tokens": (
                _number(usage or {}, "total_tokens")
                or _number(usage or {}, "prompt_tokens", "input_tokens")
                + _number(usage or {}, "completion_tokens", "output_tokens")
            ),
        })
        employee["events"] = employee["events"][-100:]
        HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_file = HEALTH_FILE.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(HEALTH_FILE)


def get_health_snapshot():
    with LOCK:
        return _load()
