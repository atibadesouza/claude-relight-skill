import sys, pathlib
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import relight_batch as rb
import relight_common as rc

PROBE = {"duration": 21.0, "width": 1920, "height": 1080, "size_bytes": 1000}


def test_estimate_batch_counts_and_total():
    est = rb.estimate_batch(21.0, "2K")
    assert est["segments"] == 3
    assert est["total"] == round(0.15 + 3 * round(0.169 * 7, 2), 2)   # 0.15 + 3*1.18 = 3.69


def test_dry_run_spends_nothing(monkeypatch):
    monkeypatch.setattr(rb, "probe_video", lambda p: PROBE)
    out = rb.run_batch("v.mp4", "s.png", "work", "out.mp4", dry_run=True)
    assert out["plan"]["segments"] == 3
    assert out["est_cost"]["total"] == rb.estimate_batch(21.0)["total"]


def test_real_run_refuses_without_approval(monkeypatch):
    monkeypatch.setattr(rb, "probe_video", lambda p: PROBE)
    with pytest.raises(rc.GuidedError) as e:
        rb.run_batch("v.mp4", "s.png", "work", "out.mp4", dry_run=False, approved=False)
    assert "approv" in str(e.value).lower()


def test_segment_failure_stops_without_concat(monkeypatch):
    monkeypatch.setattr(rb, "probe_video", lambda p: PROBE)
    monkeypatch.setattr(rb, "split_video", lambda p, w, segs: ["s0.mp4", "s1.mp4", "s2.mp4"])
    def boom(*a, **k): raise RuntimeError("fal 500")
    monkeypatch.setattr(rb, "relight_video_run", boom)
    called = {"concat": False}
    monkeypatch.setattr(rb, "concat_videos", lambda *a, **k: called.__setitem__("concat", True))
    with pytest.raises(rc.GuidedError) as e:
        rb.run_batch("v.mp4", "s.png", "work", "out.mp4", dry_run=False, approved=True)
    assert "segment" in str(e.value).lower()
    assert called["concat"] is False
