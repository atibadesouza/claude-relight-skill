import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import split_video as sv


def test_short_clip_is_single_segment():
    assert sv.plan_segments(5.0) == [(0.0, 5.0)]
    assert sv.plan_segments(10.0) == [(0.0, 10.0)]   # exactly 10s stays single


def test_long_clip_even_split_in_bounds():
    segs = sv.plan_segments(21.0)
    assert len(segs) == 3                              # ceil(21/10)
    assert all(3.0 <= length <= 10.0 for _, length in segs)
    assert abs(sum(length for _, length in segs) - 21.0) < 0.01


def test_avoids_invalid_short_tail():
    # naive 10s cuts -> 10+10+1 (1s tail rejected by Kling). Even-split must not.
    assert all(length >= 3.0 for _, length in sv.plan_segments(21.0))


def test_just_over_limit_two_segments():
    segs = sv.plan_segments(10.1)
    assert len(segs) == 2
    assert all(3.0 <= length <= 10.0 for _, length in segs)
