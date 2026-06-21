"""Batch relight: split a >10s clip, relight each segment with one shared still, concat."""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError, estimate_image_cost, estimate_video_cost
from extract_frame import probe_video
from split_video import plan_segments, split_video
from concat_video import concat_videos
from relight_video import run as relight_video_run, ENDPOINT

try:
    import fal_client
except ImportError:
    fal_client = None


def estimate_batch(duration: float, resolution: str = "2K") -> dict:
    segs = plan_segments(duration)
    video = round(sum(estimate_video_cost(length) for _, length in segs), 2)
    image = estimate_image_cost(resolution)
    return {"segments": len(segs), "image_cost": image, "video_cost": video,
            "total": round(image + video, 2)}


def run_batch(video_path, still_path, work_dir, out_path,
              approved=False, dry_run=False, resolution="2K") -> dict:
    probe = probe_video(video_path)
    duration = probe["duration"]
    segments = plan_segments(duration)
    if dry_run:
        return {"endpoint": ENDPOINT,
                "plan": {"segments": len(segments), "lengths": [l for _, l in segments]},
                "est_cost": estimate_batch(duration, resolution)}
    if not approved:
        raise GuidedError("Batch relight not approved. Confirm the still + total cost before the paid run.")
    seg_paths = split_video(video_path, work_dir, segments)
    relit = []
    for i, (seg_path, (_, length)) in enumerate(zip(seg_paths, segments)):
        seg_out = str(pathlib.Path(work_dir) / f"relit_{i:03d}.mp4")
        try:
            relight_video_run(seg_path, still_path, length, seg_out, approved=True)
        except Exception as e:
            raise GuidedError(
                f"Segment {i} failed: {e}. {len(relit)} of {len(segments)} segments rendered; "
                f"not concatenating a partial result. Re-run when resolved."
            )
        relit.append(seg_out)
    concat_videos(relit, out_path)
    return {"video": out_path, "segments": len(segments), "est_cost": estimate_batch(duration, resolution)["total"]}


def main():
    ap = argparse.ArgumentParser(description="Batch relight a >10s clip.")
    ap.add_argument("video")
    ap.add_argument("still")
    ap.add_argument("--work", default="relight_work")
    ap.add_argument("--out", default="relit_video.mp4")
    ap.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved", action="store_true")
    args = ap.parse_args()
    try:
        import json
        print(json.dumps(run_batch(args.video, args.still, args.work, args.out,
                                   approved=args.approved, dry_run=args.dry_run,
                                   resolution=args.resolution), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
