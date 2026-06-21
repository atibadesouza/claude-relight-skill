import sys, pathlib
import numpy as np
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import extract_frame as ef


def test_sharpness_sharp_beats_blurry():
    rng = np.random.default_rng(0)
    sharp = (rng.integers(0, 255, (200, 200))).astype("uint8")
    blurry = np.full((200, 200), 128, dtype="uint8")
    assert ef.sharpness(sharp) > ef.sharpness(blurry)


def test_validate_clip_ok():
    assert ef.validate_clip(
        {"duration": 5.0, "width": 1920, "height": 1080, "size_bytes": 10_000_000}
    ) == []


def test_validate_clip_flags_long_and_big():
    w = ef.validate_clip(
        {"duration": 14.0, "width": 1920, "height": 1080, "size_bytes": 300_000_000}
    )
    assert any("10" in m for m in w)        # duration warning mentions the limit
    assert any("200" in m for m in w)       # size warning mentions the limit


def test_validate_clip_flags_low_res():
    w = ef.validate_clip(
        {"duration": 5.0, "width": 640, "height": 480, "size_bytes": 1_000_000}
    )
    assert any("720" in m for m in w)
