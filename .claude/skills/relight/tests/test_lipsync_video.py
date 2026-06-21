import sys, pathlib
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import lipsync_video as lv
import relight_common as rc


# --- registry / resolver -------------------------------------------------

def test_resolve_default_is_sync_lipsync_v2():
    entry = lv.resolve_lipsync()
    assert entry["endpoint"] == "fal-ai/sync-lipsync/v2"
    assert entry["model"] == "lipsync-2"


def test_resolve_cheap_is_latentsync():
    entry = lv.resolve_lipsync(tier="cheap")
    assert entry["endpoint"] == "fal-ai/latentsync"
    assert entry["model"] is None


def test_resolve_override_wins():
    entry = lv.resolve_lipsync(override="fal-ai/sync-lipsync/v2/pro")
    assert entry["endpoint"] == "fal-ai/sync-lipsync/v2/pro"


def test_resolve_unknown_tier_raises():
    with pytest.raises(rc.GuidedError):
        lv.resolve_lipsync(tier="ultra")


# --- cost estimator ------------------------------------------------------

def test_cost_best_is_three_dollars_per_minute():
    assert lv.estimate_lipsync_cost(60.0, "best") == 3.00
    assert lv.estimate_lipsync_cost(30.0, "best") == 1.50


def test_cost_cheap_flat_under_40s_then_per_second():
    assert lv.estimate_lipsync_cost(30.0, "cheap") == 0.20   # flat <= 40s
    assert lv.estimate_lipsync_cost(40.0, "cheap") == 0.20   # boundary stays flat
    assert lv.estimate_lipsync_cost(60.0, "cheap") == 0.30   # 0.20 + 0.005*20


# --- audio extraction + request builder ----------------------------------

def test_audio_extract_cmd_strips_video_to_wav():
    cmd = lv.audio_extract_cmd("clip.mp4", "out.wav")
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd                      # drop the video stream
    assert "clip.mp4" in cmd
    assert cmd[-1] == "out.wav"


def test_build_request_best_includes_model_and_sync_mode():
    entry = lv.resolve_lipsync("best")
    req = lv.build_lipsync_request(entry, "v.mp4", "a.wav")
    assert req["video_url"] == "v.mp4"
    assert req["audio_url"] == "a.wav"
    assert req["model"] == "lipsync-2"
    assert req["sync_mode"] == "cut_off"


def test_build_request_cheap_omits_model_param():
    entry = lv.resolve_lipsync("cheap")
    req = lv.build_lipsync_request(entry, "v.mp4", "a.wav")
    assert req == {"video_url": "v.mp4", "audio_url": "a.wav"}
    assert "model" not in req


def test_build_request_honors_sync_mode_override():
    entry = lv.resolve_lipsync("best")
    req = lv.build_lipsync_request(entry, "v.mp4", "a.wav", sync_mode="loop")
    assert req["sync_mode"] == "loop"


# --- run() orchestration: dry-run + approval guards -----------------------

def test_dry_run_spends_nothing_no_approval_needed(monkeypatch):
    # No fal client, no ffprobe call: dry-run must not need either to estimate.
    monkeypatch.setattr(lv, "fal_client", None)
    monkeypatch.setattr(lv, "probe_duration", lambda p: 60.0)
    out = lv.run("relit.mp4", "out.mp4", tier="best", dry_run=True)
    assert out["endpoint"] == "fal-ai/sync-lipsync/v2"
    assert out["tier"] == "best"
    assert out["est_cost"] == 3.00
    assert out["payload"]["model"] == "lipsync-2"


def test_dry_run_cheap_tier_estimate(monkeypatch):
    monkeypatch.setattr(lv, "fal_client", None)
    monkeypatch.setattr(lv, "probe_duration", lambda p: 30.0)
    out = lv.run("relit.mp4", "out.mp4", tier="cheap", dry_run=True)
    assert out["endpoint"] == "fal-ai/latentsync"
    assert out["est_cost"] == 0.20


def test_real_run_refuses_without_approval(monkeypatch):
    # Even with a fake client present, no approval => no spend.
    monkeypatch.setattr(lv, "fal_client", object())
    monkeypatch.setattr(lv, "probe_duration", lambda p: 30.0)
    with pytest.raises(rc.GuidedError) as e:
        lv.run("relit.mp4", "out.mp4", dry_run=False, approved=False)
    assert "approv" in str(e.value).lower()


def test_real_run_requires_fal_client(monkeypatch):
    monkeypatch.setattr(lv, "fal_client", None)
    monkeypatch.setattr(lv, "probe_duration", lambda p: 30.0)
    with pytest.raises(rc.GuidedError) as e:
        lv.run("relit.mp4", "out.mp4", dry_run=False, approved=True)
    assert "fal-client" in str(e.value).lower() or "fal_client" in str(e.value).lower()
