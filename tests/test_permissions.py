import pytest

from backend import audit, org, tasks, tools


def _task_count(conn):
    return len(tasks.list_tasks(conn, limit=100))


def test_frontend_cannot_create_task(conn):
    with pytest.raises(tools.PermissionDenied):
        tools.execute(
            conn,
            actor="frontend",
            tool_name="create_task",
            args={"title": "Bikin halaman", "assignee": "frontend"},
        )
    assert _task_count(conn) == 0
    assert any(entry["action"] == "tool.denied" for entry in audit.list_entries(conn, limit=20))


def test_secretary_can_create_task(conn):
    outcome = tools.execute(
        conn,
        actor="secretary",
        tool_name="create_task",
        args={"title": "Susun agenda", "assignee": "secretary"},
    )
    assert outcome["task"]["status"] == "PENDING"
    assert _task_count(conn) == 1


def test_unknown_tool_and_unknown_actor_rejected(conn):
    with pytest.raises(tools.UnknownTool):
        tools.execute(conn, actor="secretary", tool_name="drop_database", args={})
    with pytest.raises(tools.PermissionDenied):
        tools.execute(conn, actor="tidak-ada", tool_name="log_message", args={"text": "halo"})


def test_manager_can_assign_to_department_member(conn):
    tools.execute(
        conn,
        actor="promo_manager",
        tool_name="create_task",
        args={"title": "Kampanye baru", "assignee": "promo_writer"},
    )
    assert org.get_employee(conn, "promo_writer")["id"] == "promo_writer"

