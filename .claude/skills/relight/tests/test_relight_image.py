import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import relight_image as ri


def test_template_wraps_user_prompt():
    req = ri.build_image_request("f.png", None, "neon streamer background", "2K")
    assert "neon streamer background" in req["prompt"]
    assert req["prompt"] != "neon streamer background"   # template added context
    assert req["image_urls"] == ["f.png"]
    assert req["resolution"] == "2K"
    assert req["num_images"] == 1


def test_reference_appended_when_given():
    req = ri.build_image_request("f.png", "ref.png", "x", "1K")
    assert req["image_urls"] == ["f.png", "ref.png"]


def test_dry_run_spends_nothing(monkeypatch):
    # If fal_client is touched, fail loudly.
    monkeypatch.setattr(ri, "fal_client", None)
    out = ri.run("f.png", None, "warm office", "out.png", "2K", dry_run=True)
    assert out["endpoint"] == "fal-ai/nano-banana-pro/edit"
    assert out["est_cost"] == 0.15
    assert "warm office" in out["payload"]["prompt"]
