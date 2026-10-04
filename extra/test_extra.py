"""Checks for hero/ and extra/: full params, job ids backed by cache records, no secrets or signed URLs.

Run:  .venv\\Scripts\\python -m pytest -q extra\\test_extra.py
"""
import glob
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def cache_ids(engine):
    return {json.loads(Path(f).read_text(encoding="utf-8"))["job_id"]
            for f in glob.glob(str(ROOT / "cache" / engine / "*.json"))}


def test_hero_png_is_the_engine_output_at_max_size():
    p = json.loads((ROOT / "hero" / "params.json").read_text(encoding="utf-8"))
    im = Image.open(ROOT / "hero" / "hero.png")
    assert im.format == "PNG" and im.size == (1024, 1024)
    idx = json.loads((ROOT / "hero" / "ladder" / "index.json").read_text(encoding="utf-8"))
    rung = next(r for r in idx["rungs"] if r.get("job_id") == p["job_id"])
    assert (ROOT / rung["file"]).read_bytes() == (ROOT / "hero" / "hero.png").read_bytes()
    assert p["job_id"] in cache_ids("blur-v1")


def test_hero_params_cover_every_schema_field():
    p = json.loads((ROOT / "hero" / "params.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "hero" / "blur-v1_schema.json").read_text(encoding="utf-8"))
    props = schema["params_schema"]["properties"]
    assert set(p["params_full"]) == set(props)
    for k, v in props.items():
        if k not in p["params_sent"]:
            assert p["params_full"][k] == v.get("default"), k
    assert p["params_full"]["size"] == props["size"]["maximum"]


def test_hero_strength_matches_measurement():
    import sys
    sys.path.insert(0, str(ROOT))
    import fmap
    F, _ = fmap.load_F(json.loads((ROOT / "probes" / "otoc_scrambling.json").read_text(encoding="utf-8")))
    p = json.loads((ROOT / "hero" / "params.json").read_text(encoding="utf-8"))
    assert abs(p["params_full"]["strength"] - (1 - np.abs(F)[:, 16:].mean())) < 0.01


def test_extra_job_ids_resolve_to_cache():
    t = json.loads((ROOT / "extra" / "tamagotchi" / "results.json").read_text(encoding="utf-8"))
    ids = cache_ids("tamagotchi-v1")
    assert len(t["echo"]) == 32 and all(e["job_id"] in ids for e in t["sweep"] + t["echo"])
    q = json.loads((ROOT / "extra" / "qpixl" / "results.json").read_text(encoding="utf-8"))
    ids = cache_ids("qpixl-v1")
    assert all(r["job_id"] in ids for r in q["runs"].values() if "rmse" in r)
    assert q["runs"]["aer"]["rmse"] < 0.05  # noiseless round trip must be close; noisy one may not
    d = json.loads((ROOT / "extra" / "qdrive" / "results.json").read_text(encoding="utf-8"))
    ids = cache_ids("qdrive-api-v1")
    assert len(d["steps"]) == 8 and all(s["job_id"] in ids for s in d["steps"])
    assert max(s["max_abs_err"] for s in d["steps"]) < 0.06


def test_extra_readme_lists_every_new_job_id():
    readme = (ROOT / "extra" / "README.md").read_text(encoding="utf-8")
    d = json.loads((ROOT / "extra" / "qdrive" / "results.json").read_text(encoding="utf-8"))
    q = json.loads((ROOT / "extra" / "qpixl" / "results.json").read_text(encoding="utf-8"))
    for jid in [s["job_id"] for s in d["steps"]] + [r["job_id"] for r in q["runs"].values() if "job_id" in r]:
        assert jid[:8] in readme, jid


def test_no_key_or_signed_url_in_hero_or_extra():
    bad = re.compile(rb"moth_[A-Za-z0-9]{10,}|X-Amz-Signature|X-Amz-Credential|X-Amz-Security-Token")
    hits = []
    for d in ("hero", "extra"):
        for f in (ROOT / d).rglob("*"):
            if f.is_file() and f.suffix.lower() in {".json", ".md", ".py", ".txt", ".brf", ".qasm"}:
                if bad.search(f.read_bytes()) and f.name != "test_extra.py":
                    hits.append(str(f))
    assert not hits, hits
