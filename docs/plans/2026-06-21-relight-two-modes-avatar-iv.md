# Relight Two Modes (Kling Motion + HeyGen Avatar IV Sync) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a user-selectable **Sync mode** (HeyGen Avatar IV) to the Relight skill alongside the existing **Motion mode** (Kling), and revert the abandoned Fal lip-sync stage.

**Architecture:** Both modes share the front half (best frame → relit still → approval). Motion mode is the unchanged Kling video-to-video pipeline. Sync mode is new: extract the clip's audio, upload the approved relit still + audio to HeyGen, generate an Avatar IV video (perfect lip-sync, generated motion), poll, download. New `heygen_common.py` (key + HTTP) and `heygen_avatar.py` (audio extract, dimension, payload, run/poll) scripts, mirroring the validation spike that already rendered a user-approved result. SKILL.md gains a mode-selection step.

**Tech Stack:** Python 3, `requests` (HeyGen HTTP), `fal_client` (existing), ffmpeg/ffprobe (existing). HeyGen REST API (`X-Api-Key`).

**Reference spec:** `docs/superpowers/specs/2026-06-21-relight-two-modes-avatar-iv-design.md`.

## Global Constraints

- **HeyGen auth:** header `X-Api-Key`. Base `https://api.heygen.com`; uploads host `https://upload.heygen.com`.
- **HeyGen key** resolves via `heygen_common.load_heygen_key()`: `HEYGEN_API_KEY` env, else `~/.claude/heygen.env`. Missing/blank → `GuidedError` naming that path. Never commit the key.
- **Upload cap 32MB** per HeyGen asset. Audio extracted as **mp3** to stay under it; still is small (~5MB).
- **Avatar IV output ≤1080p.** `dimension` derived from the still's aspect, shorter side capped at 1080.
- **Paid-step discipline:** `--dry-run` (no spend; prints endpoint + payload + estimate); real generate requires `--approved`. Always show the dollar estimate first. Avatar IV ≈ **$4/min**.
- **Errors** are `GuidedError`, printed by `main()` as one `ERROR: …` line to stderr + `sys.exit(1)` (matches every existing Relight script).
- **Credit gotcha:** HeyGen returns `Insufficient credit. This operation requires 'api' credits.` — detect and raise a fund-credits `GuidedError`, never a cryptic failure.
- **Platform:** Windows; commands via Bash tool (Git Bash) with ffmpeg on PATH. `<skill>` = `.claude/skills/relight/`.

## File Structure

- **Delete:** `scripts/lipsync_video.py`, `tests/test_lipsync_video.py`.
- **Create:** `scripts/heygen_common.py`, `scripts/heygen_avatar.py`, `tests/test_heygen_avatar.py`, `heygen.env.example`.
- **Modify:** `SKILL.md` (revert lip-sync edits + add mode selection & Sync steps), `scripts/preflight.py` (HeyGen key check), `requirements.txt` (add `requests`), `docs/plans/2026-06-21-relight-skill-buildlog.md` (remove lip-sync section).

---

### Task 1: Revert the abandoned Fal lip-sync stage

**Files:**
- Delete: `.claude/skills/relight/scripts/lipsync_video.py`, `.claude/skills/relight/tests/test_lipsync_video.py`
- Modify: `.claude/skills/relight/SKILL.md`, `docs/plans/2026-06-21-relight-skill-buildlog.md`

**Interfaces:** none produced; this restores Motion mode to its pre-lip-sync form.

- [ ] **Step 1: Delete the lip-sync script + tests**

```bash
cd ".claude/skills/relight"
git rm scripts/lipsync_video.py tests/test_lipsync_video.py
```

- [ ] **Step 2: Revert the SKILL.md lip-sync edits**

