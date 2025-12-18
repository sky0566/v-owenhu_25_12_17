import time
import logging
import uuid
from typing import Any, Dict, Optional, Callable

logger = logging.getLogger("appointment_v2")
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message_id)s %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


def mask_sensitive(data: Dict[str, Any]) -> Dict[str, Any]:
    d = dict(data)
    if "email" in d:
        d["email"] = "***REDACTED***"
    return d


class CircuitBreaker:
    def __init__(self, max_failures: int = 3, reset_timeout: float = 2.0):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.opened_at = None

    def record_success(self):
        self.failures = 0
        self.opened_at = None

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.max_failures:
            self.opened_at = time.monotonic()

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at > self.reset_timeout:
            # half-open
            self.failures = 0
            self.opened_at = None
            return False
        return True


class AppointmentService:
    def __init__(self, calendar_client: Any):
        self.calendar = calendar_client
        self.db: Dict[str, Dict[str, Any]] = {}
        self.idempotency: Dict[str, Any] = {}
        self.outbox: list[Dict[str, Any]] = []
        self.circuit = CircuitBreaker()

    def _log(self, level: str, msg: str, message_id: Optional[str] = None, **kwargs):
        extra = {"message_id": message_id or "-"}
        logger.log(getattr(logging, level.upper()), f"{msg} | {mask_sensitive(kwargs)}", extra=extra)

    def create_appointment(self, payload: Dict[str, Any], idempotency_key: Optional[str] = None, max_retries: int = 3, backoff: float = 0.01) -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        self._log("info", "create_appointment: received", message_id=request_id, payload=payload, idempotency_key=idempotency_key)

        if idempotency_key:
            if idempotency_key in self.idempotency:
                self._log("info", "idempotent replay", message_id=request_id, idempotency_key=idempotency_key)
                return self.idempotency[idempotency_key]

        if self.circuit.is_open():
            self._log("warning", "circuit open - fast-fail to calendar", message_id=request_id)
            # create local appointment with pending external state
            appt = self._create_local(payload, external_state="PENDING")
            # put outbox message
            self.outbox.append({"type": "create_calendar", "payload": appt, "status": "pending"})
            result = {"status": "pending", "appointment": appt}
            if idempotency_key:
                self.idempotency[idempotency_key] = result
            return result

        # attempt to create in external calendar with retries
        attempts = 0
        while attempts <= max_retries:
            try:
                cal_resp = self.calendar.create_event(payload)
                self.circuit.record_success()
                appt = self._create_local(payload, external_state="CONFIRMED", external_id=cal_resp.get("calendar_id"))
                result = {"status": "confirmed", "appointment": appt}
                if idempotency_key:
                    self.idempotency[idempotency_key] = result
                return result
            except self.calendar.TransientError as e:
                attempts += 1
                self.circuit.record_failure()
                self._log("warning", "transient calendar error - retrying", message_id=request_id, attempt=attempts, error=str(e))
                time.sleep(backoff * attempts)
                continue
            except self.calendar.PermanentError as e:
                self.circuit.record_failure()
                self._log("error", "permanent calendar error - giving up", message_id=request_id, error=str(e))
                appt = self._create_local(payload, external_state="FAILED")
                self.outbox.append({"type": "create_calendar", "payload": appt, "status": "failed"})
                result = {"status": "failed", "appointment": appt}
                if idempotency_key:
                    self.idempotency[idempotency_key] = result
                return result
        # retries exhausted - open circuit
        # record an additional failure so the circuit breaker transitions to open
        self.circuit.record_failure()
        self._log("error", "calendar retries exhausted - marking pending and opening circuit", message_id=request_id)
        appt = self._create_local(payload, external_state="PENDING")
        self.outbox.append({"type": "create_calendar", "payload": appt, "status": "pending"})
        result = {"status": "pending", "appointment": appt}
        if idempotency_key:
            self.idempotency[idempotency_key] = result
        return result

    def _create_local(self, payload: Dict[str, Any], external_state: str = "PENDING", external_id: Optional[str] = None) -> Dict[str, Any]:
        appt_id = str(uuid.uuid4())
        record = {
            "id": appt_id,
            "title": payload.get("title"),
            "owner": payload.get("owner"),
            "external_state": external_state,
            "external_id": external_id,
            "raw": payload,
        }
        self.db[appt_id] = record
        self._log("info", "local appointment created", message_id=appt_id, appointment=record)
        return record

    def flush_outbox(self, sender: Callable[[Dict[str, Any]], Any]) -> list[Dict[str, Any]]:
        results = []
        for msg in list(self.outbox):
            try:
                res = sender(msg)
                msg["status"] = "sent"
                results.append({"msg": msg, "resp": res})
                self.outbox.remove(msg)
            except Exception as e:
                msg["status"] = "failed"
                self._log("warning", "outbox send failed", message_id="outbox", error=str(e))
        return results


if __name__ == "__main__":
    print("AppointmentService module")
