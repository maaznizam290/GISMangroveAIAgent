import json

from typer.testing import CliRunner

from indus_delta.cli import app
from indus_delta.manifest import software_versions, write_manifest

from .conftest import CONFIG_DIR

runner = CliRunner()


def test_manifest_records_hashes_and_versions(tmp_path):
    out = tmp_path / "a.txt"
    out.write_text("x")
    path = write_manifest(
        tmp_path / "m.json",
        milestone="M1",
        command="test",
        config_sha256={"c": "0"},
        inputs=[],
        outputs=[out],
        status="PASS",
    )
    m = json.loads(path.read_text())
    assert m["outputs"][0]["sha256"] == (
        "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
    )
    assert m["software"]["python"]
    assert "rasterio" in software_versions()


def test_cli_validate_config_exit_code():
    result = runner.invoke(app, ["validate-config", "--config-dir", str(CONFIG_DIR)])
    assert result.exit_code == 0, result.output
    assert "crs_utm_zone_matches_location" in result.output
    assert "[FAIL]" not in result.output


def test_cli_bad_config_dir(tmp_path):
    result = runner.invoke(app, ["validate-config", "--config-dir", str(tmp_path)])
    assert result.exit_code == 2


def test_later_milestones_do_not_pretend_to_run():
    # select-sites is still a placeholder (M6).
    result = runner.invoke(app, ["select-sites"])
    assert result.exit_code == 3
    assert "no processing was run" in result.output


def test_check_ee_without_project_fails_cleanly(monkeypatch):
    monkeypatch.delenv("EE_PROJECT", raising=False)
    result = runner.invoke(app, ["check-ee"])
    assert result.exit_code == 1
    assert "EE_PROJECT" in result.output


def test_ee_commands_exit_cleanly_without_project(monkeypatch):
    monkeypatch.delenv("EE_PROJECT", raising=False)
    for cmd in ("inventory", "preview"):
        result = runner.invoke(app, [cmd])
        assert result.exit_code == 4, result.output
        assert "No processing was run" in result.output


def test_preprocess_refused_without_confirmed_aoi():
    result = runner.invoke(app, ["preprocess"])
    assert result.exit_code == 5
    assert "operator_confirmed" in result.output
