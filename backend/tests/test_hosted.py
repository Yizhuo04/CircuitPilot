import os
import signal
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app import hosted
from app.config import Settings
from sqlalchemy.exc import OperationalError


def deployment_env():
    return {
        "CIRCUITPILOT_DATABASE_URL": "postgresql://user:password@postgres/circuitpilot",
        "RENDER_EXTERNAL_URL": "https://circuitpilot-example.onrender.com/",
    }


def test_hosted_environment_uses_https_secure_cookies_and_durable_worker():
    source = deployment_env()
    environment = hosted.prepare_environment(source)
    assert environment["CIRCUITPILOT_ALLOWED_ORIGINS"] == (
        '["https://circuitpilot-example.onrender.com"]'
    )
    assert environment["CIRCUITPILOT_COOKIE_SECURE"] == "true"
    assert environment["CIRCUITPILOT_AUTO_CREATE_SCHEMA"] == "false"
    assert environment["CIRCUITPILOT_REQUIRE_WORKER_HEALTH"] == "true"
    assert environment["HOSTNAME"] == "0.0.0.0"
    assert "PORT" not in source


@pytest.mark.parametrize("url", ["postgres://", "postgresql://", "postgresql+psycopg://"])
def test_managed_postgres_urls_use_installed_driver(url):
    assert Settings(database_url=url + "u:p@host/db").database_url == (
        "postgresql+psycopg://u:p@host/db"
    )


@pytest.mark.parametrize("port", ["80", "8000", "65536", "invalid"])
def test_hosted_port_rejects_privileged_or_conflicting_values(port):
    with pytest.raises(ValueError):
        hosted.prepare_environment({**deployment_env(), "PORT": port})


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "http://example.com",
        "https://x/path",
        "https://u:p@x",
        "https://x?q=1",
        "https://x#frag",
    ],
)
def test_hosted_default_origin_fails_closed(origin):
    with pytest.raises(ValueError):
        hosted.prepare_environment({**deployment_env(), "RENDER_EXTERNAL_URL": origin})


def test_explicit_origins_support_a_custom_domain():
    environment = hosted.prepare_environment(
        {
            **deployment_env(),
            "CIRCUITPILOT_ALLOWED_ORIGINS": '["https://circuits.example.com"]',
        }
    )
    assert environment["CIRCUITPILOT_ALLOWED_ORIGINS"] == '["https://circuits.example.com"]'


def test_readiness_reports_database_and_worker_outages(client, monkeypatch):
    assert client.get("/api/v1/health/ready").status_code == 200
    settings = client.app.state.settings
    settings.require_worker_health = True
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    (settings.storage_dir / ".worker-heartbeat").touch()
    assert client.get("/api/v1/health/ready").status_code == 200
    broken = Mock(side_effect=OperationalError("select", {}, Exception("offline")))
    monkeypatch.setattr(client.app.state, "sessions", broken)
    assert client.get("/api/v1/health/ready").status_code == 503
    assert client.get("/api/v1/health").status_code == 200


def test_non_root_bootstrap_checks_storage_without_leaving_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(hosted.os, "geteuid", lambda: 10001)
    previous = os.umask(0o077)
    try:
        hosted.initialize_storage(tmp_path / "uploads")
        assert list((tmp_path / "uploads").iterdir()) == []
    finally:
        os.umask(previous)


def test_root_bootstrap_does_not_chown_an_arbitrary_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(hosted.os, "geteuid", lambda: 0)
    previous = os.umask(0o077)
    try:
        with pytest.raises(ValueError, match="Root bootstrap"):
            hosted.initialize_storage(tmp_path)
    finally:
        os.umask(previous)


@pytest.mark.parametrize("failure", ["migration", "service", "shutdown"])
def test_supervisor_stops_owned_groups_on_failure_or_sigterm(monkeypatch, failure):
    children = []
    signals = {}
    monkeypatch.setattr(
        hosted.signal, "signal", lambda signum, handler: signals.update({signum: handler})
    )
    monkeypatch.setattr(
        hosted,
        "prepare_environment",
        lambda _: {
            "CIRCUITPILOT_STORAGE_DIR": "/unused",
            "HOME": "/unused",
        },
    )
    monkeypatch.setattr(hosted, "initialize_storage", lambda _: None)
    monkeypatch.setenv("HOME", "/unused")

    def spawn(command, **kwargs):
        migration = command[0] == "alembic"
        code = (
            (1 if failure == "migration" else 0)
            if migration
            else (1 if failure == "service" and len(children) == 1 else None)
        )
        child = SimpleNamespace(
            pid=100 + len(children),
            returncode=code,
            poll=lambda: code,
            wait=Mock(return_value=code),
        )
        children.append(child)
        return child

    monkeypatch.setattr(hosted.subprocess, "Popen", spawn)
    monkeypatch.setattr(hosted.time, "sleep", lambda _: signals[signal.SIGTERM](15, None))
    killed = []
    monkeypatch.setattr(hosted.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    result = hosted.main()
    assert result == (0 if failure == "shutdown" else 1)
    assert len(children) == (1 if failure == "migration" else 4)
    for child in children[1:]:
        if child.poll() is None:
            assert (child.pid, signal.SIGTERM) in killed


def test_shutdown_escalates_only_after_grace_period(monkeypatch):
    child = Mock(pid=123)
    child.poll.return_value = None
    child.wait.side_effect = [subprocess.TimeoutExpired("child", 20), 0]
    killed = []
    monkeypatch.setattr(hosted.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    hosted.stop_children([child])
    assert killed == [(123, signal.SIGTERM), (123, signal.SIGKILL)]
