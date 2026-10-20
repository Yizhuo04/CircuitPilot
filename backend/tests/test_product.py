import io
from datetime import timedelta

import pytest
from app.models import ImageRecord, LoginSession, UploadTicket, now
from app.security import hash_password, token_hash, verify_password
from app.worker import maintenance, process_job
from PIL import Image

API = "/api/v1"


@pytest.fixture
def account(client):
    response = client.post(
        API + "/auth/register",
        json={"email": "builder@example.com", "password": "a-long-test-password"},
    )
    assert response.status_code == 201, response.text
    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
    return client


@pytest.fixture
def project_case(account, series_led):
    project = account.post(API + "/projects", json={"name": "Series LED project"}).json()
    version = account.post(API + f"/projects/{project['id']}/circuits", json=series_led).json()
    response = account.post(API + "/plans", json={"circuit_version_id": version["id"]})
    assert response.status_code == 201, response.text
    return account, project, version, response.json()


def png(width=640, height=480):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def upload(account, project_id, consent=False):
    ticket = account.post(
        API + "/images/uploads", json={"project_id": project_id, "consent_for_training": consent}
    )
    assert ticket.status_code == 201, ticket.text
    response = account.put(
        ticket.json()["upload_url"], content=png(), headers={"Content-Type": "image/png"}
    )
    assert response.status_code == 201, response.text
    return response.json(), ticket.json()["upload_url"]


def calibration(plan_id, image_id):
    return {
        "plan_id": plan_id,
        "image_id": image_id,
        "calibration_points": [
            {"hole_id": "A1", "x": 80, "y": 40},
            {"hole_id": "J1", "x": 540, "y": 40},
            {"hole_id": "J63", "x": 540, "y": 440},
            {"hole_id": "A63", "x": 80, "y": 440},
        ],
    }


def test_password_hashes_are_salted_and_verified():
    first, second = hash_password("strong-password"), hash_password("strong-password")
    assert first != second
    assert verify_password("strong-password", first)
    assert not verify_password("incorrect-password", first)
    assert not verify_password("strong-password", "broken-hash")


def test_auth_lifecycle(client):
    credentials = {"email": "builder@example.com", "password": "a-long-test-password"}
    response = client.post(API + "/auth/register", json=credentials)
    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert client.get(API + "/auth/me").json()["email"] == credentials["email"]
    assert client.post(API + "/auth/register", json=credentials).status_code == 409
    assert (
        client.post(
            API + "/auth/login", json={**credentials, "password": "wrong-test-password"}
        ).status_code
        == 401
    )
    assert client.post(API + "/auth/logout", json={}).status_code == 403
    assert (
        client.post(
            API + "/auth/logout", json={}, headers={"Origin": "http://127.0.0.1:3000"}
        ).status_code
        == 204
    )
    assert client.get(API + "/auth/me").status_code == 401
    login = client.post(API + "/auth/login", json=credentials)
    assert login.status_code == 200
    with client.app.state.sessions() as db:
        record = db.get(LoginSession, token_hash(login.json()["access_token"]))
        record.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.get(API + "/auth/me").status_code == 401


def test_auth_rate_limit(client):
    for _ in range(10):
        assert (
            client.post(
                API + "/auth/login",
                json={"email": "unknown@example.com", "password": "valid-length-password"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            API + "/auth/login",
            json={"email": "unknown@example.com", "password": "valid-length-password"},
        ).status_code
        == 429
    )


def test_project_import_plan_retrieve_steps_and_explain(project_case, series_led):
    account, project, version, plan = project_case
    assert account.get(API + "/projects").json()[0]["id"] == project["id"]
    detail = account.get(API + f"/projects/{project['id']}").json()
    assert detail["circuits"][0]["circuit"]["name"] == "Series LED"
    assert detail["plans"][0]["id"] == plan["id"]
    fetched = account.get(API + f"/plans/{plan['id']}").json()
    assert fetched == plan
    assert fetched["plan"]["validation"]["valid"] is True
    assert fetched["plan"]["validation"]["ready_to_build"] is False
    steps = account.get(API + f"/plans/{plan['id']}/steps").json()
    assert [s["sequence"] for s in steps] == list(range(1, len(steps) + 1))
    explanation = account.post(
        API + "/assistant/messages", json={"plan_id": plan["id"], "step_sequence": 2}
    ).json()
    assert explanation["llm_used"] is False
    assert explanation["holes"] == steps[1]["holes"]
    assert (
        account.post(
            API + "/assistant/messages", json={"plan_id": plan["id"], "step_sequence": 999}
        ).status_code
        == 404
    )
    # Versions append; importing does not mutate earlier snapshots or plans.
    changed = {**series_led, "name": "Revision two"}
    other = account.post(API + f"/projects/{project['id']}/circuits", json=changed).json()
    assert other["id"] != version["id"]
    assert account.get(API + f"/plans/{plan['id']}").json() == plan
    exported = account.get(API + f"/projects/{project['id']}/export").json()
    assert exported["plan_contents"][0]["id"] == plan["id"]


def test_owners_are_isolated_for_every_resource(project_case):
    account, project, version, plan = project_case
    image, _ = upload(account, project["id"])
    run = account.post(API + "/verification-runs", json=calibration(plan["id"], image["id"])).json()
    other = account.post(
        API + "/auth/register",
        json={"email": "other@example.com", "password": "another-long-password"},
    ).json()
    account.headers["Authorization"] = "Bearer " + other["access_token"]
    assert account.get(API + "/projects").json() == []
    for path in [
        f"/projects/{project['id']}",
        f"/projects/{project['id']}/export",
        f"/plans/{plan['id']}",
        f"/plans/{plan['id']}/steps",
        f"/images/{image['id']}/content",
        f"/verification-runs/{run['id']}",
    ]:
        assert account.get(API + path).status_code == 404
    assert (
        account.post(API + "/plans", json={"circuit_version_id": version["id"]}).status_code == 404
    )
    assert (
        account.post(API + "/images/uploads", json={"project_id": project["id"]}).status_code == 404
    )
    assert account.delete(API + f"/projects/{project['id']}").status_code == 404


def test_invalid_netlist_is_not_saved(account, series_led):
    project = account.post(API + "/projects", json={"name": "Invalid circuit"}).json()
    series_led["nets"][0]["members"].append("MISSING.1")
    assert (
        account.post(API + f"/projects/{project['id']}/circuits", json=series_led).status_code
        == 422
    )
    assert account.get(API + f"/projects/{project['id']}").json()["circuits"] == []


def test_upload_single_use_privacy_annotation_consent_and_delete(project_case):
    account, project, _, plan = project_case
    image, url = upload(account, project["id"])
    assert not image["consent_for_training"]
    assert account.put(url, content=png()).status_code == 404
    content = account.get(API + f"/images/{image['id']}/content")
    assert content.status_code == 200 and content.headers["content-type"] == "image/png"
    annotation = {
        "setup_id": "physical-setup-1",
        "capture_session_id": "session-1",
        "review_status": "reviewed",
        "boxes": [{"class_name": "resistor", "x": 20, "y": 40, "width": 100, "height": 30}],
    }
    assert (
        account.post(API + f"/images/{image['id']}/annotations", json=annotation).status_code == 201
    )
    assert account.get(API + "/datasets/export").json()["images"] == []
    consented, _ = upload(account, project["id"], consent=True)
    assert (
        account.post(API + f"/images/{consented['id']}/annotations", json=annotation).status_code
        == 201
    )
    exported = account.get(API + "/datasets/export").json()
    assert [i["image_id"] for i in exported["images"]] == [consented["id"]]
    annotation["boxes"][0]["width"] = 10000
    assert (
        account.post(API + f"/images/{image['id']}/annotations", json=annotation).status_code == 422
    )
    assert account.delete(API + f"/images/{image['id']}").status_code == 204
    assert account.get(API + f"/images/{image['id']}/content").status_code == 404


def test_upload_rejects_invalid_images_and_expired_tickets(project_case):
    account, project, _, _ = project_case
    response = account.post(API + "/images/uploads", json={"project_id": project["id"]})
    url = response.json()["upload_url"]
    assert account.put(url, content=b"not-an-image").status_code == 422
    assert account.put(url, content=png(10, 10)).status_code == 422
    with account.app.state.sessions() as db:
        ticket = db.get(UploadTicket, token_hash(url.rsplit("/", 1)[-1]))
        ticket.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert account.put(url, content=png()).status_code == 404
    assert account.put(API + "/images/uploads/missing", content=png()).status_code == 404


def test_manual_calibration_is_uncertain_not_detection(project_case):
    account, project, _, plan = project_case
    image, _ = upload(account, project["id"])
    response = account.post(API + "/verification-runs", json=calibration(plan["id"], image["id"]))
    assert response.status_code == 202
    run = account.get(API + "/verification-runs/" + response.json()["id"]).json()
    assert run["status"] == "needs_confirmation", run
    assert run["electrically_verified"] is False
    assert run["results"]["component_detection_available"] is False
    assert len(run["results"]["holes"]) == 830
    assert run["results"]["holes"]["A1"] == {"x": 80.0, "y": 40.0}
    assert run["results"]["observations"] == []
    # Re-executing a claimed/completed job is a no-op.
    process_job(run["id"], account.app.state.sessions)
    assert account.get(API + "/verification-runs/" + run["id"]).json() == run


def test_degenerate_calibration_fails_and_cross_project_rejected(project_case):
    account, project, _, plan = project_case
    image, _ = upload(account, project["id"])
    request = calibration(plan["id"], image["id"])
    for point in request["calibration_points"]:
        point["y"] = 20
    created = account.post(API + "/verification-runs", json=request).json()
    assert account.get(API + "/verification-runs/" + created["id"]).json()["status"] == "failed"
    other_project = account.post(API + "/projects", json={"name": "Other project"}).json()
    other_image, _ = upload(account, other_project["id"])
    assert (
        account.post(
            API + "/verification-runs", json=calibration(plan["id"], other_image["id"])
        ).status_code
        == 409
    )
    assert account.get(API + "/verification-runs/missing").status_code == 404


def test_retention_and_interrupted_job_recovery(project_case):
    account, project, _, plan = project_case
    image, _ = upload(account, project["id"])
    with account.app.state.sessions() as db:
        stored = db.get(ImageRecord, image["id"])
        key = stored.storage_key
        stored.expires_at = now() - timedelta(days=1)
        db.commit()
    assert account.get(API + f"/images/{image['id']}/content").status_code == 404
    maintenance(account.app.state.sessions, account.app.state.store)
    assert not account.app.state.store.path(key).exists()
    assert account.get(API + f"/projects/{project['id']}").json()["images"] == []


def test_pilot_measurements_are_recorded_not_fabricated(project_case):
    account, project, _, _ = project_case
    assert account.get(API + "/pilot-sessions").json() == []
    pilot = account.post(
        API + "/pilot-sessions", json={"project_id": project["id"], "condition": "guided"}
    ).json()
    result = account.post(
        API + f"/pilot-sessions/{pilot['id']}/complete", json={"error_count": 2, "help_count": 1}
    )
    assert result.status_code == 200 and result.json()["duration_seconds"] >= 0
    assert result.json()["error_count"] == 2
    assert (
        account.post(
            API + f"/pilot-sessions/{pilot['id']}/complete",
            json={"error_count": 0, "help_count": 0},
        ).status_code
        == 409
    )
    assert (
        account.post(
            API + "/pilot-sessions/missing/complete", json={"error_count": 0, "help_count": 0}
        ).status_code
        == 404
    )
    assert len(account.get(API + "/pilot-sessions").json()) == 1


def test_project_and_account_deletion_cascade(project_case):
    account, project, version, plan = project_case
    image, _ = upload(account, project["id"])
    with account.app.state.sessions() as db:
        key = db.get(ImageRecord, image["id"]).storage_key
    assert account.delete(API + f"/projects/{project['id']}").status_code == 204
    assert not account.app.state.store.path(key).exists()
    assert account.get(API + f"/plans/{plan['id']}").status_code == 404
    assert account.get(API + "/projects").json() == []
    assert account.delete(API + "/auth/account").status_code == 204
    assert account.get(API + "/auth/me").status_code == 401


def test_public_catalog_and_missing_resources(client, account):
    assert client.get(API + "/board-models").json()[0]["hole_count"] == 830
    assert client.get(API + "/board-models/bb830-reference").status_code == 200
    assert client.get(API + "/board-models/missing").status_code == 404
    assert len(client.get(API + "/circuit-library").json()) >= 2
    assert account.get(API + "/projects/missing").status_code == 404
    assert account.post(API + "/plans", json={"circuit_version_id": "missing"}).status_code == 404


def test_body_limit_including_chunked_input(account):
    response = account.post(API + "/circuits/validate", content=iter([b"a" * 1024 * 1024] * 3))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
