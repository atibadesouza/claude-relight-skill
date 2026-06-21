"""MediaGen: upscale any video via Topaz on Fal (approval-gated)."""
import argparse, json, pathlib, shutil, subprocess, sys
import falkit as fal
from falkit import GuidedError

TASK = "upscale"
MAX_FACTOR = 8  # Topaz supports up to 8x


def build_request(video_url, factor=2, target_fps=None) -> dict:
    req = {"video_url": video_url, "upscale_factor": factor}
    if target_fps:
        req["target_fps"] = target_fps
    return req


def output_res_tier(in_min_dim, factor) -> str:
    """Map output short side (in_min_dim*factor) to a Topaz price tier."""
    out = (in_min_dim or 0) * factor
    if out <= 720:
        return "720"
    if out <= 1080:
        return "1080"
    return "4K"


def _probe(path):
    """Return (duration_s, min_dim) via ffprobe, or (None, None) if unavailable."""
    if shutil.which("ffprobe") is None:
        return (None, None)
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration", "-of", "json", path],
            capture_output=True, text=True, check=True).stdout
        meta = json.loads(out)
        s = meta["streams"][0]
        return (float(meta["format"]["duration"]), min(int(s["width"]), int(s["height"])))
    except Exception:
        return (None, None)


def run(video_path, out_path, factor=2, target_fps=None, duration_s=None, in_min_dim=None,
        out_res="1080", tier="best", model=None, dry_run=False, approved=False) -> dict:
    if factor > MAX_FACTOR:
        raise GuidedError(f"Topaz supports up to {MAX_FACTOR}x; got {factor}x.")
    endpoint = fal.resolve_model(TASK, tier=tier, override=model)
    # Auto-probe duration/short-side when the caller didn't supply them, so the cost
    # estimate is accurate even on the real run (done-gate fix: est was $0 otherwise).
    if (duration_s is None or in_min_dim is None) and pathlib.Path(video_path).exists():
        pd, pm = _probe(video_path)
        if duration_s is None:
            duration_s = pd
        if in_min_dim is None:
            in_min_dim = pm
    # If we know the input short side, derive the output tier from factor so the
    # estimate scales with factor instead of quoting a flat price.
    eff_res = output_res_tier(in_min_dim, factor) if in_min_dim else out_res
    est = fal.estimate_cost(TASK, duration_s=duration_s or 0, out_res=eff_res)
    if dry_run:
        return {"endpoint": endpoint, "payload": build_request(video_path, factor, target_fps),
                "est_cost": est, "approx": True}
    if not approved:
        raise GuidedError("upscale not approved. Show the cost and confirm first.")
    fal.load_fal_key()
    url = fal.upload_file(video_path)
    payload = build_request(url, factor, target_fps)
    result = fal.subscribe(endpoint, payload, with_logs=True)
    vurl = result["video"]["url"]
    fal.download(vurl, out_path)
    return {"endpoint": endpoint, "video": out_path, "remote_url": vurl, "est_cost": est}


def main():
    ap = argparse.ArgumentParser(description="Upscale a video via Topaz.")
    ap.add_argument("video")
    ap.add_argument("--out", default="mediagen_upscaled.mp4")
    ap.add_argument("--factor", type=float, default=2)
    ap.add_argument("--target-fps", type=int, default=None)
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--in-min-dim", type=int, default=None, help="Input short side (px); lets the cost estimate scale with --factor.")
    ap.add_argument("--out-res", default="1080")
    ap.add_argument("--tier", default="best", choices=["best", "cheap"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved", action="store_true")
    args = ap.parse_args()
    try:
        print(json.dumps(run(args.video, args.out, args.factor, args.target_fps, args.duration,
                             args.in_min_dim, args.out_res, args.tier, args.model,
                             args.dry_run, args.approved), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
