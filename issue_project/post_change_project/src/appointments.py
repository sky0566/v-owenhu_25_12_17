"""Minimal appointment service runtime for integration tests.
Features:
- idempotency by request_id
- simple retry with backoff
- timeout and circuit-breaker (very small window)
- compensation: cancel appointment on persistent failure
- structured logging with masked sensitive fields
"""
import json
import time
import threading
from collections import defaultdict

STORE_FILE = 'post_change_store.json'

# in-memory circuit tracker
CIRCUIT = {'fail_count': 0, 'open_until': 0}
CIRCUIT_THRESHOLD = 3
CIRCUIT_OPEN_SECONDS = 2

# simple in-memory store persisted to disk
try:
    with open(STORE_FILE, 'r') as f:
        STORE = json.load(f)
except Exception:
    STORE = {'appointments': {}, 'outbox': []}

lock = threading.Lock()


def _persist():
    with open(STORE_FILE, 'w') as f:
        json.dump(STORE, f, indent=2)


def _log(evt, request_id, appointment_id=None, extra=None):
    # mask patient_name and any 'email'
    if extra and 'patient_name' in extra:
        extra = dict(extra)
        extra['patient_name'] = extra['patient_name'][:1] + '***'
        if 'email' in extra:
            extra['email'] = '***'
    entry = {
        'time': time.time(), 'evt': evt, 'request_id': request_id,
        'appointment_id': appointment_id, 'extra': extra
    }
    with open('logs/log_post.txt', 'a') as f:
        f.write(json.dumps(entry) + '\n')


class ProviderError(Exception):
    pass


# Provider dispatch to mocks
import requests


def _call_provider(provider, payload, timeout=0.5):
    """Call the mock provider endpoints implemented in mocks/providers.py (local import)"""
    # Circuit breaker short-circuits
    now = time.time()
    if CIRCUIT['open_until'] > now:
        raise ProviderError('circuit-open')
    try:
        from mocks import providers
        resp = providers.call(provider, payload, timeout=timeout)
        # success => reset fail count
        CIRCUIT['fail_count'] = 0
        return resp
    except ProviderError:
        CIRCUIT['fail_count'] += 1
        if CIRCUIT['fail_count'] >= CIRCUIT_THRESHOLD:
            CIRCUIT['open_until'] = time.time() + CIRCUIT_OPEN_SECONDS
        raise


def create_appointment(request_id, payload, max_attempts=3):
    """Create appointment with idempotency and retry/backoff. Returns appointment_id and state."""
    _log('create_request', request_id, extra=payload)
    with lock:
        if request_id in STORE['appointments']:
            _log('idempotent_hit', request_id, appointment_id=STORE['appointments'][request_id]['id'])
            return STORE['appointments'][request_id]['id'], STORE['appointments'][request_id]['state']
        # allocate
        appt = {'id': payload['id'], 'state': 'pending', 'payload': payload, 'attempts': 0}
        STORE['appointments'][request_id] = appt
        STORE['outbox'].append({'type': 'create', 'request_id': request_id, 'payload': payload})
        _persist()

    # try to deliver with retries
    backoff = 0.05
    for attempt in range(1, max_attempts + 1):
        try:
            _log('provider_call', request_id, appointment_id=appt['id'], extra={'attempt': attempt})
            _call_provider(payload['provider'], payload)
            with lock:
                STORE['appointments'][request_id]['state'] = 'confirmed'
                STORE['appointments'][request_id]['attempts'] = attempt
                _persist()
            _log('confirmed', request_id, appointment_id=appt['id'])
            return appt['id'], 'confirmed'
        except ProviderError as e:
            _log('provider_error', request_id, appointment_id=appt['id'], extra={'err': str(e), 'attempt': attempt})
            # record attempt count even on failure so observability and tests can see retries
            with lock:
                STORE['appointments'][request_id]['attempts'] = attempt
                _persist()
            time.sleep(backoff)
            backoff *= 2
            continue
    # After attempts -> compensate/cancel
    with lock:
        STORE['appointments'][request_id]['state'] = 'failed'
        _persist()
    _log('compensate_cancel', request_id, appointment_id=appt['id'])
    return appt['id'], 'failed'


def get_appointment(request_id):
    with lock:
        return STORE['appointments'].get(request_id)


def reset_store():
    global STORE
    with lock:
        STORE = {'appointments': {}, 'outbox': []}
        _persist()
    # reset circuit
    CIRCUIT['fail_count'] = 0
    CIRCUIT['open_until'] = 0
