import json
from pathlib import Path

import pytest

from scrambled import client as C
from scrambled import otoc

ROOT = Path(__file__).resolve().parents[1]


def test_cache_key_is_compatible_with_the_existing_cache():
    # known-good literal: the committed blur-v1 record was written by the original moth.py under this key
    rec = json.loads((ROOT / "cache" / "blur-v1" / "03c3679d2f3478fa.json").read_text(encoding="utf-8"))
    assert C.cache_key("blur-v1", rec["params"], rec["input_files"]) == "03c3679d2f3478fa"
    params = {"strength": 0.3, "reach": 0}
    assert C.cache_key("blur-v1", params, {"image": "a"}) != C.cache_key("blur-v1", params, {"image": "b"})


def test_replay_mode_needs_no_key_and_reads_the_cache(monkeypatch):
    monkeypatch.delenv("MOTH_API_KEY", raising=False)
    monkeypatch.setattr(C, "_load_key", lambda: "")
    monkeypatch.setattr(C.requests, "request", _no_network)
    cl = C.AtlasClient(mode="replay", cache_dir=ROOT / "cache")
    m = otoc.measure(otoc.OTOCParams(), mode="replay", client=cl)
    assert m.F.shape == (12, 32) and m.source == "atlas"
    assert cl.jobs == [("otoc-echo-v1", m.job_id, True)]


def test_replay_mode_miss_is_a_clear_error_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(C.requests, "request", _no_network)
    cl = C.AtlasClient(mode="replay", cache_dir=tmp_path)
    with pytest.raises(C.ReplayMiss):
        cl.run("otoc-echo-v1", {"depth": 3})
    img = tmp_path / "x.png"
    img.write_bytes(b"not really a png")
    with pytest.raises(C.ReplayMiss):
        cl.upload(img)


def test_atlas_mode_without_key_explains_how_to_run_offline(monkeypatch, tmp_path):
    monkeypatch.delenv("MOTH_API_KEY", raising=False)
    monkeypatch.setattr(C, "_load_key", lambda: "")
    cl = C.AtlasClient(mode="atlas", cache_dir=tmp_path)
    with pytest.raises(C.AtlasError, match="replay"):
        cl.run("otoc-echo-v1", {"depth": 3})


class FakeAPI:
    """Minimal stand-in for the Atlas HTTP API: a job that stays running, then completes."""

    def __init__(self, polls_until_done):
        self.polls_until_done = polls_until_done
        self.submitted = 0
        self.polls = 0
        self.result_calls = 0

    def __call__(self, method, url, headers=None, timeout=None, json=None, **kw):
        path = url.split("/api/v1", 1)[1]
        if path.startswith("/engines/") and path.endswith("/process"):
            self.submitted += 1
            return _Resp(202, {"job_id": "job-1", "status": "queued"})
        if path.startswith("/engines/"):
            return _Resp(200, {"params_schema": {"properties": {"depth": {}}}})
        if path.endswith("/status"):
            self.polls += 1
            return _Resp(200, {"status": "completed" if self.polls >= self.polls_until_done else "running"})
        if path.endswith("/result"):
            self.result_calls += 1
            if self.result_calls == 1:
                return _Resp(409, {"detail": "not ready"})
            return _Resp(200, {"result": {"ok": True}})
        raise AssertionError(path)


class _Resp:
    def __init__(self, code, body, headers=None):
        self.status_code = code
        self._body = body
        self.headers = headers or {}
        self.content = json.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        return self._body


def _no_network(*a, **k):
    raise AssertionError("network call in a test that must stay offline")


def test_timed_out_job_is_resumed_not_resubmitted(monkeypatch, tmp_path):
    api = FakeAPI(polls_until_done=5)
    monkeypatch.setattr(C.requests, "request", api)
    monkeypatch.setattr(C, "_load_key", lambda: "test-key")
    clock = iter(range(0, 10_000, 100))
    monkeypatch.setattr(C.time, "time", lambda: next(clock))
    cl = C.AtlasClient(mode="atlas", cache_dir=tmp_path, sleep=lambda s: None)
    with pytest.raises(C.JobTimeout) as e:
        cl.run("otoc-echo-v1", {"depth": 3}, timeout=150)
    assert e.value.job_id == "job-1" and api.submitted == 1
    rec = cl.run("otoc-echo-v1", {"depth": 3}, timeout=10_000)
    assert api.submitted == 1, "a pending job must be resumed, not paid for again"
    assert rec["job_id"] == "job-1" and rec["response"] == {"result": {"ok": True}}
    assert not list((tmp_path / "pending").rglob("*.json"))
    # third call is a pure cache hit
    monkeypatch.setattr(C.requests, "request", _no_network)
    assert cl.run("otoc-echo-v1", {"depth": 3})["job_id"] == "job-1"


def test_unknown_params_are_rejected_before_submitting(monkeypatch, tmp_path):
    api = FakeAPI(polls_until_done=1)
    monkeypatch.setattr(C.requests, "request", api)
    monkeypatch.setattr(C, "_load_key", lambda: "test-key")
    cl = C.AtlasClient(mode="atlas", cache_dir=tmp_path, sleep=lambda s: None)
    with pytest.raises(C.AtlasError, match="does not accept"):
        cl.run("otoc-echo-v1", {"depth": 3, "bogus": 1})
    assert api.submitted == 0


def test_expired_output_url_is_resigned_through_the_asset(monkeypatch, tmp_path):
    def api(method, url, **kw):
        assert url.endswith("/assets/out-1/download")
        return _Resp(200, {"download_url": "https://s3.example/fresh", "expires_at": "later"})

    def s3(url, timeout=None):
        r = _Resp(403 if url.endswith("stale") else 200, {})
        r.content = b"" if url.endswith("stale") else b"PNGDATA"
        return r

    monkeypatch.setattr(C.requests, "request", api)
    monkeypatch.setattr(C.requests, "get", s3)
    monkeypatch.setattr(C, "_load_key", lambda: "test-key")
    cl = C.AtlasClient(mode="atlas", cache_dir=tmp_path, sleep=lambda s: None)
    rec = {"engine_id": "blur-v1", "job_id": "abcdef1234", "response": {"outputs": [
        {"slot": "result", "output_asset_id": "out-1", "filename": "r.png", "url": "https://s3.example/stale"}]}}
    p = cl.fetch_outputs(rec)["result"]
    assert p.read_bytes() == b"PNGDATA" and p.name == "abcdef12_result_r.png"
    # now cached on disk: replay can read it
    assert C.AtlasClient(mode="replay", cache_dir=tmp_path).fetch_outputs(rec)["result"] == p


def test_rate_limit_is_retried(monkeypatch, tmp_path):
    calls = []

    def flaky(method, url, **kw):
        calls.append(url)
        return _Resp(429, {}, {"Retry-After": "1"}) if len(calls) < 3 else _Resp(200, {"engine_id": "x"})

    monkeypatch.setattr(C.requests, "request", flaky)
    monkeypatch.setattr(C, "_load_key", lambda: "test-key")
    slept = []
    cl = C.AtlasClient(mode="atlas", cache_dir=tmp_path, sleep=slept.append)
    assert cl.get("/engines/x") == {"engine_id": "x"}
    assert slept == [1.0, 1.0]
