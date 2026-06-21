# Relight — Two Modes (Kling Motion + HeyGen Avatar IV Sync) — Design Spec

**Date:** 2026-06-21
**Branch:** `mediagen-skill`
**Status:** Approved (design), pending implementation plan
**Related:** [[relight skill]] (`docs/plans/2026-06-21-relight-skill.md`), the abandoned Fal lip-sync stage (`docs/plans/2026-06-21-relight-lipsync.md` — to be reverted, see §8).

## 1. Goal

Give the Relight skill **two user-selectable modes** so the user can choose, per clip, between preserving their real filmed motion and getting perfect lip-sync:

- **Motion mode** — the existing Kling O1 video-to-video pipeline, unchanged. Preserves the real performance (head motion, gestures, original audio); lips can drift; face is slightly synthetic.
- **Sync mode** — a new pipeline driven by **HeyGen Avatar IV**: animate the already-approved relit still from the clip's audio. Lip-sync is perfect by construction; motion is AI-generated; cheaper than Kling.

## 2. Background — why this design

The lip drift in Motion mode is introduced by Kling regenerating every frame. We tried to repair it post-hoc and it failed conclusively:

- **Fal lip-sync (3 models)** — `sync-lipsync v2` ($2.71), `MuseTalk` ($0.04), `LatentSync` ($0.27) all failed on the synthetic relit face (timing off, face warped, fake mouth). Patching after a generative pass is a dead end.
- **HeyGen A/B validation spike** (this session) — on the same relit clip:
  - **A** (`video_translate`, keep-motion + re-lipsync) **failed before render** with `Insufficient credit. This operation requires 'api' credits.` — *untested*, not a quality result. Needs HeyGen API credits.
  - **B** (Avatar IV from the approved relit still + audio) **rendered cleanly** (54.5s, 1080²) and the user judged it **good**.

So Sync mode is built on the proven **B** path. A (fixing Motion mode's lips) is explicitly out of scope here (§11) — Motion mode keeps its known drift as the trade for real motion.

## 3. Architecture — mode selection

At the start of a relight job, SKILL.md instructs Claude to ask the user which mode they want (a one-line orchestration choice, not a code flag):

| | **Motion mode** (Kling) | **Sync mode** (Avatar IV) |
|---|---|---|
| Real motion | preserved | generated |
| Lip-sync | drifts | perfect |
| Face | slightly synthetic | from relit still |
| Cost | ~$10/min (Kling) + $0.15 still | ~$4/min (Avatar IV) + $0.15 still |
| Vendor | Fal | HeyGen |

Both modes share Steps 1–3 (frame → relit still → approval). They diverge only at the video step.

## 4. Shared front half (unchanged, both modes)

1. `extract_frame.py` — sharpest frame + duration probe.
2. `relight_image.py` — relit still via Fal Nano Banana Pro.
3. Approval gate — show still + the **mode-appropriate** cost estimate; require explicit approval.

## 5. Motion mode (unchanged Kling pipeline)

Exactly today's behavior: `relight_video.py` (≤10s) or `relight_batch.py` (>10s split→relight→concat) using Kling O1 video-to-video reference, preserving motion + audio. **No change** beyond removing the abandoned mandatory Fal lip-sync stage (§8).

## 6. Sync mode (new — HeyGen Avatar IV)

Pipeline after the approved still:
```
extract audio from the ORIGINAL clip (mp3, ≤32MB)
  → upload still as talking_photo  → talking_photo_id
  → upload audio asset             → audio_url
  → POST /v2/video/generate (Avatar IV) → video_id
  → poll /v1/video_status.get until completed → download
```

**HeyGen API shapes — proven by the spike that rendered "B":**
- **Auth:** header `X-Api-Key: <key>`. Base `https://api.heygen.com`.
- **Upload talking photo (the still):** `POST https://upload.heygen.com/v1/talking_photo`, header `Content-Type: image/png` (or `image/jpeg`), **raw image bytes** as body → `data.talking_photo_id`. (≤32MB; the relit still ≈ 5MB.)
- **Upload audio asset:** `POST https://api.heygen.com/v3/assets`, `multipart/form-data` field `file` → `data.url` (+ `data.asset_id`). (≤32MB.)
- **Generate:** `POST https://api.heygen.com/v2/video/generate`, JSON:
  ```json
  {
    "test": false,
    "title": "<stem> Sync",
    "dimension": { "width": <W>, "height": <H> },
    "use_avatar_iv_model": true,
    "video_inputs": [{
      "character": { "type": "talking_photo", "talking_photo_id": "<id>" },
      "voice":     { "type": "audio", "audio_url": "<url>" }
    }]
  }
  ```
  → `data.video_id`.
- **Status:** `GET https://api.heygen.com/v1/video_status.get?video_id=<id>` → `data.status` (`processing` | `completed` | `failed`), `data.video_url` when completed.

**Details:**
- **Audio source = the original clip**, not the relit one (Sync mode never runs Kling). Extract to **mp3** (not WAV) so long clips stay under HeyGen's 32MB upload cap (a 54s WAV was already 10MB; WAV would blow the cap around ~3min).
- **`dimension`** is computed from the **still's aspect ratio**, capped at 1080p (Avatar IV's ceiling): square→1080×1080, 16:9→1920×1080, etc.
- **Output:** `<output_dir>/<input-stem>/<input-stem> Synced.mp4` (Sync mode), parallel to Motion mode's `<input-stem> Relit.mp4`. Keep the approved still in the same subfolder.

