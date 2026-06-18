"""py: target spec, --fail-on-findings exit code, and the hosted webapp (offline)."""

from crucible.runner import build_target


def test_py_target_wraps_any_callable():
    adapter = build_target("py:builtins:str")     # str(message) -> text
    assert adapter.send("hello").text == "hello"


def test_cli_fail_on_findings_returns_nonzero(tmp_path):
    from crucible.cli import main
    code = main(["run", "--target", "builtin:acmebot", "--mode", "auto", "--i-own-this-target",
                 "--yes", "--quiet", "--max-attacks", "2", "--fail-on-findings",
                 "--out", str(tmp_path)])
    assert code == 3                              # findings present -> CI gate fails


def test_webapp_offline_run_renders_report():
    from crucible.webapp_demo import _run_offline
    out = _run_offline()
    assert "Crucible report" in out and "held-out catch rate" in out
