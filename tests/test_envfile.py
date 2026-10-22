from indus_delta.envfile import load_env_file


def test_env_file_sets_only_unset_nonempty(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text(
        '# comment\nEE_PROJECT="my-project"\nEXPORT_BUCKET=\n'
        "export EXPORT_DRIVE_FOLDER=drive_folder\nALREADY=from_file\n"
    )
    monkeypatch.delenv("EE_PROJECT", raising=False)
    monkeypatch.delenv("EXPORT_BUCKET", raising=False)
    monkeypatch.delenv("EXPORT_DRIVE_FOLDER", raising=False)
    monkeypatch.setenv("ALREADY", "from_shell")
    loaded = load_env_file(p)
    import os

    assert os.environ["EE_PROJECT"] == "my-project"
    assert os.environ["EXPORT_DRIVE_FOLDER"] == "drive_folder"
    assert "EXPORT_BUCKET" not in os.environ  # empty values ignored
    assert os.environ["ALREADY"] == "from_shell"  # shell wins
    assert sorted(loaded) == ["EE_PROJECT", "EXPORT_DRIVE_FOLDER"]


def test_missing_env_file(tmp_path):
    assert load_env_file(tmp_path / "none") == []
