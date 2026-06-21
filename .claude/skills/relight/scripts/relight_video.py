"""Relight the original clip using the approved still via Fal Kling O1 video-to-video reference."""
import argparse
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError, estimate_video_cost, load_fal_key

try:
    import fal_client
except ImportError:
    fal_client = None

ENDPOINT = "fal-ai/kling-video/o1/video-to-video/reference"

VIDEO_PROMPT = (
    "Preserve the subject's exact motion, performance, and identity from the source "
    "video. Apply the lighting, color grade, and environment from the reference image. "
    "Subtly animate the background (screens, lights, smoke, water, or ambient motion) "
    "for realism without distracting from the subject."
)


def build_video_request(video_url, still_url, duration, keep_audio=True, aspect_ratio="auto") -> dict:
    if not (3.0 <= duration <= 10.0):
        raise GuidedError(
            f"Clip is {duration:.1f}s; Kling O1 only accepts 3-10s. Trim it first."
        )
    return {
        "video_url": video_url,
        "image_urls": [still_url],
        "keep_audio": keep_audio,
        "duration": str(round(duration)),
        "aspect_ratio": aspect_ratio,
        "prompt": VIDEO_PROMPT,
    }


def run(video_path, still_path, duration, out_path, keep_audio=True, dry_run=False, approved=False) -> dict:
    if dry_run:
        payload = build_video_request(video_path, still_path, duration, keep_audio)
        return {"endpoint": ENDPOINT, "payload": payload, "est_cost": estimate_video_cost(duration)}
    if not approved:
        raise GuidedError("Video relight not approved. Confirm the still + cost before running the paid step.")
    if fal_client is None:
        raise GuidedError("fal-client not installed. Run install.ps1 or pip install -r requirements.txt.")
    load_fal_key()
    video_url = fal_client.upload_file(video_path)
    still_url = fal_client.upload_file(still_path)
    payload = build_video_request(video_url, still_url, duration, keep_audio)
    result = fal_client.subscribe(ENDPOINT, arguments=payload, with_logs=True)
    url = result["video"]["url"]
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)
    return {"endpoint": ENDPOINT, "video": out_path, "remote_url": url,
            "est_cost": estimate_video_cost(duration)}


def main():
    ap = argparse.ArgumentParser(description="Relight a clip with an approved reference still.")
    ap.add_argument("video")
    ap.add_argument("still")
    ap.add_argument("duration", type=float)
    ap.add_argument("--out", default="relit_video.mp4")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved", action="store_true")
    args = ap.parse_args()
    try:
        import json
        print(json.dumps(run(args.video, args.still, args.duration, args.out,
                             keep_audio=not args.no_audio, dry_run=args.dry_run,
                             approved=args.approved), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
