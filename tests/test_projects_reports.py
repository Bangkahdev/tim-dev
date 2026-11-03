from pathlib import Path

import pytest

from backend import db, projects, reports, settings, tasks


def _project(conn, name, priority="normal"):
    return projects.create_project(conn, name=name, actor="owner", priority=priority)


def test_project_queue_respects_concurrency_limit(conn, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_PROJECTS", 2)
    first = _project(conn, "Alpha")
    second = _project(conn, "Beta")
    third = _project(conn, "Gamma")
    for project in (first, second, third):
        projects.enqueue(conn, project["id"], actor="owner")

    statuses = {row["id"]: row["status"] for row in projects.list_projects(conn)}
    assert statuses[first["id"]] == "ACTIVE"
    assert statuses[second["id"]] == "ACTIVE"
    assert statuses[third["id"]] == "QUEUED"
    assert projects.active_count(conn) == 2

    projects.complete_project(conn, first["id"], actor="owner", force=True)
    assert projects.get_project(conn, third["id"])["status"] == "ACTIVE"


def test_priority_orders_the_queue(conn, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_PROJECTS", 1)
    blocker = _project(conn, "Blocker")
    low = _project(conn, "Low", priority="low")
    urgent = _project(conn, "Urgent", priority="urgent")
    projects.enqueue(conn, blocker["id"], actor="owner")
    projects.enqueue(conn, low["id"], actor="owner")
    projects.enqueue(conn, urgent["id"], actor="owner")

    assert projects.get_project(conn, low["id"])["status"] == "QUEUED"
    assert projects.get_project(conn, urgent["id"])["status"] == "QUEUED"

    projects.complete_project(conn, blocker["id"], actor="owner", force=True)
    assert projects.get_project(conn, urgent["id"])["status"] == "ACTIVE"
    assert projects.get_project(conn, low["id"])["status"] == "QUEUED"


def test_completion_archives_snapshot_and_triggers_promotion(conn, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_PROJECTS", 1)
    project = _project(conn, "Delta")
    workspace = Path(project["workspace_path"])
    (workspace / "app.py").write_text("print('halo')", encoding="utf-8")
    task = tasks.create_task(
        conn, title="Bangun API", project_id=project["id"], assignee="backend",
        created_by="lead", actor_kind="manager",
    )
    conn.execute("UPDATE tasks SET status = 'COMPLETED' WHERE id = ?", (task["id"],))

    result = projects.complete_project(conn, project["id"], actor="owner")

    archive = Path(result["archive"]["path"])
    assert archive.is_dir()
    assert (archive / "project.json").is_file()
    assert (archive / "report.md").is_file()
    assert (archive / "MANIFEST.sha256").is_file()
    assert (archive / "workspace" / "app.py").read_text(encoding="utf-8") == "print('halo')"
    assert result["project"]["archive_hash"] == result["archive"]["hash"]
    assert result["promotion_task"]["assignee"] == "promo_manager"
    assert result["promotion_task"]["kind"] == "non_code"
    assert result["paper"]["type"] == "project_report"
    assert result["paper"]["delivery_status"] == "DELIVERED"

    with pytest.raises(projects.ProjectError):
        projects.complete_project(conn, project["id"], actor="owner", force=True)


def test_completion_is_blocked_while_tasks_are_open(conn):
    project = _project(conn, "Epsilon")
    tasks.create_task(
        conn, title="Belum selesai", project_id=project["id"], assignee="backend",
        created_by="lead", actor_kind="manager",
    )
    with pytest.raises(projects.ProjectError):
        projects.complete_project(conn, project["id"], actor="owner")


def test_activity_filters_by_department(conn):
    tasks.create_task(conn, title="Kerja backend", assignee="backend", created_by="lead", actor_kind="manager")
    tasks.create_task(conn, title="Kerja promosi", assignee="promo_writer", created_by="promo_manager", actor_kind="manager")
    db.fetch_one(conn, "SELECT 1")

    engineering = reports.activity(conn, department_id="engineering")
    promotion = reports.activity(conn, department_id="promotion")

    assert engineering and all(row["department_id"] == "engineering" for row in engineering)
    assert promotion and all(row["department_id"] == "promotion" for row in promotion)
    assert {row["action"] for row in engineering} >= {"task.created"}


def test_project_start_needs_approval_then_activates(client, owner_headers):
    created = client.post("/api/projects", json={"name": "Zeta"}, headers=owner_headers).json()
    project_id = created["project"]["id"]

    requested = client.post(f"/api/projects/{project_id}/request-start", headers=owner_headers)
    assert requested.status_code == 201, requested.text
    approval_id = requested.json()["approval"]["id"]
    listed = client.get("/api/projects").json()
    assert next(row for row in listed["projects"] if row["id"] == project_id)["status"] == "PLANNED"

    approved = client.post(f"/api/approvals/{approval_id}/approve", headers=owner_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["execution"]["type"] == "project_start"
    listed = client.get("/api/projects").json()
    assert next(row for row in listed["projects"] if row["id"] == project_id)["status"] == "ACTIVE"


def test_division_report_usage_dashboard_and_pdf_export(client, owner_headers):
    created = client.post("/api/projects", json={"name": "Eta"}, headers=owner_headers).json()
    project_id = created["project"]["id"]
    task = client.post(
        "/api/tasks",
        json={"title": "Tulis dokumentasi", "assignee": "promo_writer", "kind": "non_code"},
        headers=owner_headers,
    )
    assert task.status_code == 201, task.text

    recorded = client.post(
        "/api/usage/record",
        json={
            "employee_id": "promo_writer", "model": "model-uji", "prompt_tokens": 12,
            "completion_tokens": 8, "estimated_cost": 0.02, "project_id": project_id,
        },
        headers=owner_headers,
    )
    assert recorded.status_code == 201, recorded.text

    usage = client.get("/api/usage").json()
    assert usage["totals"]["total_tokens"] >= 20
    assert any(row["project_id"] == project_id for row in usage["by_project"])
    assert any(row["model"] == "model-uji" for row in usage["by_model"])

    divisions = client.get("/api/reports/divisions").json()["divisions"]
    promotion = next(row for row in divisions if row["id"] == "promotion")
    assert promotion["employees"] >= 2
    assert promotion["total_tokens"] >= 20

    report = client.get("/api/reports/divisions/promotion")
    assert report.status_code == 200
    assert "Laporan Divisi: Promosi" in report.json()["markdown"]

    exported = client.post("/api/reports/divisions/promotion/export", headers=owner_headers)
    assert exported.status_code == 200, exported.text
    assert Path(exported.json()["pdf_path"]).is_file()


def test_command_center_exposes_division_and_usage_summaries(client):
    payload = client.get("/api/command-center").json()
    assert "division_performance" in payload
    assert "usage_summary" in payload
    assert payload["usage_summary"]["totals"]["total_tokens"] == 0
