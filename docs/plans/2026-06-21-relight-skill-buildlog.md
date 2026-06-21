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

(Task 11 is intentionally NOT executed in this run — it spends money and needs the user's key, which is a Tier-1 stop.)
