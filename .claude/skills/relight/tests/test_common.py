import os
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import relight_common as rc


def test_image_cost_table():
    assert rc.estimate_image_cost("1K") == 0.15
    assert rc.estimate_image_cost("4K") == 0.30


def test_video_cost_scales_with_duration():
    assert rc.estimate_video_cost(4.5) == 0.76  # round(0.169*4.5,2)
    assert rc.estimate_video_cost(10) == 1.69


def test_load_fal_key_missing_raises_guided(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "find_skill_root", lambda: tmp_path)
    (tmp_path / ".env").write_text("FAL_KEY=\n", encoding="utf-8")
    with pytest.raises(rc.GuidedError) as e:
        rc.load_fal_key()
    assert ".env" in str(e.value)


def test_load_fal_key_present(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "find_skill_root", lambda: tmp_path)
    (tmp_path / ".env").write_text("FAL_KEY=abc123\n", encoding="utf-8")
    assert rc.load_fal_key() == "abc123"
    assert os.environ["FAL_KEY"] == "abc123"
