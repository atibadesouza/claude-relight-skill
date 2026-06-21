import sys, pathlib
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import heygen_common as hc
import relight_common as rc


def test_load_key_from_env(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "sk_test_123")
    assert hc.load_heygen_key() == "sk_test_123"


def test_load_key_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    monkeypatch.setattr(hc.pathlib.Path, "home", lambda: tmp_path)  # empty home, no heygen.env
    with pytest.raises(rc.GuidedError):
        hc.load_heygen_key()


def test_headers_sets_api_key_and_content_type():
    h = hc.headers("k", "application/json")
    assert h["X-Api-Key"] == "k"
    assert h["Content-Type"] == "application/json"
    assert "Content-Type" not in hc.headers("k")


def test_check_credit_error_raises_on_insufficient():
    with pytest.raises(rc.GuidedError) as e:
        hc.check_credit_error({"status": "failed", "message": "Insufficient credit. This operation requires 'api' credits."})
    assert "credit" in str(e.value).lower()


def test_check_credit_error_silent_when_fine():
    hc.check_credit_error({"status": "processing"})   # no raise
    hc.check_credit_error({})                          # no raise


class _Resp:
    """Minimal stand-in for a requests.Response."""
    content = b"x"
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


def test_parse_data_returns_data_dict():
    assert hc._parse_data(_Resp({"data": {"url": "u"}})) == {"url": "u"}


def test_parse_data_missing_data_raises_guided_not_keyerror():
    with pytest.raises(rc.GuidedError):                       # NOT KeyError
        hc._parse_data(_Resp({"error": "bad input"}))


def test_parse_data_credit_error_in_envelope_raises():
    with pytest.raises(rc.GuidedError) as e:
        hc._parse_data(_Resp({"message": "Insufficient credit. This operation requires 'api' credits."}))
    assert "credit" in str(e.value).lower()


def test_get_status_raises_guided_on_http_error(monkeypatch):
    class _R:
        status_code = 401
        text = "unauthorized"
    monkeypatch.setattr(hc.requests, "get", lambda *a, **k: _R())
    with pytest.raises(rc.GuidedError):
        hc.get_status("k", "vid")


import heygen_avatar as ha


def test_audio_extract_cmd_makes_mp3():
    cmd = ha.audio_extract_cmd("clip.mp4", "a.mp3")
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert "libmp3lame" in cmd
    assert cmd[-1] == "a.mp3"


def test_aspect_to_dimension_square_caps_to_1080():
    assert ha.aspect_to_dimension(1440, 1440) == {"width": 1080, "height": 1080}


def test_aspect_to_dimension_landscape_1080p():
    assert ha.aspect_to_dimension(1920, 1080) == {"width": 1920, "height": 1080}


def test_aspect_to_dimension_no_upscale():
    assert ha.aspect_to_dimension(720, 720) == {"width": 720, "height": 720}


def test_aspect_to_dimension_even_dimensions():
    d = ha.aspect_to_dimension(1441, 1080)   # odd width in -> even out
    assert d["width"] % 2 == 0 and d["height"] % 2 == 0


def test_aspect_to_dimension_preserves_ratio_and_caps_short_side():
    d = ha.aspect_to_dimension(1170, 2532)   # phone portrait, non-trivial ratio
    assert min(d["width"], d["height"]) <= 1080            # short side capped
    assert abs(d["width"] / d["height"] - 1170 / 2532) < 0.01   # ratio preserved


def test_build_generate_request_shape():
    req = ha.build_generate_request("tp123", "https://a/audio.mp3", {"width": 1080, "height": 1080}, "My Title")
    assert req["use_avatar_iv_model"] is True
    assert req["dimension"] == {"width": 1080, "height": 1080}
    vi = req["video_inputs"][0]
    assert vi["character"] == {"type": "talking_photo", "talking_photo_id": "tp123"}
    assert vi["voice"] == {"type": "audio", "audio_url": "https://a/audio.mp3"}
    assert req["test"] is False


def test_estimate_avatar_cost_four_dollars_per_minute():
    assert ha.estimate_avatar_cost(60.0) == 4.00
    assert ha.estimate_avatar_cost(30.0) == 2.00
    assert ha.estimate_avatar_cost(54.0) == 3.60


def test_dry_run_spends_nothing_no_approval(monkeypatch):
    monkeypatch.setattr(ha, "probe_duration", lambda p: 54.0)
    monkeypatch.setattr(ha, "probe_dimensions", lambda p: (1440, 1440))
    out = ha.run("clip.mp4", "still.png", "out.mp4", dry_run=True)
    assert out["endpoint"].endswith("/v2/video/generate")
    assert out["est_cost"] == 3.60
    assert out["payload"]["dimension"] == {"width": 1080, "height": 1080}
    assert out["payload"]["use_avatar_iv_model"] is True


def test_real_run_refuses_without_approval(monkeypatch):
    monkeypatch.setattr(ha, "probe_duration", lambda p: 30.0)
    monkeypatch.setattr(ha, "probe_dimensions", lambda p: (1080, 1080))
    with pytest.raises(rc.GuidedError) as e:
        ha.run("clip.mp4", "still.png", "out.mp4", dry_run=False, approved=False)
    assert "approv" in str(e.value).lower()


def test_poll_raises_on_credit_error(monkeypatch):
    monkeypatch.setattr(hc, "get_status",
                        lambda key, vid: {"status": "failed", "message": "Insufficient credit. This operation requires 'api' credits."})
    with pytest.raises(rc.GuidedError) as e:
        ha.poll_until_done("k", "vid", "out.mp4", interval=0, max_tries=1)
    assert "credit" in str(e.value).lower()


def test_poll_raises_on_plain_failure(monkeypatch):
    monkeypatch.setattr(hc, "get_status",
                        lambda key, vid: {"status": "failed", "error": "bad input"})
    with pytest.raises(rc.GuidedError):
        ha.poll_until_done("k", "vid", "out.mp4", interval=0, max_tries=1)


def test_verify_nonempty_raises_on_zero_byte(tmp_path):
    f = tmp_path / "x.mp4"; f.write_bytes(b"")
    with pytest.raises(rc.GuidedError) as e:
        ha._verify_nonempty(str(f), "https://recover/url")
    assert "recover" in str(e.value).lower() or "empty" in str(e.value).lower()


def test_verify_nonempty_ok_on_real_bytes(tmp_path):
    f = tmp_path / "x.mp4"; f.write_bytes(b"abc")
    ha._verify_nonempty(str(f), "https://recover/url")   # no raise