In `SKILL.md`, restore the four edits made by commit `2e71e8d`:
1. **Step 3** — remove the "Then add the **lip-sync** estimate…" paragraph and the "combined" wording; restore the original: `Present the still + the dollar estimate. Ask the user to **approve**, or request a rerun (loop back to Step 2 with a tweaked prompt / new reference). Do not proceed without explicit approval.`
2. **Step 4** — restore the heading `**Step 4 — on approval, run the paid step (branch on duration):**` and change both run commands' `--out "<work>/relit.mp4"` back to `--out "<out>"`; restore the trailing line `Report the final path. Batch automatically splits → relights each segment with the shared still → concatenates.`
3. **Remove the entire `**Step 5 — fix lip-sync (always runs).**` block.**
4. **Output / Cost transparency / Constraints** — delete the lip-sync sentences added in those three sections, restoring them to the commit-`cbc02d2` text (Output ends at "Intermediate segments live in `<work>` and can be deleted."; Cost ends at "a 24s clip ≈ 3 segments ≈ ~$4)."; Constraints ends at "Video must be 720–2160px and ≤200MB per Kling O1.").

(Task 6 re-edits SKILL.md for the two-mode flow; this step only removes the dead lip-sync content so the diff is clean.)

- [ ] **Step 3: Remove the lip-sync section from the buildlog**

In `docs/plans/2026-06-21-relight-skill-buildlog.md`, delete the `## Lip-sync stage — paid done-gate (2026-06-21)` section added by commit `4f7eeb5`.

- [ ] **Step 4: Verify the Relight (Kling) suite is green without the lip-sync module**

Run: `cd .claude/skills/relight && python -m pytest -q`
Expected: **all green, 0 failures** — `test_lipsync_video.py` gone. (For reference the non-lip-sync suite is **29 passed**: test_common 7, test_concat 2, test_extract_frame 4, test_relight_batch 4, test_relight_image 3, test_relight_video 5, test_split 4. Treat "0 failures" as the gate, not a pinned integer.)

- [ ] **Step 5: Commit**

```bash
git add -A .claude/skills/relight docs/plans/2026-06-21-relight-skill-buildlog.md
git commit -m "revert(relight): remove abandoned Fal lip-sync stage"
```

---

### Task 2: `heygen_common.py` — key loading + HTTP helpers

**Files:**
- Create: `.claude/skills/relight/scripts/heygen_common.py`
- Modify: `.claude/skills/relight/requirements.txt`
- Test: `.claude/skills/relight/tests/test_heygen_avatar.py`

**Interfaces:**
- Produces:
  - `API = "https://api.heygen.com"`, `UPLOAD = "https://upload.heygen.com"`.
  - `load_heygen_key() -> str` — env then `~/.claude/heygen.env`; raises `GuidedError` if absent/blank.
  - `headers(key, content_type=None) -> dict`.
  - `check_credit_error(payload: dict) -> None` — raises a fund-credits `GuidedError` if `payload["message"]` contains "insufficient credit" (case-insensitive).
  - `_parse_data(resp) -> dict` — returns `resp.json()["data"]`, but converts HeyGen's 200-with-error envelopes and credit errors into `GuidedError` (never a raw `KeyError`/traceback). `_require_under_cap(path)` raises `GuidedError` if a file exceeds the 32MB upload cap.
  - `upload_talking_photo(key, image_path) -> str` (talking_photo_id), `upload_audio_asset(key, audio_path) -> str` (url), `generate_avatar_iv(key, payload) -> str|None` (video_id), `get_status(key, video_id) -> dict` — all routed through `_parse_data`, so a failed/credit-starved/over-cap upload raises a clean `GuidedError`, not a traceback.

- [ ] **Step 1: Add `requests` to requirements**

In `.claude/skills/relight/requirements.txt`, add a line: `requests`.

- [ ] **Step 2: Write the failing test (key loading + credit detection)**

Create `.claude/skills/relight/tests/test_heygen_avatar.py`:

```python
import sys, pathlib
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import heygen_common as hc
import relight_common as rc


def test_load_key_from_env(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "sk_test_123")
    assert hc.load_heygen_key() == "sk_test_123"


def test_load_key_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    monkeypatch.setattr(hc.pathlib.Path, "home", lambda: tmp_path)  # empty home, no heygen.env
    with pytest.raises(rc.GuidedError):
        hc.load_heygen_key()


def test_headers_sets_api_key_and_content_type():
    h = hc.headers("k", "application/json")
    assert h["X-Api-Key"] == "k"
    assert h["Content-Type"] == "application/json"
    assert "Content-Type" not in hc.headers("k")


def test_check_credit_error_raises_on_insufficient():
    with pytest.raises(rc.GuidedError) as e:
        hc.check_credit_error({"status": "failed", "message": "Insufficient credit. This operation requires 'api' credits."})
    assert "credit" in str(e.value).lower()


def test_check_credit_error_silent_when_fine():
    hc.check_credit_error({"status": "processing"})   # no raise
    hc.check_credit_error({})                          # no raise


class _Resp:
    """Minimal stand-in for a requests.Response."""
    content = b"x"
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


def test_parse_data_returns_data_dict():
    assert hc._parse_data(_Resp({"data": {"url": "u"}})) == {"url": "u"}


def test_parse_data_missing_data_raises_guided_not_keyerror():
    with pytest.raises(rc.GuidedError):                       # NOT KeyError
        hc._parse_data(_Resp({"error": "bad input"}))


def test_parse_data_credit_error_in_envelope_raises():
    with pytest.raises(rc.GuidedError) as e:
        hc._parse_data(_Resp({"message": "Insufficient credit. This operation requires 'api' credits."}))
    assert "credit" in str(e.value).lower()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd .claude/skills/relight && python -m pytest tests/test_heygen_avatar.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'heygen_common'`.

- [ ] **Step 4: Write `heygen_common.py`**

Create `.claude/skills/relight/scripts/heygen_common.py`:

```python
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
    return r.json().get("data", {})
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd .claude/skills/relight && python -m pytest tests/test_heygen_avatar.py -q`
Expected: PASS (8 passed).

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/relight/scripts/heygen_common.py .claude/skills/relight/tests/test_heygen_avatar.py .claude/skills/relight/requirements.txt
git commit -m "feat(relight): heygen_common — key load + HTTP + credit-error detection"
```

---

### Task 3: `heygen_avatar.py` pure functions (audio cmd, dimension, payload, cost)

**Files:**
- Create: `.claude/skills/relight/scripts/heygen_avatar.py`
- Test: `.claude/skills/relight/tests/test_heygen_avatar.py`

**Interfaces:**
- Produces:
  - `audio_extract_cmd(video_path, out_mp3) -> list[str]` (ffmpeg argv → mp3).
  - `aspect_to_dimension(width, height, cap=1080) -> dict` — `{"width", "height"}`, shorter side ≤ cap, even, no upscale.
  - `build_generate_request(talking_photo_id, audio_url, dimension, title) -> dict`.
  - `estimate_avatar_cost(duration_s) -> float` (= $4/min).

- [ ] **Step 1: Write the failing test**

Append to `.claude/skills/relight/tests/test_heygen_avatar.py`:

```python
import heygen_avatar as ha


def test_audio_extract_cmd_makes_mp3():
    cmd = ha.audio_extract_cmd("clip.mp4", "a.mp3")
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert "libmp3lame" in cmd
    assert cmd[-1] == "a.mp3"


def test_aspect_to_dimension_square_caps_to_1080():
    assert ha.aspect_to_dimension(1440, 1440) == {"width": 1080, "height": 1080}


def test_aspect_to_dimension_landscape_1080p():
    assert ha.aspect_to_dimension(1920, 1080) == {"width": 1920, "height": 1080}


def test_aspect_to_dimension_no_upscale():
    assert ha.aspect_to_dimension(720, 720) == {"width": 720, "height": 720}


def test_aspect_to_dimension_even_dimensions():
    d = ha.aspect_to_dimension(1441, 1080)   # odd width in -> even out
    assert d["width"] % 2 == 0 and d["height"] % 2 == 0


