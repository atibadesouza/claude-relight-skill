"""Verify the Relight skill's environment is ready."""
import importlib
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError, load_fal_key


def main():
    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        present = shutil.which(tool) is not None
        ok = ok and present
        print(f"[{'OK' if present else 'XX'}] {tool}")
    for mod in ("cv2", "fal_client"):
        try:
            importlib.import_module(mod)
            print(f"[OK] python: {mod}")
        except ImportError:
            ok = False
            print(f"[XX] python: {mod} (run install.ps1)")
    try:
        load_fal_key()
        print("[OK] FAL_KEY loaded from .env")
    except GuidedError as e:
        ok = False
        print(f"[XX] FAL_KEY: {e}")
    # Sync mode only — advisory, never flips `ok` (Motion mode needs only the Fal key)
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import heygen_common
        heygen_common.load_heygen_key()
        print("[OK] HeyGen key found — Sync mode (Avatar IV) available")
    except Exception:
        print("[--] HeyGen key not set — Sync mode unavailable (Motion mode still works). "
              "Add ~/.claude/heygen.env to enable.")
    try:
        import requests  # noqa: F401
        print("[OK] python: requests")
    except ImportError:
        print("[--] 'requests' not installed — Sync mode needs it. Run install.ps1 / pip install -r requirements.txt.")
    print("\nREADY" if ok else "\nNOT READY - fix the [XX] items above.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
