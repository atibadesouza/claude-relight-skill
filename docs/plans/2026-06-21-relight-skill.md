# Relight Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shareable Claude Code skill, "Relight," that relights short talking-head footage via Fal AI (Nano Banana Pro still → Kling O1 video-to-video reference), reproducing the Systems by Vic workflow.

**Architecture:** Focused Python scripts sharing one helper module (`relight_common`): `preflight`, `extract_frame`, `relight_image`, `relight_video` (single ≤10s clip), plus batch trio `split_video` / `concat_video` / `relight_batch` for footage >10s. `SKILL.md` orchestrates them, including the human approval gate. Batch mode generates ONE relit still from the whole video and reuses it across all segments for cross-seam consistency, then concatenates. An `install.ps1` symlinks the canonical repo skill into `~/.claude/skills/` and installs system + Python deps. Pure logic (sharpness, validation, cost, segment planning, concat-list building, prompt/payload building) is unit-tested; paid Fal calls are exercised via `--dry-run`; one real end-to-end run is the manual done-gate.

**Tech Stack:** Python 3, pytest, `fal-client`, `opencv-python`, system `ffmpeg`/`ffprobe` (via winget), PowerShell (install).

## Global Constraints

- **Kling O1 input limits (verbatim):** video 3–10 seconds (3s floor AND 10s ceiling), 720–2160px, ≤200MB. Resolution/size outside → stop. Duration >10s → batch mode (even-split into 3–10s segments); duration <3s → stop. Never silently truncate.
- **Fal is paid.** No script makes a paid Fal call without (a) a valid `FAL_KEY` and (b) for the video step, explicit user approval. `--dry-run` must spend nothing.
- **Secrets:** `FAL_KEY` only ever read from the skill's local `.env` (gitignored). Never printed, never pasted in chat.
- **Canonical source of truth:** `.claude/skills/relight/` in the repo. User-level copy is a symlink created by `install.ps1` — never edited directly.
- **Fal endpoints (pinned):** image = `fal-ai/nano-banana-pro/edit`; video = `fal-ai/kling-video/o1/video-to-video/reference`.
- **Python import name:** pip package `fal-client` imports as `fal_client`.
- All scripts run from any CWD; resolve paths relative to the script file, not CWD.

---

## File Structure

```
.claude/skills/relight/
├─ SKILL.md                     orchestration: setup, prompts, approval gate, errors, cost
├─ requirements.txt             fal-client, opencv-python, pytest
├─ .env.example                 FAL_KEY=
├─ scripts/
│  ├─ relight_common.py         env load, GuidedError, cost estimators, fal wrappers
│  ├─ preflight.py              verify ffmpeg/ffprobe + deps + FAL_KEY
│  ├─ extract_frame.py          probe, validate, sharpness, best-frame selection
│  ├─ relight_image.py          build image request, dry-run, run via Fal
│  ├─ relight_video.py          build video request, dry-run, run via Fal (one ≤10s clip)
│  ├─ split_video.py            plan_segments + ffmpeg even-split into ≤10s parts
│  ├─ concat_video.py           build_concat_list + ffmpeg concat to single mp4
│  └─ relight_batch.py          orchestrate split → relight each (shared still) → concat
└─ tests/
   ├─ test_common.py
   ├─ test_extract_frame.py
   ├─ test_relight_image.py
   ├─ test_relight_video.py
   ├─ test_split_video.py
   ├─ test_concat_video.py
   └─ test_relight_batch.py
install.ps1                     symlink skill to ~/.claude/skills; install deps; seed .env
README.md                       setup, Fal key, cost, usage, 10s constraint
```

---

### Task 1: Scaffold + shared helper module (`relight_common`)

**Files:**
- Create: `.claude/skills/relight/requirements.txt`
- Create: `.claude/skills/relight/.env.example`
- Create: `.claude/skills/relight/scripts/relight_common.py`
- Test: `.claude/skills/relight/tests/test_common.py`

**Interfaces:**
- Produces:
  - `class GuidedError(Exception)` — carries a user-facing remediation message in `.args[0]`.
  - `find_skill_root() -> pathlib.Path` — the `relight/` dir (parent of `scripts/`).
  - `load_fal_key() -> str` — reads `FAL_KEY` from `<skill_root>/.env`; sets `os.environ["FAL_KEY"]`; raises `GuidedError` with the `.env` path if missing/blank.
  - `estimate_image_cost(resolution: str) -> float` — `{"1K":0.15,"2K":0.15,"4K":0.30}` (Fal Nano Banana Pro pricing; web-search surcharge excluded).
  - `estimate_video_cost(duration_s: float) -> float` — Kling O1 estimate: `round(0.169 * duration_s, 2)` (= $0.76 for 4.5s, matching the reference video; rate chosen to avoid half-cent rounding ambiguity).

- [ ] **Step 1: Write requirements + env example**

`.claude/skills/relight/requirements.txt`:
```
fal-client>=0.5.0
opencv-python>=4.9.0
pytest>=8.0.0
```
`.claude/skills/relight/.env.example`:
```
# Get a key at https://fal.ai/dashboard/keys then copy this file to .env and paste it below.
FAL_KEY=
```

- [ ] **Step 2: Install deps**

Run: `python -m pip install -r ".claude/skills/relight/requirements.txt"`
Expected: installs fal-client, opencv-python, pytest (or "already satisfied").

- [ ] **Step 3: Write the failing tests**

