# MediaGen Skill + Shared `falkit` Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MediaGen Claude Code skill (text→image, image edit w/ references, image→video, video upscale on Fal AI) on top of a new shared `falkit` core that Relight also adopts, with baked-in model auto-selection so the user never names a model.

**Architecture:** A pip-installable `falkit/` package holds the Fal plumbing (`core.py`: key/env, upload, subscribe, cost, GuidedError) and the model registry (`models.py`: task→best-endpoint resolver + cost fns). MediaGen is four thin scripts over `falkit`. Relight's `relight_common.py` becomes a shim re-exporting `falkit` so its 26 tests keep passing. One shared `FAL_KEY` serves both skills.

**Tech Stack:** Python 3, pytest, `fal-client`, system `ffmpeg`/`ffprobe` (for the >10MB image compress + any probing), PowerShell installer.

## Global Constraints

- **Fal endpoints (pinned in `falkit/models.py`):** image=`fal-ai/nano-banana-pro`; image_edit=`fal-ai/nano-banana-pro/edit`; image_to_video=`fal-ai/kling-video/v3/pro/image-to-video`; upscale=`fal-ai/topaz/upscale/video`.
- **User never names a model.** Scripts resolve the model from the task via `resolve_model`. `--model`/`--tier` are optional power-user overrides, never required.
- **No paid call without** (a) a resolvable key AND (b) for `image_to_video`+`upscale`, explicit `--approved`. `--dry-run` spends nothing on every paid script.
- **Cost policy:** images run automatically (cheap); video + upscale show estimate + require approval.
- **Shared key precedence (`falkit.load_fal_key`):** `FAL_KEY` env → `~/.claude/fal.env` → skill-local `.env`. Sets `os.environ["FAL_KEY"]`.
- **Relight must not regress:** its existing 26 tests stay green after the shim refactor.
- **pip import name:** package `fal-client` imports as `fal_client`; our package is `falkit`.
- Scripts resolve paths relative to the script file, run from any CWD.

---

## File Structure

```
falkit/                                  shared core (NEW)
  pyproject.toml
  falkit/__init__.py                     re-exports public API
  falkit/core.py                         GuidedError, load_fal_key, upload_file, subscribe, cost helpers
  falkit/models.py                       REGISTRY, resolve_model, cost fns
  tests/test_core.py
  tests/test_models.py
.claude/skills/mediagen/                 NEW skill
  SKILL.md
  requirements.txt
  scripts/image_generate.py
  scripts/image_edit.py
  scripts/image_to_video.py
  scripts/upscale.py
  tests/test_image_generate.py
  tests/test_image_edit.py
  tests/test_image_to_video.py
  tests/test_upscale.py
.claude/skills/relight/scripts/relight_common.py   MODIFIED -> falkit shim
install.ps1                              MODIFIED -> pip install -e ./falkit + shared fal.env
fal.env.example                          NEW (shared key example)
```

---

### Task 1: `falkit` package scaffold + `core.py`

**Files:**
- Create: `falkit/pyproject.toml`, `falkit/falkit/__init__.py`, `falkit/falkit/core.py`
- Test: `falkit/tests/test_core.py`

**Interfaces (Produces):**
- `class GuidedError(Exception)`
- `load_fal_key() -> str` — precedence: `FAL_KEY` env → `~/.claude/fal.env` → `skill_env_path` arg if given. Sets `os.environ["FAL_KEY"]`. `GuidedError` if none.
- `shared_key_path() -> pathlib.Path` → `~/.claude/fal.env`
- `upload_file(path) -> str` and `subscribe(endpoint, arguments, with_logs=False) -> dict` — thin wrappers over `fal_client` (raise `GuidedError` if `fal_client` missing).
- `download(url, out_path) -> str`

- [ ] **Step 1: Write `pyproject.toml`**

`falkit/pyproject.toml`:
```toml
[project]
name = "falkit"
version = "0.1.0"
description = "Shared Fal AI core for Claude media skills (Relight, MediaGen)."
requires-python = ">=3.9"
dependencies = ["fal-client>=0.5.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["falkit"]
```

- [ ] **Step 2: Write the failing tests**

`falkit/tests/test_core.py`:
```python
import os, pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from falkit import core


def test_load_key_from_env_wins(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "env-key")
    assert core.load_fal_key() == "env-key"


def test_load_key_from_shared_file(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    shared = tmp_path / "fal.env"
    shared.write_text("FAL_KEY=shared-key\n", encoding="utf-8")
    monkeypatch.setattr(core, "shared_key_path", lambda: shared)
    assert core.load_fal_key() == "shared-key"
    assert os.environ["FAL_KEY"] == "shared-key"


def test_load_key_skill_local_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(core, "shared_key_path", lambda: tmp_path / "nope.env")
    local = tmp_path / ".env"
    local.write_text("FAL_KEY=local-key\n", encoding="utf-8")
    assert core.load_fal_key(skill_env_path=local) == "local-key"


def test_load_key_missing_raises_guided(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(core, "shared_key_path", lambda: tmp_path / "nope.env")
    with pytest.raises(core.GuidedError) as e:
        core.load_fal_key()
    assert "fal.env" in str(e.value)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest falkit/tests/test_core.py -v`
