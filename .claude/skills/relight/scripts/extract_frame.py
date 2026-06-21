"""Probe a clip, validate it against Kling O1 limits, and extract the sharpest frame."""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError

MIN_DUR, MAX_DUR = 3.0, 10.0
MIN_DIM, MAX_DIM = 720, 2160
MAX_BYTES = 200 * 1024 * 1024


def sharpness(gray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def validate_clip(probe: dict) -> list[str]:
    warns = []
    d = probe["duration"]
    if not (MIN_DUR <= d <= MAX_DUR):
        warns.append(f"Duration {d:.1f}s is outside the 3-10s Kling limit.")
    if min(probe["width"], probe["height"]) < MIN_DIM:
        warns.append(f"Resolution {probe['width']}x{probe['height']} is below the 720px minimum.")
    if max(probe["width"], probe["height"]) > MAX_DIM:
        warns.append(f"Resolution {probe['width']}x{probe['height']} exceeds the 2160px maximum.")
    if probe["size_bytes"] > MAX_BYTES:
        warns.append(f"File is {probe['size_bytes']/1024/1024:.0f}MB, over the 200MB limit.")
    return warns


def probe_video(path: str) -> dict:
    if shutil.which("ffprobe") is None:
        raise GuidedError("ffprobe not found. Run install.ps1 (installs ffmpeg via winget).")
    p = pathlib.Path(path)
    if not p.exists():
        raise GuidedError(f"Video not found: {path}")
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height:format=duration",
           "-of", "json", str(p)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
        meta = json.loads(out)
        stream = meta["streams"][0]
        return {
            "duration": float(meta["format"]["duration"]),
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "size_bytes": p.stat().st_size,
        }
    except (subprocess.CalledProcessError, KeyError, IndexError, ValueError) as e:
        raise GuidedError(f"Could not read video metadata from {path}: {e}")


def extract_best_frame(path: str, out_path: str, n: int = 12) -> tuple[str, float]:
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if total <= 0:
        cap.release()
        raise GuidedError(f"No frames readable from {path}.")
    idxs = np.linspace(0, total - 1, min(n, total)).astype(int)
    best_frame, best_score = None, -1.0
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok:
            continue
        score = sharpness(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        if score > best_score:
            best_frame, best_score = frame, score
    cap.release()
    if best_frame is None:
        raise GuidedError(f"Could not decode any frame from {path}.")
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(out_path, best_frame)
    return out_path, best_score


def main():
    ap = argparse.ArgumentParser(description="Probe + extract sharpest frame.")
    ap.add_argument("video")
    ap.add_argument("--out", default="best_frame.png")
    ap.add_argument("--frames", type=int, default=12)
    args = ap.parse_args()
    try:
        probe = probe_video(args.video)
        warns = validate_clip(probe)
        out, score = extract_best_frame(args.video, args.out, args.frames)
        print(json.dumps({"probe": probe, "warnings": warns, "frame": out, "sharpness": score}, indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