`.claude/skills/relight/tests/test_common.py`:
```python
import os
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import relight_common as rc


def test_image_cost_table():
    assert rc.estimate_image_cost("1K") == 0.15
    assert rc.estimate_image_cost("4K") == 0.30


def test_video_cost_scales_with_duration():
    assert rc.estimate_video_cost(4.5) == 0.76  # round(0.169*4.5,2)
    assert rc.estimate_video_cost(10) == 1.69


def test_load_fal_key_missing_raises_guided(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "find_skill_root", lambda: tmp_path)
    (tmp_path / ".env").write_text("FAL_KEY=\n", encoding="utf-8")
    with pytest.raises(rc.GuidedError) as e:
        rc.load_fal_key()
    assert ".env" in str(e.value)


def test_load_fal_key_present(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "find_skill_root", lambda: tmp_path)
    (tmp_path / ".env").write_text("FAL_KEY=abc123\n", encoding="utf-8")
    assert rc.load_fal_key() == "abc123"
    assert os.environ["FAL_KEY"] == "abc123"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/relight/tests/test_common.py -v`
Expected: FAIL — `ModuleNotFoundError: relight_common`.

- [ ] **Step 5: Implement `relight_common.py`**

```python
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
    return round(0.17 * duration_s, 2)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/relight/tests/test_common.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/relight/requirements.txt .claude/skills/relight/.env.example .claude/skills/relight/scripts/relight_common.py .claude/skills/relight/tests/test_common.py
git commit -m "feat(relight): scaffold skill + shared helper module"
```

---

### Task 2: Frame extraction (`extract_frame.py`)

**Files:**
- Create: `.claude/skills/relight/scripts/extract_frame.py`
- Test: `.claude/skills/relight/tests/test_extract_frame.py`

**Interfaces:**
- Consumes: `relight_common.GuidedError`.
- Produces:
  - `sharpness(gray) -> float` — variance of Laplacian of a grayscale numpy array.
  - `validate_clip(probe: dict) -> list[str]` — returns human-readable warnings for any of: duration not in [3,10], min(width,height) not in [720,2160], size > 200MB. Empty list = OK.
  - `probe_video(path: str) -> dict` — `{"duration": float, "width": int, "height": int, "size_bytes": int}` via `ffprobe`. Raises `GuidedError` if ffprobe missing or file unreadable.
  - `extract_best_frame(path: str, out_path: str, n: int = 12) -> tuple[str, float]` — samples `n` evenly-spaced frames with OpenCV, writes the sharpest to `out_path`, returns `(out_path, score)`. Raises `GuidedError` if no frame is readable.

- [ ] **Step 1: Write the failing tests**

`.claude/skills/relight/tests/test_extract_frame.py`:
```python
import sys, pathlib
import numpy as np
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import extract_frame as ef


def test_sharpness_sharp_beats_blurry():
    rng = np.random.default_rng(0)
    sharp = (rng.integers(0, 255, (200, 200))).astype("uint8")
    blurry = np.full((200, 200), 128, dtype="uint8")
    assert ef.sharpness(sharp) > ef.sharpness(blurry)


def test_validate_clip_ok():
    assert ef.validate_clip(
        {"duration": 5.0, "width": 1920, "height": 1080, "size_bytes": 10_000_000}
    ) == []


def test_validate_clip_flags_long_and_big():
    w = ef.validate_clip(
        {"duration": 14.0, "width": 1920, "height": 1080, "size_bytes": 300_000_000}
    )
    assert any("10" in m for m in w)        # duration warning mentions the limit
    assert any("200" in m for m in w)       # size warning mentions the limit


def test_validate_clip_flags_low_res():
    w = ef.validate_clip(
        {"duration": 5.0, "width": 640, "height": 480, "size_bytes": 1_000_000}
    )
    assert any("720" in m for m in w)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/relight/tests/test_extract_frame.py -v`
Expected: FAIL — `ModuleNotFoundError: extract_frame`.

- [ ] **Step 3: Implement `extract_frame.py`**

```python
"""Probe a clip, validate it against Kling O1 limits, and extract the sharpest frame."""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError

MIN_DUR, MAX_DUR = 3.0, 10.0
MIN_DIM, MAX_DIM = 720, 2160
MAX_BYTES = 200 * 1024 * 1024


def sharpness(gray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def validate_clip(probe: dict) -> list[str]:
    warns = []
    d = probe["duration"]
    if not (MIN_DUR <= d <= MAX_DUR):
        warns.append(f"Duration {d:.1f}s is outside the 3-10s Kling limit.")
    if min(probe["width"], probe["height"]) < MIN_DIM:
        warns.append(f"Resolution {probe['width']}x{probe['height']} is below the 720px minimum.")
    if max(probe["width"], probe["height"]) > MAX_DIM:
        warns.append(f"Resolution {probe['width']}x{probe['height']} exceeds the 2160px maximum.")
    if probe["size_bytes"] > MAX_BYTES:
        warns.append(f"File is {probe['size_bytes']/1024/1024:.0f}MB, over the 200MB limit.")
    return warns


def probe_video(path: str) -> dict:
    if shutil.which("ffprobe") is None:
        raise GuidedError("ffprobe not found. Run install.ps1 (installs ffmpeg via winget).")
    p = pathlib.Path(path)
    if not p.exists():
        raise GuidedError(f"Video not found: {path}")
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height:format=duration",
           "-of", "json", str(p)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
        meta = json.loads(out)
        stream = meta["streams"][0]
        return {
            "duration": float(meta["format"]["duration"]),
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "size_bytes": p.stat().st_size,
        }
    except (subprocess.CalledProcessError, KeyError, IndexError, ValueError) as e:
        raise GuidedError(f"Could not read video metadata from {path}: {e}")


def extract_best_frame(path: str, out_path: str, n: int = 12) -> tuple[str, float]:
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if total <= 0:
        cap.release()
        raise GuidedError(f"No frames readable from {path}.")
    idxs = np.linspace(0, total - 1, min(n, total)).astype(int)
    best_frame, best_score = None, -1.0
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok:
            continue
        score = sharpness(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        if score > best_score:
            best_frame, best_score = frame, score
    cap.release()
    if best_frame is None:
        raise GuidedError(f"Could not decode any frame from {path}.")
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(out_path, best_frame)
    return out_path, best_score


def main():
    ap = argparse.ArgumentParser(description="Probe + extract sharpest frame.")
    ap.add_argument("video")
    ap.add_argument("--out", default="best_frame.png")
    ap.add_argument("--frames", type=int, default=12)
    args = ap.parse_args()
    try:
        probe = probe_video(args.video)
        warns = validate_clip(probe)
        out, score = extract_best_frame(args.video, args.out, args.frames)
        print(json.dumps({"probe": probe, "warnings": warns, "frame": out, "sharpness": score}, indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/relight/tests/test_extract_frame.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/relight/scripts/extract_frame.py .claude/skills/relight/tests/test_extract_frame.py
git commit -m "feat(relight): clip probe, validation, and sharpest-frame extraction"
```

