import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import image_generate as ig


def _no_spend(monkeypatch):
    """Make any network/key use explode so dry-run is provably free.
    resolve_model/estimate_cost stay live (they are pure, no network)."""
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent or keyed!"))
    monkeypatch.setattr(ig.fal, "subscribe", boom)
    monkeypatch.setattr(ig.fal, "load_fal_key", boom)
    monkeypatch.setattr(ig.fal, "upload_file", boom)


def test_build_request_shape():
    r = ig.build_request("a dog as superman", resolution="4K")
    assert r["prompt"] == "a dog as superman"
    assert r["resolution"] == "4K"
    assert r["num_images"] == 1


def test_dry_run_resolves_model_no_spend(monkeypatch):
    _no_spend(monkeypatch)
    out = ig.run("a dog as superman", "out.png", resolution="2K", dry_run=True)
    assert out["endpoint"] == "fal-ai/nano-banana-pro"
    assert out["est_cost"] == 0.15
    assert out["payload"]["prompt"] == "a dog as superman"


def test_override_model(monkeypatch):
    _no_spend(monkeypatch)
    out = ig.run("x", "out.png", model="fal-ai/flux/dev", dry_run=True)
    assert out["endpoint"] == "fal-ai/flux/dev"
