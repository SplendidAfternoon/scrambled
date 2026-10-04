"""Acceptance checks for the explainer outputs. Run after make_explainer.py: .venv\\Scripts\\python edu\\check_outputs.py"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

EDU = Path(__file__).resolve().parent
sys.path.insert(0, str(EDU))
import make_explainer as m  # noqa: E402  (import re-checks F == (X+iY)_kick / (X+iY)_ref for both datasets)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main():
    fails = []
    durs = {}
    for name in ("scrambled_explained.mp4", "scrambled_explained_vo.mp4"):
        p = EDU / "out" / name
        if not p.exists():
            fails.append(f"missing {p}")
            continue
        info = probe(p)
        v = [s for s in info["streams"] if s["codec_type"] == "video"]
        a = [s for s in info["streams"] if s["codec_type"] == "audio"]
        durs[name] = float(info["format"]["duration"])
        if not (v and v[0]["codec_name"] == "h264" and v[0]["width"] == 1920 and v[0]["height"] == 1080
                and v[0]["r_frame_rate"] == "30/1"):
            fails.append(f"{name}: video stream {v}")
        if not (a and a[0]["codec_name"] == "aac"):
            fails.append(f"{name}: audio stream {a}")
        if not 90 <= durs[name] <= 150:
            fails.append(f"{name}: duration {durs[name]:.1f} s outside 90-150")
    if len(durs) == 2 and abs(durs["scrambled_explained.mp4"] - durs["scrambled_explained_vo.mp4"]) > 0.1:
        fails.append(f"durations differ {durs}")

    beats = m.parse_script()
    n_lines = sum(len(b["lines"]) for b in beats)
    srt = (EDU / "out" / "scrambled_explained.srt").read_text(encoding="utf-8")
    n_cues = srt.count(" --> ")
    if n_cues != n_lines:
        fails.append(f"srt cues {n_cues} != narration lines {n_lines}")

    tl = json.loads((EDU / "build" / "timeline.json").read_text(encoding="utf-8"))
    for b in tl["beats"]:
        if b["cues"][-1][1] > b["dur"]:
            fails.append(f"beat {b['n']}: narration overruns beat")

    vo, sr = sf.read(EDU / "vo_placeholder.wav")
    voiced = float((np.abs(vo) > 0.01).mean())
    if sr != 48000 or voiced < 0.3:
        fails.append(f"vo_placeholder.wav sr={sr} voiced fraction {voiced:.2f}")

    for f in ("script.md", "NOTES.md", "out/contact_sheet.jpg"):
        if not (EDU / f).exists():
            fails.append(f"missing edu/{f}")

    print(json.dumps({"durations_s": durs, "narration_lines": n_lines, "srt_cues": n_cues,
                      "vo_voiced_fraction": round(voiced, 3), "total_timeline_s": round(tl["total"], 2)}, indent=1))
    if fails:
        print("FAIL\n" + "\n".join(fails))
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
