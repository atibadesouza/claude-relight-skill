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
