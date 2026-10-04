"""Minimal Moth Atlas API client with a content-addressed job cache."""
import hashlib
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

BASE = "https://api.mothquantum.com/api/v1"
ROOT = Path(__file__).parent
CACHE = ROOT / "cache"
MODE = os.environ.get("MODE", "atlas")  # atlas | replay


class MothError(RuntimeError):
    pass


def _key():
    key = os.environ.get("MOTH_API_KEY", "").strip()
    if not key:
        raise MothError("MOTH_API_KEY is not set (put it in .env)")
    return key


def _req(method, path, **kw):
    headers = {"Authorization": f"Bearer {_key()}"}
    for attempt in range(6):
        r = requests.request(method, BASE + path, headers=headers, timeout=60, **kw)
        if r.status_code != 429:
            break
        time.sleep(2 ** attempt)
    if r.status_code >= 400:
        raise MothError(f"{method} {path} -> {r.status_code}: {r.text[:2000]}")
    return r.json() if r.content else None


def get(path):
    return _req("GET", path)


MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".wav": "audio/wav", ".mp3": "audio/mpeg", ".json": "application/json"}


def upload(path):
    """Upload a file once (deduped by sha256 via cache/assets.json). Returns asset_id."""
    path = Path(path)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    index_path = CACHE / "assets.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    if digest in index:
        return index[digest]["asset_id"]
    if MODE == "replay":
        raise MothError(f"asset not uploaded in replay mode: {path}")
    a = _req("POST", "/assets", json={"filename": path.name, "content_type": MIME[path.suffix.lower()],
                                       "size_bytes": len(data)})
    up = a["upload"]
    r = requests.put(up["url"], data=data, headers=up.get("headers") or {}, timeout=300)
    if r.status_code >= 400:
        raise MothError(f"PUT upload {path.name} -> {r.status_code}: {r.text[:500]}")
    _req("POST", f"/assets/{a['asset_id']}/complete")
    index[digest] = {"asset_id": a["asset_id"], "file": path.name}
    CACHE.mkdir(exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return a["asset_id"]


def fetch_outputs(rec, dest_dir):
    """Download a job's file outputs into dest_dir (skips existing). Returns {slot: path}."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for o in (rec["response"] or {}).get("outputs") or []:
        name = f"{rec['job_id'][:8]}_{o['slot']}_{o.get('filename') or o['slot']}"
        p = dest_dir / name
        if not p.exists():
            r = requests.get(o["url"], timeout=300)
            if r.status_code == 410 or r.status_code == 403:
                dl = get(f"/assets/{o['output_asset_id']}/download")
                r = requests.get(dl["url"], timeout=300)
            r.raise_for_status()
            p.write_bytes(r.content)
        paths[o["slot"]] = p
    return paths


def cache_key(engine_id, params, input_files=None):
    blob = json.dumps({"e": engine_id, "p": params, "f": input_files or {}}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def run(engine_id, params, input_files=None, poll=3.0, max_poll=15.0, timeout=1800):
    """Submit a job (or return the cached result). Returns the cached record dict."""
    key = cache_key(engine_id, params, input_files)
    path = CACHE / engine_id / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if MODE == "replay":
        raise MothError(f"cache miss in replay mode: {engine_id} {key}")

    body = {"params": params}
    if input_files:
        body["input_files"] = input_files
    t0 = time.time()
    job = _req("POST", f"/engines/{engine_id}/process", json=body)
    job_id = job["job_id"]
    delay = poll
    while True:
        st = get(f"/jobs/{job_id}/status")
        state = st.get("status")
        if state == "completed":
            break
        if state in ("failed", "cancelled"):
            raise MothError(f"job {job_id} {state}: {json.dumps(st)[:2000]}")
        if time.time() - t0 > timeout:
            raise MothError(f"job {job_id} timed out locally after {timeout}s (state={state})")
        time.sleep(delay)
        delay = min(delay * 1.3, max_poll)
    result = get(f"/jobs/{job_id}/result")
    rec = {
        "engine_id": engine_id,
        "params": params,
        "input_files": input_files or {},
        "job_id": job_id,
        "seconds": round(time.time() - t0, 1),
        "response": result,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec
