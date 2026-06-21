"""Shared helpers for the Relight skill."""
import os
import pathlib


class GuidedError(Exception):
    """Raised with a user-facing remediation message (no stack trace needed)."""


def find_skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def _parse_env(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_fal_key() -> str:
    env_path = find_skill_root() / ".env"
    if not env_path.exists():
        raise GuidedError(
            f"No .env found. Copy {find_skill_root() / '.env.example'} to "
            f"{env_path} and paste your Fal key into it."
        )
    key = _parse_env(env_path.read_text(encoding="utf-8")).get("FAL_KEY", "")
    if not key:
        raise GuidedError(
            f"FAL_KEY is blank. Open {env_path}, set FAL_KEY=<your key from "
            f"https://fal.ai/dashboard/keys>, and save."
        )
    os.environ["FAL_KEY"] = key
    return key


def estimate_image_cost(resolution: str) -> float:
    return {"1K": 0.15, "2K": 0.15, "4K": 0.30}.get(resolution, 0.15)


def estimate_video_cost(duration_s: float) -> float:
    return round(0.169 * duration_s, 2)
