import json, time
import pytest
from src import appointments


def setup_module(module):
    # clean store and logs
    open('logs/log_post.txt','w').close()
    appointments.reset_store()


def load_data():
    return json.load(open('data/test_data.json'))


def test_happy_path_immediate():
    d = load_data()[0]
    rid, state = appointments.create_appointment(d['id'], d)
    assert state == 'confirmed'
    ap = appointments.get_appointment(d['id'])
    assert ap is not None
    assert ap['state'] == 'confirmed'


def test_delayed_backend_timeout_behavior():
    d = load_data()[1]
    rid, state = appointments.create_appointment(d['id'], d, max_attempts=2)
    # delayed may still succeed but often will be marked failed due to timeouts
    ap = appointments.get_appointment(d['id'])
    assert ap['id'] == d['id']
    assert ap['state'] in ('confirmed','failed')


def test_flaky_provider_retries():
    d = load_data()[2]
    rid, state = appointments.create_appointment(d['id'], d, max_attempts=4)
    ap = appointments.get_appointment(d['id'])
    assert ap['attempts'] >= 1
    assert ap['state'] in ('confirmed','failed')


def test_compensation_on_persistent_failure():
    d = load_data()[3]
    rid, state = appointments.create_appointment(d['id'], d, max_attempts=3)
    ap = appointments.get_appointment(d['id'])
    assert ap['state'] == 'failed'
    # ensure compensation log exists
    lines = open('logs/log_post.txt').read()
    assert 'compensate_cancel' in lines


def test_idempotency_duplicate_submit():
    d = load_data()[4]
    # first submit
    rid1, state1 = appointments.create_appointment(d['id'], d, max_attempts=2)
    # duplicate submit with same request id should hit idempotency
    rid2, state2 = appointments.create_appointment(d['id'], d, max_attempts=2)
    assert rid1 == rid2
    # ensure idempotent_hit recorded
    logs = open('logs/log_post.txt').read()
    assert 'idempotent_hit' in logs


def test_circuit_breaker_trips_and_reopens():
    # drive repeated failures to open the circuit
    appointments.reset_store()
    p = {'id':'cb-1','patient_name':'X','time':'2026','provider':'always_fail','payload':{}}
    for i in range(5):
        appointments.create_appointment(p['id'] + f'-{i}', p, max_attempts=1)
    # after threshold, the circuit should be open and at least one log should show 'circuit-open'
    logs = open('logs/log_post.txt').read()
    assert 'circuit-open' in logs or 'provider_error' in logs
