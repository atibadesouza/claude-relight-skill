# Relight — Claude Code Skill (Design Spec)

**Date:** 2026-06-21
**Status:** Approved (design), pending implementation plan
**Source inspiration:** "This Claude Skill Generates Studio Lighting & Crazy Backgrounds" — Systems by Vic (YouTube `pZNQwzW_JjM`)

## 1. Goal

Relight and replace the background of short talking-head footage entirely from Claude Code, reproducing Vic's "Relight" workflow. Given a short clip + a text description + an optional reference image, the skill produces a new video where the subject is placed in a cinematic, well-lit environment with the original motion and audio preserved.

This is a reusable, shareable skill: the canonical source lives in a git repo so others can clone and install it.

## 2. Hard constraints (from the model APIs)

- **Kling O1 video-to-video reference** (`fal-ai/kling-video/o1/video-to-video/reference`) accepts input video **3–10 seconds, 720–2160px, ≤200MB**. This is why the tool targets short-form. Longer footage must be split into ≤10s segments (batch mode is a future extension, not in v1).
- **Fal AI is paid.** Nano Banana Pro edit ≈ $0.15 (1K) / $0.30 (4K) per image. Kling O1 video cost is per-run (a few seconds ≈ <$1, matching Vic's ~$0.76). The skill must show cost before the paid video step.
- Requires a **Fal API key** (`FAL_KEY`), stored in a local `.env` file, never pasted into chat.

## 3. Pipeline

1. **Preflight** — verify `ffmpeg` is on PATH; verify Python deps (`fal-client`, `opencv-python`); load `FAL_KEY` from the skill's `.env`. If anything is missing, guide the fix and stop.
2. **Validate clip** — probe duration / resolution / file size. If outside Kling O1 limits, explain and offer to auto-trim to 10s (with ffmpeg). Never silently truncate.
3. **Extract best frame** — sample N evenly-spaced frames, score each by sharpness (variance-of-Laplacian via OpenCV), select the clearest non-blurry frame as the subject reference still.
4. **Relight still** — call `fal-ai/nano-banana-pro/edit` with `image_urls = [best_frame, reference_image?]` and a prompt built from a baked-in cinematic/warm/flattering template wrapping the user's description. Return a still.
5. **Approval gate** — present the generated still + projected video cost. User approves, or requests a rerun with tweaks (re-prompt, new seed, or different frame).
6. **Relight video** — call `fal-ai/kling-video/o1/video-to-video/reference` with `video_url = clip`, `image_urls = [approved_still]`, `keep_audio = true`. Preserves original motion + audio, applies the new lighting/background, subtly animates the background.
7. **Deliver** — download final MP4 + approved still + source frame into the output folder; print the absolute path.

## 4. Repository layout (single source of truth + symlink)

```
Video Editing/                      (git repo)
├─ .claude/skills/relight/          ← CANONICAL skill source
│  ├─ SKILL.md                       orchestration, prompts, approval gate, errors, cost
│  ├─ scripts/
│  │  ├─ preflight.py                check ffmpeg + deps + FAL_KEY
│  │  ├─ extract_frame.py            clip → best sharp frame (+ probe/validate/trim)
│  │  ├─ relight_image.py            frame + reference + prompt → still via Fal
│  │  └─ relight_video.py            clip + still → final video via Fal
│  ├─ .env.example                   FAL_KEY=
│  └─ requirements.txt               fal-client, opencv-python
├─ install.ps1                       symlink .claude/skills/relight → ~/.claude/skills/relight;
│                                     install ffmpeg (winget) + pip deps; seed .env from example
├─ README.md                         setup, Fal key, cost, usage, 10s constraint
├─ docs/superpowers/specs/…          this spec
└─ .gitignore                        .env, relight-outputs/, model caches
```

- **Canonical source:** the repo's `.claude/skills/relight/` — auto-activates for anyone working inside the cloned repo (project-level use).
- **User-level install:** `install.ps1` creates a symlink `~/.claude/skills/relight → <repo>/.claude/skills/relight`, so the skill works from anywhere with zero drift. (Windows symlinks require Developer Mode or an elevated shell; install.ps1 detects and instructs.)
- **`.env` is per-machine** (gitignored). `.env.example` is committed.

## 5. Output location

- Default: `./relight-outputs/` in the current working project (the folder Claude is invoked from).
- Fallback: `~/Documents/relight/` if not in a project.
- Configurable per run ("save it to X").
- `relight-outputs/` is gitignored.

## 6. Components (each independently testable)

| Script | Input | Output | Depends on |
|---|---|---|---|
| `preflight.py` | — | pass/fail report | ffmpeg, fal-client, opencv, .env |
| `extract_frame.py` | clip path, N | best frame path + probe JSON | opencv, ffmpeg |
| `relight_image.py` | frame, reference?, prompt, resolution | still path + cost | fal-client |
| `relight_video.py` | clip, still, keep_audio | final mp4 path + cost | fal-client |

Each script: standalone CLI with `--help`. The two Fal scripts support `--no-api`/`--dry-run` (print the request that *would* be sent, plus cost estimate, without spending money).

## 7. Cinematic prompt template (baked-in)

`relight_image.py` wraps the user description in a fixed template enforcing: three-point/cinematic lighting, warm flattering skin tones, shallow depth of field, color-graded look, subject identity + framing preserved from the source frame, background per the user's description/reference. Exact wording finalized during implementation; the user only supplies the creative intent.

## 8. Error handling

- Missing/invalid `FAL_KEY` → point to the `.env` path; do not proceed.
- Fal job failure / insufficient credit → surface the Fal error message + dashboard link.
- Clip out of bounds (duration/res/size) → explain the specific limit, offer auto-trim, never silently truncate.
- No usable sharp frame (all blurry) → return the least-blurry with a warning and offer manual frame choice.
- ffmpeg/deps missing → exact install command, stop.

## 9. Test Plan

- **Smoke test:** `preflight.py` reports all-green on a configured machine; `extract_frame.py` on a bundled ~5s sample clip produces a sharp frame and a probe JSON with correct duration. No paid calls. Pass signal: frame file exists + sharpness score logged + probe shows duration ≤10s.
- **Backend / script logic tests:**
  - *extract_frame:* clip exactly at bounds (3s, 10s) passes; 12s clip triggers the out-of-bounds path and the auto-trim offer; a synthetically blurred clip selects the least-blurry frame and warns; a corrupt/non-video file errors cleanly (no crash, actionable message).
  - *relight_image `--dry-run`:* asserts the request payload contains both image URLs (when a reference is supplied) and the cinematic template wraps the user prompt; asserts cost estimate is reported; missing `FAL_KEY` produces the guided-stop, not a stack trace.
  - *relight_video `--dry-run`:* asserts `keep_audio=true`, `video_url` set, `image_urls=[still]`, duration within 3–10s; out-of-bounds duration is rejected before any API call.
- **Abuse / edge:** `FAL_KEY` absent → guided stop; reference image path that doesn't exist → clear error; output folder not writable → clear error; double-invocation/rerun at the approval gate does not re-spend on the already-approved still.
- **Cost-safety regression:** no script makes a paid Fal call without (a) a valid key and (b) for the video step, explicit user approval at the gate. A test asserts `--dry-run` spends nothing and that `relight_video` refuses to run without the approval flag/confirmation.
- **AI-output quality (manual done-gate):** one real end-to-end paid run on a real clip — verify lighting is cinematic/flattering, identity preserved, background matches intent and animates subtly, **audio preserved**, output lands in the right folder. Human exploratory pass.
- **Known-bug regressions:** add a regression test for any bug found during the real run (e.g., audio dropped, wrong aspect ratio, frame with motion blur chosen).
- **Done-gate:** smoke + script tests green, cost-safety green, one real paid run reviewed by a human (golden path + audio + identity + background animation), edge/error states covered.

## 10. Out of scope (v1 / YAGNI)

- Batch mode for footage >10s (split → relight each → concat). Future extension.
- Non-Fal providers.
- GUI / web UI — this is a Claude Code skill only.
- Auto-editing back into a timeline (Premiere/Resolve). User re-imports the output manually, like Vic.

## 11. Open implementation details (resolved during plan/build)

- Exact Nano Banana Pro resolution default (1K vs 2K) balancing cost vs. quality for the still.
- Exact frame-count `N` and sharpness threshold for `extract_frame.py`.
- Final cinematic prompt wording.
- Fal cost values to display (pulled from current Fal pricing at build time).
