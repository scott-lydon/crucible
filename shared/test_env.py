import os
from pathlib import Path

import pytest

from shared.env import load_env

_PROBE = "CRUCIBLE_ENV_PROBE"


def test_load_env_from_explicit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_PROBE, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f"{_PROBE}=loaded\n")

    assert load_env(env_file) is True
    assert os.environ[_PROBE] == "loaded"


def test_load_env_absent_is_safe(tmp_path: Path) -> None:
    assert load_env(tmp_path / "nope.env") is False


def test_real_env_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_PROBE, "real")
    env_file = tmp_path / ".env"
    env_file.write_text(f"{_PROBE}=fromfile\n")

    load_env(env_file)

    assert os.environ[_PROBE] == "real"
