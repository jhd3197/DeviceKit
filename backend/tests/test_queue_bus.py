"""Queue Bus semantics: send/receive/complete, retry with backoff, dead-letter, visibility
timeout reclaim, and stats — all on the SQL-backed broker (plan 05)."""
from devicekit.queue_bus.service import QueueBusService, QueueBusError
from devicekit.queue_bus.models import QueueMessage


GROUP = "test-group"
QUEUE = "work"


def _ensure():
    return QueueBusService.ensure_queue(GROUP, QUEUE, config={"max_attempts": 3})


def test_ensure_queue_is_idempotent(fresh_db):
    _ensure()
    _ensure()  # second call must not raise
    assert QueueBusService.get_group(GROUP) is not None
    assert QueueBusService.get_queue(GROUP, QUEUE) is not None


def test_send_receive_complete(fresh_db):
    _ensure()
    QueueBusService.send(GROUP, QUEUE, {"n": 1})
    msgs = QueueBusService.receive(GROUP, QUEUE, visibility_timeout_ms=60000)
    assert len(msgs) == 1
    m = msgs[0]
    assert m["status"] == QueueMessage.STATUS_IN_FLIGHT
    assert m["attempts"] == 1
    assert m["payload"] == {"n": 1}
    # A second receive gets nothing (the only message is in-flight).
    assert QueueBusService.receive(GROUP, QUEUE) == []
    QueueBusService.complete(GROUP, QUEUE, m["id"])
    assert QueueBusService.get_message(GROUP, QUEUE, m["id"])["status"] == QueueMessage.STATUS_COMPLETED


def test_priority_ordering(fresh_db):
    _ensure()
    QueueBusService.send(GROUP, QUEUE, {"p": "low"}, priority=0)
    QueueBusService.send(GROUP, QUEUE, {"p": "high"}, priority=10)
    msgs = QueueBusService.receive(GROUP, QUEUE, max_messages=1)
    assert msgs[0]["payload"]["p"] == "high"


def test_fail_retries_with_backoff_then_dead_letters(fresh_db):
    _ensure()
    QueueBusService.send(GROUP, QUEUE, {"n": 1}, max_attempts=2)
    m = QueueBusService.receive(GROUP, QUEUE)[0]
    # First failure: attempts(1) < max(2) -> back to pending with a future visibility.
    out = QueueBusService.fail(GROUP, QUEUE, m["id"], error_message="boom")
    assert out["status"] == QueueMessage.STATUS_PENDING
    assert out["visible_after"] > out["created_at"]
    assert "boom" in out["error_message"]


def test_dead_letter_on_exhaustion(fresh_db):
    _ensure()
    QueueBusService.send(GROUP, QUEUE, {"n": 1}, max_attempts=1)
    m = QueueBusService.receive(GROUP, QUEUE)[0]
    out = QueueBusService.fail(GROUP, QUEUE, m["id"], error_message="dead")
    assert out["status"] == QueueMessage.STATUS_DEAD_LETTER


def test_requeue_dead_letter(fresh_db):
    _ensure()
    QueueBusService.send(GROUP, QUEUE, {"n": 1}, max_attempts=1)
    m = QueueBusService.receive(GROUP, QUEUE)[0]
    QueueBusService.fail(GROUP, QUEUE, m["id"])
    out = QueueBusService.requeue(GROUP, QUEUE, m["id"])
    assert out["status"] == QueueMessage.STATUS_PENDING
    # Now receivable again.
    assert len(QueueBusService.receive(GROUP, QUEUE)) == 1


def test_visibility_timeout_reclaim(fresh_db):
    _ensure()
    QueueBusService.send(GROUP, QUEUE, {"n": 1})
    m = QueueBusService.receive(GROUP, QUEUE, visibility_timeout_ms=0)[0]
    # In-flight with an already-lapsed deadline: reap flips it back to pending.
    reaped = QueueBusService.reap_expired(GROUP, QUEUE)
    assert reaped == 1
    again = QueueBusService.receive(GROUP, QUEUE)
    assert len(again) == 1
    assert again[0]["id"] == m["id"]
    assert again[0]["attempts"] == 2  # re-claimed increments the attempt count


def test_delayed_delivery(fresh_db):
    _ensure()
    QueueBusService.send(GROUP, QUEUE, {"n": 1}, delay_ms=60000)
    # Not yet visible.
    assert QueueBusService.receive(GROUP, QUEUE) == []


def test_stats(fresh_db):
    _ensure()
    QueueBusService.send(GROUP, QUEUE, {"n": 1})
    QueueBusService.send(GROUP, QUEUE, {"n": 2})
    stats = QueueBusService.get_stats(GROUP, QUEUE)
    assert stats["messages"][QueueMessage.STATUS_PENDING] == 2
    assert stats["total"] == 2


def test_unknown_queue_raises(fresh_db):
    try:
        QueueBusService.send("nope", "nope", {})
        assert False, "expected QueueBusError"
    except QueueBusError as e:
        assert e.status_code == 404
