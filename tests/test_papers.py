import pytest

from backend import papers


def _bundle(conn, **overrides):
    values = {
        "approval_type": "email",
        "payload": {"to": "klien@example.com", "subject": "Penawaran", "body": "Halo"},
        "requester": "promo_manager",
        "summary": "Draf email penawaran",
    }
    values.update(overrides)
    return papers.create_approval_bundle(conn, **values)


def _deliver(conn, paper_id):
    papers.print_paper(conn, paper_id)
    return papers.deliver_paper(conn, paper_id)


def test_print_generates_pdf_and_deliver_puts_paper_in_tray(conn):
    bundle = _bundle(conn)
    paper_id = bundle["paper"]["id"]
    printed = papers.print_paper(conn, paper_id)
    assert printed["paper"]["delivery_status"] == "PRINTED"
    path = papers.pdf_path(conn, paper_id)
    assert path and path.exists()
    assert path.read_bytes().startswith(b"%PDF-1.4")

    delivered = papers.deliver_paper(conn, paper_id)
    assert delivered["delivery_status"] == "DELIVERED"
    assert any(item["id"] == paper_id for item in papers.tray(conn))


def test_approval_decision_binds_payload_hash_and_outbox(conn):
    bundle = _bundle(conn)
    paper_id = bundle["paper"]["id"]
    approval_id = bundle["approval"]["id"]
    _deliver(conn, paper_id)

    decided = papers.decide_paper(
        conn, paper_id, decision="APPROVED", actor="owner", actor_kind="owner", note="setuju"
    )
    assert decided["review_status"] == "APPROVED"
    approval = papers.get_approval(conn, approval_id)
    assert approval["status"] == "APPROVED"
    assert approval["execution_status"] == "PENDING"
    claimed = papers.claim_execution(conn, approval_id, "backend")
    assert claimed and claimed["status"] == "CLAIMED"
    assert papers.claim_execution(conn, approval_id, "frontend") is None
    finished = papers.finish_execution(conn, approval_id, status="SUCCEEDED", result="terkirim")
    assert finished["execution_status"] == "SUCCEEDED"

    with pytest.raises(papers.PaperError):
        papers.decide_paper(
            conn, paper_id, decision="REJECTED", actor="owner", actor_kind="owner"
        )


def test_only_owner_can_decide_and_only_after_delivery(conn):
    bundle = _bundle(conn)
    paper_id = bundle["paper"]["id"]
    with pytest.raises(papers.PaperError):
        papers.decide_paper(conn, paper_id, decision="APPROVED", actor="owner", actor_kind="owner")
    _deliver(conn, paper_id)
    with pytest.raises(papers.PaperError):
        papers.decide_paper(conn, paper_id, decision="APPROVED", actor="secretary", actor_kind="manager")


def test_defer_keeps_approval_pending(conn):
    bundle = _bundle(conn)
    paper_id = bundle["paper"]["id"]
    _deliver(conn, paper_id)
    deferred = papers.decide_paper(
        conn, paper_id, decision="DEFERRED", actor="owner", actor_kind="owner", note="nanti"
    )
    assert deferred["review_status"] == "DEFERRED"
    assert papers.get_approval(conn, bundle["approval"]["id"])["status"] == "PENDING"


def test_expired_paper_cannot_be_approved(conn):
    bundle = _bundle(conn, ttl_hours=-1)
    paper_id = bundle["paper"]["id"]
    _deliver(conn, paper_id)
    with pytest.raises(papers.PaperError):
        papers.decide_paper(conn, paper_id, decision="APPROVED", actor="owner", actor_kind="owner")
    assert papers.get_paper(conn, paper_id)["review_status"] == "EXPIRED"


def test_changed_payload_invalidates_approval(conn):
    bundle = _bundle(conn)
    paper_id = bundle["paper"]["id"]
    approval_id = bundle["approval"]["id"]
    _deliver(conn, paper_id)
    conn.execute("UPDATE approvals SET payload_hash = 'tampered' WHERE id = ?", (approval_id,))
    with pytest.raises(papers.PaperError):
        papers.decide_paper(conn, paper_id, decision="APPROVED", actor="owner", actor_kind="owner")
    assert papers.get_paper(conn, paper_id)["review_status"] == "REVISION_REQUESTED"


def test_revision_creates_new_version_and_archives_old(conn):
    bundle = _bundle(conn)
    paper_id = bundle["paper"]["id"]
    _deliver(conn, paper_id)
    papers.decide_paper(
        conn, paper_id, decision="REVISION_REQUESTED", actor="owner", actor_kind="owner", note="perbaiki"
    )
    revised = papers.revise_paper(
        conn,
        paper_id,
        payload={"to": "klien@example.com", "subject": "Penawaran", "body": "Halo, revisi"},
        summary="Draf email revisi",
        actor="promo_manager",
    )
    assert revised["version"] == 2
    assert revised["approval_id"]
    assert papers.get_approval(conn, revised["approval_id"])["status"] == "PENDING"
    assert papers.get_paper(conn, paper_id)["delivery_status"] == "ARCHIVED"
    assert papers.get_approval(conn, bundle["approval"]["id"])["status"] == "SUPERSEDED"
