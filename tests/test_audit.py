import sqlite3

import pytest

from backend import audit


def test_audit_log_is_append_only(conn):
    audit.log(conn, actor="owner", actor_kind="owner", action="test.event", detail="satu")
    assert audit.count(conn) == 1

    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE audit_log SET detail = 'diubah'")

    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM audit_log")

    assert audit.count(conn) == 1
    assert audit.list_entries(conn, limit=5)[0]["detail"] == "satu"


def test_audit_can_be_searched(conn):
    audit.log(conn, actor="arman", actor_kind="manager", action="task.created", ref_type="task", ref_id="t1")
    audit.log(conn, actor="owner", actor_kind="owner", action="paper.approved", ref_type="paper", ref_id="p1")
    entries = audit.list_entries(conn, action="task.created")
    assert len(entries) == 1
    assert entries[0]["actor"] == "arman"
