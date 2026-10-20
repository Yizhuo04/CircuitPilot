import json
from pathlib import Path
from typing import Any

import pytest
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def series_led() -> dict[str, Any]:
    return json.loads((FIXTURES / "series_led.json").read_text())  # type: ignore[no-any-return]


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        environment="test", database_url="sqlite://", storage_dir=tmp_path / "uploads"
    )
    with TestClient(create_app(settings)) as connection:
        yield connection
