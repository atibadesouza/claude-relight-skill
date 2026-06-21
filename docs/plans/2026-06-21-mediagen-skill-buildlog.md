# MediaGen + falkit — Build Log

**Run started:** 2026-06-21
**Plan:** `docs/plans/2026-06-21-mediagen-skill.md` (APPROVED via plan-loop, round 3)
**Branch:** `mediagen-skill`
**Scope:** Tasks 1–9 (free, no Fal spend). Stop before Task 10 (paid per-capability done-gate).

## Strategy
- **Single agent.** Strict dependency chain: falkit core → models → `pip install -e ./falkit` → mediagen scripts (`import falkit`) → relight shim (`from falkit.core import`). Sequencing dominates; no independent fan-out to parallelize.

## Assumptions
- **`__init__.py` built in two steps.** Task 1 created a core-only `__init__.py`; Task 2 added the `models` exports. Avoids `from falkit import core` (which runs `__init__`) failing before `models.py` exists. Matches the plan's intent; just sequenced cleanly.

## Done
- Task 1 — `falkit-core` scaffold + `core.py` (key precedence, client wrappers). 4 tests.
- Task 2 — `models.py` registry + resolver + cost fns. 9 falkit tests; editable install.
- Task 3 — relight `relight_common.py` → falkit shim w/ `ImportError` fallback; 2 key tests isolated + 3 appended. **Relight 43 passed, 0 failed (no regression).**
- Tasks 4–7 — `image_generate`, `image_edit`, `image_to_video`, `upscale`. 17 mediagen tests.
- Task 8 — `mediagen/SKILL.md` (invisible model selection, prompt rewriting, cost gates).
- Task 9 — `install.ps1` (ordered: ffmpeg → falkit editable → deps → link both → seed shared key → verify import), `fal.env.example`, `.gitignore`, README (both skills + self-executing setup).
- **Final verification:** full suite **69 passed** (9 + 17 + 43) via `python -m pytest` from repo root; CLI dry-runs confirm auto model selection + factor-aware upscale cost, no spend.

## Deviations
- **Renamed `falkit/` → `falkit-core/` (significant).** The plan put the package project dir at `./falkit`, but a repo-root dir named `falkit` *shadows* the installed package whenever CWD is the repo root (and `python -m pytest` from root puts root on `sys.path`), so `import falkit` resolved to the empty outer dir and mediagen tests would break. Renaming the **project** dir to `falkit-core` (package inside stays `falkit`) removes the collision. Updated `install.ps1`, README, and `.gitignore` to match. This is exactly the round-2 reviewer's "interpreter/shadowing" hidden-assumption, caught and fixed at build time.
- **`test_core.py` assertion fix.** The plan's `test_load_key_missing_raises_guided` patched `shared_key_path` to `nope.env` but asserted `"fal.env" in message` — the message contains the patched path. Changed the assertion to `"FAL_KEY" in message` (robust, still tests the guided error). Plan test bug; behavior unchanged.

## Follow-ups
- **Task 10 (paid done-gate) — left for the user.** Needs the shared `FAL_KEY` in `~/.claude/fal.env`. Run one of each: generate an image (verify Claude rewrites the prompt), edit with a reference (identity preserved), animate a still (cost + approval; >10MB auto-compress), upscale a clip (cost scales with factor + approval). Add a regression test for any defect.
- Branch `mediagen-skill` is ready to merge once Task 10 passes. Not pushed yet.

## Task 10 — paid done-gate (executed 2026-06-21)

Shared key seeded to `~/.claude/fal.env` from the existing relight `.env` (one key, both skills). All four capabilities run with real Fal calls:

- **Text→image** ($0.15) — golden retriever in a Superman cape playing a Switch in a warm library. Auto-selected `nano-banana-pro`. Excellent.
- **Image edit w/ reference** ($0.15) — same dog/pose/couch/library/Switch preserved, costume swapped Superman→Hulk. Identity-preserving edit confirmed (`nano-banana-pro/edit`).
- **Image→video** ($0.50) — animated the still to a 3.04s 1440×1440 clip via `kling-video/v3/pro/image-to-video`; approval gate showed $0.50 before spend.
- **Upscale** (~$0.24) — `topaz/upscale/video` took 1440²→2880² (true 2×); gate showed $0.24.

**Total ≈ $1.04.**

**Defect found + fixed (done-gate):** the real upscale run reported `est_cost: 0.0` because the post-run estimate relied on `--duration`/`--in-min-dim` being passed (the dry-run got them, the final command didn't). The approval gate was correct ($0.24), but the post-run number was wrong. Fix: `upscale.py` now **auto-probes** duration + short side via ffprobe when not supplied, so the estimate is accurate on the real run too. Regression test `test_run_autoprobes_duration_for_cost` added. Full suite **70 passed**.

**All four capabilities verified. Plan complete (Tasks 1–10).** Branch `mediagen-skill` ready to merge/push.
