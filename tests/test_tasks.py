from pathlib import Path

import pytest

from backend import settings, tasks


def _new_task(conn, **overrides):
    data = {
        "title": "Implementasi login",
        "assignee": "backend",
        "kind": "code",
        "created_by": "lead",
        "actor_kind": "manager",
    }
    data.update(overrides)
    return tasks.create_task(conn, **data)


def _evidence_file(name="src/app.py"):
    root = Path(settings.WORKSPACE_DIR)
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('ok')\n", encoding="utf-8")
    return name


def _to_qa(conn, task, file_name="src/app.py"):
    tasks.transition(conn, task_id=task["id"], to_status="IN_PROGRESS", actor="lead", actor_kind="manager")
    tasks.update_evidence(
        conn, task["id"], {"files": [file_name], "notes": "implementasi awal"}, "backend", "employee"
    )
    tasks.transition(conn, task_id=task["id"], to_status="REVIEW", actor="backend", actor_kind="employee")
    tasks.transition(
        conn, task_id=task["id"], to_status="QA", actor="lead", actor_kind="manager", note="tinjauan lulus"
    )
    return tasks.get_task(conn, task["id"])


def test_happy_path_completes_only_with_valid_evidence(conn):
    task = _new_task(conn)
    _evidence_file()
    task = _to_qa(conn, task)
    completed = tasks.transition(
        conn,
        task_id=task["id"],
        to_status="COMPLETED",
        actor="backend",
        actor_kind="backend",
        evidence={"test_results": [{"command": "pytest", "exit_code": 0}]},
    )
    assert completed["status"] == "COMPLETED"


def test_completion_rejected_when_files_do_not_exist(conn):
    task = _new_task(conn)
    task = _to_qa(conn, task, file_name="src/tidak-ada.py")
    with pytest.raises(tasks.TaskTransitionDenied):
        tasks.transition(
            conn, task_id=task["id"], to_status="COMPLETED", actor="backend", actor_kind="backend",
            evidence={"test_results": [{"command": "pytest", "exit_code": 0}]},
        )
    assert tasks.get_task(conn, task["id"])["status"] == "QA"


def test_completion_rejected_without_passing_test_or_commit(conn):
    task = _new_task(conn)
    _evidence_file()
    task = _to_qa(conn, task)
    with pytest.raises(tasks.TaskTransitionDenied):
        tasks.transition(
            conn, task_id=task["id"], to_status="COMPLETED", actor="backend", actor_kind="backend",
            evidence={"test_results": [{"command": "pytest", "exit_code": 1}]},
        )


def test_non_code_task_requires_review(conn):
    task = _new_task(conn, title="Tulis proposal", kind="non_code")
    file_name = _evidence_file("docs/proposal.md")
    task = _to_qa(conn, task, file_name=file_name)
    with pytest.raises(tasks.TaskTransitionDenied):
        tasks.transition(
            conn, task_id=task["id"], to_status="COMPLETED", actor="backend", actor_kind="backend"
        )
    completed = tasks.transition(
        conn, task_id=task["id"], to_status="COMPLETED", actor="backend", actor_kind="backend",
        evidence={"reviewed_by": "lead", "reviewer_kind": "manager"},
    )
    assert completed["status"] == "COMPLETED"


def test_invalid_transition_and_wrong_actor_rejected(conn):
    task = _new_task(conn)
    with pytest.raises(tasks.TaskTransitionDenied):
        tasks.transition(conn, task_id=task["id"], to_status="QA", actor="backend", actor_kind="employee")

    tasks.transition(conn, task_id=task["id"], to_status="IN_PROGRESS", actor="lead", actor_kind="manager")
    with pytest.raises(tasks.TaskTransitionDenied):
        tasks.transition(conn, task_id=task["id"], to_status="REVIEW", actor="frontend", actor_kind="employee")


def test_review_requires_initial_evidence(conn):
    task = _new_task(conn)
    tasks.transition(conn, task_id=task["id"], to_status="IN_PROGRESS", actor="lead", actor_kind="manager")
    with pytest.raises(tasks.TaskTransitionDenied):
        tasks.transition(conn, task_id=task["id"], to_status="REVIEW", actor="backend", actor_kind="employee")


def test_dependencies_must_be_completed(conn):
    first = _new_task(conn, title="Fondasi")
    second = _new_task(conn, title="Lanjutan", depends_on=[first["id"]])
    with pytest.raises(tasks.TaskTransitionDenied):
        tasks.transition(conn, task_id=second["id"], to_status="IN_PROGRESS", actor="lead", actor_kind="manager")


def test_failed_retry_resets_attempts_only_for_manager(conn, monkeypatch):
    monkeypatch.setattr(settings, "MAX_REPAIR_ROUNDS", 1)
    task = _new_task(conn)
    _evidence_file()
    task = _to_qa(conn, task)
    tasks.transition(conn, task_id=task["id"], to_status="IN_PROGRESS", actor="backend", actor_kind="backend")
    assert tasks.get_task(conn, task["id"])["attempts"] == 1
    tasks.transition(conn, task_id=task["id"], to_status="FAILED", actor="backend", actor_kind="backend")
    with pytest.raises(tasks.TaskTransitionDenied):
        tasks.transition(
            conn, task_id=task["id"], to_status="IN_PROGRESS", actor="backend", actor_kind="employee", note="coba lagi"
        )
    retried = tasks.transition(
        conn, task_id=task["id"], to_status="IN_PROGRESS", actor="lead", actor_kind="manager", note="coba lagi"
    )
    assert retried["attempts"] == 0
