# Relight Lip-Sync Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a **mandatory** final lip-sync stage to the Relight skill that re-syncs the speaker's mouth to the original audio, fixing the lip drift Kling video-to-video introduces. It always runs as the last step of every relight job, always at the `best` tier.

**Architecture:** A new standalone script `lipsync_video.py` in the existing Relight skill. It extracts the audio from a video (ffmpeg), uploads video + audio to Fal, and calls a Fal lip-sync endpoint to redraw only the mouth to match the waveform. A small tier→endpoint registry mirrors the shape of the planned `falkit` model registry, so this lifts cleanly into `falkit`/MediaGen later; the user-facing flow always uses `best` (`fal-ai/sync-lipsync/v2`), with `cheap` (`fal-ai/latentsync`) kept only as a power-user/`falkit`-parity escape hatch, never surfaced in SKILL.md. It reuses Relight's `relight_common.py` (`GuidedError`, `load_fal_key`) and follows the exact dry-run + `--approved` + cost-before-spend pattern of `relight_video.py`. Runs **last**, after relight, on the relit footage — and its cost is folded into the single Step 3 approval so the user approves the whole job (relight + sync) once.

**Tech Stack:** Python 3, `fal_client`, ffmpeg/ffprobe (all already installed by `install.ps1`). No new dependencies.

## Why this design (decision record)

- **Lives in the Relight skill, not MediaGen.** `falkit`/MediaGen are spec-approved but **not yet built** (no `falkit/` package exists on disk). The lip drift is a Relight problem today, and Relight already has the key-loading, cost, and approval plumbing. Building here ships now. The registry/resolver are written in the same shape as the future `falkit.models` table (`task → {endpoint, tier}`), so migrating this into `falkit` later is a lift-and-shift, not a rewrite.
- **Mandatory, not optional.** Every relight job ends with the lip-sync stage — Claude runs it automatically as Step 5 after Step 4, no user prompt to opt in. The relit MP4 with drifted lips is now an *intermediate*; the lip-synced video is the only deliverable handed to the user.
- **Always `best`.** The user-facing flow is hard-wired to the `best` tier (`fal-ai/sync-lipsync/v2`, ~$3/min, strongest on close-up talking heads). SKILL.md never offers `cheap`; the `cheap` tier stays in the registry purely for `falkit` parity / power-user `--tier`.
- **Lip-sync runs last.** Relight (Kling v2v) regenerates frames and desyncs the mouth from the preserved audio. A lip-sync model reads the audio waveform and redraws only the mouth to match it, so it must run *after* relight to correct that drift.
- **Audio comes from the video itself by default.** The relit MP4 already carries the original audio (`keep_audio=True`). Extracting audio from the input video guarantees the audio we sync to is exactly the audio that will play. A `--audio` override lets the user supply the pristine original clip's audio if they prefer.
- **One approval for the whole job.** The Step 3 gate now shows the *combined* relight + lip-sync estimate, so the user approves the full spend once; Step 5 still passes `--approved` internally (no script ever spends without it).

## Global Constraints

- **Fal key** resolves via `relight_common.load_fal_key()` (reads `<skill>/.env`). No second key path in this work.
- **No new dependencies.** Only `fal_client` + ffmpeg/ffprobe, already present.
- **Paid step discipline:** every paid script supports `--dry-run` (spends nothing, prints endpoint + payload + estimate) and **requires `--approved`** for the real call. Never spend without explicit user approval. Always state the dollar estimate before the paid step.
- **Errors** are raised as `GuidedError` and printed by `main()` as a single `ERROR: …` line to stderr with `sys.exit(1)` (matches every existing Relight script).
- **Platform:** Windows; commands run via the Bash tool (Git Bash) or PowerShell. `python` on PATH.
- **Skill folder** `<skill>` = `.claude/skills/relight/`. Scripts under `<skill>/scripts/`, tests under `<skill>/tests/`. Tests run with `pytest` from the skill folder.

## File Structure

- **Create** `.claude/skills/relight/scripts/lipsync_video.py` — registry + resolver + cost estimator + audio-extract command builder + payload builder + `run()` + `main()`.
- **Create** `.claude/skills/relight/tests/test_lipsync_video.py` — unit tests for all pure functions and the dry-run/approval guards.
- **Modify** `.claude/skills/relight/SKILL.md` — add the optional Step 5 "Fix lip-sync" section, cost line, and constraint note.

