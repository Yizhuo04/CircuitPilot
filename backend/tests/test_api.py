import pytest


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_validate_success(client, series_led):
    response = client.post("/api/v1/circuits/validate", json=series_led)
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["ready_to_build"] is False
    assert body["errors"] == []
    assert body["warnings"]


def test_semantic_failure(client, series_led):
    series_led["nets"][0]["members"].append("D1.cathode")
    response = client.post("/api/v1/circuits/validate", json=series_led)
    assert response.status_code == 422
    assert response.json()["valid"] is False
    assert "pin_in_multiple_nets" in {item["code"] for item in response.json()["errors"]}


@pytest.mark.parametrize("payload", [{}, [], None, {"schema_version": "9.0"}])
def test_schema_failures_have_stable_envelope(client, payload):
    response = client.post("/api/v1/circuits/validate", json=payload)
    assert response.status_code == 422
    result = response.json()
    assert result["valid"] is False
    assert result["ready_to_build"] is False
    assert result["validation_scope"] == "netlist_structure"
    assert all(issue["code"].startswith("schema.") for issue in result["errors"])


def test_malformed_json(client):
    response = client.post(
        "/api/v1/circuits/validate", content="{", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "schema.json_invalid"


def test_error_does_not_echo_raw_input(client, series_led):
    series_led["private"] = "DO-NOT-ECHO-THIS"
    response = client.post("/api/v1/circuits/validate", json=series_led)
    assert response.status_code == 422
    assert "DO-NOT-ECHO-THIS" not in response.text


def test_openapi_contract(client):
    schema = client.get("/openapi.json").json()
    route = schema["paths"]["/api/v1/circuits/validate"]["post"]
    assert route["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ValidationResult"
    )
    assert client.get("/docs").status_code == 200