---

### Task 3: Image relight (`relight_image.py`)

**Files:**
- Create: `.claude/skills/relight/scripts/relight_image.py`
- Test: `.claude/skills/relight/tests/test_relight_image.py`

**Interfaces:**
- Consumes: `relight_common.{load_fal_key, estimate_image_cost, GuidedError}`.
- Produces:
  - `CINEMATIC_TEMPLATE: str` — contains the literal token `{user_prompt}`.
  - `build_image_request(frame_url, reference_url, user_prompt, resolution="2K") -> dict` — returns Fal payload with keys `prompt` (template applied), `image_urls` (frame, then reference if given), `resolution`, `num_images=1`.
  - `run(frame_path, reference_path, user_prompt, out_path, resolution, dry_run) -> dict` — uploads local files via `fal_client.upload_file`, calls `fal_client.subscribe("fal-ai/nano-banana-pro/edit", ...)`, downloads result to `out_path`. When `dry_run`, returns `{"endpoint","payload","est_cost"}` WITHOUT uploading or calling Fal.

- [ ] **Step 1: Write the failing tests**

`.claude/skills/relight/tests/test_relight_image.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import relight_image as ri


def test_template_wraps_user_prompt():
    req = ri.build_image_request("f.png", None, "neon streamer background", "2K")
    assert "neon streamer background" in req["prompt"]
    assert req["prompt"] != "neon streamer background"   # template added context
    assert req["image_urls"] == ["f.png"]
    assert req["resolution"] == "2K"
    assert req["num_images"] == 1


def test_reference_appended_when_given():
    req = ri.build_image_request("f.png", "ref.png", "x", "1K")
    assert req["image_urls"] == ["f.png", "ref.png"]


def test_dry_run_spends_nothing(monkeypatch):
    # If fal_client is touched, fail loudly.
    monkeypatch.setattr(ri, "fal_client", None)
    out = ri.run("f.png", None, "warm office", "out.png", "2K", dry_run=True)
    assert out["endpoint"] == "fal-ai/nano-banana-pro/edit"
    assert out["est_cost"] == 0.15
    assert "warm office" in out["payload"]["prompt"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/relight/tests/test_relight_image.py -v`
Expected: FAIL — `ModuleNotFoundError: relight_image`.

- [ ] **Step 3: Implement `relight_image.py`**

```python
"""Generate a relit still from the source frame + optional reference via Fal Nano Banana Pro."""
import argparse
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError, estimate_image_cost, load_fal_key

try:
    import fal_client
except ImportError:
    fal_client = None

ENDPOINT = "fal-ai/nano-banana-pro/edit"

CINEMATIC_TEMPLATE = (
    "Relight and re-environment this person. Keep their exact face, identity, "
    "clothing, pose, and framing from the first image. Apply cinematic three-point "
    "lighting with a warm, flattering key light and soft fill; gentle rim light to "
    "separate the subject; natural shadow falloff; subtle film color grade; shallow "
    "depth of field. Make the subject look attractive, warm, and professional. "
    "Background and scene: {user_prompt}. Photorealistic, no distortion of the face, "
    "no text or watermarks."
)


def build_image_request(frame_url, reference_url, user_prompt, resolution="2K") -> dict:
    image_urls = [frame_url]
    if reference_url:
        image_urls.append(reference_url)
    return {
        "prompt": CINEMATIC_TEMPLATE.format(user_prompt=user_prompt),
        "image_urls": image_urls,
        "resolution": resolution,
        "num_images": 1,
    }


def run(frame_path, reference_path, user_prompt, out_path, resolution="2K", dry_run=False) -> dict:
    if dry_run:
        payload = build_image_request(frame_path, reference_path, user_prompt, resolution)
        return {"endpoint": ENDPOINT, "payload": payload, "est_cost": estimate_image_cost(resolution)}
    if fal_client is None:
        raise GuidedError("fal-client not installed. Run install.ps1 or pip install -r requirements.txt.")
    load_fal_key()
    frame_url = fal_client.upload_file(frame_path)
    reference_url = fal_client.upload_file(reference_path) if reference_path else None
    payload = build_image_request(frame_url, reference_url, user_prompt, resolution)
    result = fal_client.subscribe(ENDPOINT, arguments=payload, with_logs=False)
    url = result["images"][0]["url"]
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)
    return {"endpoint": ENDPOINT, "image": out_path, "remote_url": url,
            "est_cost": estimate_image_cost(resolution)}


def main():
    ap = argparse.ArgumentParser(description="Relight a frame into a new environment.")
    ap.add_argument("frame")
    ap.add_argument("prompt")
    ap.add_argument("--reference", default=None)
    ap.add_argument("--out", default="relit_still.png")
    ap.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        import json
        print(json.dumps(run(args.frame, args.reference, args.prompt, args.out,
                             args.resolution, args.dry_run), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/relight/tests/test_relight_image.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/relight/scripts/relight_image.py .claude/skills/relight/tests/test_relight_image.py
git commit -m "feat(relight): Nano Banana Pro image relight with cinematic prompt + dry-run"
```

