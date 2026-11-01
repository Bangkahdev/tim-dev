def test_session_requires_configured_token(client):
    assert client.post("/api/session", json={"api_auth_token": "salah"}).status_code == 401
    response = client.post("/api/session", json={"api_auth_token": "test-owner-secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["token"] and body["expires_at"] and body["hours"] > 0


def test_mutations_require_owner_session(client, owner_headers):
    assert client.post("/api/tasks", json={"title": "Tanpa sesi", "assignee": "backend"}).status_code == 401

    response = client.post(
        "/api/tasks",
        json={"title": "Implementasi API", "assignee": "backend"},
        headers=owner_headers,
    )
    assert response.status_code == 201
    task = response.json()["task"]
    assert task["status"] == "PENDING"

    listing = client.get("/api/tasks")
    assert listing.status_code == 200
    assert any(item["id"] == task["id"] for item in listing.json()["tasks"])


def test_status_endpoint_is_read_only_summary(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert "summary" in body


def test_secretary_email_then_owner_approves_via_api(client, owner_headers):
    command = client.post(
        "/api/secretary/command",
        json={"text": "Kirim email ke klien@example.com tentang penawaran"},
        headers=owner_headers,
    )
    assert command.status_code == 200, command.text

    tray = client.get("/api/papers", params={"tray_only": True}, headers=owner_headers)
    assert tray.status_code == 200
    items = tray.json()["papers"]
    assert len(items) == 1
    paper_id = items[0]["id"]

    pdf = client.get(f"/api/papers/{paper_id}/pdf", headers=owner_headers)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    decision = client.post(
        f"/api/papers/{paper_id}/decision",
        json={"decision": "APPROVED", "note": "silakan"},
        headers=owner_headers,
    )
    assert decision.status_code == 200
    assert decision.json()["paper"]["review_status"] == "APPROVED"

    ag = client.get("/api/secretary/agenda", headers=owner_headers)
    assert ag.status_code == 200


def test_audit_and_events_are_visible(client, owner_headers):
    client.post(
        "/api/secretary/command",
        json={"text": "Buat tugas untuk Dira: rapikan halaman"},
        headers=owner_headers,
    )
    audit = client.get("/api/audit", headers=owner_headers)
    assert audit.status_code == 200
    assert audit.json()["entries"]

    replay = client.get("/api/events", params={"last_event_id": 0})
    assert replay.status_code == 200
    event = replay.json()["events"][0]
    assert {"id", "type", "actor", "payload", "created_at"} <= set(event)


def test_websocket_streams_replayed_event(client, owner_headers):
    client.post(
        "/api/secretary/command",
        json={"text": "Bagaimana status proyek?"},
        headers=owner_headers,
    )
    with client.websocket_connect("/ws/events?last_event_id=0") as websocket:
        message = websocket.receive_json()
        assert "id" in message or message["type"] == "snapshot_required"