def test_aspect_to_dimension_preserves_ratio_and_caps_short_side():
    d = ha.aspect_to_dimension(1170, 2532)   # phone portrait, non-trivial ratio
    assert min(d["width"], d["height"]) <= 1080            # short side capped
    assert abs(d["width"] / d["height"] - 1170 / 2532) < 0.01   # ratio preserved


def test_build_generate_request_shape():
    req = ha.build_generate_request("tp123", "https://a/audio.mp3", {"width": 1080, "height": 1080}, "My Title")
    assert req["use_avatar_iv_model"] is True
    assert req["dimension"] == {"width": 1080, "height": 1080}
    vi = req["video_inputs"][0]
    assert vi["character"] == {"type": "talking_photo", "talking_photo_id": "tp123"}
    assert vi["voice"] == {"type": "audio", "audio_url": "https://a/audio.mp3"}
    assert req["test"] is False


def test_estimate_avatar_cost_four_dollars_per_minute():
    assert ha.estimate_avatar_cost(60.0) == 4.00
    assert ha.estimate_avatar_cost(30.0) == 2.00
    assert ha.estimate_avatar_cost(54.0) == 3.60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/relight && python -m pytest tests/test_heygen_avatar.py -k "extract or dimension or build_generate or estimate" -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'heygen_avatar'`.

- [ ] **Step 3: Write the pure functions**

Create `.claude/skills/relight/scripts/heygen_avatar.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/relight && python -m pytest tests/test_heygen_avatar.py -q`
Expected: PASS — all green (16 in the file so far: 8 from Task 2 + 8 here).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/relight/scripts/heygen_avatar.py .claude/skills/relight/tests/test_heygen_avatar.py
git commit -m "feat(relight): heygen_avatar pure fns — audio cmd, dimension, payload, cost"
```

---

### Task 4: `heygen_avatar.py` orchestration (probe, run, poll) + CLI

**Files:**
- Modify: `.claude/skills/relight/scripts/heygen_avatar.py`
- Test: `.claude/skills/relight/tests/test_heygen_avatar.py`

**Interfaces:**
- Produces:
  - `probe_duration(video_path) -> float`, `probe_dimensions(image_path) -> tuple[int,int]` (via ffprobe).
  - `run(video_path, still_path, out_path, title=None, dry_run=False, approved=False) -> dict` — dry-run returns `{"endpoint","payload","est_cost"}` and spends nothing; real run requires `approved`, extracts audio (mp3), uploads still+audio, generates, polls, downloads. Returns `{"endpoint","video","video_id","est_cost"}`.
  - `poll_until_done(key, video_id, out_path, interval=15, max_tries=160) -> str` — emits periodic status to **stderr** (stdout is the JSON contract), downloads via `_download` (requests + 120s timeout), and `_verify_nonempty` rejects a 0-byte download (relaying the recoverable `video_url`). `run()` prints `video_id` to stderr before polling so a spent-but-undownloaded render is recoverable.
  - `_download(url, out_path) -> str`, `_verify_nonempty(out_path, recover_url) -> None`.
  - `main()` — CLI: `video`, `still`, `--out` (default `synced_video.mp4`), `--title`, `--dry-run`, `--approved`.

- [ ] **Step 1: Write the failing test (guards)**

Append to `.claude/skills/relight/tests/test_heygen_avatar.py`:

