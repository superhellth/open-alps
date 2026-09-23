import json
from datetime import date

import common


class FakeResp:
    def __init__(self, obj):
        self._raw = json.dumps(obj).encode()

    def read(self, *a):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_request_json_ok_sets_user_agent():
    seen = {}

    def fake(req, timeout):
        seen["ua"] = req.get_header("User-agent")
        return FakeResp([1, 2])

    out = common.request_json("http://x", urlopen=fake, sleep=lambda s: None)
    assert out == {"ok": True, "body": [1, 2]}
    assert seen["ua"] == common.USER_AGENT


def test_request_json_retries_then_returns_error_record():
    calls = []

    def fake(req, timeout):
        calls.append(1)
        raise OSError("boom")

    out = common.request_json("http://x", urlopen=fake, sleep=lambda s: None)
    assert len(calls) == 3
    assert out["ok"] is False and "boom" in out["error"]


def test_fetch_cached_skips_ok_retries_error_and_refresh(tmp_path):
    p = tmp_path / "a.json"
    n = []

    def ok():
        n.append(1)
        return {"ok": True, "body": 1}

    assert common.fetch_cached(p, ok, sleep=lambda s: None) == "ok"
    assert common.fetch_cached(p, ok, sleep=lambda s: None) == "cached"
    assert common.fetch_cached(p, ok, refresh=True, sleep=lambda s: None) == "ok"
    assert len(n) == 2
    common.write_json(p, {"ok": False, "error": "x"})
    assert common.fetch_cached(p, ok, sleep=lambda s: None) == "ok"


def test_hut_scope_dedups_and_skips_null():
    feats = [
        {"properties": {"ohrsHutId": "73"}},
        {"properties": {"ohrsHutId": "73"}},
        {"properties": {"ohrsHutId": None}},
        {"properties": {"ohrsHutId": "5"}},
    ]
    assert common.hut_scope(feats) == [5, 73]


def test_fmt_date():
    assert common.fmt_date(date(2025, 5, 1)) == "01.05.2025"


def test_seasons():
    assert common.SEASONS[2025].end == date(2025, 10, 31)
    assert common.SEASONS[2026].end == date(2026, 9, 23)
    assert common.SEASONS[2026].fetch_end == date(2026, 10, 10)
