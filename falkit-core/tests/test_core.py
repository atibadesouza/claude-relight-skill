import os, pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from falkit import core


def test_load_key_from_env_wins(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "env-key")
    assert core.load_fal_key() == "env-key"


def test_load_key_from_shared_file(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    shared = tmp_path / "fal.env"
    shared.write_text("FAL_KEY=shared-key\n", encoding="utf-8")
    monkeypatch.setattr(core, "shared_key_path", lambda: shared)
    assert core.load_fal_key() == "shared-key"
    assert os.environ["FAL_KEY"] == "shared-key"


def test_load_key_skill_local_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(core, "shared_key_path", lambda: tmp_path / "nope.env")
    local = tmp_path / ".env"
    local.write_text("FAL_KEY=local-key\n", encoding="utf-8")
    assert core.load_fal_key(skill_env_path=local) == "local-key"


def test_load_key_missing_raises_guided(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(core, "shared_key_path", lambda: tmp_path / "nope.env")
    with pytest.raises(core.GuidedError) as e:
        core.load_fal_key()
    assert "FAL_KEY" in str(e.value)
