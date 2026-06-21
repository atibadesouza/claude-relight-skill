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
