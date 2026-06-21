# Plan Review (Round 3)

**Verdict:** APPROVED
**Plan reviewed:** docs/plans/2026-06-21-mediagen-skill.md
**Goal as understood:** Build a new MediaGen Claude Code skill (text→image, image edit, image→video, video upscale on Fal AI) on top of a new shared `falkit` Python package that Relight also adopts via a graceful-fallback shim, with auto model selection so the user never names a model — without regressing Relight's existing test suite.

## What's right

The architecture is coherent and the prior two rounds' corrections are real and well-executed. Verified against the live codebase:

- **Round-2 Issue 1 (count baseline) — FIXED and verified.** `python -m pytest .claude/skills/relight/tests/ --co -q` collects exactly **40** (test_common 4, test_concat_video 2, test_extract_frame 4, test_lipsync_video 14, test_relight_batch 4, test_relight_image 3, test_relight_video 5, test_split_video 4 = 40; no skip/xfail). The plan now states "40 existing + 3 appended = 43" at every *pass-condition* site — Global Constraints (line 18), Task 3 Step 4 gate (line 497), Test Plan smoke (line 1196), Relight-regression (line 1202), and Done-gate (line 1206) — and the headline pass signal is now **"0 failed," with counts re-baselined via `pytest --co -q`**, never a magic integer. The grand total is given as ≈69 (9 falkit + 17 mediagen + 43 relight) and labelled approximate/re-baselineable. This is the correct fix for a suite that is growing underneath the plan.

- **Round-2 Issue 2 (fallback branch + scripts outside the gate) — FIXED and verified.** Task 3 Step 3 (lines 462-492) appends three tests:
  - `test_shim_exposes_public_api` — asserts all five public names survive.
  - `test_all_relight_scripts_import` — globs `scripts/*.py` and imports each in a subprocess. I reproduced this against the real tree: it resolves **9 modules** (`concat_video, extract_frame, lipsync_video, preflight, relight_batch, relight_common, relight_image, relight_video, split_video`) and prints `IMPORTS_OK`. This covers **`preflight.py`** — the script `install.ps1:36` tells a new user to run first — closing the round-2 gap where a shim break there was invisible to the gate. `grep -rl relight_common scripts/` confirms exactly 8 importers, all caught.
  - `test_fallback_runs_without_falkit` — runs a subprocess with `sys.modules['falkit']=None` then imports `relight_common` and asserts `estimate_image_cost('4K')==0.30`. **I verified the trick actually forces the `except ImportError` branch even when falkit is installed:** with `sys.modules['falkit']=None`, `from falkit.core import GuidedError` raises `ImportError: ... 'falkit' is not a package`. So the inline fallback (the round-1 graceful-degradation fix) is now genuinely executed under test, not merely asserted. This directly retires the round-2 hidden assumption that the fallback was a dead path (the old plan line 460 admitted only the present branch ran).

- **Gate language is consistent at every pass condition.** Every place that actually gates the merge (Task 3 Step 4, Test Plan smoke/regression/done-gate) reads "0 failed" + re-baseline-via-`--co`, with no leftover integer used *as a pass threshold*. The mediagen+falkit subtotal "26 passed" at Task 7 Step 4 (line 1066) is correct and is a *different* number (9 falkit + 3 + 3 + 5 + 6 = 26, mediagen-only run), not a stale relight count. The 26/27/53 figures elsewhere all sit inside the Review-log audit trail (Rounds 1–2), where they are historical records and belong.

- **Cost / resolver / approval architecture re-verified by re-running the arithmetic.** `_cost_video(3)=0.50`; `_cost_upscale(5,'1080')=0.10`; `output_res_tier(540,2)='1080'→0.10` vs `output_res_tier(540,4)='4K'→0.40`, so `four>two` holds and `factor` is no longer ignored. Image 2K=0.15 / 4K=0.30. The resolver (`override` wins → unknown-task `GuidedError` → tier lookup with `best` fallback) is sound. In both `image_to_video.run` and `upscale.run`, `if not approved: raise` fires **before** `load_fal_key`/upload/`subscribe`, so the dry-run and refuse-without-approval tests provably spend nothing.

- **Shim preserves Relight's historical economics.** The shim keeps `estimate_video_cost` at Relight's `0.169/s` (plan line 387), not the registry's `0.168`, so the existing `test_video_cost_scales_with_duration` (`0.169*4.5=0.76`, `0.169*10=1.69`) still passes. The two `load_fal_key` tests are correctly rewritten to `delenv FAL_KEY` + patch `falkit.core.shared_key_path` + patch `find_skill_root`, isolating them from the installer-seeded `~/.claude/fal.env`.

