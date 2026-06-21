"""Task -> best Fal model registry, resolver, and cost estimators."""
from .core import GuidedError


def _cost_image(resolution="2K", n_images=1, **_):
    per = 0.30 if resolution == "4K" else 0.15
    return round(per * n_images, 2)


def _cost_video(duration_s=5, **_):
    # Kling v3 Pro, audio off ~ $0.168/s (pinned; reported as approximate).
    return round(0.168 * float(duration_s), 2)


def _cost_upscale(duration_s=5, out_res="1080", **_):
    # Topaz: ~$0.01 <=720p, $0.02 <=1080p, $0.08 >1080p per second (pinned).
    rate = 0.01 if out_res in ("720", "720p") else (0.08 if out_res in ("4K", "2160") else 0.02)
    return round(rate * float(duration_s), 2)


REGISTRY = {
    "image": {
        "best": "fal-ai/nano-banana-pro",
        "cheap": "fal-ai/nano-banana",
        "cost": _cost_image,
    },
    "image_edit": {
        "best": "fal-ai/nano-banana-pro/edit",
        "cheap": "fal-ai/nano-banana/edit",
        "cost": _cost_image,
    },
    "image_to_video": {
        "best": "fal-ai/kling-video/v3/pro/image-to-video",
        "cheap": "fal-ai/kling-video/v3/standard/image-to-video",
        "cost": _cost_video,
    },
    "upscale": {
        "best": "fal-ai/topaz/upscale/video",
        "cheap": "fal-ai/topaz/upscale/video",
        "cost": _cost_upscale,
    },
}


def resolve_model(task, tier="best", override=None):
    if override:
        return override
    if task not in REGISTRY:
        raise GuidedError(f"Unknown task '{task}'. Valid tasks: {', '.join(REGISTRY)}.")
    entry = REGISTRY[task]
    return entry.get(tier) or entry["best"]


def estimate_cost(task, **kw):
    if task not in REGISTRY:
        raise GuidedError(f"Unknown task '{task}'. Valid tasks: {', '.join(REGISTRY)}.")
    return REGISTRY[task]["cost"](**kw)
