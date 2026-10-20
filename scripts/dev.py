"""Run backend, background worker, and frontend together; Ctrl+C stops owned processes."""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Install locked dependencies first")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--node-bin", type=Path)
    parser.add_argument("--pnpm-bin", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    if args.node_bin:
        environment["PATH"] = str(args.node_bin.parent) + os.pathsep + environment["PATH"]
    uv = shutil.which("uv", path=environment["PATH"])
    pnpm = str(args.pnpm_bin) if args.pnpm_bin else shutil.which("pnpm", path=environment["PATH"])
    if not uv or not pnpm or not shutil.which("node", path=environment["PATH"]):
        parser.error("Install uv, Node.js 24, and pnpm 11.25.0, or pass --node-bin/--pnpm-bin.")
    if args.install:
        subprocess.run([uv, "sync", "--locked"], cwd=root, env=environment, check=True)
        subprocess.run(
            [pnpm, "install", "--frozen-lockfile"],
            cwd=root / "frontend",
            env=environment,
            check=True,
        )
    environment.setdefault("NEXT_TELEMETRY_DISABLED", "1")
    environment["CIRCUITPILOT_API_URL"] = f"http://127.0.0.1:{args.backend_port}"
    environment.setdefault(
        "CIRCUITPILOT_ALLOWED_ORIGINS",
        json.dumps(
            [
                f"http://127.0.0.1:{args.frontend_port}",
                f"http://localhost:{args.frontend_port}",
            ]
        ),
    )
    commands = [
        (
            [
                uv,
                "run",
                "--locked",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.backend_port),
                "--no-access-log",
            ],
            root,
        ),
        ([uv, "run", "--locked", "python", "-m", "app.worker"], root),
        ([pnpm, "dev", "--port", str(args.frontend_port)], root / "frontend"),
    ]
    children: list[subprocess.Popen[bytes]] = []
    try:
        for command, directory in commands:
            if len(children) == 1:
                for _ in range(60):
                    if children[0].poll() is not None:
                        raise RuntimeError(
                            "Backend did not start; check the error above or port usage."
                        )
                    try:
                        with urlopen(
                            f"http://127.0.0.1:{args.backend_port}/api/v1/health", timeout=1
                        ):
                            break
                    except (URLError, TimeoutError):
                        time.sleep(0.5)
                else:
                    raise RuntimeError("Backend startup timed out.")
            children.append(
                subprocess.Popen(command, cwd=directory, env=environment, start_new_session=True)
            )
        print(
            (f"\nCircuitPilot: http://127.0.0.1:{args.frontend_port}\n"
             f"API docs: http://127.0.0.1:{args.backend_port}/docs\n"
             "Ctrl+C stops this development session.\n"),
            flush=True,
        )
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise RuntimeError("A development service exited. Check its output above.")
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
    return


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
