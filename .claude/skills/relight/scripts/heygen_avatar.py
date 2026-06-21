"""Relight Sync mode: animate the approved relit still from the clip's audio via
HeyGen Avatar IV (perfect lip-sync, generated motion)."""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import heygen_common as hc
from relight_common import GuidedError


def audio_extract_cmd(video_path, out_mp3) -> list:
    # strip video; encode speech to mp3 (small enough for HeyGen's 32MB upload cap)
    return ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-c:a", "libmp3lame",
            "-q:a", "2", str(out_mp3)]


def aspect_to_dimension(width: int, height: int, cap: int = 1080) -> dict:
    shorter = min(width, height)
    scale = min(1.0, cap / shorter)          # never upscale
    w = int(round(width * scale))
    h = int(round(height * scale))
    w -= w % 2
    h -= h % 2
    return {"width": w, "height": h}


def build_generate_request(talking_photo_id: str, audio_url: str, dimension: dict, title: str) -> dict:
    return {
        "test": False,
        "title": title,
        "dimension": dimension,
        "use_avatar_iv_model": True,
        "video_inputs": [{
            "character": {"type": "talking_photo", "talking_photo_id": talking_photo_id},
            "voice": {"type": "audio", "audio_url": audio_url},
        }],
    }


def estimate_avatar_cost(duration_s: float) -> float:
    return round(4.00 * duration_s / 60.0, 2)


ENDPOINT = f"{hc.API}/v2/video/generate"


def _ffprobe(args: list) -> str:
    if shutil.which("ffprobe") is None:
        raise GuidedError("ffprobe not found. Run install.ps1 (installs ffmpeg/ffprobe).")
    try:
        out = subprocess.run(args, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise GuidedError(f"ffprobe failed: {e.stderr[-300:]}")
    return out.stdout.strip()


def probe_duration(video_path) -> float:
    return float(_ffprobe(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                           "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)]))


def probe_dimensions(image_path) -> tuple:
    txt = _ffprobe(["ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height", "-of", "csv=p=0", str(image_path)])
    w, h = txt.split(",")[:2]
    return int(w), int(h)


def _extract_audio(video_path, out_mp3) -> str:
    if shutil.which("ffmpeg") is None:
        raise GuidedError("ffmpeg not found. Run install.ps1 (installs ffmpeg via winget).")
    try:
        subprocess.run(audio_extract_cmd(video_path, out_mp3), capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise GuidedError(f"ffmpeg failed extracting audio: {e.stderr[-300:]}")
    return out_mp3


def _verify_nonempty(out_path, recover_url) -> None:
    if pathlib.Path(out_path).stat().st_size == 0:
        raise GuidedError(f"Downloaded file is empty. The render is at {recover_url} — retry the download.")


def _download(url, out_path) -> str:
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:   # timeout: never hang forever post-render
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
    _verify_nonempty(out_path, url)
    return out_path


# NOTE: all progress goes to STDERR — stdout is reserved for the final JSON the
# SKILL.md orchestration parses; printing progress to stdout would corrupt it.
def poll_until_done(key, video_id, out_path, interval=15, max_tries=160) -> str:
    for i in range(max_tries):                 # 160 * 15s ≈ 40min worst-case ceiling
        d = hc.get_status(key, video_id)
        hc.check_credit_error(d)
        st = d.get("status")
        if i % 8 == 0:                          # ~every 2 min, so a stalled job is visible
            print(f"  …HeyGen: {st} (~{i * interval // 60}m elapsed)", file=sys.stderr)
        if st == "completed":
            url = d.get("video_url")
            if not url:
                raise GuidedError(f"HeyGen completed but returned no video_url: {d}")
            try:
                return _download(url, out_path)
            except GuidedError:
                raise
            except Exception as e:
                raise GuidedError(f"Render done but download failed ({e}). Recover it at: {url}")
        if st in ("failed", "error"):
            raise GuidedError(f"HeyGen job failed: {d.get('error') or d.get('message') or d}")
        time.sleep(interval)
    raise GuidedError(
        f"HeyGen job timed out after ~{max_tries * interval // 60}min (video_id={video_id}). "
        "Check the HeyGen dashboard later — the render may still finish.")


def run(video_path, still_path, out_path, title=None, dry_run=False, approved=False) -> dict:
    duration = probe_duration(video_path)
    w, h = probe_dimensions(still_path)
    dimension = aspect_to_dimension(w, h)
    title = title or f"{pathlib.Path(out_path).stem}"
    est = estimate_avatar_cost(duration)
    if dry_run:
        payload = build_generate_request("<talking_photo_id>", "<audio_url>", dimension, title)
        return {"endpoint": ENDPOINT, "payload": payload, "est_cost": est}
    if not approved:
        raise GuidedError("Avatar IV not approved. Confirm the cost before running the paid step.")
    key = hc.load_heygen_key()
    # interior-dot suffix would ValueError on Python <=3.11; with_name is version-safe
    work = pathlib.Path(out_path).with_name(pathlib.Path(out_path).stem + ".audio.mp3")
    _extract_audio(video_path, work)
    tp_id = hc.upload_talking_photo(key, still_path)
    audio_url = hc.upload_audio_asset(key, work)
    payload = build_generate_request(tp_id, audio_url, dimension, title)
    video_id = hc.generate_avatar_iv(key, payload)
    if not video_id:
        raise GuidedError("HeyGen did not return a video_id; check API credits and inputs.")
    # surface the video_id BEFORE polling — if the download later fails, the spend is
    # recoverable from the HeyGen dashboard rather than re-paid.
    print(f"  HeyGen video_id={video_id} (recover here if interrupted)", file=sys.stderr)
    poll_until_done(key, video_id, out_path)
    return {"endpoint": ENDPOINT, "video": out_path, "video_id": video_id, "est_cost": est}


def main():
    ap = argparse.ArgumentParser(description="Relight Sync mode — HeyGen Avatar IV from a relit still + the clip's audio.")
    ap.add_argument("video", help="The original clip (audio source).")
    ap.add_argument("still", help="The approved relit still (talking photo).")
    ap.add_argument("--out", default="synced_video.mp4")
    ap.add_argument("--title", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved", action="store_true")
    args = ap.parse_args()
    try:
        print(json.dumps(run(args.video, args.still, args.out, title=args.title,
                             dry_run=args.dry_run, approved=args.approved), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
