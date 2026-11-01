from backend import events


def test_event_ids_are_monotonic_and_replayable(conn):
    first = events.publish(conn, "test.satu", "tester", {"n": 1})
    second = events.publish(conn, "test.dua", "tester", {"n": 2})
    third = events.publish(conn, "test.tiga", "tester", {"n": 3})
    assert first["id"] < second["id"] < third["id"]

    replay = events.replay(conn, last_event_id=second["id"])
    assert [event["id"] for event in replay["events"]] == [third["id"]]
    assert replay["gap"] is False


def test_replay_reports_gap_when_events_were_pruned(conn):
    events.publish(conn, "test.satu", "tester")
    events.publish(conn, "test.dua", "tester")
    events.publish(conn, "test.tiga", "tester")
    conn.execute("DELETE FROM event_log WHERE id IN (1, 2)")
    replay = events.replay(conn, last_event_id=1)
    assert replay["gap"] is True
    assert events.oldest_id(conn) == 3


def test_ack_is_idempotent(conn):
    event = events.publish(conn, "test.ack", "tester")
    events.ack(conn, "client-a", event["id"])
    events.ack(conn, "client-a", event["id"])
    row = conn.execute("SELECT COUNT(*) AS total FROM event_acks").fetchone()
    assert row["total"] == 1
