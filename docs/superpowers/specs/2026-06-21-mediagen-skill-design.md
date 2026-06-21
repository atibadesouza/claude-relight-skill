# MediaGen Skill + Shared Fal Core (`falkit`) — Design Spec

**Date:** 2026-06-21
**Branch:** `mediagen-skill`
**Status:** Approved (design), pending implementation plan
**Source inspiration:** "I Cancelled Higgsfield & Built This Claude Skill Instead" — Systems by Vic (YouTube `P7Aruo5J3BQ`)
**Related:** [[relight skill]] (`docs/superpowers/specs/2026-06-21-relight-skill-design.md`) — sibling skill; this work extracts the shared Fal plumbing both use.

## 1. Goal

Build **MediaGen**, a general media-generation skill for Claude Code that runs entirely on **Fal AI** with one pay-per-use API key: text→image, image editing with references, image→video, and video upscaling. Extract the Fal plumbing shared with the existing Relight skill into a small importable package, **`falkit`**, that both skills use.

Two hard product requirements:
- **The user never names a model.** They describe the task ("generate an image of…", "animate this", "upscale this"); the skill maps task → the current best Fal model automatically. Model names (Nano Banana Pro, Kling, Topaz) are baked into a registry and invisible to the user.
- **Claude rewrites rough prompts.** For image generation, Claude turns the user's loose idea into a strong, model-appropriate prompt before generating (a SKILL.md behavior, not code).

## 2. Architecture — shared core, two skills

A small pip-installable package at the repo root holds everything both skills need, so it works regardless of how each skill folder is symlinked into `~/.claude/skills`.

```
falkit/                          shared Fal core (NEW, pip install -e .)
  __init__.py                    re-exports the public API
  core.py                        GuidedError; load_fal_key; upload_file; subscribe; cost helpers
  models.py                      task→model registry + resolve_model()
  pyproject.toml
.claude/skills/mediagen/         NEW skill
  SKILL.md
  scripts/
    image_generate.py            text → image
    image_edit.py                image(s) + refs → edited image
    image_to_video.py            still → video
    upscale.py                   video → upscaled video
  tests/
    test_image_generate.py
    test_image_edit.py
    test_image_to_video.py
    test_upscale.py
.claude/skills/relight/          refactored to import falkit
  scripts/relight_common.py      becomes a thin shim re-exporting falkit (no breakage)
install.ps1                      also runs: pip install -e ./falkit
```

`relight_common.py` keeps its current public names (`GuidedError`, `load_fal_key`, `estimate_image_cost`, `estimate_video_cost`, `find_skill_root`) by re-exporting from `falkit`, so all of Relight's scripts and its 26 tests keep working unchanged.

## 3. Model auto-selection — `falkit/models.py`

A registry maps each task to the current best Fal endpoint, with an optional cheaper tier. The user never supplies a model.

| Task key | "best" (default) | "cheap" | Endpoint (best) |
|---|---|---|---|
| `image` | Nano Banana Pro | Nano Banana | `fal-ai/nano-banana-pro` |
| `image_edit` | Nano Banana Pro edit | Nano Banana edit | `fal-ai/nano-banana-pro/edit` |
| `image_to_video` | Kling v3 Pro | Kling v3 Standard | `fal-ai/kling-video/v3/pro/image-to-video` |
| `upscale` | Topaz | Topaz | `fal-ai/topaz/upscale/video` |

```
resolve_model(task: str, tier: str = "best", override: str | None = None) -> str
```
- `override` (a literal Fal endpoint, or a known friendly alias) wins if given — for power users only.
- Unknown `task` → `GuidedError` listing valid tasks.
- Updating models when Fal ships new ones = editing this one table.

The registry also carries each model's **cost function** so callers get estimates without hard-coding numbers per script (see §6).

## 4. The four capabilities

Each is a thin script over `falkit`, with a pure `build_*_request()` (unit-tested) and a `run(..., dry_run, approved)` wrapper. All paid scripts support `--dry-run` (no spend) and the two pricier ones require `--approved`.

