import json
import time
from appointment_v2.mocks.calendar_api import CalendarMock
from appointment_v2.src.service import AppointmentService


def run():
    with open("appointment_v2/data/test_data.json") as f:
        cases = json.load(f)
    results = {}
    svc = None
    for c in cases:
        mode = c.get("mode", "success")
        fail_times = c.get("fail_times", 0)
        cal = CalendarMock(mode=mode, fail_times=fail_times, delay=0)
        svc = AppointmentService(cal)
        start = time.time()
        res = svc.create_appointment(c["payload"], idempotency_key=c.get("idempotency"), max_retries=2, backoff=0)
        duration = time.time() - start
        results[c["id"]] = {
            "status": res["status"],
            "duration_ms": round(duration * 1000, 2),
            "cal_calls": cal.calls,
            "outbox_len": len(svc.outbox)
        }
    with open("appointment_v2/results/results_post.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Wrote appointment_v2/results/results_post.json")


if __name__ == '__main__':
    run()