No change to `relight_common.py`, `relight_video.py`, `relight_batch.py`, `split_video.py`, `concat_video.py`, `extract_frame.py`, or `requirements.txt`.

---

### Task 1: Lip-sync model registry, resolver, and cost estimator

**Files:**
- Create: `.claude/skills/relight/scripts/lipsync_video.py`
- Test: `.claude/skills/relight/tests/test_lipsync_video.py`

**Interfaces:**
- Consumes: `relight_common.GuidedError`.
- Produces:
  - `LIPSYNC_MODELS: dict[str, dict]` — `{"best": {"endpoint": str, "model": str|None}, "cheap": {"endpoint": str, "model": None}}`.
  - `resolve_lipsync(tier: str = "best", override: str | None = None) -> dict` — returns the model entry `{"endpoint", "model"}`; `override` (a literal Fal endpoint) wins and yields `{"endpoint": override, "model": None}`; unknown `tier` raises `GuidedError`.
  - `estimate_lipsync_cost(duration_s: float, tier: str = "best") -> float` — dollars, rounded to 2dp.

- [ ] **Step 1: Write the failing test**

Create `.claude/skills/relight/tests/test_lipsync_video.py`:

```python
import sys, pathlib
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import lipsync_video as lv
import relight_common as rc


def test_resolve_default_is_sync_lipsync_v2():
    entry = lv.resolve_lipsync()
    assert entry["endpoint"] == "fal-ai/sync-lipsync/v2"
    assert entry["model"] == "lipsync-2"


def test_resolve_cheap_is_latentsync():
    entry = lv.resolve_lipsync(tier="cheap")
    assert entry["endpoint"] == "fal-ai/latentsync"
    assert entry["model"] is None


def test_resolve_override_wins():
    entry = lv.resolve_lipsync(override="fal-ai/sync-lipsync/v2/pro")
    assert entry["endpoint"] == "fal-ai/sync-lipsync/v2/pro"


def test_resolve_unknown_tier_raises():
    with pytest.raises(rc.GuidedError):
        lv.resolve_lipsync(tier="ultra")


def test_cost_best_is_three_dollars_per_minute():
    assert lv.estimate_lipsync_cost(60.0, "best") == 3.00
    assert lv.estimate_lipsync_cost(30.0, "best") == 1.50


def test_cost_cheap_flat_under_40s_then_per_second():
    assert lv.estimate_lipsync_cost(30.0, "cheap") == 0.20   # flat <= 40s
    assert lv.estimate_lipsync_cost(40.0, "cheap") == 0.20
    assert lv.estimate_lipsync_cost(60.0, "cheap") == 0.30   # 0.20 + 0.005*20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/relight && python -m pytest tests/test_lipsync_video.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lipsync_video'`.

- [ ] **Step 3: Write minimal implementation**

Create `.claude/skills/relight/scripts/lipsync_video.py`:

```python
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
# (None for endpoints that take no model param, e.g. latentsync).
LIPSYNC_MODELS = {
    "best":  {"endpoint": "fal-ai/sync-lipsync/v2", "model": "lipsync-2"},
    "cheap": {"endpoint": "fal-ai/latentsync",      "model": None},
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
    # best: sync-lipsync v2 (lipsync-2) ~ $3.00 / minute
    return round(3.00 * duration_s / 60.0, 2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/relight && python -m pytest tests/test_lipsync_video.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/relight/scripts/lipsync_video.py .claude/skills/relight/tests/test_lipsync_video.py
git commit -m "feat(relight): lip-sync model registry, resolver, cost estimator"
```

---

### Task 2: Audio-extract command + lip-sync request builder

**Files:**
- Modify: `.claude/skills/relight/scripts/lipsync_video.py`
- Test: `.claude/skills/relight/tests/test_lipsync_video.py`

**Interfaces:**
- Consumes: `resolve_lipsync` (Task 1), `GuidedError`.
- Produces:
  - `audio_extract_cmd(video_path: str, out_path: str) -> list[str]` — the ffmpeg argv that strips video and writes a WAV (codec/sample-rate preserved from source).
  - `build_lipsync_request(entry: dict, video_url: str, audio_url: str, sync_mode: str = "cut_off") -> dict` — payload; includes `model` + `sync_mode` only when `entry["model"]` is set (sync-lipsync family); latentsync gets just `video_url` + `audio_url`.

- [ ] **Step 1: Write the failing test**

Append to `.claude/skills/relight/tests/test_lipsync_video.py`:

```python
def test_audio_extract_cmd_strips_video_to_wav():
    cmd = lv.audio_extract_cmd("clip.mp4", "out.wav")
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd                      # drop the video stream
    assert "clip.mp4" in cmd
    assert cmd[-1] == "out.wav"


def test_build_request_best_includes_model_and_sync_mode():
    entry = lv.resolve_lipsync("best")
    req = lv.build_lipsync_request(entry, "v.mp4", "a.wav")
    assert req["video_url"] == "v.mp4"
    assert req["audio_url"] == "a.wav"
    assert req["model"] == "lipsync-2"
    assert req["sync_mode"] == "cut_off"


def test_build_request_cheap_omits_model_param():
    entry = lv.resolve_lipsync("cheap")
    req = lv.build_lipsync_request(entry, "v.mp4", "a.wav")
    assert req == {"video_url": "v.mp4", "audio_url": "a.wav"}
    assert "model" not in req


def test_build_request_honors_sync_mode_override():
    entry = lv.resolve_lipsync("best")
    req = lv.build_lipsync_request(entry, "v.mp4", "a.wav", sync_mode="loop")
    assert req["sync_mode"] == "loop"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/relight && python -m pytest tests/test_lipsync_video.py -k "extract or build_request" -v`
Expected: FAIL — `AttributeError: module 'lipsync_video' has no attribute 'audio_extract_cmd'`.

- [ ] **Step 3: Write minimal implementation**

Add to `lipsync_video.py` (after `estimate_lipsync_cost`):

```python
def audio_extract_cmd(video_path: str, out_path: str) -> list[str]:
    # Strip the video stream, keep the original audio as PCM WAV (no resample /
    # downmix) so the lip-sync model gets the exact speech that will play back.
    return ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-c:a", "pcm_s16le",
            str(out_path)]


def build_lipsync_request(entry: dict, video_url: str, audio_url: str,
                          sync_mode: str = "cut_off") -> dict:
    req = {"video_url": video_url, "audio_url": audio_url}
    if entry.get("model"):           # sync-lipsync family takes model + sync_mode
        req["model"] = entry["model"]
        req["sync_mode"] = sync_mode
    return req
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .claude/skills/relight && python -m pytest tests/test_lipsync_video.py -v`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/relight/scripts/lipsync_video.py .claude/skills/relight/tests/test_lipsync_video.py
git commit -m "feat(relight): audio-extract command + lip-sync request builder"
```

---

### Task 3: `run()` orchestration (probe, extract, upload, sync, download) + CLI

**Files:**
- Modify: `.claude/skills/relight/scripts/lipsync_video.py`
- Test: `.claude/skills/relight/tests/test_lipsync_video.py`

**Interfaces:**
- Consumes: all of Tasks 1–2, `load_fal_key`, `fal_client`, ffprobe/ffmpeg.
- Produces:
  - `probe_duration(video_path: str) -> float` — seconds via ffprobe; raises `GuidedError` if ffprobe missing.
  - `run(video_path, out_path, tier="best", audio_path=None, sync_mode="cut_off", override=None, dry_run=False, approved=False) -> dict` — dry-run returns `{"endpoint", "tier", "payload", "est_cost"}` and spends nothing; real run requires `approved=True`, extracts audio (unless `audio_path` given), uploads both, calls Fal, downloads to `out_path`, returns `{"endpoint", "tier", "video", "remote_url", "est_cost"}`.
  - `main()` — argparse CLI: `video`, `--out` (default `synced_video.mp4`), `--tier` (`best`/`cheap`, default `best`), `--audio`, `--sync-mode` (default `cut_off`), `--model` (override), `--dry-run`, `--approved`.

- [ ] **Step 1: Write the failing test**

Append to `.claude/skills/relight/tests/test_lipsync_video.py`:

```python
def test_dry_run_spends_nothing_no_approval_needed(monkeypatch):
    # No fal client, no ffprobe call: dry-run must not need either to estimate.
    monkeypatch.setattr(lv, "fal_client", None)
    monkeypatch.setattr(lv, "probe_duration", lambda p: 60.0)
    out = lv.run("relit.mp4", "out.mp4", tier="best", dry_run=True)
    assert out["endpoint"] == "fal-ai/sync-lipsync/v2"
    assert out["tier"] == "best"
    assert out["est_cost"] == 3.00
    assert out["payload"]["model"] == "lipsync-2"


