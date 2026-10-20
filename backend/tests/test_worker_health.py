import os
import time

from app.worker import worker_healthy


def test_worker_health_requires_recent_successful_loop_heartbeat(tmp_path):
    assert not worker_healthy(tmp_path)
    heartbeat = tmp_path / ".worker-heartbeat"
    heartbeat.touch()
    assert worker_healthy(tmp_path)
    stale = time.time() - 180
    os.utime(heartbeat, (stale, stale))
    assert not worker_healthy(tmp_path)
    future = time.time() + 3600
    os.utime(heartbeat, (future, future))
    assert not worker_healthy(tmp_path)