```python
def test_dry_run_spends_nothing_no_approval(monkeypatch):
    monkeypatch.setattr(ha, "probe_duration", lambda p: 54.0)
    monkeypatch.setattr(ha, "probe_dimensions", lambda p: (1440, 1440))
    out = ha.run("clip.mp4", "still.png", "out.mp4", dry_run=True)
    assert out["endpoint"].endswith("/v2/video/generate")
    assert out["est_cost"] == 3.60
    assert out["payload"]["dimension"] == {"width": 1080, "height": 1080}
    assert out["payload"]["use_avatar_iv_model"] is True


def test_real_run_refuses_without_approval(monkeypatch):
    monkeypatch.setattr(ha, "probe_duration", lambda p: 30.0)
    monkeypatch.setattr(ha, "probe_dimensions", lambda p: (1080, 1080))
    with pytest.raises(rc.GuidedError) as e:
        ha.run("clip.mp4", "still.png", "out.mp4", dry_run=False, approved=False)
    assert "approv" in str(e.value).lower()


def test_poll_raises_on_credit_error(monkeypatch):
    monkeypatch.setattr(hc, "get_status",
                        lambda key, vid: {"status": "failed", "message": "Insufficient credit. This operation requires 'api' credits."})
    with pytest.raises(rc.GuidedError) as e:
        ha.poll_until_done("k", "vid", "out.mp4", interval=0, max_tries=1)
    assert "credit" in str(e.value).lower()


def test_poll_raises_on_plain_failure(monkeypatch):
    monkeypatch.setattr(hc, "get_status",
                        lambda key, vid: {"status": "failed", "error": "bad input"})
    with pytest.raises(rc.GuidedError):
        ha.poll_until_done("k", "vid", "out.mp4", interval=0, max_tries=1)


def test_verify_nonempty_raises_on_zero_byte(tmp_path):
    f = tmp_path / "x.mp4"; f.write_bytes(b"")
    with pytest.raises(rc.GuidedError) as e:
        ha._verify_nonempty(str(f), "https://recover/url")
    assert "recover" in str(e.value).lower() or "empty" in str(e.value).lower()


def test_verify_nonempty_ok_on_real_bytes(tmp_path):
    f = tmp_path / "x.mp4"; f.write_bytes(b"abc")
    ha._verify_nonempty(str(f), "https://recover/url")   # no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/relight && python -m pytest tests/test_heygen_avatar.py -k "dry_run or refuses or poll" -q`
Expected: FAIL — `AttributeError: module 'heygen_avatar' has no attribute 'probe_duration'`.

- [ ] **Step 3: Implement orchestration + CLI**

Append to `.claude/skills/relight/scripts/heygen_avatar.py`:

```python
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
```

- [ ] **Step 4: Run the full suite**

Run: `cd .claude/skills/relight && python -m pytest -q`
Expected: **all green, 0 failures** (≈51 = 29 original + 22 in `test_heygen_avatar.py`). Treat "0 failures" as the gate, not the integer.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/relight/scripts/heygen_avatar.py .claude/skills/relight/tests/test_heygen_avatar.py
git commit -m "feat(relight): heygen_avatar run/poll/CLI with dry-run + approval guards"
```

---

### Task 5: Preflight HeyGen check + `heygen.env.example`

**Files:**
- Create: `.claude/skills/relight/heygen.env.example`
- Modify: `.claude/skills/relight/scripts/preflight.py`

**Interfaces:** consumes `heygen_common.load_heygen_key`. Docs/diagnostic only.

- [ ] **Step 1: Create the example env file**

Create `.claude/skills/relight/heygen.env.example`:

```
# Copy to ~/.claude/heygen.env (outside the repo) and paste your HeyGen API key.
# Get/fund a key at https://app.heygen.com/settings (Avatar IV needs 'API' credits).
HEYGEN_API_KEY=
```

- [ ] **Step 2: Add an INFORMATIONAL HeyGen check to preflight (must not flip the fatal `ok` gate)**

`preflight.py` has a single global `ok` flag that gates `sys.exit(0 if ok else 1)` and the bottom-line `READY`/`NOT READY`. Motion mode needs only the Fal key, so the HeyGen check must be **advisory** — it prints a per-check line in the existing `[OK]`/`[--]` style but **must not** set `ok = False` (otherwise a Motion-only user with no HeyGen key gets a false "NOT READY"). Add, after the Fal check, code in this shape (match the file's exact print idiom):

```python
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
except ImportError:
    print("[--] 'requests' not installed — Sync mode needs it. Run install.ps1 / pip install -r requirements.txt.")