Expected: FAIL — `ModuleNotFoundError: falkit`.

- [ ] **Step 4: Implement `core.py` + `__init__.py`**

`falkit/falkit/core.py`:
```python
"""Shared Fal AI core: key loading, client wrappers, cost helpers."""
import os
import pathlib
import urllib.request

try:
    import fal_client
except ImportError:
    fal_client = None


class GuidedError(Exception):
    """Carries a user-facing remediation message."""


def shared_key_path() -> pathlib.Path:
    return pathlib.Path.home() / ".claude" / "fal.env"


def _parse_env(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _key_from_file(p: pathlib.Path):
    if p and p.exists():
        return _parse_env(p.read_text(encoding="utf-8")).get("FAL_KEY", "")
    return ""


def load_fal_key(skill_env_path=None) -> str:
    key = os.environ.get("FAL_KEY", "").strip()
    if not key:
        key = _key_from_file(shared_key_path()).strip()
    if not key and skill_env_path:
        key = _key_from_file(pathlib.Path(skill_env_path)).strip()
    if not key:
        raise GuidedError(
            f"No FAL_KEY found. Create {shared_key_path()} with a line "
            f"FAL_KEY=<your key from https://fal.ai/dashboard/keys>, or set the "
            f"FAL_KEY environment variable."
        )
    os.environ["FAL_KEY"] = key
    return key


def upload_file(path: str) -> str:
    if fal_client is None:
        raise GuidedError("fal-client not installed. Run install.ps1.")
    return fal_client.upload_file(path)


def subscribe(endpoint: str, arguments: dict, with_logs: bool = False) -> dict:
    if fal_client is None:
        raise GuidedError("fal-client not installed. Run install.ps1.")
    return fal_client.subscribe(endpoint, arguments=arguments, with_logs=with_logs)


def download(url: str, out_path: str) -> str:
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)
    return out_path
```

