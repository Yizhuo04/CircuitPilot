"""Supervise the single-instance hosted web/API/worker bundle.

The hosting disk can only be mounted in one service. All three processes share it;
any process exit shuts down the bundle so the platform can restart it consistently.
"""

import contextlib
import json
import os
import pwd
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from app.config import Settings


def prepare_environment(source: Mapping[str, str]) -> dict[str, str]:
    environment = dict(source)
    environment.setdefault("PORT", "10000")
    port = int(environment["PORT"])
    if not 1024 <= port <= 65535 or port == 8000:
        raise ValueError("PORT must be an unprivileged port other than internal API port 8000.")
    environment.setdefault("CIRCUITPILOT_ENVIRONMENT", "production")
    environment.setdefault("CIRCUITPILOT_COOKIE_SECURE", "true")
    environment.setdefault("CIRCUITPILOT_AUTO_CREATE_SCHEMA", "false")
    environment.setdefault("CIRCUITPILOT_REQUIRE_WORKER_HEALTH", "true")
    environment.setdefault("CIRCUITPILOT_STORAGE_DIR", "/var/data/uploads")
    environment.setdefault("NODE_ENV", "production")
    environment.setdefault("NEXT_TELEMETRY_DISABLED", "1")
    environment["HOSTNAME"] = "0.0.0.0"
    if "CIRCUITPILOT_ALLOWED_ORIGINS" not in environment:
        origin = environment.get("RENDER_EXTERNAL_URL", "").rstrip("/")
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Set an exact HTTPS origin or supply RENDER_EXTERNAL_URL.")
        environment["CIRCUITPILOT_ALLOWED_ORIGINS"] = json.dumps([origin])
    # Validate before launching anything; never print environment secrets on failure.
    Settings.model_validate(
        {
            key.removeprefix("CIRCUITPILOT_").lower(): json.loads(value)
            if key == "CIRCUITPILOT_ALLOWED_ORIGINS"
            else value
            for key, value in environment.items()
            if key.startswith("CIRCUITPILOT_")
        },
    )
    return environment


def initialize_storage(directory: Path) -> None:
    os.umask(0o077)
    if os.geteuid() == 0:
        # Only this fixed mount is initialized with elevated container privileges.
        if (
            directory != Path("/var/data/uploads")
            or directory.is_symlink()
            or directory.parent.is_symlink()
        ):
            raise ValueError("Root bootstrap only initializes /var/data/uploads.")
        account = pwd.getpwnam("circuitpilot")
        directory.parent.mkdir(exist_ok=True)
        directory.parent.chmod(0o755)
        directory.mkdir(exist_ok=True)
        os.chown(directory, account.pw_uid, account.pw_gid)
        directory.chmod(0o700)
        os.initgroups(account.pw_name, account.pw_gid)
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
        os.environ["HOME"] = account.pw_dir
    else:
        directory.mkdir(parents=True, exist_ok=True)
    probe = directory / ".startup-write-check"
    probe.write_bytes(b"")
    probe.unlink()


def stop_children(children: list[subprocess.Popen[bytes]]) -> None:
    for child in children:
        if child.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGTERM)
    deadline = time.monotonic() + 20
    for child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def main() -> int:
    children: list[subprocess.Popen[bytes]] = []
    stopping = False

    def shutdown(signum: int, frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        environment = prepare_environment(os.environ)
        initialize_storage(Path(environment["CIRCUITPILOT_STORAGE_DIR"]))
        environment["HOME"] = os.environ["HOME"]
        # Apply migrations once before any serving/job processing in this instance.
        migration = subprocess.Popen(
            ["alembic", "upgrade", "head"], env=environment, start_new_session=True
        )
        children.append(migration)
        while migration.poll() is None and not stopping:
            time.sleep(0.2)
        if stopping:
            return 0
        if migration.returncode != 0:
            raise RuntimeError("Database migrations failed; services were not started.")
        children.clear()
        commands = [
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
            ],
            [sys.executable, "-m", "app.worker"],
            ["node", "web/server.js"],
        ]
        for command in commands:
            if stopping:
                return 0
            children.append(subprocess.Popen(command, env=environment, start_new_session=True))
        while not stopping:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A hosted service exited; restarting the bundle is required.")
            time.sleep(0.5)
        return 0
    except (ValueError, OSError, RuntimeError):
        # Validation/driver exceptions can contain DSNs. Log only a generic summary.
        print(
            "Hosted startup failed. Check configuration, disk access and database health.",
            file=sys.stderr,
            flush=True,
        )
        return 1
    finally:
        stop_children(children)


if __name__ == "__main__":
    raise SystemExit(main())