1. **`image_generate.py`** — input: final prompt (Claude pre-rewrites the user's idea per SKILL.md), `--tier`, optional `--model` override. Resolves `image`, calls Fal, downloads to output folder. Cheap → no approval gate (reports cost after).
2. **`image_edit.py`** — input: prompt + one or more local reference image paths (uploaded via `falkit.upload_file`). Resolves `image_edit`. Preserves identity. Cheap → no approval gate.
3. **`image_to_video.py`** — input: still path + prompt + duration (per-second priced). Resolves `image_to_video`. **Shows cost + prompt, requires approval.** Pre-flight: if the still is >10MB, auto-compress to ≤10MB (Kling cap) before upload, logging that it did so.
4. **`upscale.py`** — input: any video path + `--factor` (default 2) + optional `--target-fps`. Resolves `upscale`. **Shows cost + requires approval.** Works on any video, not just generations.

## 5. Prompt rewriting (SKILL.md behavior)

For `image_generate`, SKILL.md instructs Claude to expand the user's rough idea into a detailed, photorealistic-or-styled prompt appropriate to the model, then pass that as the script's prompt argument. This is Claude's job in orchestration, not a code path — the script receives an already-good prompt.

## 6. Cost & approval policy

- Cost estimates come from the registry's per-model cost function:
  - `image` / `image_edit`: flat per image (Nano Banana Pro: $0.15 at ≤2K, $0.30 at 4K).
  - `image_to_video`: per-second (Kling v3 Pro ≈ $0.168/s audio-off; estimator uses a pinned rate, reported as "approx").
  - `upscale`: per-second by output resolution (Topaz: ~$0.01–0.08/s; estimator uses a conservative pinned rate).
- **Images run automatically** (cheap), reporting actual cost after.
- **Video and upscale always show the dollar estimate + prompt and require explicit approval** before the paid call (mirrors Relight and Vic's flow). No `--approved`, no spend.
- `--dry-run` on any paid script prints the resolved endpoint + payload + estimate and spends nothing.

## 7. Shared key / `.env`

`falkit.load_fal_key()` resolves in order and sets `os.environ["FAL_KEY"]`:
1. `FAL_KEY` already in the environment.
2. Shared file `~/.claude/fal.env` (`FAL_KEY=...`) — the cross-skill home, so one key serves MediaGen and Relight.
3. Skill-local `.env` (back-compat: Relight's existing `<skill>/.env` still works).

Missing/blank in all three → `GuidedError` naming the shared path to create. The shared file is created by `install.ps1` from an example and is gitignored.

## 8. Output location

Default `./mediagen-outputs/` in the current project; fallback `~/Documents/MediaGen/`; per-job subfolders (e.g. `mediagen-outputs/<slug>/`) like Relight. Gitignored.

## 9. Error handling

- Missing/blank key → `GuidedError` to the shared `~/.claude/fal.env` path; stop.
- Unknown task/model → `GuidedError` listing valid options.
- Fal job failure / insufficient credit → surface the Fal error + dashboard link.
- Image>10MB for Kling → auto-compress and log; never silently fail.
- Reference/input file missing → clear `GuidedError`.
- No paid call without (a) a key and (b) for video/upscale, explicit approval.

## 10. Testing

- **Model resolver:** `resolve_model` returns the right endpoint per task; `tier="cheap"` differs; `override` wins; unknown task raises.
- **Payload builders:** each `build_*_request` carries the resolved endpoint, the prompt, and required params (e.g. image_to_video duration string, reference image list for edit).
- **Cost estimators:** per-task functions return expected values at known inputs (deterministic, no half-cent ambiguity).
- **Dry-run / approval guards:** every paid script spends nothing on `--dry-run`; `image_to_video` and `upscale` refuse the real run without `approved=True`.
- **>10MB compression:** the pre-flight compresses an oversized still below the cap (or, in a no-ffmpeg unit context, the decision function flags it) — tested without a paid call.
- **Relight regression:** Relight's existing 26 tests stay green after `relight_common.py` becomes a `falkit` shim.
- **Manual done-gate (paid):** one real run of each capability — generate an image, edit with a reference, animate a still, upscale a clip — verifying output quality, cost-shown-before-paid-step, and audio handling on video.

## 11. Out of scope (v1 / YAGNI)

- Audio/music/voice generation models.
- A general "any Fal model" passthrough beyond the four task categories (the `override` escape hatch covers rare needs).
- Batch/queue management of many generations.
- Making Relight *call into* MediaGen for its still/video steps (Relight keeps its own pipeline; only the shared core is unified now). Relight→upscale hand-off is a documented option, not an automated dependency.

## 12. Open implementation details (resolved during plan/build)

- Exact pinned per-second rates to display for Kling v3 Pro and Topaz (from current Fal pricing at build time).
- Whether the shared key file is `~/.claude/fal.env` vs `~/.fal/key` (default to `~/.claude/fal.env`).
- Friendly-alias table for `--model` overrides (power-user nicety).
- Exact Topaz `enhancement_model` default (likely "Standard V2").
