import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from falkit import models as m
from falkit import core


def test_resolve_best_defaults():
    assert m.resolve_model("image") == "fal-ai/nano-banana-pro"
    assert m.resolve_model("image_edit") == "fal-ai/nano-banana-pro/edit"
    assert m.resolve_model("image_to_video") == "fal-ai/kling-video/v3/pro/image-to-video"
    assert m.resolve_model("upscale") == "fal-ai/topaz/upscale/video"


def test_cheap_tier_differs_for_video():
    assert m.resolve_model("image_to_video", tier="cheap") != m.resolve_model("image_to_video")


def test_override_wins():
    assert m.resolve_model("image", override="fal-ai/flux/dev") == "fal-ai/flux/dev"


def test_unknown_task_raises():
    with pytest.raises(core.GuidedError) as e:
        m.resolve_model("teleport")
    assert "image" in str(e.value)  # lists valid tasks


def test_cost_estimates():
    assert m.estimate_cost("image", resolution="2K") == 0.15
    assert m.estimate_cost("image", resolution="4K") == 0.30
    assert m.estimate_cost("image_to_video", duration_s=3) == 0.50   # round(0.168*3,2)
    assert m.estimate_cost("upscale", duration_s=5, out_res="1080") == 0.10  # round(0.02*5,2)
