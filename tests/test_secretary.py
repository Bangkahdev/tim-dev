from backend import chat, org, papers, secretary, tasks


def _run(conn, text):
    return secretary.handle_command(conn, text)


def test_ten_issue_scenarios(conn):
    result = _run(conn, "Buat tugas untuk Bima: perbaiki login")
    assert result["status"] == "executed"
    task = tasks.list_tasks(conn, assignee="backend")[0]
    assert "login" in task["title"].lower()

    result = _run(conn, "Pindahkan Sinta ke ruang rapat")
    assert result["status"] == "executed"
    assert org.get_employee(conn, "coo")["room"] == "ruang rapat"

    result = _run(conn, "Adakan rapat besok jam 10 tentang rilis")
    assert result["status"] == "executed"
    rows = conn.execute("SELECT * FROM meetings").fetchall()
    assert len(rows) == 1

    result = _run(conn, "Buat laporan mingguan")
    assert result["status"] == "executed"
    assert papers.list_papers(conn)[0]["type"] == "task_report"

    result = _run(conn, "Mulai proyek baru: aplikasi kasir")
    assert result["status"] == "executed"
    rows = conn.execute("SELECT * FROM projects").fetchall()
    assert len(rows) == 1

    result = _run(conn, "Kirim email ke klien@example.com tentang penawaran")
    assert result["status"] == "executed"
    approval = next(
        paper for paper in papers.list_papers(conn, delivery_status="DELIVERED")
        if paper["type"] == "email_draft"
    )
    assert approval["type"] == "email_draft"
    assert papers.get_approval(conn, approval["approval_id"])["status"] == "PENDING"

    result = _run(conn, "Publikasikan perubahan website")
    assert result["status"] == "executed"
    assert any(p["type"] == "website_package" for p in papers.list_papers(conn))

    result = _run(conn, "Cari di knowledge tentang kebijakan cuti")
    assert result["status"] == "executed"

    result = _run(conn, "Bagaimana status proyek?")
    assert result["status"] == "status"
    assert "task" in result["reply"].lower()

    result = _run(conn, "Buat tugas promosi untuk kampanye")
    assert result["status"] == "executed"
    promo = tasks.list_tasks(conn, assignee="promo_manager")
    assert len(promo) == 1


def test_ambiguous_command_asks_one_question_and_creates_nothing(conn):
    result = _run(conn, "Buat tugas perbaiki login")
    assert result["status"] == "clarification"
    assert result["reply"]
    assert tasks.list_tasks(conn) == []


def test_secretary_command_is_persisted(conn):
    _run(conn, "Bagaimana status proyek?")
    messages = chat.history(conn, thread_type="secretary", thread_id="owner-secretary", limit=10)
    assert any(message["content"] == "Bagaimana status proyek?" for message in messages)

