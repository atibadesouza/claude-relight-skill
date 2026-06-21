"""Backwards-compatible shim: use shared `falkit` when available, else inline fallback."""
import pathlib


def find_skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def estimate_video_cost(duration_s: float) -> float:
    # Relight uses Kling O1 v2v (~$0.169/s); keep its historical rate (not the registry's 0.168).
    return round(0.169 * duration_s, 2)


try:
    from falkit.core import GuidedError as GuidedError
    from falkit.core import load_fal_key as _falkit_load_fal_key
    from falkit.models import estimate_cost as _estimate_cost

    def load_fal_key() -> str:
        # Shared key first; relight's own .env as back-compat fallback.
        return _falkit_load_fal_key(skill_env_path=find_skill_root() / ".env")

    def estimate_image_cost(resolution: str) -> float:
        return _estimate_cost("image", resolution=resolution)

except ImportError:  # falkit not installed — degrade, do not crash.
    import os

    class GuidedError(Exception):
        """Carries a user-facing remediation message."""

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
                f"FAL_KEY is blank. Open {env_path}, set FAL_KEY=<your key>, and save."
            )
        os.environ["FAL_KEY"] = key
        return key

    def estimate_image_cost(resolution: str) -> float:
        return {"1K": 0.15, "2K": 0.15, "4K": 0.30}.get(resolution, 0.15)
