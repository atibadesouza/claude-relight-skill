import os
import subprocess
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import relight_common as rc

try:
    import falkit.core as _falkit_core
except ImportError:
    _falkit_core = None


def test_image_cost_table():
    assert rc.estimate_image_cost("1K") == 0.15
    assert rc.estimate_image_cost("4K") == 0.30


def test_video_cost_scales_with_duration():
    assert rc.estimate_video_cost(4.5) == 0.76  # round(0.169*4.5,2)
    assert rc.estimate_video_cost(10) == 1.69


def test_load_fal_key_missing_raises_guided(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    if _falkit_core is not None:
        monkeypatch.setattr(_falkit_core, "shared_key_path", lambda: tmp_path / "nope.env")
    monkeypatch.setattr(rc, "find_skill_root", lambda: tmp_path)
    (tmp_path / ".env").write_text("FAL_KEY=\n", encoding="utf-8")
    with pytest.raises(rc.GuidedError):
        rc.load_fal_key()


def test_load_fal_key_present(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    if _falkit_core is not None:
        monkeypatch.setattr(_falkit_core, "shared_key_path", lambda: tmp_path / "nope.env")
    monkeypatch.setattr(rc, "find_skill_root", lambda: tmp_path)
    (tmp_path / ".env").write_text("FAL_KEY=abc123\n", encoding="utf-8")
    assert rc.load_fal_key() == "abc123"
    assert os.environ["FAL_KEY"] == "abc123"


def test_shim_exposes_public_api():
    for name in ("GuidedError", "load_fal_key", "estimate_image_cost", "estimate_video_cost", "find_skill_root"):
        assert hasattr(rc, name)


def test_all_relight_scripts_import():
    scripts = pathlib.Path(__file__).resolve().parents[1] / "scripts"
    mods = [p.stem for p in scripts.glob("*.py") if p.stem != "__init__"]
    code = (f"import sys; sys.path.insert(0, r'{scripts}');"
            + "".join(f"import {m};" for m in mods) + "print('IMPORTS_OK')")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "IMPORTS_OK" in out.stdout, out.stderr


def test_fallback_runs_without_falkit():
    # Force `import falkit` to fail, then prove the inline fallback still works.
    scripts = pathlib.Path(__file__).resolve().parents[1] / "scripts"
    code = ("import sys; sys.modules['falkit']=None;"
            f"sys.path.insert(0, r'{scripts}');"
            "import relight_common as rc;"
            "assert rc.estimate_image_cost('4K')==0.30;"
            "assert hasattr(rc,'load_fal_key');"
            "print('FALLBACK_OK')")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "FALLBACK_OK" in out.stdout, out.stderr
