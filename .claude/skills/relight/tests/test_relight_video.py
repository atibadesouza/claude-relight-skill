import sys, pathlib
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import relight_video as rv
import relight_common as rc


def test_build_request_keeps_audio_and_reference():
    req = rv.build_video_request("v.mp4", "still.png", 5.0)
    assert req["keep_audio"] is True
    assert req["image_urls"] == ["still.png"]
    assert req["video_url"] == "v.mp4"
    assert req["duration"] == "5"
    assert req["prompt"] == rv.VIDEO_PROMPT


def test_build_request_rejects_out_of_bounds_duration():
    with pytest.raises(rc.GuidedError):
        rv.build_video_request("v.mp4", "s.png", 14.0)


def test_prompt_override_used_when_given():
    req = rv.build_video_request("v.mp4", "s.png", 5.0, prompt="custom scene")
    assert req["prompt"] == "custom scene"
    # default still applies when no override
    assert rv.build_video_request("v.mp4", "s.png", 5.0)["prompt"] == rv.VIDEO_PROMPT


def test_dry_run_spends_nothing_no_approval_needed(monkeypatch):
    monkeypatch.setattr(rv, "fal_client", None)
    out = rv.run("v.mp4", "s.png", 4.5, "out.mp4", dry_run=True)
    assert out["endpoint"] == "fal-ai/kling-video/o1/video-to-video/reference"
    assert out["est_cost"] == 0.76
    assert out["payload"]["keep_audio"] is True


def test_real_run_refuses_without_approval(monkeypatch):
    # Even with a fake client present, no approval => no spend.
    monkeypatch.setattr(rv, "fal_client", object())
    with pytest.raises(rc.GuidedError) as e:
        rv.run("v.mp4", "s.png", 4.5, "out.mp4", dry_run=False, approved=False)
    assert "approv" in str(e.value).lower()
