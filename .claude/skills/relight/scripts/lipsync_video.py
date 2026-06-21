"""Fix lip-sync on a (relit) talking-head clip: re-sync the mouth to the
original audio via Fal lip-sync. Runs as the final stage after relight."""
import argparse
import pathlib
import shutil
import subprocess
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError, load_fal_key

try:
    import fal_client
except ImportError:
    fal_client = None

# tier -> Fal endpoint. Same shape as the planned falkit model registry, so this
# lifts into falkit/MediaGen unchanged. "model" is the sync-lipsync sub-model
# (None for endpoints that take no model param). "video_key" is the input field
# name for the source video (most use "video_url"; musetalk uses "source_video_url").
LIPSYNC_MODELS = {
    "best":     {"endpoint": "fal-ai/sync-lipsync/v2",                  "model": "lipsync-2", "video_key": "video_url"},
    "cheap":    {"endpoint": "fal-ai/latentsync",                       "model": None,        "video_key": "video_url"},
    "musetalk": {"endpoint": "fal-ai/musetalk",                         "model": None,        "video_key": "source_video_url"},
    "kling":    {"endpoint": "fal-ai/kling-video/lipsync/audio-to-video", "model": None,      "video_key": "video_url"},
}


def resolve_lipsync(tier: str = "best", override: str | None = None) -> dict:
    if override:
        return {"endpoint": override, "model": None}
    if tier not in LIPSYNC_MODELS:
        raise GuidedError(
            f"Unknown lip-sync tier '{tier}'. Valid tiers: {', '.join(LIPSYNC_MODELS)}."
        )
    return LIPSYNC_MODELS[tier]


def estimate_lipsync_cost(duration_s: float, tier: str = "best") -> float:
    if tier == "cheap":  # latentsync: flat $0.20 up to 40s, then $0.005/s
        if duration_s <= 40.0:
            return 0.20
        return round(0.20 + 0.005 * (duration_s - 40.0), 2)
    if tier == "musetalk":  # ~ $0.04 per inference (mouth-region repaint)
        return 0.04
    if tier == "kling":     # ~ $0.014 / s
        return round(0.014 * duration_s, 2)
    # best: sync-lipsync v2 (lipsync-2) ~ $3.00 / minute
    return round(3.00 * duration_s / 60.0, 2)


def audio_extract_cmd(video_path: str, out_path: str) -> list[str]:
    # Strip the video stream, keep the original audio as PCM WAV (no resample /
    # downmix) so the lip-sync model gets the exact speech that will play back.
    return ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-c:a", "pcm_s16le",
            str(out_path)]


def build_lipsync_request(entry: dict, video_url: str, audio_url: str,
                          sync_mode: str = "cut_off") -> dict:
    req = {entry.get("video_key", "video_url"): video_url, "audio_url": audio_url}
    if entry.get("model"):           # sync-lipsync family takes model + sync_mode
        req["model"] = entry["model"]
        req["sync_mode"] = sync_mode
    return req


def probe_duration(video_path: str) -> float:
    if shutil.which("ffprobe") is None:
        raise GuidedError("ffprobe not found. Run install.ps1 (installs ffmpeg/ffprobe).")
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise GuidedError(f"ffprobe failed reading {video_path}: {e.stderr[-300:]}")
    return float(out.stdout.strip())


def _extract_audio(video_path: str, out_path: str) -> str:
    if shutil.which("ffmpeg") is None:
        raise GuidedError("ffmpeg not found. Run install.ps1 (installs ffmpeg via winget).")
    try:
        subprocess.run(audio_extract_cmd(video_path, out_path),
                       capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise GuidedError(f"ffmpeg failed extracting audio: {e.stderr[-300:]}")
    return out_path


def run(video_path, out_path, tier="best", audio_path=None, sync_mode="cut_off",
        override=None, dry_run=False, approved=False) -> dict:
    entry = resolve_lipsync(tier, override)
    duration = probe_duration(video_path)
    est = estimate_lipsync_cost(duration, tier)
    if dry_run:
        payload = build_lipsync_request(entry, video_path, audio_path or "<audio-from-video>",
                                        sync_mode)
        return {"endpoint": entry["endpoint"], "tier": tier, "payload": payload,
                "est_cost": est}
    if not approved:
        raise GuidedError(
            "Lip-sync not approved. Confirm the cost before running the paid step.")
    if fal_client is None:
        raise GuidedError("fal-client not installed. Run install.ps1 or pip install -r requirements.txt.")
    load_fal_key()
    # default: sync to the video's own (original) audio track
    if audio_path is None:
        audio_path = str(pathlib.Path(out_path).with_suffix(".extracted.wav"))
        _extract_audio(video_path, audio_path)
    video_url = fal_client.upload_file(video_path)
    audio_url = fal_client.upload_file(audio_path)
    payload = build_lipsync_request(entry, video_url, audio_url, sync_mode)
    result = fal_client.subscribe(entry["endpoint"], arguments=payload, with_logs=True)
    url = result["video"]["url"]
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)
    return {"endpoint": entry["endpoint"], "tier": tier, "video": out_path,
            "remote_url": url, "est_cost": est}


def main():
    ap = argparse.ArgumentParser(
        description="Re-sync a talking-head clip's mouth to its audio (final relight stage).")
    ap.add_argument("video", help="Video to lip-sync (e.g. the '<name> Relit.mp4').")
    ap.add_argument("--out", default="synced_video.mp4")
    ap.add_argument("--tier", choices=["best", "cheap", "musetalk", "kling"], default="best")
    ap.add_argument("--audio", default=None,
                    help="Audio to sync to. Default: extracted from the video itself.")
    ap.add_argument("--sync-mode", default="cut_off",
                    choices=["cut_off", "loop", "bounce", "silence", "remap"])
    ap.add_argument("--model", default=None, help="Override Fal endpoint (power users).")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved", action="store_true")
    args = ap.parse_args()
    try:
        import json
        print(json.dumps(run(args.video, args.out, tier=args.tier, audio_path=args.audio,
                             sync_mode=args.sync_mode, override=args.model,
                             dry_run=args.dry_run, approved=args.approved), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
