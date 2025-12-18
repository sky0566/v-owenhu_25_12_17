import time
import uuid


class TransientError(Exception):
    pass


class PermanentError(Exception):
    pass


class CalendarMock:
    def __init__(self, mode: str = "success", fail_times: int = 0, delay: float = 0.0):
        # mode: success, transient, permanent
        self.mode = mode
        self.fail_times = fail_times
        self.calls = 0
        self.delay = delay

    def create_event(self, payload: dict) -> dict:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.mode == "success":
            return {"calendar_id": str(uuid.uuid4()), "status": "ok"}
        if self.mode == "transient":
            if self.calls <= self.fail_times:
                raise TransientError("temporary network")
            return {"calendar_id": str(uuid.uuid4()), "status": "ok"}
        if self.mode == "permanent":
            raise PermanentError("invalid payload")
        # fallback
        return {"calendar_id": str(uuid.uuid4()), "status": "ok"}

    # expose errors so callers can catch them
    TransientError = TransientError
    PermanentError = PermanentError