- **Installer ordering is correct and matches a real `install.ps1`.** ffmpeg → `pip install -e ./falkit` → mediagen requirements → relight requirements → link skills → seed `~/.claude/fal.env` → `python -c "import falkit"` verify. The editable install precedes the relight-requirements step, and the `import falkit` assertion is last, so a wrong-interpreter mismatch surfaces loudly. `relight/requirements.txt` and `.gitignore` both exist on disk, so the Task 9 edits (run relight reqs; append `fal.env`, `mediagen-outputs/`, `*.egg-info/`, `falkit/build/`, `__editable__.*`) integrate cleanly.

## Issues

None blocking. One trivial copy-edit to fold into the build (not a re-review trigger):

### Stale "26" in the Task 3 regression-note prose (cosmetic)
- **Problem:** Line 371 still reads: *"The claim is '26 relight tests still pass, 2 of them updated for shared-key precedence'."* That "26" is a stale figure from the round-1 framing and is factually 40.
- **Evidence:** Plan line 371 vs the re-baselined 40/43 used everywhere that gates the merge (lines 18, 497, 1196, 1202, 1206) and the verified collection of 40.
- **Impact:** Cosmetic only. This sentence is an explanatory aside about *why* 2 tests must be edited; it is **not** a pass condition and contradicts no gate. The actual gate (Task 3 Step 4) and all Test Plan pass signals are correctly "0 failed / 43 / re-baseline via `--co`". An implementer following the Steps and the Test Plan is never misled.
- **Correction:** During the build, change "26 relight tests still pass" → "40 relight tests still pass (0 failed)" at line 371 for consistency. Not worth another review round.

## Hidden assumptions

- **"The shim's fallback branch is now exercised."** — TRUE as verified above; the `sys.modules['falkit']=None` subprocess forces the `except ImportError` path even with falkit installed. The graceful-degradation guarantee is now earned, not asserted.
- **"All 8 relight scripts (incl. preflight.py) still import under the shim."** — Now gated by `test_all_relight_scripts_import` (covers 9 modules in a subprocess). Verified the glob/import harness runs green against the current tree.
- **"`nano-banana-pro/edit` is priced like generation."** — Still assumed (registry reuses `_cost_image` for `image_edit`). Acceptable: image tasks run un-gated and SKILL.md labels edit cost "approximate." Carried unchanged from round-1.
- **Endpoint response shapes** (`result["images"][0]["url"]`, `result["video"]["url"]`) — only exercised in the manual paid done-gate (Task 10), never in unit tests. Correct, since they require network; Task 10 stays mandatory before merge, as the plan requires.
- **Interpreter pinning** — handled: `install.ps1` echoes `sys.executable` and throws on `import falkit` failure. Holds as long as Claude Code runs scripts under the same `python` that ran the editable install; a mismatch fails the installer loudly.

## Blindspots

- **Count drift is now structurally defused.** The done-gate asserts "0 failed" and instructs re-baselining via `pytest --co -q`, so the number can't rot on the next revision the way it did across rounds 1→2. The one remaining literal "26" (line 371) is prose, not a gate. Recommend the implementer paste freshly-collected per-suite counts at build time rather than trusting any in-doc integer.
- **Fractional upscale factor** — `--factor` is `type=float`; `MAX_FACTOR=8` with strict `>` admits `8.0` and a value like `1.5` flows into `output_res_tier`/`build_request(upscale_factor=1.5)`. Whether Topaz accepts fractional factors is unverified. Minor — the approval gate always shows a (factor-aware) cost first. Acceptable for a single-user skill.
- **Same `out_path`, two runs** — the i2v *temp* compress name is now unique-per-output, but two invocations to the same final `out_path` still overwrite the artifact. Acknowledged minor in round-1; acceptable single-user.

## Recommended course of action

APPROVED — build it. The two round-2 defects (wrong relight baseline; untested fallback / `preflight.py` outside the gate) are genuinely fixed and were re-verified against the live codebase: relight collects 40, the import-smoke covers all 8 importers including `preflight.py`, and the `sys.modules['falkit']=None` subprocess provably forces the `except ImportError` branch. The model resolver, cost arithmetic, approval-before-spend ordering, dry-run-spends-nothing guards, installer ordering (falkit editable → reqs → link → seed → verify-import), and the mandatory manual paid done-gate are all coherent. The Test Plan exceeds the happy path (resolver, payload, cost, money-guard, compression boundary, relight regression incl. fallback branch, abuse/edge `GuidedError` cases, AI-output quality in the paid gate, per-bug regressions). Fold one cosmetic copy-edit into the build — change the stale "26 relight tests still pass" at line 371 to "40 ... (0 failed)" — but that is a build-time nit, not a blocker. Ship to the human checkpoint.
