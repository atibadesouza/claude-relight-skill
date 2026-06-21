# Relight Skill — Build Log

**Run started:** 2026-06-21
**Plan:** `docs/plans/2026-06-21-relight-skill.md`
**Scope:** Tasks 1–10 (free, no Fal key). Stop before Task 11 (paid run, needs user's FAL_KEY).

## Strategy
- **Single agent.** Scripts are interdependent (shared `relight_common`; `relight_batch` imports `split_video`/`concat_video`/`relight_video`/`extract_frame`). Plan is small and fully specified with exact code. Parallel/swarm coordination overhead not justified.

## Assumptions
- **Em-dash → hyphen in `preflight.py` output.** The Windows console (cp1252) rendered the `—` in "NOT READY — fix…" as a mojibake `�`. Swapped to a plain `-` so the user-facing checklist reads cleanly. Cosmetic only; no logic change.
- **`<work>` temp dir convention** = `<output_dir>/.work-<name>/` (documented in SKILL.md). Plan left the exact temp path to build-time; chose a hidden sibling of the output so intermediates are easy to find and delete.

## Done
- Task 1 — scaffold + `relight_common` (env load, GuidedError, cost estimators). 4 tests green.
- Task 2 — `extract_frame` (probe, validate_clip, sharpness, best-frame). 4 tests green.
- Task 3 — `relight_image` (Nano Banana Pro, cinematic template, dry-run). 3 tests green.
- Task 4 — `relight_video` (Kling O1, approval gate, dry-run). 4 tests green.
- Task 5 — `split_video` (plan_segments even-split + ffmpeg split). 4 tests green.
- Task 6 — `concat_video` (build_concat_list + ffmpeg concat). 2 tests green.
- Task 7 — `relight_batch` (estimate_batch + orchestrate split→relight→concat). 4 tests green.
- Task 8 — `preflight` (ffmpeg/ffprobe/cv2/fal_client/FAL_KEY checklist). Manually verified: correct XX/OK + exit 1 pre-install.
- Task 9 — `SKILL.md` (orchestration, approval gate, duration branch single vs batch).
- Task 10 — `install.ps1` (PowerShell syntax-checked OK) + `README.md`.
- **Final verification:** full suite **25 passed**; CLI dry-run smoke test for `relight_image` and `relight_video` returns correct endpoints/cost with no spend.

## Deviations
- None of substance. (See Assumptions for the two minor build-time choices.)

## Follow-ups (for the user — Task 11, the paid done-gate)
1. **Run `install.ps1`** — installs ffmpeg (not yet on this machine), pip deps (already installed), symlinks the skill, seeds `.env`. Needs Developer Mode/admin for the symlink (else it copies).
2. **Add your Fal key** to `.claude/skills/relight/.env` (`FAL_KEY=...`), then `python .claude/skills/relight/scripts/preflight.py` → expect `READY`.
3. **Single-clip real run** — a ≤10s talking-head clip through the skill. Verify cinematic/flattering lighting, identity preserved, background animates subtly, **audio preserved**, output in `relight-outputs/`, cost shown before spending.
4. **Batch real run** — a >10s clip. Verify segment count + total shown before spend; same still across segments; final stitched MP4 plays continuously with audio across seams; no jarring seam jumps.
5. For any defect found, add a regression test under `tests/` and fix before declaring done.

(Task 11 was originally deferred; the user then supplied the key + inputs, so it was executed — see below.)

## Task 11 — real paid run (executed 2026-06-21)

**Inputs:** `Build Projects from Video Tutorials with Claude.mp4` (54.6s screen recording, webcam panel) + a living-room/computers `.avif` reference.

**Findings / deviations:**
- **Input wasn't a full-frame talking head** — it was a screen recording with the person as a webcam panel. Cropped to the person (x295–985, y162–775) and upscaled to 1218×1080 (>720 min) before relighting. The `.avif` reference was converted to PNG (models don't take AVIF).
- **Still (Nano Banana Pro): excellent** first try — subject placed in the computer-room with cinematic warm lighting, identity preserved. ~$0.15.
- **BUG found in video stage:** the original soft `VIDEO_PROMPT` ("apply the environment from the reference") produced **inconsistent backgrounds across segments** — seg0 rendered a plain wall, seg1 rendered the full computer room. Stitching would jump at seams. Stopped the batch at 2/6 (~$3.23 spent) rather than burn the full $9.39.
- **Fix:** strengthened `VIDEO_PROMPT` to insist on a *full background rebuild every segment*, and added a `--prompt` per-run override (relight_video + relight_batch). Committed with a regression test (`test_prompt_override_used_when_given`); suite now **26 passing**. Verified the strong prompt on one test segment → consistent computer-room background in both early and late frames.
- **Finish:** re-rendered the remaining 5 segments with the strong scene prompt (reusing the validated test segment as #2) and concatenated all 6. Extra spend ~$7.70; run total ~$12.50 (vs $9.39 estimate — delta = cost of discovering/fixing the background bug). User approved the higher total.

**Skill improvement banked for next time:** the stronger default prompt means a single talking-head clip should get a consistent replaced background first try; `--prompt` allows scene-specific direction.

**Follow-up still open:** a proper full-frame talking-head export would skip the crop step. Consider adding (a) an auto-crop/letterbox-detection helper and (b) AVIF→PNG conversion into the skill so these aren't manual.
