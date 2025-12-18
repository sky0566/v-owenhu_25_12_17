"""Mock provider implementations to simulate immediate, delayed, flaky, and failing backends."""
import time
from src.appointments import ProviderError


def call(name, payload, timeout=0.5):
    if name == 'immediate':
        return {'status': 'ok'}
    if name == 'delayed':
        # simulate a backend that takes longer than timeout
        time.sleep(timeout + 0.1)
        # we still return success (but the caller may have timed out)
        return {'status': 'ok', 'delayed': True}
    if name == 'flaky':
        # alternate between fail and success using id hash
        if hash(payload.get('id','')) % 2 == 0:
            raise ProviderError('5xx')
        return {'status': 'ok'}
    if name == 'always_fail':
        raise ProviderError('permanent-5xx')
    raise ProviderError('unknown-provider')