def test_dry_run_cheap_tier_estimate(monkeypatch):
    monkeypatch.setattr(lv, "fal_client", None)
    monkeypatch.setattr(lv, "probe_duration", lambda p: 30.0)
    out = lv.run("relit.mp4", "out.mp4", tier="cheap", dry_run=True)
    assert out["endpoint"] == "fal-ai/latentsync"
    assert out["est_cost"] == 0.20


def test_real_run_refuses_without_approval(monkeypatch):
    # Even with a fake client present, no approval => no spend.
    monkeypatch.setattr(lv, "fal_client", object())
    monkeypatch.setattr(lv, "probe_duration", lambda p: 30.0)
    with pytest.raises(rc.GuidedError) as e:
        lv.run("relit.mp4", "out.mp4", dry_run=False, approved=False)
    assert "approv" in str(e.value).lower()


def test_real_run_requires_fal_client(monkeypatch):
    monkeypatch.setattr(lv, "fal_client", None)
    monkeypatch.setattr(lv, "probe_duration", lambda p: 30.0)
    with pytest.raises(rc.GuidedError) as e:
        lv.run("relit.mp4", "out.mp4", dry_run=False, approved=True)
    assert "fal-client" in str(e.value).lower() or "fal_client" in str(e.value).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .claude/skills/relight && python -m pytest tests/test_lipsync_video.py -k "run" -v`
Expected: FAIL — `AttributeError: module 'lipsync_video' has no attribute 'probe_duration'` / `run`.

- [ ] **Step 3: Write minimal implementation**

Add to `lipsync_video.py` (after `build_lipsync_request`):

```python
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
    ap.add_argument("--tier", choices=["best", "cheap"], default="best")
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
```

- [ ] **Step 4: Run the full suite to verify it passes**

Run: `cd .claude/skills/relight && python -m pytest tests/test_lipsync_video.py -v`
Expected: PASS (14 passed).

Run the regression suite to prove nothing else broke:
Run: `cd .claude/skills/relight && python -m pytest -v`
Expected: PASS — all prior Relight tests plus the 14 new ones, 0 failures.

- [ ] **Step 5: Smoke-test the CLI dry-run against a real file (no spend)**

Run (substitute any real local video; this only probes + estimates, spends nothing):
`cd .claude/skills/relight && python scripts/lipsync_video.py "<path-to-a-relit-clip>.mp4" --dry-run`
Expected: JSON with `"endpoint": "fal-ai/sync-lipsync/v2"`, a numeric `est_cost`, and a `payload`. Exit code 0.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/relight/scripts/lipsync_video.py .claude/skills/relight/tests/test_lipsync_video.py
git commit -m "feat(relight): lip-sync run() orchestration + CLI"
```

---

### Task 4: Wire the mandatory lip-sync stage into SKILL.md + paid done-gate

**Files:**
- Modify: `.claude/skills/relight/SKILL.md`

**Interfaces:**
- Consumes: `lipsync_video.py` CLI from Task 3. Docs only — no code.

The relit MP4 becomes an **intermediate** written to the work dir; the lip-synced video is the final `<out>` (`<input-stem> Relit.mp4`). The flow always ends with sync; no opt-in.

- [ ] **Step 1: Fold the lip-sync cost into the Step 3 approval gate**

In `SKILL.md`, in **Step 3 — approval gate**, after the duration-branch that produces the relight estimate, add a line so the presented figure is the *combined* spend:

```markdown
Then add the **lip-sync** estimate (always runs as Step 5) to the figure:
`python scripts/lipsync_video.py "<video>" --dry-run` → take `est_cost`.
Present **relight + lip-sync = total** (e.g. "23s → 3 segments ≈ $2.49 relight + ~$1.15 sync = ~$3.64 total"). One approval covers the whole job.
```

- [ ] **Step 2: Point Step 4's relight output at the work dir (intermediate)**

In **Step 4**, change the `--out` target from the final `<out>` to an intermediate in the work dir, since Step 5 now produces the final file. Replace the two run commands' `--out "<out>"` with `--out "<work>/relit.mp4"`, and update the surrounding prose to:

```markdown
**Step 4 — on approval, run the relight (branch on duration).** Writes the relit
(but not-yet-synced) video to `<work>/relit.mp4`:
- `duration <= 10`:
  `python scripts/relight_video.py "<video>" "<work>/still.png" <duration> --out "<work>/relit.mp4" --approved`
- `duration > 10`:
  `python scripts/relight_batch.py "<video>" "<work>/still.png" --work "<work>" --out "<work>/relit.mp4" --approved`
Do **not** report this as the final file — Step 5 produces it.
```

