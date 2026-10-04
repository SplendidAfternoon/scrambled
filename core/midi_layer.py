"""MIDI layer: seed.mid -> qrc-midi-v1 (quantum reservoir re-sequencing) -> blur-midi-v1, one blur per act.

Per-act blur parameters come from the measured F map of that act's run:
    strength = scramble_strength(F)  (1 - late mean |F| off the kicked site), floored at 0.05
    reach    = spread_fraction(F)    (fraction of (site, t) cells the perturbation has reached)
So the control run barely blurs the melody, the low-theta_x run blurs it a little, the scrambling run smears it.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
import moth  # noqa: E402
from data import F_of, scramble_strength, spread_fraction  # noqa: E402

moth.MIME.setdefault(".mid", "audio/midi")
OUT = ROOT / "renders" / "core" / "midi"
QRC = {"length": 128, "bpm": 90, "quality": "moderate", "seed": 20261004, "variation": 0.9,
       "velocity": 96, "loop": True}
ACTS = {"control": "control_clifford_n12", "lowx": "lowx_n12", "scrambling": "scrambling_n12"}


def blur_params(run):
    F, ex = F_of(run)
    k = ex["kick_site"]
    return {"strength": round(max(0.05, scramble_strength(F, k)), 3),
            "reach": round(min(1.0, spread_fraction(F, k)), 3),
            "margin": 0.15, "threshold": 0.1, "qubits": 20, "resolution": 0}


def main(acts=ACTS):
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    seed = moth.upload(OUT / "seed.mid")
    rec = moth.run("qrc-midi-v1", QRC, {"midi": seed}, timeout=1800)
    qrc_path = moth.fetch_outputs(rec, OUT)
    qrc_file = qrc_path["result"]
    qrc_mid = OUT / "qrc.mid"
    qrc_mid.write_bytes(qrc_file.read_bytes())
    index["qrc"] = {"job_id": rec["job_id"], "params": QRC, "file": str(qrc_mid.relative_to(ROOT)),
                    "model": str(qrc_path["model"].relative_to(ROOT)), "seconds": rec["seconds"]}
    print("qrc", rec["job_id"], qrc_mid, flush=True)
    qrc_asset = moth.upload(qrc_mid)
    for act, run in acts.items():
        try:
            p = blur_params(run)
        except FileNotFoundError:
            print("skip", act, "(no measured run yet)", flush=True)
            continue
        r = moth.run("blur-midi-v1", p, {"midi": qrc_asset}, timeout=1800)
        paths = moth.fetch_outputs(r, OUT / act)
        f = next(iter(paths.values()))
        index[act] = {"job_id": r["job_id"], "run": run, "params": p, "file": str(f.relative_to(ROOT)),
                      "seconds": r["seconds"]}
        print(act, r["job_id"], p, flush=True)
    old = json.loads((OUT / "index.json").read_text(encoding="utf-8")) if (OUT / "index.json").exists() else {}
    old.update(index)
    (OUT / "index.json").write_text(json.dumps(old, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main({a: ACTS[a] for a in sys.argv[1:]} if len(sys.argv) > 1 else ACTS)