```

Do **not** add `ok = False` anywhere in this block.

- [ ] **Step 3: Run preflight and confirm HeyGen is advisory-only**

Run: `cd .claude/skills/relight && python scripts/preflight.py`
Expected with a HeyGen key present (it exists this session): a `[OK] HeyGen key found` line, overall `READY`, exit 0.
Expected with the key temporarily unset (`HEYGEN_API_KEY= python scripts/preflight.py` and no `~/.claude/heygen.env`): a `[--] HeyGen key not set …` line **but still overall `READY` and exit 0** as long as the Fal key is set — proving the HeyGen check is advisory and Motion-only users aren't blocked.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/relight/heygen.env.example .claude/skills/relight/scripts/preflight.py
git commit -m "feat(relight): preflight HeyGen key check + heygen.env.example"
```

---

### Task 6: Wire two-mode selection into SKILL.md

**Files:**
- Modify: `.claude/skills/relight/SKILL.md`

**Interfaces:** consumes the Motion (Kling) and Sync (`heygen_avatar.py`) pipelines. Docs only.

- [ ] **Step 1: Add the mode-selection step**

After the "Inputs to collect from the user" section, add a **Mode selection** block instructing Claude to ask the user, up front, which mode they want:

```markdown
## Mode selection (ask first)

Ask the user which mode they want — it changes the video engine:

- **Motion mode (Kling)** — keeps your real head motion, gestures, and audio; lips can drift slightly; ~$10/min. (Steps 1–4 below.)
- **Sync mode (Avatar IV)** — perfect lip-sync; motion is AI-generated from the relit still; ~$4/min; needs a funded HeyGen key. (Steps 1–3, then the Sync step.)

Both modes share Steps 1–3 (frame → relit still → approval). They differ only at the video step.
```

- [ ] **Step 2: Make Step 3's cost branch on mode**

In **Step 3**, after the relight estimate, add: for **Sync mode**, get the estimate from
`python scripts/heygen_avatar.py "<video>" "<work>/still.png" --dry-run` and present that ($4/min) instead of the Kling figure. Approval still required.

- [ ] **Step 3: Add the Sync-mode video step**

After Step 4 (Motion/Kling), add:

```markdown
**Step 4S — Sync mode video (Avatar IV).** Instead of Step 4, on approval run:
```
python scripts/heygen_avatar.py "<video>" "<work>/still.png" --out "<out_sync>" --approved
```
`<out_sync>` = `<output_dir>/<input-stem>/<input-stem> Synced.mp4`. This extracts the
clip's audio, animates the approved still via HeyGen Avatar IV, and downloads the result.
If it reports an `Insufficient credit` error, tell the user to fund **API** credits at
the HeyGen dashboard and retry. Report `<out_sync>` as the final result.
```

- [ ] **Step 4: Update Setup + Output sections**

In **Setup**, add a line: Sync mode needs a HeyGen key — copy `heygen.env.example` to `~/.claude/heygen.env` and paste the key; verify with `preflight.py`.
In **Output**, note both possible finals: `<input-stem> Relit.mp4` (Motion) or `<input-stem> Synced.mp4` (Sync).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/relight/SKILL.md
git commit -m "docs(relight): two-mode selection (Kling motion + Avatar IV sync) in SKILL.md"
```

---

### Task 7: Live done-gate (one real Sync-mode run) + buildlog

**Files:**
- Modify: `docs/plans/2026-06-21-relight-skill-buildlog.md`

**Interfaces:** none. Real-API verification.

- [ ] **Step 1: Dry-run the CLI against the existing relit still (no spend)**

Run: `cd .claude/skills/relight && python scripts/heygen_avatar.py "<a real clip>.mp4" "<a real still>.png" --dry-run`
Expected: JSON with `endpoint` ending `/v2/video/generate`, `use_avatar_iv_model: true`, dimension derived from the still, numeric `est_cost`. Exit 0.

- [ ] **Step 2: One real Sync-mode run (paid — requires funded HeyGen API credits)**

Run the real generate on a short clip + its approved relit still (the validation spike already proved the path with a user-approved result; this re-confirms after refactor into the skill):

```bash
cd .claude/skills/relight
python scripts/heygen_avatar.py "<clip>.mp4" "<relit still>.png" --out "/tmp/sync-gate.mp4" --approved
```

Verify by watching `/tmp/sync-gate.mp4`: lips track the words; the relit look from the still is preserved; audio aligned to length; cost was shown before the run; the run refused without `--approved` (unit-tested; reconfirm once).

- [ ] **Step 3: Log it**

Append a `## Sync mode (Avatar IV) — done-gate` section to `docs/plans/2026-06-21-relight-skill-buildlog.md` with the real cost, the input clip, and the verified result.

