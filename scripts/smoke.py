"""Exercise the full HTTP product flow and delete the temporary test account."""

import argparse
import json
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    token: str | None = None

    def request(
        path: str, method: str = "GET", body: object = None, binary: bytes | None = None
    ) -> Any:
        headers = {"Authorization": "Bearer " + token} if token else {}
        data = (
            binary
            if binary is not None
            else json.dumps(body).encode()
            if body is not None
            else None
        )
        if data is not None:
            headers["Content-Type"] = "image/png" if binary is not None else "application/json"
        with urlopen(
            Request(base + path, data=data, headers=headers, method=method), timeout=30
        ) as response:
            content = response.read()
            return (
                json.loads(content)
                if content and response.headers.get_content_type() == "application/json"
                else content
            )

    assert request("/api/v1/health")["status"] == "ok"
    library = request("/api/v1/circuit-library")
    assert len(library) == 3
    account = request(
        "/api/v1/auth/register",
        "POST",
        {
            "email": f"smoke-{secrets.token_hex(8)}@example.com",
            "password": secrets.token_urlsafe(24),
        },
    )
    token = account["access_token"]
    try:
        project = request("/api/v1/projects", "POST", {"name": "Isolated HTTP smoke check"})
        circuit = next(circuit for circuit in library if circuit["name"] == "Series LED")
        version = request(f"/api/v1/projects/{project['id']}/circuits", "POST", circuit)
        plan = request("/api/v1/plans", "POST", {"circuit_version_id": version["id"]})
        assert (
            plan["plan"]["validation"]["valid"] and not plan["plan"]["validation"]["ready_to_build"]
        )
        assert request(f"/api/v1/plans/{plan['id']}/steps")
        ticket = request("/api/v1/images/uploads", "POST", {"project_id": project["id"]})
        image_bytes = (
            Path(__file__).resolve().parents[1]
            / "frontend/tests/fixtures/synthetic-calibration.png"
        ).read_bytes()
        image = request(ticket["upload_url"], "PUT", binary=image_bytes)
        assert not image["consent_for_training"]
        assert request(f"/api/v1/images/{image['id']}/content")
        run = request(
            "/api/v1/verification-runs",
            "POST",
            {
                "plan_id": plan["id"],
                "image_id": image["id"],
                "calibration_points": [
                    {"hole_id": hole, "x": x, "y": y}
                    for hole, x, y in [
                        ("A1", 80, 40),
                        ("J1", 540, 40),
                        ("J63", 540, 440),
                        ("A63", 80, 440),
                    ]
                ],
            },
        )
        for _ in range(60):
            report = request(f"/api/v1/verification-runs/{run['id']}")
            if report["status"] not in {"pending", "running"}:
                break
            time.sleep(0.5)
        assert report["status"] == "needs_confirmation", report
        assert not report["electrically_verified"]
        assert not report["results"]["component_detection_available"]
        exported = request(f"/api/v1/projects/{project['id']}/export")
        assert exported["verification_runs"] and exported["photo_downloads"]
        print(
            "Full HTTP workflow passed: account, project, circuit, plan, steps, "
            "private photo, calibration, export."
        )
    finally:
        request("/api/v1/auth/account", "DELETE")
    print(
        "Temporary account and owned resources deleted. "
        "No electrical or real-photo ML accuracy claimed."
    )


if __name__ == "__main__":
    main()