## 7. Cost, approval, credits

- **Avatar IV ≈ $4/min** → estimator `round(4.00 * duration_s / 60, 2)`, reported as "approx".
- Same discipline as the Fal steps: `--dry-run` prints endpoint + payload + estimate and spends nothing; the real generate call requires `--approved`. Always show the dollar estimate before the paid call.
- **Credits gotcha (surfaced in the spike):** HeyGen returns `Insufficient credit. This operation requires 'api' credits.` when the account lacks funded **API** credits. The script detects this (in the generate response or the failed status payload) and raises a `GuidedError` telling the user to top up API credits at the HeyGen dashboard — not a cryptic failure.

## 8. Cleanup — revert the abandoned Fal lip-sync stage

The mandatory Fal lip-sync stage (committed earlier this session) is confirmed non-working and is removed:
- Delete `scripts/lipsync_video.py` and `tests/test_lipsync_video.py`.
- Revert the `SKILL.md` edits that folded lip-sync into Step 3, redirected Step 4 to `<work>/relit.mp4`, added the mandatory "Step 5", and the lip-sync lines in Output / Cost / Constraints. Motion mode's Step 4 returns to writing the final `<out>` directly.
- Remove the lip-sync section from `docs/plans/2026-06-21-relight-skill-buildlog.md`.

(The throwaway `relight-outputs/.heygen-spike/` and the comparison MP4s are gitignored scratch, not committed.)

## 9. Key handling

- `heygen_common.load_heygen_key()` resolves `HEYGEN_API_KEY` from, in order: the environment, then `~/.claude/heygen.env` (the cross-skill home, already created this session, outside the repo). Missing/blank → `GuidedError` naming that path.
- A `heygen.env.example` ships in the skill; `~/.claude/heygen.env` is never committed.
- `preflight.py` gains a HeyGen check (key present) alongside the existing Fal check.

## 10. File structure

```
.claude/skills/relight/
  scripts/
    heygen_common.py     NEW — load_heygen_key; X-Api-Key HTTP get/post; poll helper; GuidedError (reused from relight_common)
    heygen_avatar.py     NEW — extract_audio_mp3; upload_talking_photo; upload_audio_asset;
                                aspect_to_dimension; build_generate_request; run(dry_run, approved); poll; main
    extract_frame.py     (unchanged)
    relight_image.py     (unchanged)
    relight_video.py     (unchanged)
    relight_batch.py     (unchanged)
    preflight.py         MODIFY — add HeyGen key check
    lipsync_video.py     DELETE (§8)
  tests/
    test_heygen_avatar.py  NEW — payload builders, cost, dry-run/approval guards, aspect→dimension, credit-error detection
    test_lipsync_video.py  DELETE (§8)
  SKILL.md               MODIFY — mode selection + Sync-mode steps; revert lip-sync edits (§8)
  heygen.env.example     NEW
```

## 11. Error handling

- Missing/blank HeyGen key → `GuidedError` → `~/.claude/heygen.env`.
- `Insufficient credit` (generate or status) → `GuidedError` to fund API credits.
- Upload >32MB → clear `GuidedError` (still won't hit it; audio mp3 keeps it small — but guard anyway).
- HeyGen job `failed` → relay `data.error`/`message` verbatim.
- ffmpeg/ffprobe missing → point to `install.ps1`.
- No paid generate without (a) a key and (b) explicit `--approved`.

## 12. Testing

- **Unit (`test_heygen_avatar.py`):**
  - `build_generate_request` carries `talking_photo` character, `audio` voice, `use_avatar_iv_model: true`, and the computed `dimension`.
  - `aspect_to_dimension` → 1080×1080 for square, 1920×1080 for 16:9, capped at 1080p.
  - `estimate_avatar_cost` → $4/min at known durations (60s → 4.00; 30s → 2.00).
  - `--dry-run` spends nothing and returns endpoint + payload + estimate; real run refuses without `--approved`; missing-key path raises `GuidedError`.
  - **Credit-error detection:** given a simulated `Insufficient credit` status payload, the poll/parse function raises the fund-credits `GuidedError` (no live call).
- **Regression:** existing Relight (Kling) tests stay green; removing `lipsync_video.py` removes its 14 tests cleanly.
- **Live done-gate:** already satisfied — the spike's **"B" render** (downloaded, user-approved) is the end-to-end proof for Sync mode. One more real run during the build re-confirms after refactor into the skill.

## 13. Out of scope (this build)

- **Approach A** (HeyGen `video_translate` to fix Motion mode's lips) — untested, needs API credits; documented as a future enhancement to Motion mode, not built now.
- Folding HeyGen plumbing into the planned `falkit`/MediaGen core — Sync mode keeps its own `heygen_*` scripts for now; unify later.
- Multi-speaker, batching, or Avatar IV beyond the single talking-photo + audio path.
