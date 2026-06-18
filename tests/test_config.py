import json

import pytest

from crucible.config import (
    CrucibleConfig,
    NotAuthorizedError,
    config_from_file,
    write_config_template,
)


def test_init_writes_and_loads(tmp_path):
    p = tmp_path / "crucible.json"
    write_config_template(str(p))
    assert p.exists()
    cfg = config_from_file(str(p))
    assert isinstance(cfg, CrucibleConfig)
    assert cfg.target == "builtin:acmebot"


def test_config_from_file_ignores_unknown_keys(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"target": "builtin:acmebot", "mode": "auto",
                             "_comment": "ignored", "bogus": 123, "operator_owned": True}))
    cfg = config_from_file(str(p))
    assert cfg.mode == "auto"
    assert cfg.operator_owned is True


def test_authorize_still_enforced_from_file(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"target": "builtin:acmebot", "operator_owned": False}))
    with pytest.raises(NotAuthorizedError):
        config_from_file(str(p)).authorize()