---

### Task 4: Video relight (`relight_video.py`)

**Files:**
- Create: `.claude/skills/relight/scripts/relight_video.py`
- Test: `.claude/skills/relight/tests/test_relight_video.py`

**Interfaces:**
- Consumes: `relight_common.{load_fal_key, estimate_video_cost, GuidedError}`.
- Produces:
  - `VIDEO_PROMPT: str` — fixed instruction to preserve motion/identity and subtly animate the background.
  - `build_video_request(video_url, still_url, duration, keep_audio=True, aspect_ratio="auto") -> dict` — raises `GuidedError` if `duration` not in [3,10]; returns payload with `video_url`, `image_urls=[still_url]`, `keep_audio`, `duration=str(round(duration))`, `aspect_ratio`, `prompt=VIDEO_PROMPT`.
  - `run(video_path, still_path, duration, out_path, keep_audio=True, dry_run=False, approved=False) -> dict` — refuses to make the paid call unless `approved=True` (raises `GuidedError`); uploads inputs, calls `fal_client.subscribe("fal-ai/kling-video/o1/video-to-video/reference", ...)`, downloads to `out_path`. `dry_run` returns payload + est_cost without uploading/calling and without requiring approval.

- [ ] **Step 1: Write the failing tests**

`.claude/skills/relight/tests/test_relight_video.py`:
```python
import sys, pathlib
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import relight_video as rv
import relight_common as rc


def test_build_request_keeps_audio_and_reference():
    req = rv.build_video_request("v.mp4", "still.png", 5.0)
    assert req["keep_audio"] is True
    assert req["image_urls"] == ["still.png"]
    assert req["video_url"] == "v.mp4"
    assert req["duration"] == "5"
    assert req["prompt"] == rv.VIDEO_PROMPT


def test_build_request_rejects_out_of_bounds_duration():
    with pytest.raises(rc.GuidedError):
        rv.build_video_request("v.mp4", "s.png", 14.0)


def test_dry_run_spends_nothing_no_approval_needed(monkeypatch):
    monkeypatch.setattr(rv, "fal_client", None)
    out = rv.run("v.mp4", "s.png", 4.5, "out.mp4", dry_run=True)
    assert out["endpoint"] == "fal-ai/kling-video/o1/video-to-video/reference"
    assert out["est_cost"] == 0.76
    assert out["payload"]["keep_audio"] is True


def test_real_run_refuses_without_approval(monkeypatch):
    # Even with a fake client present, no approval => no spend.
    monkeypatch.setattr(rv, "fal_client", object())
    with pytest.raises(rc.GuidedError) as e:
        rv.run("v.mp4", "s.png", 4.5, "out.mp4", dry_run=False, approved=False)
    assert "approv" in str(e.value).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/relight/tests/test_relight_video.py -v`
Expected: FAIL — `ModuleNotFoundError: relight_video`.

- [ ] **Step 3: Implement `relight_video.py`**

```python
"""Relight the original clip using the approved still via Fal Kling O1 video-to-video reference."""
import argparse
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError, estimate_video_cost, load_fal_key

try:
    import fal_client
except ImportError:
    fal_client = None

ENDPOINT = "fal-ai/kling-video/o1/video-to-video/reference"

VIDEO_PROMPT = (
    "Preserve the subject's exact motion, performance, and identity from the source "
    "video. Apply the lighting, color grade, and environment from the reference image. "
    "Subtly animate the background (screens, lights, smoke, water, or ambient motion) "
    "for realism without distracting from the subject."
)


def build_video_request(video_url, still_url, duration, keep_audio=True, aspect_ratio="auto") -> dict:
    if not (3.0 <= duration <= 10.0):
        raise GuidedError(
            f"Clip is {duration:.1f}s; Kling O1 only accepts 3-10s. Trim it first."
        )
    return {
        "video_url": video_url,
        "image_urls": [still_url],
        "keep_audio": keep_audio,
        "duration": str(round(duration)),
        "aspect_ratio": aspect_ratio,
        "prompt": VIDEO_PROMPT,
    }


def run(video_path, still_path, duration, out_path, keep_audio=True, dry_run=False, approved=False) -> dict:
    if dry_run:
        payload = build_video_request(video_path, still_path, duration, keep_audio)
        return {"endpoint": ENDPOINT, "payload": payload, "est_cost": estimate_video_cost(duration)}
    if not approved:
        raise GuidedError("Video relight not approved. Confirm the still + cost before running the paid step.")
    if fal_client is None:
        raise GuidedError("fal-client not installed. Run install.ps1 or pip install -r requirements.txt.")
    load_fal_key()
    video_url = fal_client.upload_file(video_path)
    still_url = fal_client.upload_file(still_path)
    payload = build_video_request(video_url, still_url, duration, keep_audio)
    result = fal_client.subscribe(ENDPOINT, arguments=payload, with_logs=True)
    url = result["video"]["url"]
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)
    return {"endpoint": ENDPOINT, "video": out_path, "remote_url": url,
            "est_cost": estimate_video_cost(duration)}


def main():
    ap = argparse.ArgumentParser(description="Relight a clip with an approved reference still.")
    ap.add_argument("video")
    ap.add_argument("still")
    ap.add_argument("duration", type=float)
    ap.add_argument("--out", default="relit_video.mp4")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved", action="store_true")
    args = ap.parse_args()
    try:
        import json
        print(json.dumps(run(args.video, args.still, args.duration, args.out,
                             keep_audio=not args.no_audio, dry_run=args.dry_run,
                             approved=args.approved), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/relight/tests/test_relight_video.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest .claude/skills/relight/tests/ -v`
