"""Concatenate ordered relit segments into a single MP4 via ffmpeg."""
import argparse
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError


def build_concat_list(paths) -> str:
    return "".join(f"file '{str(p).replace(chr(92), '/')}'\n" for p in paths)


def concat_videos(paths, out_path: str) -> str:
    if shutil.which("ffmpeg") is None:
        raise GuidedError("ffmpeg not found. Run install.ps1 (installs ffmpeg via winget).")
    out = pathlib.Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    list_path = out.parent / "concat_list.txt"
    list_path.write_text(build_concat_list([str(p) for p in paths]), encoding="utf-8")
    base = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path)]
    try:
        subprocess.run(base + ["-c", "copy", str(out)], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError:
        # Stream-copy can fail if segment codecs differ; re-encode as fallback.
        subprocess.run(base + ["-c:v", "libx264", "-c:a", "aac", str(out)],
                       capture_output=True, text=True, check=True)
    return str(out)


def main():
    ap = argparse.ArgumentParser(description="Concat ordered mp4 segments.")
    ap.add_argument("out")
    ap.add_argument("segments", nargs="+")
    args = ap.parse_args()
    try:
        print(concat_videos(args.segments, args.out))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
