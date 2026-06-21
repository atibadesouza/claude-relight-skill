---
name: mediagen
description: Generate and transform media from Claude Code via Fal AI — text-to-image, image editing with reference images, animating a still into a video, and upscaling any video. Use when the user wants to "generate/make an image", "edit this image", "turn this into a video / animate this", or "upscale this video". The user NEVER needs to name a model — the skill auto-selects the best Fal model (Nano Banana Pro, Kling v3 Pro, Topaz) for the task. Pay-per-use via one shared Fal API key.
---

# MediaGen

A general media-generation toolkit on Fal AI. Four capabilities, one shared key, and **the user never names a model** — you map the task to the best model automatically.

## Model selection is invisible to the user

Never ask which model to use. The scripts call `falkit.resolve_model(task)` and pick the best one (image → Nano Banana Pro, image_edit → Nano Banana Pro edit, image_to_video → Kling v3 Pro, upscale → Topaz). Only pass `--model <endpoint>` or `--tier cheap` if the user *explicitly* insists on a specific model or a cheaper option. If the user happens to name a model (e.g. "use Nano Banana"), that's fine — but you never require it.

## Setup (first time)

1. From the repo root, run `install.ps1` (installs ffmpeg, the shared `falkit` core, deps, links this skill, seeds the shared key file).
2. Put your Fal key in `~/.claude/fal.env` as `FAL_KEY=...` (get one at https://fal.ai/dashboard/keys; it's pay-per-use). **Edit the file — never paste the key into chat.** This one key is shared with the Relight skill.

`<skill>` = this skill's folder; scripts are under `<skill>/scripts/`.

## Output location

Default `./mediagen-outputs/<slug>/` in the current project; fallback `~/Documents/MediaGen/<slug>/`. `<slug>` = a short kebab-case label from the user's request. Honor any path the user gives.

## Prompt rewriting (image generation)

For **image generation**, the user gives a rough idea; you expand it into a strong, detailed, model-appropriate prompt (subject, style, lighting, composition, quality) before calling the script. Briefly show the user the rewritten prompt, then pass it as the script's `prompt` argument. (Editing/video/upscale use the user's instruction more directly.)

## Run order per capability

All output to `<output_dir>/<slug>/`.

**Text → image** (cheap, no approval gate):
```
python scripts/image_generate.py "<rewritten prompt>" --out "<out>.png" [--resolution 4K]
```
Show the image + the actual cost (~$0.15, $0.30 at 4K).

**Image edit with references** (cheap, no approval gate):
```
python scripts/image_edit.py "<instruction>" "<ref1>" ["<ref2>" ...] --out "<out>.png"
```
Pass every reference image's file path. Show the result + cost. (Cost reuses the image price; label it approximate — Fal may price edits differently.)

**Image → video** (per-second, APPROVAL REQUIRED):
1. `python scripts/image_to_video.py "<still>" "<prompt>" <seconds> --dry-run` → read `est_cost`.
2. Present the cost + the prompt to the user; get explicit approval. (Be precise about duration — it's priced per second.)
3. On approval: `python scripts/image_to_video.py "<still>" "<prompt>" <seconds> --out "<out>.mp4" --approved`.
The script auto-compresses a still >10MB (Kling's cap) before upload. The dry-run payload prints the local image path — it's a cost/prompt preview, not the literal request.

**Upscale a video** (per-second, APPROVAL REQUIRED):
1. Probe the input with ffprobe for **duration** and **short side** (min of width/height).
2. `python scripts/upscale.py "<video>" --factor <f> --duration <secs> --in-min-dim <short side> --dry-run` → read `est_cost` (it scales with `--factor`: a 4× quote is higher than 2×).
3. Present it as an **approximate** cost; get approval.
4. On approval: `python scripts/upscale.py "<video>" --factor <f> --out "<out>.mp4" --approved`.
Works on any video, not just generations.

## Offer the next step

After generating an image, ask if they want to **animate it** into a video. After a video, offer to **upscale** it. (Mirrors the natural image → video → upscale flow.)

## Cost transparency

Always state the dollar estimate before the paid step for video/upscale, and require explicit approval. Images are cheap and run automatically (report cost after). Label edit and per-second video/upscale costs as **approximate** (the per-second rates and edit price are pinned estimates).

## Error handling

- Any script exits non-zero → relay its `ERROR:` line verbatim and stop.
- Missing/blank key → point to `~/.claude/fal.env`; don't proceed.
- Unknown task/model or a missing reference path → relay the `GuidedError` and stop.
- Never run video/upscale without `--approved`.