Expected: 15 passed.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/relight/scripts/relight_video.py .claude/skills/relight/tests/test_relight_video.py
git commit -m "feat(relight): Kling O1 video relight with approval gate + dry-run"
```

---

### Task 5: Segment planning + split (`split_video.py`)

**Files:**
- Create: `.claude/skills/relight/scripts/split_video.py`
- Test: `.claude/skills/relight/tests/test_split_video.py`

**Interfaces:**
- Consumes: `relight_common.GuidedError`.
- Produces:
  - `plan_segments(duration: float, max_len=10.0, min_len=3.0) -> list[tuple[float, float]]` — `[(start, length), ...]` covering `[0, duration]`. `ceil(duration/max_len)` segments of equal length; every length lands in `[min_len, max_len]` (even-split avoids the invalid <3s tail that naive 10s cuts produce).
  - `split_video(path: str, work_dir: str, segments: list[tuple[float,float]]) -> list[str]` — writes `seg_000.mp4 …` (re-encoded) via ffmpeg, returns the ordered paths. Raises `GuidedError` if ffmpeg missing.

- [ ] **Step 1: Write the failing tests**

`.claude/skills/relight/tests/test_split_video.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import split_video as sv


def test_short_clip_is_single_segment():
    assert sv.plan_segments(5.0) == [(0.0, 5.0)]
    assert sv.plan_segments(10.0) == [(0.0, 10.0)]   # exactly 10s stays single


def test_long_clip_even_split_in_bounds():
    segs = sv.plan_segments(21.0)
    assert len(segs) == 3                              # ceil(21/10)
    assert all(3.0 <= length <= 10.0 for _, length in segs)
    assert abs(sum(length for _, length in segs) - 21.0) < 0.01


def test_avoids_invalid_short_tail():
    # naive 10s cuts -> 10+10+1 (1s tail rejected by Kling). Even-split must not.
    assert all(length >= 3.0 for _, length in sv.plan_segments(21.0))


