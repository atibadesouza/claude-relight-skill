"""Shared Fal AI core: key loading, client wrappers, cost helpers."""
import os
import pathlib
import urllib.request

try:
    import fal_client
except ImportError:
    fal_client = None


class GuidedError(Exception):
    """Carries a user-facing remediation message."""


def shared_key_path() -> pathlib.Path:
    return pathlib.Path.home() / ".claude" / "fal.env"


def _parse_env(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _key_from_file(p: pathlib.Path):
    if p and p.exists():
        return _parse_env(p.read_text(encoding="utf-8")).get("FAL_KEY", "")
    return ""


def load_fal_key(skill_env_path=None) -> str:
    key = os.environ.get("FAL_KEY", "").strip()
    if not key:
        key = _key_from_file(shared_key_path()).strip()
    if not key and skill_env_path:
        key = _key_from_file(pathlib.Path(skill_env_path)).strip()
    if not key:
        raise GuidedError(
            f"No FAL_KEY found. Create {shared_key_path()} with a line "
            f"FAL_KEY=<your key from https://fal.ai/dashboard/keys>, or set the "
            f"FAL_KEY environment variable."
        )
    os.environ["FAL_KEY"] = key
    return key


def upload_file(path: str) -> str:
    if fal_client is None:
        raise GuidedError("fal-client not installed. Run install.ps1.")
    return fal_client.upload_file(path)


def subscribe(endpoint: str, arguments: dict, with_logs: bool = False) -> dict:
    if fal_client is None:
        raise GuidedError("fal-client not installed. Run install.ps1.")
    return fal_client.subscribe(endpoint, arguments=arguments, with_logs=with_logs)


def download(url: str, out_path: str) -> str:
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)
    return out_path
