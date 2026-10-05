"""M0: account check, engine schemas, and the two otoc-echo-v1 probes (scrambling vs Clifford control)."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

OUT = ROOT / "probes"
OUT.mkdir(exist_ok=True)


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2), encoding="utf-8")


me = moth.get("/me")
save("me.json", me)
print("me:", {k: me.get(k) for k in ("email", "credits", "credit_balance", "plan") if k in me} or list(me)[:10])

for eid in ("otoc-echo-v1", "retrocausal-echo-v1"):
    save(f"engine_{eid}.json", moth.get(f"/engines/{eid}"))
    print("schema saved:", eid)

base = {
    "depth": 32, "n_sites": 12, "min_tap_level": 0, "include_taps": True,
    "machine": "aer", "exact": True, "disorder": 0, "lattice": "chain", "kick": "Z",
    "theta_x": 0.9424777960769379, "theta_z": 0, "theta_zz": 1.0995574287564276,
    "via": "direct",
}
runs = {"scrambling": base, "control_clifford": {**base, "theta_zz": math.pi}}

for name, params in runs.items():
    rec = moth.run("otoc-echo-v1", params)
    save(f"otoc_{name}.json", rec)
    print(f"{name}: job {rec['job_id']} in {rec['seconds']}s")
