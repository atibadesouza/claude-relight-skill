"""Shared HeyGen helpers for the Relight skill (Sync mode)."""
import mimetypes
import os
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError

API = "https://api.heygen.com"
UPLOAD = "https://upload.heygen.com"


def _parse_env(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_heygen_key() -> str:
    if os.environ.get("HEYGEN_API_KEY"):
        return os.environ["HEYGEN_API_KEY"]
    env_path = pathlib.Path.home() / ".claude" / "heygen.env"
    if not env_path.exists():
        raise GuidedError(
            f"No HeyGen key. Create {env_path} with a line "
            f"HEYGEN_API_KEY=<key from https://app.heygen.com/settings>.")
    key = _parse_env(env_path.read_text(encoding="utf-8")).get("HEYGEN_API_KEY", "")
    if not key:
        raise GuidedError(f"HEYGEN_API_KEY is blank in {env_path}. Set it and save.")
    return key


def headers(key: str, content_type: str | None = None) -> dict:
    h = {"X-Api-Key": key}
    if content_type:
        h["Content-Type"] = content_type
    return h


def check_credit_error(payload: dict) -> None:
    msg = ""
    if isinstance(payload, dict):
        msg = payload.get("message") or ""
    if "insufficient credit" in str(msg).lower():
        raise GuidedError(
            "HeyGen: insufficient API credits. Avatar IV needs funded 'API' credits — "
            "top up at https://app.heygen.com/settings, then retry.")


MAX_UPLOAD_BYTES = 32 * 1024 * 1024  # HeyGen asset cap


def _require_under_cap(path):
    p = pathlib.Path(path)
    if p.stat().st_size > MAX_UPLOAD_BYTES:
        mb = p.stat().st_size // (1024 * 1024)
        raise GuidedError(
            f"{p.name} is {mb}MB; HeyGen's upload cap is 32MB. Use a shorter clip "
            "(audio is mp3 so this is unlikely below ~20min).")
    return p


def _parse_data(resp) -> dict:
    """Return resp's `data` dict, converting HeyGen's 200-with-error envelopes
    (and credit errors) into GuidedError rather than a raw KeyError/traceback."""
    j = resp.json() if resp.content else {}
    j = j if isinstance(j, dict) else {}
    data = j.get("data") if isinstance(j.get("data"), dict) else {}
    check_credit_error(data)
    check_credit_error(j)
    if not data:
        raise GuidedError(f"HeyGen returned no data: {j.get('error') or j.get('message') or j}")
    return data


def upload_talking_photo(key: str, image_path) -> str:
    p = _require_under_cap(image_path)
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    r = requests.post(f"{UPLOAD}/v1/talking_photo", headers=headers(key, mime), data=p.read_bytes())
    r.raise_for_status()
    data = _parse_data(r)
    tp = data.get("talking_photo_id") or data.get("id")
    if not tp:
        raise GuidedError(f"HeyGen talking-photo upload returned no id: {data}")
    return tp


def upload_audio_asset(key: str, audio_path) -> str:
    p = _require_under_cap(audio_path)
    mime = mimetypes.guess_type(str(p))[0] or "audio/mpeg"
    with open(p, "rb") as f:
        r = requests.post(f"{API}/v3/assets", headers=headers(key), files={"file": (p.name, f, mime)})
    r.raise_for_status()
    url = _parse_data(r).get("url")
    if not url:
        raise GuidedError("HeyGen audio upload returned no url.")
    return url


def generate_avatar_iv(key: str, payload: dict):
    r = requests.post(f"{API}/v2/video/generate", headers=headers(key, "application/json"), json=payload)
    r.raise_for_status()
    return _parse_data(r).get("video_id")


def get_status(key: str, video_id: str) -> dict:
    r = requests.get(f"{API}/v1/video_status.get", headers=headers(key), params={"video_id": video_id})
    if r.status_code >= 400:
        raise GuidedError(f"HeyGen status check failed (HTTP {r.status_code}): {r.text[:200]}")
    try:
        j = r.json()
    except ValueError:
        raise GuidedError(f"HeyGen status check returned a non-JSON response (HTTP {r.status_code}).")
    return (j.get("data") if isinstance(j, dict) else {}) or {}
