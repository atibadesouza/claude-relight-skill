import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import upscale as up
from falkit import GuidedError


def _no_spend(monkeypatch):
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent or keyed!"))
    monkeypatch.setattr(up.fal, "subscribe", boom)
    monkeypatch.setattr(up.fal, "load_fal_key", boom)
    monkeypatch.setattr(up.fal, "upload_file", boom)


def test_build_request_factor():
    r = up.build_request("v", factor=2)
    assert r["video_url"] == "v"
    assert r["upscale_factor"] == 2


def test_output_res_tier_scales_with_factor():
    assert up.output_res_tier(540, 2) == "1080"
    assert up.output_res_tier(540, 4) == "4K"   # 2160 -> top tier


def test_dry_run_spends_nothing(monkeypatch):
    _no_spend(monkeypatch)
    out = up.run("in.mp4", "out.mp4", factor=2, duration_s=5, out_res="1080", dry_run=True)
    assert out["endpoint"] == "fal-ai/topaz/upscale/video"
    assert out["est_cost"] == 0.10  # round(0.02*5,2)


def test_factor_changes_cost(monkeypatch):
    _no_spend(monkeypatch)
    two = up.run("in.mp4", "o.mp4", factor=2, duration_s=5, in_min_dim=540, dry_run=True)["est_cost"]
    four = up.run("in.mp4", "o.mp4", factor=4, duration_s=5, in_min_dim=540, dry_run=True)["est_cost"]
    assert four > two   # 4x lands in the 4K tier, costs more — factor is no longer ignored


def test_factor_cap(monkeypatch):
    _no_spend(monkeypatch)
    with pytest.raises(GuidedError):
        up.run("in.mp4", "o.mp4", factor=16, duration_s=5, dry_run=True)


def test_real_run_refuses_without_approval(monkeypatch):
    monkeypatch.setattr(up.fal, "subscribe", lambda *a, **k: {"video": {"url": "x"}})
    with pytest.raises(GuidedError):
        up.run("in.mp4", "out.mp4", dry_run=False, approved=False)
