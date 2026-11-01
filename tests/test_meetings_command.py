from backend import meetings, monitor, org, papers, settings, tasks


def test_meeting_runs_and_produces_minutes_task_and_paper(conn):
    meeting = meetings.create_meeting(
        conn,
        title="Sinkronisasi rilis",
        agenda="Tentukan kesiapan rilis minggu ini",
        participants=["secretary", "lead", "coo"],
    )
    assert meeting["status"] == "SCHEDULED"

    interrupted = meetings.interject(conn, meeting["id"], "Tambahkan uji regresi.", actor="owner")
    assert any(item["speaker"] == "owner" for item in interrupted["transcript"])

    completed = meetings.run_meeting(conn, meeting["id"], actor="owner", rounds=1)
    assert completed["status"] == "COMPLETED"
    assert completed["decisions"]
    assert any(item["speaker"] == "owner" for item in completed["transcript"])
    assert any(item["speaker"] == "lead" for item in completed["transcript"])

    minutes_path = settings.DOCS_DIR / "meetings" / f"{meeting['id']}.md"
    assert minutes_path.exists()
    assert "## Keputusan" in minutes_path.read_text(encoding="utf-8")

    follow_up = [
        task for task in tasks.list_tasks(conn, assignee="lead")
        if task["title"] == "Tindak lanjut rapat: Sinkronisasi rilis"
    ]
    assert follow_up

    tray = papers.tray(conn)
    assert any(
        paper["type"] == "meeting_minutes"
        and paper["payload"]["meeting_id"] == meeting["id"]
        for paper in tray
    )

    again = meetings.run_meeting(conn, meeting["id"], actor="owner")
    assert again["status"] == "COMPLETED"


def test_meeting_rejects_unknown_participant(conn):
    try:
        meetings.create_meeting(conn, title="Rapat", participants=["tidak_ada"])
    except meetings.MeetingError as error:
        assert "tidak dikenal" in str(error)
    else:
        raise AssertionError("peserta tidak dikenal seharusnya ditolak")


def test_employee_monitor_reports_state_and_work(conn):
    task = tasks.create_task(
        conn,
        title="Rapikan endpoint status",
        assignee="backend",
        created_by="lead",
        actor_kind="manager",
    )
    tasks.update_evidence(
        conn,
        task["id"],
        evidence={"files": ["backend/app.py"], "terminal_output": "pytest -q: 38 passed"},
        actor="backend",
        actor_kind="employee",
    )
    org.set_employee_state(conn, "backend", room="ruang_backend", activity="working", source="task")

    result = monitor.employee_monitor(conn, "backend")
    assert result["employee"]["id"] == "backend"
    assert result["state"]["activity"] == "working"
    assert any(item["id"] == task["id"] for item in result["active_tasks"])
    assert result["terminal_summary"]
    assert any(item["task_id"] == task["id"] for item in result["last_files"])


def test_tray_summary_enforces_limit_and_reports_overflow(conn, monkeypatch):
    monkeypatch.setattr(settings, "PAPER_TRAY_LIMIT", 2)
    for index in range(3):
        bundle = papers.create_approval_bundle(
            conn,
            approval_type="email",
            payload={"to": f"klien{index}@example.com", "subject": "Penawaran", "body": "Halo"},
            requester="promo_manager",
            summary=f"Draf email {index}",
        )
        papers.print_paper(conn, bundle["paper"]["id"])
        papers.deliver_paper(conn, bundle["paper"]["id"])

    summary = papers.tray_summary(conn)
    assert summary["pending"] == 3
    assert summary["limit"] == 2
    assert len(summary["papers"]) == 2
    assert summary["overflow"] == 1
    assert len(summary["overflow_papers"]) == 1
    assert summary["summary_sheet"]["total"] == 3
    assert summary["summary_sheet"]["by_type"]["email_draft"] == 3


def test_secretary_preview_does_not_execute_plan(client, owner_headers):
    before = client.get("/api/tasks").json()["tasks"]
    preview = client.post(
        "/api/secretary/command",
        json={"text": "Buat tugas untuk Dira: rapikan halaman", "preview": True},
        headers=owner_headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "PREVIEW"
    assert preview.json()["plan"]["steps"]
    after = client.get("/api/tasks").json()["tasks"]
    assert len(after) == len(before)

    executed = client.post(
        "/api/secretary/command",
        json={"text": "Buat tugas untuk Dira: rapikan halaman"},
        headers=owner_headers,
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] != "PREVIEW"


def test_command_center_api_exposes_operational_summary(client, owner_headers):
    response = client.get("/api/command-center", headers=owner_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert {"summary", "papers", "paper_tray", "projects", "tasks", "employees", "usage", "activity"} <= set(body)
    assert body["paper_tray"]["limit"] >= 1


def test_meeting_api_run_and_interject(client, owner_headers):
    created = client.post(
        "/api/meetings",
        json={"title": "Rapat API", "agenda": "Uji endpoint", "participants": ["secretary", "lead"]},
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    meeting_id = created.json()["meeting"]["id"]

    interjection = client.post(
        f"/api/meetings/{meeting_id}/interject",
        json={"content": "Prioritaskan bukti tes."},
        headers=owner_headers,
    )
    assert interjection.status_code == 200, interjection.text

    run = client.post(
        f"/api/meetings/{meeting_id}/run",
        params={"rounds": 1},
        headers=owner_headers,
    )
    assert run.status_code == 200, run.text
    assert run.json()["meeting"]["status"] == "COMPLETED"

    knowledge = client.get("/api/knowledge/search", params={"q": "Rapat API"})
    assert knowledge.status_code == 200, knowledge.text
    assert any("meetings" in item["path"] for item in knowledge.json()["results"])
