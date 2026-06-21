"""Even-split a >10s clip into Kling-legal (3-10s) segments via ffmpeg."""
import argparse
import math
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError

MAX_LEN, MIN_LEN = 10.0, 3.0


def plan_segments(duration: float, max_len: float = MAX_LEN, min_len: float = MIN_LEN):
    if duration <= max_len:
        return [(0.0, round(duration, 3))]
    n = math.ceil(duration / max_len)
    seg = duration / n
    out = []
    for i in range(n):
        start = round(i * seg, 3)
        length = round(seg, 3)
        out.append((start, length))
    return out


def split_video(path: str, work_dir: str, segments) -> list[str]:
    if shutil.which("ffmpeg") is None:
        raise GuidedError("ffmpeg not found. Run install.ps1 (installs ffmpeg via winget).")
    pathlib.Path(work_dir).mkdir(parents=True, exist_ok=True)
    out_paths = []
    for i, (start, length) in enumerate(segments):
        seg_out = str(pathlib.Path(work_dir) / f"seg_{i:03d}.mp4")
        cmd = ["ffmpeg", "-y", "-i", str(path), "-ss", f"{start}", "-t", f"{length}",
               "-c:v", "libx264", "-c:a", "aac", seg_out]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            raise GuidedError(f"ffmpeg failed splitting segment {i}: {e.stderr[-300:]}")
        out_paths.append(seg_out)
    return out_paths


def main():
    ap = argparse.ArgumentParser(description="Even-split a clip into 3-10s segments.")
    ap.add_argument("video")
    ap.add_argument("duration", type=float)
    ap.add_argument("--work", default="relight_work")
    args = ap.parse_args()
    try:
        import json
        segs = plan_segments(args.duration)
        paths = split_video(args.video, args.work, segs)
        print(json.dumps({"segments": segs, "paths": paths}, indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
