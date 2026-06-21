import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import image_to_video as iv
import falkit
from falkit import GuidedError


def _no_spend(monkeypatch):
    """Uniform money-guard: any network/key/upload use explodes."""
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent or keyed!"))
    monkeypatch.setattr(iv.fal, "subscribe", boom)
    monkeypatch.setattr(iv.fal, "load_fal_key", boom)
    monkeypatch.setattr(iv.fal, "upload_file", boom)


def test_build_request_duration_and_prompt():
    r = iv.build_request("u", "a dog nods", 3)
    assert r["image_url"] == "u"
    assert r["duration"] == "3"
    assert r["prompt"] == "a dog nods"


def test_build_request_rejects_bad_duration():
    with pytest.raises(GuidedError):
        iv.build_request("u", "x", 20)


def test_needs_compression(tmp_path):
    small = tmp_path / "s.png"; small.write_bytes(b"0" * 1024)
    assert iv.needs_compression(str(small)) is False
    big = tmp_path / "b.png"; big.write_bytes(b"0" * (11 * 1024 * 1024))
    assert iv.needs_compression(str(big)) is True


def test_dry_run_spends_nothing(monkeypatch):
    _no_spend(monkeypatch)
    out = iv.run("img.png", "a dog nods", 3, "out.mp4", dry_run=True)
    assert out["endpoint"] == "fal-ai/kling-video/v3/pro/image-to-video"
    assert out["est_cost"] == 0.50  # round(0.168*3,2)


def test_real_run_refuses_without_approval(monkeypatch):
    monkeypatch.setattr(iv.fal, "subscribe", lambda *a, **k: {"video": {"url": "x"}})
    with pytest.raises(GuidedError) as e:
        iv.run("img.png", "x", 3, "out.mp4", dry_run=False, approved=False)
    assert "approv" in str(e.value).lower()
