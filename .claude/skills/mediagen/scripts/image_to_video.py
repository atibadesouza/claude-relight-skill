"""MediaGen: animate a still into a video (approval-gated, per-second priced)."""
import argparse, json, pathlib, shutil, subprocess, sys
import falkit as fal
from falkit import GuidedError

TASK = "image_to_video"
CAP_BYTES = 10 * 1024 * 1024


def build_request(image_url, prompt, duration, with_audio=False) -> dict:
    if not (3 <= duration <= 15):
        raise GuidedError(f"Kling v3 accepts 3-15s; got {duration}s.")
    return {"image_url": image_url, "prompt": prompt,
            "duration": str(round(duration)), "audio": bool(with_audio)}


def needs_compression(path, cap_bytes=CAP_BYTES) -> bool:
    return pathlib.Path(path).stat().st_size > cap_bytes


def _compress(path, out_path) -> str:
    if shutil.which("ffmpeg") is None:
        raise GuidedError("Image >10MB and ffmpeg not found to compress it. Run install.ps1.")
    subprocess.run(["ffmpeg", "-y", "-i", path, "-vf", "scale='min(2048,iw)':-2",
                    "-q:v", "4", out_path], capture_output=True, text=True, check=True)
    return out_path


def run(image_path, prompt, duration, out_path, with_audio=False, tier="best",
        model=None, dry_run=False, approved=False) -> dict:
    endpoint = fal.resolve_model(TASK, tier=tier, override=model)
    est = fal.estimate_cost(TASK, duration_s=duration)
    if dry_run:
        return {"endpoint": endpoint,
                "payload": build_request(image_path, prompt, duration, with_audio),
                "est_cost": est}
    if not approved:
        raise GuidedError("image_to_video not approved. Show the cost + prompt and confirm first.")
    fal.load_fal_key()
    upload_path = image_path
    if needs_compression(image_path):
        # Unique temp name (per-output) so concurrent/repeated runs don't clobber.
        upload_path = str(pathlib.Path(out_path).with_name(f"_{pathlib.Path(out_path).stem}_i2v_compressed.jpg"))
        _compress(image_path, upload_path)
        print(f"NOTE: image >10MB; compressed to {upload_path} for Kling.", file=sys.stderr)
    url = fal.upload_file(upload_path)
    payload = build_request(url, prompt, duration, with_audio)
    result = fal.subscribe(endpoint, payload, with_logs=True)
    vurl = result["video"]["url"]
    fal.download(vurl, out_path)
    return {"endpoint": endpoint, "video": out_path, "remote_url": vurl, "est_cost": est}


def main():
    ap = argparse.ArgumentParser(description="Animate a still into a video.")
    ap.add_argument("image"); ap.add_argument("prompt"); ap.add_argument("duration", type=float)
    ap.add_argument("--out", default="mediagen_video.mp4")
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--tier", default="best", choices=["best", "cheap"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved", action="store_true")
    args = ap.parse_args()
    try:
        print(json.dumps(run(args.image, args.prompt, args.duration, args.out,
                             args.audio, args.tier, args.model, args.dry_run, args.approved), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