- [ ] **Step 3: Add the mandatory Step 5 to the Run order**

After the Step 4 block, insert:

```markdown
**Step 5 — fix lip-sync (always runs).** Kling v2v leaves the mouth out of sync with
the words; this final stage re-syncs it. Run it automatically on the relit
intermediate — no opt-in. (Cost was already approved in Step 3.)

`python scripts/lipsync_video.py "<work>/relit.mp4" --out "<out>" --approved`

`<out>` = `<output_dir>/<input-stem>/<input-stem> Relit.mp4` (the final deliverable).
The script extracts the relit video's own audio and syncs the mouth to it via Fal
sync-lipsync v2 (`best`); nothing else in the frame changes. Report this path as the
final result.
```

- [ ] **Step 4: Update the Output + Cost transparency + Constraints sections**

In **Output**, change the description so the final `<input-stem> Relit.mp4` is the lip-synced file and the pre-sync `relit.mp4` lives in `<work>`:

```markdown
Final MP4 in `<output_dir>/<input-stem>/`, named `<input-stem> Relit.mp4` — relit **and lip-synced**. Keep the approved still in that subfolder. The pre-sync relit video (`<work>/relit.mp4`) and any segments are intermediates and can be deleted.
```

In **Cost transparency**, after the existing rough-pricing line, add:

```markdown
Lip-sync (always runs as the final stage): sync-lipsync v2 ≈ $3/min (e.g. a 24s clip ≈ $1.20). Its estimate is folded into the single Step 3 approval, so the user approves relight + sync together. Never spend without that approval.
```

In **Constraints**, append:

```markdown
- Every relight job ends with a **mandatory** lip-sync stage (Fal sync-lipsync v2) on the relit footage, re-syncing the mouth to the clip's own audio. It is not optional and not separately approved — its cost is included in the Step 3 total.
```

- [ ] **Step 5: Manual paid done-gate (one real end-to-end run — requires Fal credit)**

Run the **full** relight→sync flow once on a short real clip to prove the mandatory stage works end-to-end and the final file is the synced one. (This spends money; it cannot be a unit test.)

```bash
cd .claude/skills/relight
# after a normal relight produces <work>/relit.mp4:
python scripts/lipsync_video.py "<work>/relit.mp4" --dry-run                 # confirm estimate
python scripts/lipsync_video.py "<work>/relit.mp4" \
  --out "<output_dir>/<stem>/<stem> Relit.mp4" --approved
```

Verify, by watching the final `<stem> Relit.mp4`:
- **Mouth now matches the words** (the drift from the relit intermediate is corrected).
- The **audio is unchanged** and still aligned to the video length.
- Face/identity, background, and lighting from the relit intermediate are **preserved** (only the mouth region changed).
- The real run refused without `--approved` (covered by unit tests; reconfirm once by omitting the flag).