`falkit/falkit/__init__.py`:
```python
from .core import (
    GuidedError, load_fal_key, shared_key_path, upload_file, subscribe, download,
)
from .models import resolve_model, REGISTRY, estimate_cost

__all__ = [
    "GuidedError", "load_fal_key", "shared_key_path", "upload_file", "subscribe",
    "download", "resolve_model", "REGISTRY", "estimate_cost",
]
```
(Note: `__init__` imports `models`; Task 2 creates it. Until then, run `test_core.py` by importing `falkit.core` directly, as the test does — it does not import the package root.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest falkit/tests/test_core.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add falkit/pyproject.toml falkit/falkit/core.py falkit/tests/test_core.py
git commit -m "feat(falkit): shared Fal core (key precedence, client wrappers)"
```

---

### Task 2: Model registry + resolver — `falkit/models.py`

**Files:**
- Create: `falkit/falkit/models.py`
- Test: `falkit/tests/test_models.py`

**Interfaces (Produces):**
- `REGISTRY: dict` — task → `{"best": endpoint, "cheap": endpoint, "cost": callable}`.
- `resolve_model(task, tier="best", override=None) -> str` — endpoint string; `override` wins; unknown task → `GuidedError`.
- `estimate_cost(task, **kw) -> float` — dispatches to the task's cost fn (e.g. `n_images`, `resolution`, `duration_s`, `out_res`).

- [ ] **Step 1: Write the failing tests**

`falkit/tests/test_models.py`:
```python
import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from falkit import models as m
from falkit import core


def test_resolve_best_defaults():
    assert m.resolve_model("image") == "fal-ai/nano-banana-pro"
    assert m.resolve_model("image_edit") == "fal-ai/nano-banana-pro/edit"
    assert m.resolve_model("image_to_video") == "fal-ai/kling-video/v3/pro/image-to-video"
    assert m.resolve_model("upscale") == "fal-ai/topaz/upscale/video"


def test_cheap_tier_differs_for_video():
    assert m.resolve_model("image_to_video", tier="cheap") != m.resolve_model("image_to_video")


def test_override_wins():
    assert m.resolve_model("image", override="fal-ai/flux/dev") == "fal-ai/flux/dev"


def test_unknown_task_raises():
    with pytest.raises(core.GuidedError) as e:
        m.resolve_model("teleport")
    assert "image" in str(e.value)  # lists valid tasks


def test_cost_estimates():
    assert m.estimate_cost("image", resolution="2K") == 0.15
    assert m.estimate_cost("image", resolution="4K") == 0.30
    assert m.estimate_cost("image_to_video", duration_s=3) == 0.50   # round(0.168*3,2)
    assert m.estimate_cost("upscale", duration_s=5, out_res="1080") == 0.10  # round(0.02*5,2)
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest falkit/tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: falkit.models`.

- [ ] **Step 3: Implement `models.py`**

```python
"""Task -> best Fal model registry, resolver, and cost estimators."""
from .core import GuidedError


def _cost_image(resolution="2K", n_images=1, **_):
    per = 0.30 if resolution == "4K" else 0.15
    return round(per * n_images, 2)


def _cost_video(duration_s=5, **_):
    # Kling v3 Pro, audio off ~ $0.168/s (pinned; reported as approximate).
    return round(0.168 * float(duration_s), 2)


def _cost_upscale(duration_s=5, out_res="1080", **_):
    # Topaz: ~$0.01 <=720p, $0.02 <=1080p, $0.08 >1080p per second (pinned).
    rate = 0.01 if out_res in ("720", "720p") else (0.08 if out_res in ("4K", "2160") else 0.02)
    return round(rate * float(duration_s), 2)


REGISTRY = {
    "image": {
        "best": "fal-ai/nano-banana-pro",
        "cheap": "fal-ai/nano-banana",
        "cost": _cost_image,
    },
    "image_edit": {
        "best": "fal-ai/nano-banana-pro/edit",
        "cheap": "fal-ai/nano-banana/edit",
        "cost": _cost_image,
    },
    "image_to_video": {
        "best": "fal-ai/kling-video/v3/pro/image-to-video",
        "cheap": "fal-ai/kling-video/v3/standard/image-to-video",
        "cost": _cost_video,
    },
    "upscale": {
        "best": "fal-ai/topaz/upscale/video",
        "cheap": "fal-ai/topaz/upscale/video",
        "cost": _cost_upscale,
    },
}


def resolve_model(task: str, tier: str = "best", override: str | None = None) -> str:
    if override:
        return override
    if task not in REGISTRY:
        raise GuidedError(f"Unknown task '{task}'. Valid tasks: {', '.join(REGISTRY)}.")
    entry = REGISTRY[task]
    return entry.get(tier) or entry["best"]


def estimate_cost(task: str, **kw) -> float:
    if task not in REGISTRY:
        raise GuidedError(f"Unknown task '{task}'. Valid tasks: {', '.join(REGISTRY)}.")
    return REGISTRY[task]["cost"](**kw)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest falkit/tests/ -v`
Expected: 9 passed (4 core + 5 models).

- [ ] **Step 5: Install falkit editable + commit**

```bash
python -m pip install -e ./falkit
git add falkit/falkit/models.py falkit/falkit/__init__.py falkit/tests/test_models.py
git commit -m "feat(falkit): task->model registry, resolver, cost estimators"
```

---

### Task 3: Refactor `relight_common.py` → `falkit` shim (no regression)

**Files:**
- Modify: `.claude/skills/relight/scripts/relight_common.py`
- (verify) `.claude/skills/relight/tests/` — all must still pass.

**Interfaces:** `relight_common` keeps `GuidedError`, `load_fal_key`, `estimate_image_cost`, `estimate_video_cost`, `find_skill_root` — now backed by `falkit`.

- [ ] **Step 1: Rewrite `relight_common.py` as a shim**

```python
"""Backwards-compatible shim. The shared implementation now lives in `falkit`."""
import pathlib
from falkit.core import GuidedError as GuidedError
from falkit.core import load_fal_key as _falkit_load_fal_key
from falkit.models import estimate_cost


def find_skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def load_fal_key() -> str:
    # Prefer the shared key; fall back to relight's own .env for back-compat.
    return _falkit_load_fal_key(skill_env_path=find_skill_root() / ".env")


def estimate_image_cost(resolution: str) -> float:
    return estimate_cost("image", resolution=resolution)


def estimate_video_cost(duration_s: float) -> float:
    # Relight uses Kling O1 v2v (~$0.169/s); keep its historical rate, not the registry's.
    return round(0.169 * duration_s, 2)
```

- [ ] **Step 2: Run the full Relight suite**

Run: `python -m pytest .claude/skills/relight/tests/ -v`
Expected: 26 passed (unchanged). The `test_common.py` tests for `load_fal_key` use `monkeypatch.setattr(rc, "find_skill_root", ...)` and a local `.env`; since env `FAL_KEY` is unset in CI and the shared path won't exist, the skill-local fallback resolves — behavior preserved.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/relight/scripts/relight_common.py
git commit -m "refactor(relight): back relight_common with shared falkit core"
```

> If any relight test fails here, fix the shim (not the tests) until green before proceeding. The shared `load_fal_key` precedence must still let a skill-local `.env` resolve when env + shared file are absent.

---

### Task 4: `image_generate.py` (text → image)

**Files:**
- Create: `.claude/skills/mediagen/scripts/image_generate.py`, `.claude/skills/mediagen/requirements.txt`
- Test: `.claude/skills/mediagen/tests/test_image_generate.py`

**Interfaces (Produces):**
- `build_request(prompt, resolution="2K", n_images=1) -> dict` — `{prompt, num_images, resolution, output_format:"png"}`.
- `run(prompt, out_path, resolution="2K", tier="best", model=None, dry_run=False) -> dict` — resolves `image`, uploads nothing, calls Fal, downloads. `dry_run` → `{endpoint, payload, est_cost}` no spend.

- [ ] **Step 1: requirements.txt**

`.claude/skills/mediagen/requirements.txt`:
```
falkit
fal-client>=0.5.0
opencv-python>=4.9.0
pytest>=8.0.0
```
(`falkit` is satisfied by the editable install from Task 2.)

- [ ] **Step 2: Write the failing tests**

`.claude/skills/mediagen/tests/test_image_generate.py`:
```python
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import image_generate as ig


def _no_spend(monkeypatch):
    """Make any network/key use explode so dry-run is provably free.
    resolve_model/estimate_cost stay live (they are pure, no network)."""
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent or keyed!"))
    monkeypatch.setattr(ig.fal, "subscribe", boom)
    monkeypatch.setattr(ig.fal, "load_fal_key", boom)
    monkeypatch.setattr(ig.fal, "upload_file", boom)


def test_build_request_shape():
    r = ig.build_request("a dog as superman", resolution="4K")
    assert r["prompt"] == "a dog as superman"
    assert r["resolution"] == "4K"
    assert r["num_images"] == 1


def test_dry_run_resolves_model_no_spend(monkeypatch):
    _no_spend(monkeypatch)
    out = ig.run("a dog as superman", "out.png", resolution="2K", dry_run=True)
    assert out["endpoint"] == "fal-ai/nano-banana-pro"
    assert out["est_cost"] == 0.15
    assert out["payload"]["prompt"] == "a dog as superman"


def test_override_model(monkeypatch):
    _no_spend(monkeypatch)
    out = ig.run("x", "out.png", model="fal-ai/flux/dev", dry_run=True)
    assert out["endpoint"] == "fal-ai/flux/dev"
```

- [ ] **Step 3: Run to verify fail**

Run: `python -m pytest .claude/skills/mediagen/tests/test_image_generate.py -v`
Expected: FAIL — `ModuleNotFoundError: image_generate`.

- [ ] **Step 4: Implement `image_generate.py`**

```python
"""MediaGen: text -> image via the resolved best image model."""
import argparse, json, sys
import falkit as fal
from falkit import GuidedError

TASK = "image"


def build_request(prompt, resolution="2K", n_images=1) -> dict:
    return {"prompt": prompt, "num_images": n_images,
            "resolution": resolution, "output_format": "png"}


def run(prompt, out_path, resolution="2K", tier="best", model=None, dry_run=False) -> dict:
    endpoint = fal.resolve_model(TASK, tier=tier, override=model)
    payload = build_request(prompt, resolution)
    est = fal.estimate_cost(TASK, resolution=resolution)
    if dry_run:
        return {"endpoint": endpoint, "payload": payload, "est_cost": est}
    fal.load_fal_key()
    result = fal.subscribe(endpoint, payload)
    url = result["images"][0]["url"]
    fal.download(url, out_path)
    return {"endpoint": endpoint, "image": out_path, "remote_url": url, "est_cost": est}


def main():
    ap = argparse.ArgumentParser(description="Generate an image from a (pre-written) prompt.")
    ap.add_argument("prompt")
    ap.add_argument("--out", default="mediagen_image.png")
    ap.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"])
    ap.add_argument("--tier", default="best", choices=["best", "cheap"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        print(json.dumps(run(args.prompt, args.out, args.resolution, args.tier,
                             args.model, args.dry_run), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest .claude/skills/mediagen/tests/test_image_generate.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/mediagen/scripts/image_generate.py .claude/skills/mediagen/requirements.txt .claude/skills/mediagen/tests/test_image_generate.py
git commit -m "feat(mediagen): text->image with auto model selection + dry-run"
```

---

### Task 5: `image_edit.py` (images + references → edited image)

**Files:**
- Create: `.claude/skills/mediagen/scripts/image_edit.py`
- Test: `.claude/skills/mediagen/tests/test_image_edit.py`

**Interfaces (Produces):**
- `build_request(prompt, image_urls, resolution="2K") -> dict` — `{prompt, image_urls, resolution, num_images:1}`.
- `run(prompt, image_paths, out_path, resolution="2K", tier="best", model=None, dry_run=False) -> dict` — resolves `image_edit`; uploads each local path; `dry_run` returns payload with the LOCAL paths (no upload) + est_cost.

- [ ] **Step 1: Write the failing tests**

`.claude/skills/mediagen/tests/test_image_edit.py`:
```python
import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import image_edit as ie


def test_build_request_includes_all_refs():
    r = ie.build_request("make it Ronaldo", ["a.png", "b.png"])
    assert r["image_urls"] == ["a.png", "b.png"]
    assert r["num_images"] == 1


def test_dry_run_no_upload(monkeypatch):
    monkeypatch.setattr(ie.fal, "upload_file", lambda p: (_ for _ in ()).throw(AssertionError("uploaded!")))
    out = ie.run("make it Ronaldo", ["a.png", "b.png"], "out.png", dry_run=True)
    assert out["endpoint"] == "fal-ai/nano-banana-pro/edit"
    assert out["payload"]["image_urls"] == ["a.png", "b.png"]
    assert out["est_cost"] == 0.15


def test_requires_at_least_one_reference():
    with pytest.raises(Exception):
        ie.build_request("x", [])
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest .claude/skills/mediagen/tests/test_image_edit.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `image_edit.py`**

```python
"""MediaGen: edit/transform image(s) using reference image paths, identity-preserving."""
import argparse, json, sys
import falkit as fal
from falkit import GuidedError

TASK = "image_edit"


def build_request(prompt, image_urls, resolution="2K") -> dict:
    if not image_urls:
        raise GuidedError("image_edit needs at least one reference image path.")
    return {"prompt": prompt, "image_urls": list(image_urls),
            "resolution": resolution, "num_images": 1}


def run(prompt, image_paths, out_path, resolution="2K", tier="best", model=None, dry_run=False) -> dict:
    endpoint = fal.resolve_model(TASK, tier=tier, override=model)
    est = fal.estimate_cost(TASK, resolution=resolution)
    if dry_run:
        return {"endpoint": endpoint, "payload": build_request(prompt, image_paths, resolution), "est_cost": est}
    fal.load_fal_key()
    urls = [fal.upload_file(p) for p in image_paths]
    payload = build_request(prompt, urls, resolution)
    result = fal.subscribe(endpoint, payload)
    url = result["images"][0]["url"]
    fal.download(url, out_path)
    return {"endpoint": endpoint, "image": out_path, "remote_url": url, "est_cost": est}


def main():
    ap = argparse.ArgumentParser(description="Edit images using reference paths.")
    ap.add_argument("prompt")
    ap.add_argument("references", nargs="+")
    ap.add_argument("--out", default="mediagen_edit.png")
    ap.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"])
    ap.add_argument("--tier", default="best", choices=["best", "cheap"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        print(json.dumps(run(args.prompt, args.references, args.out, args.resolution,
                             args.tier, args.model, args.dry_run), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest .claude/skills/mediagen/tests/test_image_edit.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/mediagen/scripts/image_edit.py .claude/skills/mediagen/tests/test_image_edit.py
git commit -m "feat(mediagen): image edit with reference images + dry-run"
```

---

### Task 6: `image_to_video.py` (still → video, approval-gated, >10MB compress)

**Files:**
- Create: `.claude/skills/mediagen/scripts/image_to_video.py`
- Test: `.claude/skills/mediagen/tests/test_image_to_video.py`

**Interfaces (Produces):**
- `build_request(image_url, prompt, duration, with_audio=False) -> dict` — `{image_url, prompt, duration:str(round(duration)), ... }`. Raises `GuidedError` if duration not in 3–15.
- `needs_compression(path, cap_mb=10) -> bool` — pure: True if file > cap.
- `run(image_path, prompt, duration, out_path, with_audio=False, tier="best", model=None, dry_run=False, approved=False) -> dict` — resolves `image_to_video`; if `needs_compression`, compress to ≤10MB (ffmpeg/opencv) before upload, logging it; `dry_run` no spend; real run requires `approved`.

- [ ] **Step 1: Write the failing tests**

`.claude/skills/mediagen/tests/test_image_to_video.py`:
```python
import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import image_to_video as iv
import falkit
from falkit import GuidedError


def test_build_request_duration_and_prompt():
    r = iv.build_request("u", "a dog nods", 3)
    assert r["image_url"] == "u"
    assert r["duration"] == "3"
    assert r["prompt"] == "a dog nods"


def test_build_request_rejects_bad_duration():
    with pytest.raises(GuidedError):
        iv.build_request("u", "x", 20)


def test_needs_compression(tmp_path):
    small = tmp_path / "s.png"; small.write_bytes(b"0" * 1024)
    assert iv.needs_compression(str(small)) is False
    big = tmp_path / "b.png"; big.write_bytes(b"0" * (11 * 1024 * 1024))
    assert iv.needs_compression(str(big)) is True


def test_dry_run_spends_nothing(monkeypatch):
    monkeypatch.setattr(iv.fal, "subscribe", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent")))
    out = iv.run("img.png", "a dog nods", 3, "out.mp4", dry_run=True)
    assert out["endpoint"] == "fal-ai/kling-video/v3/pro/image-to-video"
    assert out["est_cost"] == 0.50  # round(0.168*3,2)


def test_real_run_refuses_without_approval(monkeypatch):
    monkeypatch.setattr(iv.fal, "subscribe", lambda *a, **k: {"video": {"url": "x"}})
    with pytest.raises(GuidedError) as e:
        iv.run("img.png", "x", 3, "out.mp4", dry_run=False, approved=False)
    assert "approv" in str(e.value).lower()
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest .claude/skills/mediagen/tests/test_image_to_video.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `image_to_video.py`**

```python
"""MediaGen: animate a still into a video (approval-gated, per-second priced)."""
import argparse, json, pathlib, shutil, subprocess, sys
import falkit as fal
from falkit import GuidedError

TASK = "image_to_video"
CAP_BYTES = 10 * 1024 * 1024


def build_request(image_url, prompt, duration, with_audio=False) -> dict:
    if not (3 <= duration <= 15):
        raise GuidedError(f"Kling v3 accepts 3-15s; got {duration}s.")
    return {"image_url": image_url, "prompt": prompt,
            "duration": str(round(duration)), "audio": bool(with_audio)}


def needs_compression(path, cap_bytes=CAP_BYTES) -> bool:
    return pathlib.Path(path).stat().st_size > cap_bytes


def _compress(path, out_path) -> str:
    if shutil.which("ffmpeg") is None:
        raise GuidedError("Image >10MB and ffmpeg not found to compress it. Run install.ps1.")
    subprocess.run(["ffmpeg", "-y", "-i", path, "-vf", "scale='min(2048,iw)':-2",
                    "-q:v", "4", out_path], capture_output=True, text=True, check=True)
    return out_path


def run(image_path, prompt, duration, out_path, with_audio=False, tier="best",
        model=None, dry_run=False, approved=False) -> dict:
    endpoint = fal.resolve_model(TASK, tier=tier, override=model)
    est = fal.estimate_cost(TASK, duration_s=duration)
    if dry_run:
        return {"endpoint": endpoint,
                "payload": build_request(image_path, prompt, duration, with_audio),
                "est_cost": est}
    if not approved:
        raise GuidedError("image_to_video not approved. Show the cost + prompt and confirm first.")
    fal.load_fal_key()
    upload_path = image_path
    if needs_compression(image_path):
        upload_path = str(pathlib.Path(out_path).with_name("_i2v_compressed.jpg"))
        _compress(image_path, upload_path)
        print(f"NOTE: image >10MB; compressed to {upload_path} for Kling.", file=sys.stderr)
    url = fal.upload_file(upload_path)
    payload = build_request(url, prompt, duration, with_audio)
    result = fal.subscribe(endpoint, payload, with_logs=True)
    vurl = result["video"]["url"]
    fal.download(vurl, out_path)
    return {"endpoint": endpoint, "video": out_path, "remote_url": vurl, "est_cost": est}


def main():
    ap = argparse.ArgumentParser(description="Animate a still into a video.")
    ap.add_argument("image"); ap.add_argument("prompt"); ap.add_argument("duration", type=float)
    ap.add_argument("--out", default="mediagen_video.mp4")
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--tier", default="best", choices=["best", "cheap"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved", action="store_true")
    args = ap.parse_args()
    try:
        print(json.dumps(run(args.image, args.prompt, args.duration, args.out,
                             args.audio, args.tier, args.model, args.dry_run, args.approved), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest .claude/skills/mediagen/tests/test_image_to_video.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/mediagen/scripts/image_to_video.py .claude/skills/mediagen/tests/test_image_to_video.py
git commit -m "feat(mediagen): image->video (approval gate, >10MB auto-compress, dry-run)"
```

---

### Task 7: `upscale.py` (any video → upscaled, approval-gated)

**Files:**
- Create: `.claude/skills/mediagen/scripts/upscale.py`
- Test: `.claude/skills/mediagen/tests/test_upscale.py`

**Interfaces (Produces):**
- `build_request(video_url, factor=2, target_fps=None) -> dict` — `{video_url, upscale_factor, ...}`.
- `run(video_path, out_path, factor=2, target_fps=None, duration_s=None, out_res="1080", tier="best", model=None, dry_run=False, approved=False) -> dict` — resolves `upscale`; `dry_run` no spend; real requires `approved`.

- [ ] **Step 1: Write the failing tests**

`.claude/skills/mediagen/tests/test_upscale.py`:
```python
import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import upscale as up
from falkit import GuidedError


def test_build_request_factor():
    r = up.build_request("v", factor=2)
    assert r["video_url"] == "v"
    assert r["upscale_factor"] == 2


def test_dry_run_spends_nothing(monkeypatch):
    monkeypatch.setattr(up.fal, "subscribe", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent")))
    out = up.run("in.mp4", "out.mp4", factor=2, duration_s=5, out_res="1080", dry_run=True)
    assert out["endpoint"] == "fal-ai/topaz/upscale/video"
    assert out["est_cost"] == 0.10  # round(0.02*5,2)


def test_real_run_refuses_without_approval(monkeypatch):
    monkeypatch.setattr(up.fal, "subscribe", lambda *a, **k: {"video": {"url": "x"}})
    with pytest.raises(GuidedError):
        up.run("in.mp4", "out.mp4", dry_run=False, approved=False)
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest .claude/skills/mediagen/tests/test_upscale.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `upscale.py`**

```python
"""MediaGen: upscale any video via Topaz on Fal (approval-gated)."""
import argparse, json, sys
import falkit as fal
from falkit import GuidedError

TASK = "upscale"


def build_request(video_url, factor=2, target_fps=None) -> dict:
    req = {"video_url": video_url, "upscale_factor": factor}
    if target_fps:
        req["target_fps"] = target_fps
    return req


def run(video_path, out_path, factor=2, target_fps=None, duration_s=None, out_res="1080",
        tier="best", model=None, dry_run=False, approved=False) -> dict:
    endpoint = fal.resolve_model(TASK, tier=tier, override=model)
    est = fal.estimate_cost(TASK, duration_s=duration_s or 0, out_res=out_res)
    if dry_run:
        return {"endpoint": endpoint, "payload": build_request(video_path, factor, target_fps), "est_cost": est}
    if not approved:
        raise GuidedError("upscale not approved. Show the cost and confirm first.")
    fal.load_fal_key()
    url = fal.upload_file(video_path)
    payload = build_request(url, factor, target_fps)
    result = fal.subscribe(endpoint, payload, with_logs=True)
    vurl = result["video"]["url"]
    fal.download(vurl, out_path)
    return {"endpoint": endpoint, "video": out_path, "remote_url": vurl, "est_cost": est}


def main():
    ap = argparse.ArgumentParser(description="Upscale a video via Topaz.")
    ap.add_argument("video")
    ap.add_argument("--out", default="mediagen_upscaled.mp4")
    ap.add_argument("--factor", type=float, default=2)
    ap.add_argument("--target-fps", type=int, default=None)
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--out-res", default="1080")
    ap.add_argument("--tier", default="best", choices=["best", "cheap"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approved", action="store_true")
    args = ap.parse_args()
    try:
        print(json.dumps(run(args.video, args.out, args.factor, args.target_fps, args.duration,
                             args.out_res, args.tier, args.model, args.dry_run, args.approved), indent=2))
    except GuidedError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run + full mediagen + falkit suite**

Run: `python -m pytest falkit/tests/ .claude/skills/mediagen/tests/ -v`
Expected: 23 passed (9 falkit + 3 image_generate + 3 image_edit + 5 image_to_video + 3 upscale).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/mediagen/scripts/upscale.py .claude/skills/mediagen/tests/test_upscale.py
git commit -m "feat(mediagen): video upscale via Topaz (approval gate, dry-run)"
```

---

### Task 8: `SKILL.md` orchestration (prompt rewriting, auto model, cost gates)

**Files:**
- Create: `.claude/skills/mediagen/SKILL.md`

**Interfaces:** None (doc). Encodes: prompt rewriting, invisible model selection, when to gate on cost.

- [ ] **Step 1: Write `SKILL.md`**

Frontmatter + body. Required content:
- Frontmatter `name: mediagen`, `description:` triggering on "generate an image", "make/edit an image", "animate this image", "turn this into a video", "upscale this video", referencing Fal/Nano Banana/Kling/Topaz — and noting the user does NOT need to name a model.
- **Model invisibility:** never ask the user which model; the scripts auto-resolve the best one. Only pass `--model`/`--tier` if the user explicitly insists.
- **Prompt rewriting:** for `image_generate`, expand the user's rough idea into a strong, detailed, model-appropriate prompt, then pass THAT to the script. Briefly show the user the rewritten prompt.
- **Run order per capability** (exact commands), with output to `<output_dir>/<slug>/`:
  - Image gen: `python scripts/image_generate.py "<rewritten prompt>" --out "<out>"` → show image + actual cost (no gate; cheap).
  - Image edit: `python scripts/image_edit.py "<prompt>" "<ref1>" ["<ref2>" ...] --out "<out>"` → show image + cost.
  - Image→video: FIRST `--dry-run` to get `est_cost`; present cost + prompt; on approval re-run with `--approved`.
  - Upscale: FIRST `--dry-run` (pass `--duration <probed secs>` + `--out-res`) for cost; on approval re-run `--approved`.
- **Offer the next step:** after an image, ask if they want to animate it; after a video, offer upscaling (mirrors Vic).
- **Key setup:** one shared key at `~/.claude/fal.env`; if MediaGen and Relight are both installed they share it. Never paste the key in chat.
- **Output dir rule:** `./mediagen-outputs/<slug>/` (CWD project), fallback `~/Documents/MediaGen/<slug>/`.
- **Cost transparency + error handling:** relay `ERROR:` lines verbatim; never run video/upscale without approval.

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/mediagen/SKILL.md
git commit -m "docs(mediagen): SKILL.md orchestration (prompt rewrite, invisible models, cost gates)"
```

---

### Task 9: Installer + shared key + README updates

**Files:**
- Modify: `install.ps1`
- Create: `fal.env.example`
- Modify: `.gitignore` (add `fal.env`, `mediagen-outputs/`), `README.md` (mention MediaGen + shared key)

**Interfaces:** None.

- [ ] **Step 1: Update `install.ps1`** — add, after the existing deps step:

```powershell
Write-Host "Installing shared falkit core (editable)..."
python -m pip install -e (Join-Path $PSScriptRoot "falkit")

Write-Host "Linking mediagen skill..."
$mgLink = Join-Path $userSkills "mediagen"
$mgSrc  = Join-Path $PSScriptRoot ".claude\skills\mediagen"
if (-not (Test-Path $mgLink)) {
    try { New-Item -ItemType SymbolicLink -Path $mgLink -Target $mgSrc | Out-Null; Write-Host "  Symlinked mediagen." }
    catch { Write-Warning "  Symlink failed; copying."; Copy-Item $mgSrc $mgLink -Recurse }
} else { Write-Host "  mediagen link exists." }

Write-Host "Seeding shared Fal key file..."
$falEnv = Join-Path $env:USERPROFILE ".claude\fal.env"
if (-not (Test-Path $falEnv)) {
    Copy-Item (Join-Path $PSScriptRoot "fal.env.example") $falEnv
    Write-Host "  Created $falEnv - edit it and paste your FAL_KEY (shared by all skills)."
} else { Write-Host "  $falEnv already exists." }
```

- [ ] **Step 2: Create `fal.env.example`**

```
# Shared Fal API key for all media skills (Relight, MediaGen).
# Get one at https://fal.ai/dashboard/keys
FAL_KEY=
```

- [ ] **Step 3: Update `.gitignore`** — append:
```
fal.env
mediagen-outputs/
falkit/falkit.egg-info/
```

- [ ] **Step 4: Update `README.md`** — add a "MediaGen" section: what it does (4 capabilities), that the user never names a model, the shared `~/.claude/fal.env` key, and that `install.ps1` now also installs `falkit` + links MediaGen. Note in the Claude-setup section that setup also covers MediaGen.

- [ ] **Step 5: Commit**

```bash
git add install.ps1 fal.env.example .gitignore README.md
git commit -m "feat(mediagen): installer (falkit editable, mediagen link, shared key) + README"
```

---

### Task 10: End-to-end done-gate (manual, paid)

**Files:** None (verification).

- [ ] **Step 1:** Run `install.ps1`; put a real `FAL_KEY` in `~/.claude/fal.env`; confirm both skills resolve the shared key.
- [ ] **Step 2 (image):** Generate an image from a rough idea (verify Claude rewrites the prompt, image saved, cost reported, no model named by the user).
- [ ] **Step 3 (edit):** Edit with a reference image (identity preserved).
- [ ] **Step 4 (video):** Animate a still — verify cost shown + approval required before spend; >10MB image auto-compresses.
- [ ] **Step 5 (upscale):** Upscale a clip — cost shown + approval; output visibly sharper.
- [ ] **Step 6:** Add a regression test for any defect found before declaring done.

---

## Test Plan

- **Smoke test:** `python -m pytest falkit/tests/ .claude/skills/mediagen/tests/ .claude/skills/relight/tests/ -q` → **49 passed** (9 falkit + 14 mediagen + 26 relight), no paid calls. Pass signal: all green, including the relight regression after the shim refactor.
- **Model-resolver tests:** task→endpoint for all four tasks; `tier="cheap"` differs for video; `override` wins; unknown task raises `GuidedError` listing valid tasks. This is the core of the "user never names a model" guarantee.
- **Payload-builder tests:** each `build_request` carries the resolved endpoint's required params (prompt; edit ref-image list; video duration string + 3–15s bound; upscale factor).
- **Cost-estimator tests:** `estimate_cost` returns expected values at known inputs (image 2K/4K; video per-second; upscale per-second by out-res), deterministic, no half-cent ambiguity.
- **Cost-safety / approval (the money guard):** every paid script spends nothing on `--dry-run`; `image_to_video` and `upscale` refuse the real run without `approved=True`; the dry-run guards assert `subscribe`/`load_fal_key`/`upload_file` are never called.
- **>10MB compression:** `needs_compression` true/false at the boundary (unit, no paid call); the compress path is exercised in the manual gate.
- **Relight regression:** the existing 26 relight tests pass unchanged after `relight_common.py` becomes a falkit shim — proves the shared-core refactor didn't break the shipped skill.
- **Abuse / edge:** missing key → `GuidedError` naming `~/.claude/fal.env`; unknown task/model → `GuidedError`; image_edit with zero references → `GuidedError`; video duration out of 3–15 → `GuidedError` before any call.
- **AI-output quality (manual done-gate, Task 10):** one real run of each capability judged on output quality + correct cost-gating, not just HTTP 200.
- **Known-bug regressions:** each defect from Task 10 gets a unit test.
- **Done-gate:** full unit suite (49) green + relight regression green + cost-safety green + one human-reviewed real run of all four capabilities (with approval gates firing on video/upscale) before merging the branch.
