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