def test_just_over_limit_two_segments():
    segs = sv.plan_segments(10.1)
    assert len(segs) == 2
    assert all(3.0 <= length <= 10.0 for _, length in segs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/relight/tests/test_split_video.py -v`
Expected: FAIL — `ModuleNotFoundError: split_video`.

- [ ] **Step 3: Implement `split_video.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/relight/tests/test_split_video.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/relight/scripts/split_video.py .claude/skills/relight/tests/test_split_video.py
git commit -m "feat(relight): even-split long clips into Kling-legal segments"
```

---

### Task 6: Concatenation (`concat_video.py`)

**Files:**
- Create: `.claude/skills/relight/scripts/concat_video.py`
- Test: `.claude/skills/relight/tests/test_concat_video.py`

**Interfaces:**
- Consumes: `relight_common.GuidedError`.
- Produces:
  - `build_concat_list(paths: list[str]) -> str` — ffmpeg concat-demuxer text; one `file '<path>'` line per path, in order, backslashes normalized to `/`.
  - `concat_videos(paths: list[str], out_path: str) -> str` — writes a temp list file next to `out_path`, runs `ffmpeg -f concat -safe 0 -i list -c copy out` (falls back to re-encode), returns `out_path`. Raises `GuidedError` if ffmpeg missing.

- [ ] **Step 1: Write the failing tests**

`.claude/skills/relight/tests/test_concat_video.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import concat_video as cv


def test_concat_list_order_and_format():
    txt = cv.build_concat_list(["a.mp4", "b.mp4"])
    assert txt.strip().splitlines() == ["file 'a.mp4'", "file 'b.mp4'"]


def test_concat_list_normalizes_backslashes():
    txt = cv.build_concat_list([r"C:\work\seg_000.mp4"])
    assert txt.strip() == "file 'C:/work/seg_000.mp4'"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/relight/tests/test_concat_video.py -v`
Expected: FAIL — `ModuleNotFoundError: concat_video`.

- [ ] **Step 3: Implement `concat_video.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/relight/tests/test_concat_video.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/relight/scripts/concat_video.py .claude/skills/relight/tests/test_concat_video.py
git commit -m "feat(relight): concat relit segments into a single mp4"
```

---

### Task 7: Batch orchestrator (`relight_batch.py`)

**Files:**
- Create: `.claude/skills/relight/scripts/relight_batch.py`
- Test: `.claude/skills/relight/tests/test_relight_batch.py`

**Interfaces:**
- Consumes: `extract_frame.probe_video`, `split_video.{plan_segments, split_video}`, `concat_video.concat_videos`, `relight_video.{run as relight_video_run, ENDPOINT}`, `relight_common.{GuidedError, estimate_image_cost, estimate_video_cost}`.
- Produces:
  - `estimate_batch(duration: float, resolution="2K") -> dict` — `{"segments": int, "image_cost": float, "video_cost": float, "total": float}` (`video_cost` = Σ per-segment estimate; `total` = image + video).
  - `run_batch(video_path, still_path, work_dir, out_path, approved=False, dry_run=False, resolution="2K") -> dict` — probes, plans segments; `dry_run` returns `{"endpoint","plan","est_cost"}` with no spend; otherwise requires `approved=True` (else `GuidedError`), splits, relights each segment with the shared still (`relight_video_run(..., approved=True)`), concats, returns `{"video","segments","est_cost"}`. On a segment failure: raise `GuidedError` naming the segment index; do NOT concat a partial.

- [ ] **Step 1: Write the failing tests**

`.claude/skills/relight/tests/test_relight_batch.py`:
```python
import sys, pathlib
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import relight_batch as rb
import relight_common as rc

PROBE = {"duration": 21.0, "width": 1920, "height": 1080, "size_bytes": 1000}


def test_estimate_batch_counts_and_total():
    est = rb.estimate_batch(21.0, "2K")
    assert est["segments"] == 3
    assert est["total"] == round(0.15 + 3 * round(0.169 * 7, 2), 2)   # 0.15 + 3*1.18 = 3.69


def test_dry_run_spends_nothing(monkeypatch):
    monkeypatch.setattr(rb, "probe_video", lambda p: PROBE)
    out = rb.run_batch("v.mp4", "s.png", "work", "out.mp4", dry_run=True)
    assert out["plan"]["segments"] == 3
    assert out["est_cost"]["total"] == rb.estimate_batch(21.0)["total"]


def test_real_run_refuses_without_approval(monkeypatch):
    monkeypatch.setattr(rb, "probe_video", lambda p: PROBE)
    with pytest.raises(rc.GuidedError) as e:
        rb.run_batch("v.mp4", "s.png", "work", "out.mp4", dry_run=False, approved=False)
    assert "approv" in str(e.value).lower()


def test_segment_failure_stops_without_concat(monkeypatch):
    monkeypatch.setattr(rb, "probe_video", lambda p: PROBE)
    monkeypatch.setattr(rb, "split_video", lambda p, w, segs: ["s0.mp4", "s1.mp4", "s2.mp4"])
    def boom(*a, **k): raise RuntimeError("fal 500")
    monkeypatch.setattr(rb, "relight_video_run", boom)
    called = {"concat": False}
    monkeypatch.setattr(rb, "concat_videos", lambda *a, **k: called.__setitem__("concat", True))
    with pytest.raises(rc.GuidedError) as e:
        rb.run_batch("v.mp4", "s.png", "work", "out.mp4", dry_run=False, approved=True)
    assert "segment" in str(e.value).lower()
    assert called["concat"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/relight/tests/test_relight_batch.py -v`
Expected: FAIL — `ModuleNotFoundError: relight_batch`.

- [ ] **Step 3: Implement `relight_batch.py`**

```python
"""Batch relight: split a >10s clip, relight each segment with one shared still, concat."""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from relight_common import GuidedError, estimate_image_cost, estimate_video_cost
from extract_frame import probe_video
from split_video import plan_segments, split_video
from concat_video import concat_videos
from relight_video import run as relight_video_run, ENDPOINT

try:
    import fal_client
except ImportError:
    fal_client = None


def estimate_batch(duration: float, resolution: str = "2K") -> dict:
    segs = plan_segments(duration)
    video = round(sum(estimate_video_cost(length) for _, length in segs), 2)
    image = estimate_image_cost(resolution)
    return {"segments": len(segs), "image_cost": image, "video_cost": video,
            "total": round(image + video, 2)}


def run_batch(video_path, still_path, work_dir, out_path,
              approved=False, dry_run=False, resolution="2K") -> dict:
    probe = probe_video(video_path)
    duration = probe["duration"]
    segments = plan_segments(duration)
    if dry_run:
        return {"endpoint": ENDPOINT,
                "plan": {"segments": len(segments), "lengths": [l for _, l in segments]},
                "est_cost": estimate_batch(duration, resolution)}
    if not approved:
        raise GuidedError("Batch relight not approved. Confirm the still + total cost before the paid run.")
    seg_paths = split_video(video_path, work_dir, segments)
    relit = []
    for i, (seg_path, (_, length)) in enumerate(zip(seg_paths, segments)):
        seg_out = str(pathlib.Path(work_dir) / f"relit_{i:03d}.mp4")
        try:
            relight_video_run(seg_path, still_path, length, seg_out, approved=True)
        except Exception as e:
            raise GuidedError(
                f"Segment {i} failed: {e}. {len(relit)} of {len(segments)} segments rendered; "
                f"not concatenating a partial result. Re-run when resolved."
            )
        relit.append(seg_out)
    concat_videos(relit, out_path)
    return {"video": out_path, "segments": len(segments), "est_cost": estimate_batch(duration, resolution)["total"]}


def main():
    ap = argparse.ArgumentParser(description="Batch relight a >10s clip.")
    ap.add_argument("video")
    ap.add_argument("still")
    ap.add_argument("--work", default="relight_work")
    ap.add_argument("--out", default="relit_video.mp4")
    ap.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved", action="store_true")
    args = ap.parse_args()
    try:
        import json
        print(json.dumps(run_batch(args.video, args.still, args.work, args.out,
                                   approved=args.approved, dry_run=args.dry_run,
                                   resolution=args.resolution), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/relight/tests/test_relight_batch.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest .claude/skills/relight/tests/ -v`
Expected: 25 passed.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/relight/scripts/relight_batch.py .claude/skills/relight/tests/test_relight_batch.py
git commit -m "feat(relight): batch orchestrator (split -> relight each -> concat)"
```

---

### Task 8: Preflight check (`preflight.py`)

**Files:**
- Create: `.claude/skills/relight/scripts/preflight.py`

**Interfaces:**
- Consumes: `relight_common.{load_fal_key, GuidedError}`.
- Produces: CLI that prints a checklist (ffmpeg, ffprobe, cv2, fal_client, FAL_KEY) with ✓/✗ and exits non-zero if anything fails. No new public functions other scripts depend on.

- [ ] **Step 1: Implement `preflight.py`**

```python
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
    print("\nREADY" if ok else "\nNOT READY — fix the [XX] items above.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it (some items may legitimately fail pre-install)**

Run: `python ".claude/skills/relight/scripts/preflight.py"`
Expected: prints a checklist; exits 1 until ffmpeg + .env are set up (that's correct behavior).

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/relight/scripts/preflight.py
git commit -m "feat(relight): environment preflight check"
```

---

### Task 9: Orchestration doc (`SKILL.md`)

**Files:**
- Create: `.claude/skills/relight/SKILL.md`

**Interfaces:** None (documentation). Must encode the exact run order, the approval gate, and cost messaging so Claude Code drives the scripts correctly.

- [ ] **Step 1: Write `SKILL.md`**

Frontmatter + body. Required content:
- Frontmatter `name: relight`, `description:` triggering on "relight", "fix my lighting/background", "put me in a new background/studio", talking-head footage, referencing Fal/Nano Banana/Kling.
- **Setup section:** point to `install.ps1`; how to put the key in `.env` (edit the file, never paste in chat); run `preflight.py`.
- **Inputs:** video file path (any length — ≤10s runs single, >10s runs batch), a text description, optional reference image path. Tell the user to copy-as-path on Windows.
- **Run order (exact commands):**
  1. `python scripts/extract_frame.py "<video>" --out "<work>/frame.png"` → read the JSON. Note `probe.duration`. If `warnings` mention resolution/size, relay and stop (these aren't auto-fixable). Duration is handled by branching below, not a warning-stop.
  2. `python scripts/relight_image.py "<work>/frame.png" "<user prompt>" [--reference "<ref>"] --out "<work>/still.png" --resolution 2K` → show the still to the user. (One still is generated from the whole video's best frame and reused for every segment in batch mode.)
  3. **Approval gate (cost depends on the branch):**
     - If `duration ≤ 10`: get the figure from `python scripts/relight_video.py "<video>" "<work>/still.png" <duration> --dry-run`.
     - If `duration > 10`: get the figure from `python scripts/relight_batch.py "<video>" "<work>/still.png" --dry-run` → use `est_cost.total` and report the segment count (e.g., "23s → 3 segments → ~$2.49 total").
     - Present the still + the dollar estimate. Ask the user to approve or request a rerun (loop back to step 2 with tweaks).
  4. **On approval, branch:**
     - `duration ≤ 10`: `python scripts/relight_video.py "<video>" "<work>/still.png" <duration> --out "<output_dir>/relit_<name>.mp4" --approved`
     - `duration > 10`: `python scripts/relight_batch.py "<video>" "<work>/still.png" --work "<work>" --out "<output_dir>/relit_<name>.mp4" --approved`
     → report the final path. The batch path splits, relights each segment with the shared still, and concatenates automatically.
- **Output dir rule:** default `./relight-outputs/` in the CWD project; fall back to `~/Documents/relight/`; honor a user-specified path. `<work>` is a temp subfolder (e.g., `<output_dir>/.work-<name>/`) for frames + segments.
- **Cost transparency:** always state the dollar estimate before the paid step; for batch, state the per-segment count and total; never run without explicit approval.
- **Error handling:** if any script exits non-zero, relay the `ERROR:` line verbatim and stop; don't retry blindly. For a batch mid-failure, relay which segment failed — already-rendered segments are kept in `<work>`, nothing partial is concatenated.
- **Constraint reminder:** each Kling call is one 3–10s segment. ≤10s footage = one call; >10s = automatic even-split + concat. The 3s floor means a sub-3s clip is rejected (relay the floor and stop).

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/relight/SKILL.md
git commit -m "docs(relight): SKILL.md orchestration + approval gate"
```

---

### Task 10: Installer + README + symlink

**Files:**
- Create: `install.ps1`
- Create: `README.md`

**Interfaces:** None. `install.ps1` is the clone→use entry point.

- [ ] **Step 1: Write `install.ps1`**

```powershell
# Relight skill installer (Windows).
$ErrorActionPreference = "Stop"
$repoSkill = Join-Path $PSScriptRoot ".claude\skills\relight"
$userSkills = Join-Path $env:USERPROFILE ".claude\skills"
$link = Join-Path $userSkills "relight"

Write-Host "1/4 Installing ffmpeg (winget)..."
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
} else { Write-Host "  ffmpeg already present." }

Write-Host "2/4 Installing Python deps..."
python -m pip install -r (Join-Path $repoSkill "requirements.txt")

Write-Host "3/4 Linking skill into ~/.claude/skills ..."
New-Item -ItemType Directory -Force -Path $userSkills | Out-Null
if (Test-Path $link) { Write-Host "  Link/folder already exists, skipping." }
else {
    try {
        New-Item -ItemType SymbolicLink -Path $link -Target $repoSkill | Out-Null
        Write-Host "  Symlinked."
    } catch {
        Write-Warning "  Symlink failed (enable Developer Mode or run as admin). Copying instead."
        Copy-Item $repoSkill $link -Recurse
    }
}

Write-Host "4/4 Seeding .env ..."
$envFile = Join-Path $repoSkill ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $repoSkill ".env.example") $envFile
    Write-Host "  Created $envFile — edit it and paste your FAL_KEY."
} else { Write-Host "  .env already exists." }

Write-Host "`nDone. Edit $envFile, then run:"
Write-Host "  python `"$repoSkill\scripts\preflight.py`""
```

- [ ] **Step 2: Write `README.md`**

Cover: what it does (1 paragraph + before/after framing), how clips ≤10s run as a single relight and longer clips are auto-split into 3–10s segments and concatenated (with one shared still for consistency), prerequisites (Claude Code, Python, a Fal key with credit), `git clone` → `./install.ps1` → edit `.env` → `preflight.py`, usage example ("Use the relight skill on `C:\path\clip.mp4` — put me in a three-point setup with neon streamer lights; reference `C:\path\ref.jpg`"), cost expectations (~$0.15 image + ~$0.17/sec video; e.g. a 24s clip ≈ 3 segments ≈ $4), and that outputs land in `relight-outputs/`. Credit the Systems by Vic video as inspiration.

- [ ] **Step 3: Commit**

```bash
git add install.ps1 README.md
git commit -m "feat(relight): installer, README, user-level symlink"
```

---

### Task 11: End-to-end done-gate (manual, paid)

**Files:** None (verification only).

- [ ] **Step 1:** Run `install.ps1`, edit `.env` with a real `FAL_KEY`, run `preflight.py` → expect `READY`.
- [ ] **Step 2 (single):** Export a real ≤10s talking-head clip; run the full skill flow end-to-end through Claude Code.
- [ ] **Step 3 (single) verify done-gate:** lighting cinematic/flattering, identity preserved, background matches intent and animates subtly, **audio preserved**, output in `relight-outputs/`, cost shown before the paid step.
- [ ] **Step 4 (batch):** Run a real clip **>10s** (e.g. ~20–25s). Confirm: the cost gate reports the segment count + total before spending; the same approved still is used for all segments; the final stitched MP4 plays continuously with **audio intact across seams**; seams are not jarring; output is a single file in `relight-outputs/`.
- [ ] **Step 5:** For any defect found (single or batch — e.g. audio gap at a seam, visible lighting jump between segments, wrong segment order), add a regression test under `tests/` and fix before calling it done.

---

## Test Plan

- **Smoke test:** `python -m pytest .claude/skills/relight/tests/ -v` → 25 passed (pure logic, no paid calls). Plus `preflight.py` printing a correct checklist. Pass signal: all unit tests green and preflight accurately reports environment state.
- **Backend / script-logic tests (in the tasks above):**
  - *common:* cost tables; `load_fal_key` guided-stop on missing/blank key vs. success.
  - *extract_frame:* sharp>blurry sharpness; `validate_clip` OK at 5s/1080p; flags >10s duration, >200MB size, <720p resolution.
  - *relight_image:* cinematic template wraps the user prompt; reference image appended only when supplied; `--dry-run` returns payload + cost and touches no Fal client.
  - *relight_video:* `keep_audio=true` + `image_urls=[still]` + duration string; out-of-bounds duration raises before any call; `--dry-run` spends nothing; **real run refuses without `approved=True`**.
  - *split_video:* `plan_segments` returns `ceil(dur/10)` segments all within 3–10s and covering the full duration; 10.0s stays single, 10.1s → 2; the 21s case yields 3×7s (never a sub-3s tail).
  - *concat_video:* `build_concat_list` emits ordered, backslash-normalized `file '…'` lines.
  - *relight_batch:* `estimate_batch` reports correct segment count + total; `--dry-run` spends nothing; **refuses without `--approved`**; a mid-batch segment failure raises naming the segment and **does not concat a partial**.
- **Abuse / edge / concurrency:** missing `FAL_KEY` → guided stop (not a stack trace); nonexistent video/reference path → clean `GuidedError`; corrupt/non-video file → `probe_video` raises cleanly; resolution/size out of bounds → stop (no silent truncation); duration boundary 10.0 vs 10.1 routes single vs batch; re-approval/rerun at the gate re-uses the approved still and does not double-spend.
- **Cost-safety regression:** `relight_video` and `relight_batch` both refuse the real run without approval, and all three `--dry-run` paths spend nothing — proving no paid call happens without (a) a key and (b) explicit approval. This is the core money-safety guard, now covering the multi-segment batch total too.
- **AI-output quality (manual done-gate, Task 11):** one real single-clip run + one real batch (>10s) run judged on cinematic/flattering lighting, identity preservation, background match + subtle animation, audio preservation, and — for batch — seam continuity (audio + visual) across stitched segments. Not just "a file came back."
- **Known-bug regressions:** each defect from Task 11 (single or batch, e.g. seam audio gap, inter-segment lighting jump, wrong order) gets a test under `tests/` so it can't silently return.
- **Done-gate:** unit suite (25) green + preflight accurate + cost-safety green + one human-reviewed single run AND one human-reviewed batch run (golden path + audio + identity + background animation + seam continuity + edge/error states) before calling the skill done.
```
