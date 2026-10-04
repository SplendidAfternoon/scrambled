"""Moth Atlas API client with a content-addressed job cache.

Every job is keyed by sha256(engine_id, params, input asset ids), so re-running a command never pays twice and a
cache directory can be replayed later without an API key (``mode="replay"``). Uploads are deduplicated by file
sha256, downloaded outputs are kept next to the job records, and a job that outlives its local timeout is
remembered as *pending* so the next call resumes polling it instead of submitting (and paying for) a new one.

The cache layout is compatible with the repo's original ``moth.py``::

    cache/assets.json                 sha256 -> asset_id
    cache/<engine_id>/<key>.json      completed job record (params, job_id, seconds, response)
    cache/pending/<engine_id>/<key>.json   submitted-but-unfinished job id
    cache/files/<engine_id>/...       downloaded output files
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import requests

BASE = "https://api.mothquantum.com/api/v1"
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg",
        ".json": "application/json"}
RETRY_STATUS = {429, 500, 502, 503, 504}


class AtlasError(RuntimeError):
    pass


class ReplayMiss(AtlasError):
    """The requested job or file is not in the cache and replay mode forbids network calls."""


class JobTimeout(AtlasError):
    def __init__(self, message, job_id):
        super().__init__(message)
        self.job_id = job_id


def cache_key(engine_id, params, input_files=None):
    blob = json.dumps({"e": engine_id, "p": params, "f": input_files or {}}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _load_key():
    key = os.environ.get("MOTH_API_KEY", "").strip()
    if key:
        return key
    try:
        from dotenv import dotenv_values, find_dotenv
        path = find_dotenv(usecwd=True)
        if path:
            return (dotenv_values(path).get("MOTH_API_KEY") or "").strip()
    except ImportError:
        pass
    return ""


class AtlasClient:
    def __init__(self, mode="atlas", cache_dir=None, base=BASE, log=None, sleep=time.sleep):
        if mode not in ("atlas", "replay"):
            raise ValueError(f"AtlasClient mode must be atlas or replay, not {mode!r}")
        self.mode = mode
        self.cache = Path(cache_dir or os.environ.get("SCRAMBLED_CACHE") or "cache")
        self.base = base
        self.log = log or (lambda msg: None)
        self._sleep = sleep
        self._key = None
        self._schemas = {}
        self.jobs = []  # (engine_id, job_id, cached: bool) for every run() call, for reporting

    # -- HTTP ---------------------------------------------------------------------------------------------------
    def _headers(self):
        if self.mode == "replay":
            raise ReplayMiss("network call attempted in replay mode")
        if self._key is None:
            self._key = _load_key()
        if not self._key:
            raise AtlasError("MOTH_API_KEY is not set (environment or .env). Use --mode replay or --mode classical "
                             "to run without a key.")
        return {"Authorization": f"Bearer {self._key}"}

    def _req(self, method, path, ok=(), **kw):
        headers = self._headers()
        r = None
        for attempt in range(7):
            try:
                r = requests.request(method, self.base + path, headers=headers, timeout=60, **kw)
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt == 6:
                    raise AtlasError(f"{method} {path}: {type(e).__name__}") from None
                self._sleep(min(2 ** attempt, 30))
                continue
            if r.status_code not in RETRY_STATUS:
                break
            wait = r.headers.get("Retry-After")
            self._sleep(float(wait) if wait and wait.replace(".", "", 1).isdigit() else min(2 ** attempt, 30))
        if r.status_code in ok:
            return r
        if r.status_code >= 400:
            raise AtlasError(f"{method} {path} -> {r.status_code}: {r.text[:1500]}")
        return r

    def get(self, path):
        r = self._req("GET", path)
        return r.json() if r.content else None

    # -- schema checks ------------------------------------------------------------------------------------------
    def engine(self, engine_id):
        if engine_id not in self._schemas:
            self._schemas[engine_id] = self.get(f"/engines/{engine_id}")
        return self._schemas[engine_id]

    def check_params(self, engine_id, params):
        """Validate param names against the live engine schema (unknown params would be a 422)."""
        if self.mode == "replay":
            return
        props = (self.engine(engine_id).get("params_schema") or {}).get("properties") or {}
        unknown = sorted(set(params) - set(props))
        if unknown:
            raise AtlasError(f"{engine_id} does not accept params {unknown}; live schema has {sorted(props)}")

    # -- assets -------------------------------------------------------------------------------------------------
    def upload(self, path):
        """Upload a file once (deduplicated by sha256). Returns its asset_id."""
        path = Path(path)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        index_path = self.cache / "assets.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
        if digest in index:
            return index[digest]["asset_id"]
        if self.mode == "replay":
            raise ReplayMiss(f"{path.name} was never uploaded; cannot replay jobs that use it")
        ctype = MIME.get(path.suffix.lower())
        if not ctype:
            raise AtlasError(f"unsupported upload type {path.suffix}")
        a = self._req("POST", "/assets", json={"filename": path.name, "content_type": ctype,
                                                "size_bytes": len(data)}).json()
        up = a["upload"]
        r = requests.put(up["url"], data=data, headers=up.get("headers") or {}, timeout=300)
        if r.status_code >= 400:
            raise AtlasError(f"PUT upload {path.name} -> {r.status_code}: {r.text[:500]}")
        self._req("POST", f"/assets/{a['asset_id']}/complete")
        index[digest] = {"asset_id": a["asset_id"], "file": path.name}
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        self.log(f"uploaded {path.name} -> asset {a['asset_id']}")
        return a["asset_id"]

    def fetch_outputs(self, rec, dest_dir=None):
        """Download a job's file outputs (skipping files already on disk). Returns {slot: Path}."""
        dest = Path(dest_dir) if dest_dir else self.cache / "files" / rec["engine_id"]
        paths = {}
        for o in (rec["response"] or {}).get("outputs") or []:
            p = dest / f"{rec['job_id'][:8]}_{o['slot']}_{o.get('filename') or o['slot']}"
            if not p.exists():
                if self.mode == "replay":
                    raise ReplayMiss(f"output file {p} is not in the cache")
                r = requests.get(o["url"], timeout=300)
                if r.status_code in (403, 404, 410):  # presigned URL expired: re-sign through the asset
                    dl = self.get(f"/assets/{o['output_asset_id']}/download")
                    r = requests.get(dl.get("download_url") or dl["url"], timeout=300)
                if r.status_code >= 400:
                    raise AtlasError(f"download {o['slot']} of job {rec['job_id']} -> {r.status_code}")
                dest.mkdir(parents=True, exist_ok=True)
                p.write_bytes(r.content)
            paths[o["slot"]] = p
        return paths

    # -- jobs ---------------------------------------------------------------------------------------------------
    def cached(self, engine_id, params, input_files=None):
        path = self.cache / engine_id / f"{cache_key(engine_id, params, input_files)}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def run(self, engine_id, params, input_files=None, timeout=900, poll=3.0, max_poll=15.0):
        """Submit a job, or return its cached record. Raises JobTimeout (job stays resumable) after ``timeout`` s."""
        key = cache_key(engine_id, params, input_files)
        path = self.cache / engine_id / f"{key}.json"
        if path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
            self.jobs.append((engine_id, rec["job_id"], True))
            return rec
        if self.mode == "replay":
            raise ReplayMiss(f"cache miss in replay mode: {engine_id} {key}")

        pending = self.cache / "pending" / engine_id / f"{key}.json"
        if pending.exists():
            job_id = json.loads(pending.read_text(encoding="utf-8"))["job_id"]
            self.log(f"{engine_id}: resuming pending job {job_id}")
        else:
            self.check_params(engine_id, params)
            body = {"params": params}
            if input_files:
                body["input_files"] = input_files
            job_id = self._req("POST", f"/engines/{engine_id}/process", json=body).json()["job_id"]
            pending.parent.mkdir(parents=True, exist_ok=True)
            pending.write_text(json.dumps({"job_id": job_id, "params": params, "input_files": input_files or {},
                                           "submitted": time.time()}), encoding="utf-8")
            self.log(f"{engine_id}: submitted job {job_id}")

        t0 = time.time()
        delay = poll
        while True:
            st = self.get(f"/jobs/{job_id}/status")
            state = st.get("status")
            if state == "completed":
                break
            if state in ("failed", "cancelled"):
                pending.unlink(missing_ok=True)
                raise AtlasError(f"{engine_id} job {job_id} {state}: {json.dumps(st.get('error') or st)[:1500]}")
            if time.time() - t0 > timeout:
                raise JobTimeout(f"{engine_id} job {job_id} still {state} after {timeout}s "
                                 f"(it stays pending; re-run to resume)", job_id)
            self._sleep(delay)
            delay = min(delay * 1.3, max_poll)

        for _ in range(10):  # 409 right after completion = result not yet visible
            r = self._req("GET", f"/jobs/{job_id}/result", ok=(409, 410))
            if r.status_code == 410:
                pending.unlink(missing_ok=True)
                raise AtlasError(f"{engine_id} job {job_id}: result no longer retrievable (410)")
            if r.status_code != 409:
                break
            self._sleep(2)
        else:
            raise AtlasError(f"{engine_id} job {job_id}: result still 409 after completion")
        rec = {"engine_id": engine_id, "params": params, "input_files": input_files or {}, "job_id": job_id,
               "seconds": round(time.time() - t0, 1), "response": r.json()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        pending.unlink(missing_ok=True)
        self.jobs.append((engine_id, job_id, False))
        return rec
