import sys

import pytest
from app.export_schemas import main


def test_export_then_check(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["export", "--output", str(tmp_path)])
    main()
    monkeypatch.setattr(sys, "argv", ["export", "--output", str(tmp_path), "--check"])
    main()
    (tmp_path / "circuit_schema.json").write_text("stale")
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1


def test_check_missing_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["export", "--output", str(tmp_path), "--check"])
    with pytest.raises(SystemExit):
        main()
