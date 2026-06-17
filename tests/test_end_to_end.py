import json
from pathlib import Path

import pytest

from crucible.config import CrucibleConfig, NotAuthorizedError
from crucible.runner import run


def test_full_loop_auto(tmp_path):
    cfg = CrucibleConfig(
        target="builtin:acmebot", mode="auto", operator_owned=True, assume_yes=True,
        verbose=False, out_dir=str(tmp_path / "runs"), catalog_path=str(tmp_path / "cat.db"),
    )
    rec = run(cfg)
    assert rec.findings, "should find vulnerabilities in the sample target"
    assert rec.eval_result is not None
    assert rec.eval_result.held_out_catch_rate >= 0.99
    assert rec.eval_result.utility_delta == 0.0
    md, js = rec.report_paths
    assert Path(md).exists() and Path(js).exists()
    data = json.loads(Path(js).read_text())
    assert data["eval"]["held_out_catch_rate"] >= 0.99
    assert data["findings"]


def test_refuses_without_attestation():
    with pytest.raises(NotAuthorizedError):
        run(CrucibleConfig(operator_owned=False))
