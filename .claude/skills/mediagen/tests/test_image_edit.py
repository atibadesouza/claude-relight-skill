import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import image_edit as ie


def _no_spend(monkeypatch):
    """Uniform money-guard across all four scripts."""
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent or keyed!"))
    monkeypatch.setattr(ie.fal, "subscribe", boom)
    monkeypatch.setattr(ie.fal, "load_fal_key", boom)
    monkeypatch.setattr(ie.fal, "upload_file", boom)


def test_build_request_includes_all_refs():
    r = ie.build_request("make it Ronaldo", ["a.png", "b.png"])
    assert r["image_urls"] == ["a.png", "b.png"]
    assert r["num_images"] == 1


def test_dry_run_no_upload(monkeypatch):
    _no_spend(monkeypatch)
    out = ie.run("make it Ronaldo", ["a.png", "b.png"], "out.png", dry_run=True)
    assert out["endpoint"] == "fal-ai/nano-banana-pro/edit"
    assert out["payload"]["image_urls"] == ["a.png", "b.png"]
    assert out["est_cost"] == 0.15


def test_requires_at_least_one_reference():
    with pytest.raises(Exception):
        ie.build_request("x", [])
