"""CI exercises migrations, JSONB, ownership and cascading deletion on real PostgreSQL."""

import os

import pytest
from alembic import command
from alembic.config import Config
from app.config import Settings
from app.database import make_engine
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB


@pytest.mark.skipif(
    not os.getenv("CIRCUITPILOT_TEST_POSTGRES_URL"), reason="PostgreSQL service is not configured"
)
def test_real_postgres_migration_jsonb_and_product_workflow(tmp_path, monkeypatch, series_led):
    url = os.environ["CIRCUITPILOT_TEST_POSTGRES_URL"]
    monkeypatch.setenv("CIRCUITPILOT_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.check(config)
    engine = make_engine(url)
    columns = inspect(engine).get_columns("circuit_versions")
    assert isinstance(next(c["type"] for c in columns if c["name"] == "netlist_json"), JSONB)
    engine.dispose()
    settings = Settings(
        environment="test",
        database_url=url,
        storage_dir=tmp_path / "uploads",
        auto_create_schema=False,
    )
    with TestClient(create_app(settings)) as client:
        signup = client.post(
            "/api/v1/auth/register",
            json={"email": "postgres-check@example.com", "password": "postgres-test-password"},
        )
        assert signup.status_code == 201, signup.text
        client.headers["Authorization"] = "Bearer " + signup.json()["access_token"]
        project = client.post("/api/v1/projects", json={"name": "PostgreSQL integration"}).json()
        version = client.post(f"/api/v1/projects/{project['id']}/circuits", json=series_led).json()
        plan = client.post("/api/v1/plans", json={"circuit_version_id": version["id"]})
        assert plan.status_code == 201, plan.text
        plan_id = plan.json()["id"]
        assert client.get(f"/api/v1/plans/{plan_id}").json()["plan"]["validation"]["valid"]
        assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204
        assert client.get(f"/api/v1/plans/{plan_id}").status_code == 404
        assert client.delete("/api/v1/auth/account").status_code == 204
