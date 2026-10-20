import json
from pathlib import Path
from typing import Any

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def series_led() -> dict[str, Any]:
    return json.loads((FIXTURES / "series_led.json").read_text())  # type: ignore[no-any-return]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
