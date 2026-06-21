---
name: relight
description: Relight and replace the background of talking-head video footage entirely from Claude Code. Use when the user wants to "relight" a clip, fix bad lighting, put themselves in a studio / three-point lighting setup, swap or upgrade a video background, or make footage look cinematic. Powered by Fal AI (Nano Banana Pro for the relit still, Kling O1 video-to-video for the final video). Handles any length: clips up to 10s in one pass, longer clips auto-split into segments and stitched back together.
---

# Relight

Turn a flat, badly-lit talking-head clip into a cinematic, studio-lit shot in a new environment — without leaving Claude Code. Inspired by the Systems by Vic "Relight" workflow.

## How it works

1. Pick the sharpest frame from the clip.
2. Generate a relit still of the subject in the new environment (Fal **Nano Banana Pro**).
3. **You approve** the still + see the cost.
4. Animate the original footage in that new look, preserving motion + audio (Fal **Kling O1 video-to-video reference**).
5. Deliver the final MP4.

Clips **≤10s** run in one pass. Clips **>10s** are automatically even-split into 3–10s segments, each relit against the **same** approved still (so lighting/background stay consistent), then concatenated back into one video.

## Setup (first time)

1. From the repo root, run `install.ps1` (installs ffmpeg via winget, installs Python deps, symlinks this skill into `~/.claude/skills`, seeds `.env`).
2. Open `<skill>/.env` and paste your Fal key: `FAL_KEY=...` (get one at https://fal.ai/dashboard/keys, add credit). **Edit the file directly — never paste the key into chat.**
3. Verify: `python scripts/preflight.py` → expect `READY`.

`<skill>` = this skill's folder. Scripts are under `<skill>/scripts/`.

## Inputs to collect from the user

- **Video file path** (any length). On Windows, have them right-click the file → "Copy as path".
- **A description** of the lighting/background they want (e.g. "three-point lighting with neon streamer lights behind me").
- **Optional reference image path** (a photo of the look they're going for).

## Run order

Use a temp work dir, e.g. `<output_dir>/.work-<name>/`. `<output_dir>` defaults to `./relight-outputs/` in the current project; fall back to `~/Documents/relight/`; honor any path the user gives.

**Step 1 — extract the best frame and probe duration:**
```
python scripts/extract_frame.py "<video>" --out "<work>/frame.png"
```
Read the JSON. Note `probe.duration`. If `warnings` mention **resolution or size** out of bounds, relay them and STOP (not auto-fixable). Duration is handled by the branch in Step 3/4 — it is not a stop.
If `probe.duration < 3`, tell the user Kling needs ≥3s and STOP.

**Step 2 — generate the relit still:**
```
python scripts/relight_image.py "<work>/frame.png" "<user description>" [--reference "<ref>"] --out "<work>/still.png" --resolution 2K
```
Show the resulting still to the user. (This one still is reused for every segment in batch mode.)

**Step 3 — approval gate (always show cost before spending):**
- If `duration <= 10`: get the figure from
  `python scripts/relight_video.py "<video>" "<work>/still.png" <duration> --dry-run`
- If `duration > 10`: get the figure from
  `python scripts/relight_batch.py "<video>" "<work>/still.png" --dry-run`
  → report `est_cost.total` AND the segment count (e.g. "23s → 3 segments → ~$2.49 total").

Present the still + the dollar estimate. Ask the user to **approve**, or request a rerun (loop back to Step 2 with a tweaked prompt / new reference). Do not proceed without explicit approval.

**Step 4 — on approval, run the paid step (branch on duration):**
- `duration <= 10`:
  ```
  python scripts/relight_video.py "<video>" "<work>/still.png" <duration> --out "<output_dir>/relit_<name>.mp4" --approved
  ```
- `duration > 10`:
  ```
  python scripts/relight_batch.py "<video>" "<work>/still.png" --work "<work>" --out "<output_dir>/relit_<name>.mp4" --approved
  ```
Report the final path. Batch automatically splits → relights each segment with the shared still → concatenates.

## Output

Final MP4 in `<output_dir>`. Keep the approved still and source frame alongside it. Intermediate segments live in `<work>` and can be deleted.

## Cost transparency

Always state the dollar estimate before the paid step. For batch, state the segment count and total. Never run a paid step without explicit user approval. Rough pricing: still ≈ $0.15 (2K); video ≈ $0.17/sec (e.g. a 4.5s clip ≈ $0.76; a 24s clip ≈ 3 segments ≈ ~$4).

## Error handling

- Any script exits non-zero → relay its `ERROR:` line verbatim and stop. Don't retry blindly.
- Missing/blank `FAL_KEY` → point the user to `<skill>/.env`; don't proceed.
- Batch mid-failure → relay which segment failed. Already-rendered segments stay in `<work>`; nothing partial is concatenated. Re-run after the user resolves it (e.g. adds Fal credit).
- ffmpeg/ffprobe missing → tell them to run `install.ps1`.

## Constraints

- Each Kling call is one 3–10s segment. ≤10s = one call; >10s = automatic even-split + concat; <3s = rejected (relay the 3s floor and stop).
- Video must be 720–2160px and ≤200MB per Kling O1.