- [ ] **Step 4: Commit**

```bash
git add docs/plans/2026-06-21-relight-skill-buildlog.md
git commit -m "docs(relight): log Avatar IV Sync-mode done-gate"
```

---

## Test Plan

- **Smoke test:** `python scripts/heygen_avatar.py "<clip>.mp4" "<still>.png" --dry-run` → JSON with endpoint `/v2/video/generate`, `use_avatar_iv_model: true`, computed `dimension`, numeric `est_cost`; spends nothing; exit 0.

- **Backend/unit tests** (`tests/test_heygen_avatar.py`):
  - *Happy path* — `build_generate_request` carries the talking-photo character, audio voice, `use_avatar_iv_model: true`, and dimension; `estimate_avatar_cost` = $4/min (60s→4.00, 54s→3.60); `aspect_to_dimension` square→1080², 16:9→1920×1080.
  - *Edge / boundary* — `aspect_to_dimension` never upscales (720²→720²) and always returns even dimensions (odd input → even output); cost at 30s = 2.00.
  - *Adversarial / failure paths* — real `run()` refuses without `--approved` (no spend); **`Insufficient credit` payload → fund-credits `GuidedError`** at generate, poll, AND the upload envelope (via `_parse_data`); **a 200-with-error upload response (no `data`) → `GuidedError`, never a raw `KeyError`/traceback** (the exact failure the design exists to prevent); a **0-byte download → `GuidedError`** carrying the recoverable `video_url`; plain `failed` status → `GuidedError`; missing/blank key → `GuidedError` naming `~/.claude/heygen.env`; ffprobe/ffmpeg-missing → `GuidedError` to `install.ps1`.
  - *Spend-safety invariant* — every test touching `run()`/`poll_until_done`/uploads stubs probes/`get_status`/responses; no unit test performs a live HeyGen upload/generate.

- **Regression:** `cd .claude/skills/relight && python -m pytest -q` — original Relight (Kling/Motion) tests stay green after Task 1's revert (lip-sync module + its 14 tests removed cleanly); new HeyGen tests added; 0 failures.

- **AI-output quality (live done-gate, Task 7):** one real Sync-mode run, judged by eye — lips track the words, relit look preserved, audio length-aligned, cost shown before spend. The validation-spike "B" render (user-approved this session) is the precedent; Task 7 re-confirms post-refactor. Ties to `definition-of-usable`: Sync mode is "usable" only when the lips visibly track on a standard talking-head clip.

- **Known-bug regression guard:** the credit-error path (which silently sank Approach A) is unit-tested at both the generate and poll layers, so a future refactor can't reintroduce a cryptic failure.

- **Done-gate:** unit suite green + full Relight regression green + dry-run smoke green + one human-verified paid Sync run. All four before merge.

## Self-Review

- **Spec coverage:** mode selection (Task 6), Motion unchanged + lip-sync reverted (Task 1), Sync pipeline (Tasks 2–4), key handling + preflight + example (Tasks 2, 5), cost/approval/credit-error (Tasks 2–4), output naming `<stem> Synced.mp4` (Tasks 4, 6), testing (above). All spec sections map to a task.
- **Type consistency:** `load_heygen_key()->str`, `headers(key,ct)->dict`, `check_credit_error(dict)->None`, `upload_talking_photo->str`, `upload_audio_asset->str`, `generate_avatar_iv->str|None`, `get_status->dict` used consistently across `heygen_common`/`heygen_avatar`. `aspect_to_dimension`/`build_generate_request`/`estimate_avatar_cost` signatures match every call site.
- **No placeholders:** complete code in every code step; the only `<…>` tokens are illustrative payload placeholders inside dry-run output, not unwritten code. Task 5 Step 2 (preflight) now gives concrete advisory-check code that explicitly must not flip `ok`, resolving the earlier "match existing style" contradiction.
- **HeyGen shapes** are the exact ones the validation spike used to render a user-approved video, not guesses.

