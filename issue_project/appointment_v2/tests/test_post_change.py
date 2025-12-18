import time
import json
import pytest
from appointment_v2.src import service
from appointment_v2.mocks.calendar_api import CalendarMock


def make_payload(i=1):
    return {"title": f"appt-{i}", "owner": {"name": "Alice", "email": "alice@example.com"}}


def test_healthy_path():
    cal = CalendarMock(mode="success")
    svc = service.AppointmentService(cal)
    res = svc.create_appointment(make_payload(), idempotency_key="k1")
    assert res["status"] == "confirmed"
    assert len(svc.db) == 1
    assert svc.outbox == []


def test_idempotency():
    cal = CalendarMock(mode="success")
    svc = service.AppointmentService(cal)
    res1 = svc.create_appointment(make_payload(2), idempotency_key="idem-1")
    res2 = svc.create_appointment(make_payload(2), idempotency_key="idem-1")
    assert res1 == res2
    assert len(svc.db) == 1


def test_retry_transient_then_success():
    cal = CalendarMock(mode="transient", fail_times=1)
    svc = service.AppointmentService(cal)
    res = svc.create_appointment(make_payload(3), idempotency_key="retry-1", max_retries=3, backoff=0)
    assert res["status"] == "confirmed"
    assert cal.calls >= 2


def test_permanent_failure_creates_outbox():
    cal = CalendarMock(mode="permanent")
    svc = service.AppointmentService(cal)
    res = svc.create_appointment(make_payload(4), idempotency_key="perm-1", max_retries=1, backoff=0)
    assert res["status"] == "failed"
    assert len(svc.outbox) == 1
    assert svc.outbox[0]["status"] == "failed"


def test_circuit_breaker_opens_after_exhaustion():
    cal = CalendarMock(mode="transient", fail_times=10)
    svc = service.AppointmentService(cal)
    # first call will exhaust retries and mark pending
    res1 = svc.create_appointment(make_payload(5), idempotency_key="cb-1", max_retries=1, backoff=0)
    assert res1["status"] == "pending"
    # circuit should now be open (failures recorded)
    assert svc.circuit.is_open() is True
    # subsequent call should fast-fail without calling calendar
    cal.calls = 0
    res2 = svc.create_appointment(make_payload(6), idempotency_key="cb-2", max_retries=1, backoff=0)
    assert res2["status"] == "pending"
    assert cal.calls == 0


def test_flush_outbox_sends():
    cal = CalendarMock(mode="permanent")
    svc = service.AppointmentService(cal)
    _ = svc.create_appointment(make_payload(7), idempotency_key="outbox-1", max_retries=1, backoff=0)
    assert len(svc.outbox) == 1

    def sender(msg):
        return {"sent": True}

    results = svc.flush_outbox(sender)
    assert len(results) == 1
    assert svc.outbox == []
