"""Daisy-chain census: every Atlas engine with a completed job anywhere in the project -> core/ENGINES.md.

Ground truth is the content-addressed job cache (cache/<engine>/*.json, written by moth.run for every completed job)
plus job records that other parts of the project keep outside it (web/public/data/sprites.json, measurements/retro/).
Re-run at any time: python core/engines_census.py
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROLE = {
    "otoc-echo-v1": ("Measures the OTOC F(site, t): the data behind everything. Piece acts I-III, size study, "
                     "explorer, game levels, explainer, 3D egg crack timing, plugin tap maps.",
                     "measurements/raw/, probes/, web/public/data/, plugin/tools/measured.json"),
    "blur-v1": ("Quantum blur of photo A (whole eggs): the strip ladder for 'echo partly lost'; game sprites; "
                "Challenge 01 hero (strength = 1 - late mean |F|).",
                "renders/v2/index.json (blurR:*), out/piece/scrambled_piece_v3.mp4, web/public/data/ladder.json, "
                "hero/params.json, hero/ladder/index.json"),
    "telablur-v1": ("Quantum rotation morph photo A -> photo B (whole -> scrambled eggs): the strip ladder for "
                    "'echo erased'.", "renders/v2/index.json (telablur:*), out/piece/, web/public/data/ladder.json"),
    "qrc-midi-v1": ("Quantum reservoir re-sequences the seed melody derived from the cooking audio.",
                    "renders/core/midi/index.json, out/piece/scrambled_track.wav"),
    "blur-midi-v1": ("Quantum blur of that melody, one pass per act, strength/reach set from the act's measured F.",
                     "renders/core/midi/index.json, out/piece/track_manifest.json"),
    "blur-core-v1": ("Quantum blur of the 3D egg mesh's radius grid: the cracked interior.",
                     "three/engine_outputs/blurcore_*.json, three/README.md"),
    "entanglement-shader-v1": ("Quantum iridescent BSDF: the 3D egg's shell material.",
                               "three/engine_outputs/shader_9214cb9d/, three/README.md"),
    "tamagotchi-v1": ("Steane [[7,1,3]] QEC test: the measured OTOC disturbance of the 7 sites around the kick "
                      "as an idle error rate; error correction cannot undo the scrambling (toy mapping). "
                      "41 jobs in the figure + 6 probes.",
                      "extra/tamagotchi/qec_card.png, extra/tamagotchi/results.json"),
    "qpixl-v1": ("QPIXL quantum encoding of the measured |F(site, t)| map (aer and fake_fez noise model): "
                 "the poster's data band.",
                 "extra/qpixl/qpixl_compare.png, extra/poster/scrambled_poster.png"),
    "qdrive-api-v1": ("Compiles the measured scrambling front Re F(site, t), t = 0..7, into one 12-qubit "
                      "circuit per step (product state, <Z> within 0.042 of target).",
                      "extra/qdrive/front_circuits.png, extra/qdrive/out/"),
    "tessa-image-v1": ("Attempted for game sprites; every job ended in engine_timeout.",
                       "web/public/data/sprites.json, extra/README.md"),
    "retrocausal-echo-v1": ("Media engine that would render the measured tap map as audio. Submitted; the "
                            "jobs never completed (see status), so the track uses the documented local render.",
                            "measurements/retro/status.json, measurements/retro/status_log.jsonl"),
}


def from_cache():
    jobs = defaultdict(list)
    for d in sorted((ROOT / "cache").iterdir()):
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if rec.get("job_id"):
                jobs[d.name].append((rec["job_id"], rec.get("seconds"), str(p.relative_to(ROOT))))
    return jobs


def from_sprites(jobs):
    p = ROOT / "web" / "public" / "data" / "sprites.json"
    if not p.exists():
        return
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data.values() if isinstance(data, dict) else data
    for it in items:
        if isinstance(it, dict) and it.get("job_id") and not it.get("error"):
            engine = it.get("engine_id")
            if not engine:
                continue
            if it["job_id"] not in {j[0] for j in jobs[engine]}:
                jobs[engine].append((it["job_id"], None, str(p.relative_to(ROOT))))


def retro_status():
    p = ROOT / "measurements" / "retro" / "status.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    jobs = from_cache()
    from_sprites(jobs)
    retro = retro_status()
    done_retro = [j for j, s in retro.items() if s.get("status") == "completed"]
    for j in done_retro:
        jobs["retrocausal-echo-v1"].append((j, None, f"measurements/retro/{j[:8]}.json"))
    engines = [e for e in ROLE if jobs.get(e)] + [e for e in jobs if e not in ROLE]
    lines = ["# Atlas engines used in SCRAMBLED", "",
             "Generated by `core/engines_census.py` from the job cache (`cache/<engine>/*.json`, one file per "
             "completed job) and the project's own job records. Every engine below returned real output that the "
             "project uses. All quantum runs are on Moth Atlas; otoc-echo-v1 runs on the `aer` emulator "
             "(exact expectation values), not on QPU hardware.", "",
             f"**{len(engines)} engines with completed, used jobs.**", "",
             "| Engine | Completed jobs | What it does in the project | Evidence |", "|---|---|---|---|"]
    for e in engines:
        role, ev = ROLE.get(e, ("(used by another part of the project)", ""))
        js = jobs[e]
        ids = ", ".join(f"`{j[0][:8]}`" for j in js[:12]) + (f" … (+{len(js) - 12})" if len(js) > 12 else "")
        lines.append(f"| `{e}` | {len(js)}: {ids} | {role} | {ev} |")
    lines += ["", "## Attempted but not completed", ""]
    if "retrocausal-echo-v1" not in engines:
        role, ev = ROLE["retrocausal-echo-v1"]
        lines.append(f"- `retrocausal-echo-v1`: {role} Evidence: {ev}.")
        for j, s in retro.items():
            prog = s.get("progress") or {}
            lines.append(f"  - `{j}`: {s.get('status')}, last progress \"{prog.get('detail', '')}\" "
                         f"(step `{prog.get('step', '')}`), checked {s.get('checked')}.")
    lines += ["", "## Full job id list", ""]
    for e in engines:
        lines.append(f"<details><summary>{e} ({len(jobs[e])})</summary>\n")
        for j, sec, path in jobs[e]:
            lines.append(f"- `{j}`" + (f" ({sec} s)" if sec else "") + f" — `{path}`")
        lines.append("\n</details>\n")
    (ROOT / "core" / "ENGINES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(len(engines), "engines:", ", ".join(f"{e}={len(jobs[e])}" for e in engines))


if __name__ == "__main__":
    main()