## Review log

### Round 1 — 2026-06-21

**Reviewer verdict:** CHANGES REQUIRED

**Reviewer summary:**
- Wrong test-count targets (plan said 26 original / 16 total; real non-lip-sync count is 29).
- Task 4 ships a knowingly-wrong endpoint assertion (`or "fal-or-heygen-not-checked"`), patched a step later.
- Upload helpers can throw raw `KeyError`/traceback on HeyGen's 200-with-error envelope (the credit/over-cap failure the design exists to prevent); no 32MB guard; untested.
- Preflight instruction is internally contradictory ("non-fatal to Motion" vs "match existing style" — existing style is a single fatal `ok` gate).
- `aspect_to_dimension` test is weak (only `% 2`, no ratio/cap assertion).
- `with_suffix(".audio.mp3")` raises `ValueError` on Python ≤3.11.
- Blindspots: 40-min silent poll loop; no spend-recovery (`video_id` lost on download failure); `urlretrieve` no timeout; no downloaded-file validation.

**Accepted:**
- Test counts — replaced pinned "26"/"16" with "all green, 0 failures" gates plus accurate reference numbers (29 original; ≈51 full after the added tests).
- Knowingly-wrong assertion — wrote `endswith("/v2/video/generate")` directly in Task 4 Step 1; deleted the old "tighten" Step 4 and the note; renumbered.
- Upload hardening — added `_parse_data` (converts 200-with-error/credit envelopes to `GuidedError`, never `KeyError`) and `_require_under_cap` (32MB pre-check); routed all three HTTP helpers through it; added 3 `_parse_data` unit tests.
- Preflight — replaced "match existing style" with concrete advisory-check code that explicitly must **not** flip `ok` (Motion-only users stay READY); added a `requests` import check; updated the run-it step to verify exit 0 without a HeyGen key.
- `aspect_to_dimension` — added a ratio-preservation + short-side-≤1080 assertion on a non-trivial phone-portrait ratio.
- `with_name(stem + ".audio.mp3")` — version-safe path; replaces the interior-dot suffix.
- Spend-recovery + observability — `run()` prints `video_id` to stderr before polling; `poll_until_done` emits periodic status; added `_download` (timeout) + `_verify_nonempty` (0-byte → `GuidedError` carrying the recoverable `video_url`) with 2 unit tests; documented the ~40-min ceiling.

**Contested / refined (deviations from the reviewer's exact suggestion, with reasoning):**
- **Progress to stderr, not stdout.** The reviewer said "add a periodic status print" without naming the stream. The script's **stdout is the JSON contract** SKILL.md parses — progress on stdout would corrupt it. Implemented all progress/`video_id` prints to **stderr** instead. (Refinement of, not disagreement with, the observability ask.)
- **Bounded the download hardening — no retry loop.** The reviewer floated `requests` + retry. I added a 120s timeout + non-empty validation + a `GuidedError` that surfaces the recoverable `video_url`, but deliberately **did not** build automatic retry/resume — YAGNI for a tool the user re-runs, and the surfaced `video_url` already makes a failed download recoverable without re-paying. If real-world flakiness proves this wrong, retry is a cheap follow-up.

**Plan body changes:** Task 1 Step 4 count; Task 2 hardened upload helpers + `_parse_data`/`_require_under_cap` + 3 tests + Interfaces; Task 3 aspect test; Task 4 assertion fix, Step-4 deletion + renumber, `import requests`, hardened `poll_until_done`/`_download`/`_verify_nonempty`/`run` (stderr, video_id, with_name) + 2 tests + Interfaces; Task 5 concrete advisory preflight; Test Plan adversarial bullet + Self-Review note.