Record the real cost and a one-line result in `docs/plans/2026-06-21-relight-skill-buildlog.md` (matches how the relight paid run was logged).

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/relight/SKILL.md docs/plans/2026-06-21-relight-skill-buildlog.md
git commit -m "docs(relight): make lip-sync a mandatory final stage in SKILL.md + log paid gate"
```

---

## Test Plan

- **Smoke test:** `python scripts/lipsync_video.py "<a relit clip>.mp4" --dry-run` returns JSON with `endpoint = fal-ai/sync-lipsync/v2`, a numeric `est_cost`, and a payload — proves probe + resolve + estimate + CLI are wired, spends nothing. Pass signal: exit 0 and that JSON shape.

- **Backend/unit tests** (`tests/test_lipsync_video.py`, run via `pytest`):
  - *Happy path* — `resolve_lipsync()` → sync-lipsync v2 + `lipsync-2`; `build_lipsync_request` for `best` carries `model` + `sync_mode`; dry-run returns the endpoint + estimate.
  - *Tier / branch coverage* — `tier="cheap"` resolves latentsync and **omits** the `model` param (latentsync rejects it); cost estimator: best 60s = $3.00, cheap 30s = $0.20, cheap 60s = $0.30 (the 40s boundary tested explicitly).
  - *Edge / boundary* — cost at exactly 40s (cheap) stays flat $0.20; `--sync-mode` override propagates into the payload; `override` endpoint wins over tier.
  - *Adversarial / failure paths* — **real run refuses without `--approved`** even when a Fal client is present (no spend); real run with approval but **no `fal_client` installed** raises a GuidedError naming the install step; **unknown `--tier`** raises a GuidedError listing valid tiers; ffprobe/ffmpeg-missing paths raise GuidedError pointing at `install.ps1` (asserted via the `shutil.which` guard).
  - *Spend-safety invariant* — every test that touches `run()` either sets `dry_run=True` or stubs `probe_duration` and asserts no `fal_client` call happens; no unit test performs a real Fal upload/subscribe.

- **Regression:** `cd .claude/skills/relight && python -m pytest -v` — all pre-existing Relight tests (26) stay green after adding the new module; the new file imports `relight_common` without modifying it, so Relight's pipeline is untouched.

- **AI-output quality (paid done-gate, Task 4 Step 5):** one real **end-to-end** relight→sync run on a clip that shows lip-drift. Judged by eye, not HTTP 200: (a) the final `<stem> Relit.mp4` is the lip-synced file and the mouth now tracks the words, (b) audio unchanged and length-aligned, (c) identity/background/lighting from the relit intermediate preserved (only the mouth changed), (d) the combined relight + sync cost was shown at the single Step 3 approval. This ties to `definition-of-usable` — since sync now runs on *every* job, "usable" means the mandatory stage corrects the drift without wrecking the relit look on the standard talking-head clip.

- **Known-bug regression guard:** the failure this feature fixes (Kling v2v lip-drift) has no automated visual assertion, so the paid done-gate result is logged in the buildlog with the input clip name; re-runnable if a future Fal model swap regresses sync quality.

- **Done-gate:** unit suite green + full Relight regression green + dry-run smoke green + one human-verified paid run showing corrected sync with preserved relit look. All four before merge.

## Self-Review

- **Spec coverage:** registry entry (Task 1 `LIPSYNC_MODELS` + `resolve_lipsync`), script (Tasks 1–3 `lipsync_video.py`), cost/approval (`estimate_lipsync_cost` + `--dry-run`/`--approved` guards in Task 3, mirrored from `relight_video.py`), where it hooks into relight output (Task 4 SKILL.md Step 5, runs on `<out>` from Step 4), test plan (above). All requested items covered.
- **Type consistency:** `resolve_lipsync` returns a dict with keys `endpoint` + `model`; `build_lipsync_request` reads `entry["model"]`; `run` reads `entry["endpoint"]`. Consistent across Tasks 1–3. Cost estimator signature `(duration_s, tier)` identical everywhere it's called.
- **No placeholders:** every code step shows complete code; every command shows expected output. No "add error handling later" — error paths are concrete `GuidedError` raises with tested messages.
- **Migration note:** `LIPSYNC_MODELS` + `resolve_lipsync` are deliberately shaped like the future `falkit.models` registry so this lifts into `falkit`/MediaGen without a rewrite when that lands.

## Review log

### 2026-06-21 — User revision (pre-build)

User direction after the initial draft: **(1)** lip-sync is **not optional** — it must always run as part of every relight job; **(2)** always use the **`best`** tier (no cheap option in the user flow); **(3)** confirmed it's a Relight skill edit.

Changes applied to the plan body:
- Goal/Architecture/decision-record reworded from "optional final stage" to a **mandatory** stage that always runs at `best`. Added explicit "Mandatory, not optional" and "Always `best`" decision bullets.
- Approval model changed: the lip-sync estimate is now **folded into the single Step 3 approval** (relight + sync = one total), instead of a second approval gate. Scripts still require `--approved` internally.
- Output contract: the relit MP4 becomes an **intermediate** in `<work>/relit.mp4`; the **lip-synced** video is the final `<input-stem> Relit.mp4` deliverable. Task 4 (SKILL.md) rewritten accordingly — Step 4 writes to the work dir, new mandatory Step 5 produces the final file, Output/Cost/Constraints sections updated.
- `cheap` tier retained in the registry + unit tests (for `falkit` parity and a power-user `--tier` hatch) but never surfaced in SKILL.md.
- Test Plan done-gate reframed as a full **end-to-end** relight→sync run (every job now syncs), verifying the final file is the synced one.

Code tasks (1–3) and their unit tests are unchanged — `lipsync_video.py` still defaults to `best`, still guards spend with `--approved`/`--dry-run`. Build proceeding inline after this revision.
