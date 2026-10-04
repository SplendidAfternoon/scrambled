"""One fresh retrocausal-echo-v1 attempt: a short (8 s) stem excerpt through the measured scrambling tap map.

Re-uses the uploaded IR asset (renders/ir/scrambling.json, the n = 12 scrambling trajectory) so no measurement is
paid for again. Waits up to 3 h; on completion the output is downloaded to renders/core/retro/ and the job is cached.
"""
import json
import sys
import time
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

PARAMS = {"min_level": 0.02, "decay": 1.0, "master_ms": 5333, "negative_mode": "invert",
          "mix": 0.6, "include_tap_map": True, "emit": "audio"}
OUT = ROOT / "measurements" / "retro"
ATTEMPTS = 8           # engine_timeout (no worker picked the job up) is retryable; space attempts 10 min apart


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clip = ROOT / "renders" / "core" / "retro" / "stem_8s.wav"
    clip.parent.mkdir(parents=True, exist_ok=True)
    if not clip.exists():
        x, sr = sf.read(ROOT / "media" / "stem_full.wav")
        sf.write(clip, x[int(26 * sr):int(34 * sr)], sr)
    files = {"audio": moth.upload(clip), "ir": moth.upload(ROOT / "renders" / "ir" / "scrambling.json")}
    t0 = time.time()
    log = {"params": PARAMS, "input_files": files, "submitted": time.strftime("%Y-%m-%dT%H:%M:%S")}
    log["attempts"] = []
    for attempt in range(ATTEMPTS):
        try:
            rec = moth.run("retrocausal-echo-v1", PARAMS, files, poll=30, max_poll=120, timeout=3 * 3600)
            paths = moth.fetch_outputs(rec, ROOT / "renders" / "core" / "retro")
            log.update(status="completed", job_id=rec["job_id"], seconds=rec["seconds"],
                       outputs={k: str(v.relative_to(ROOT)) for k, v in paths.items()})
            break
        except Exception as e:
            log["attempts"].append({"error": str(e)[:600], "at_s": round(time.time() - t0)})
            log.update(status="failed_or_timeout", waited_s=round(time.time() - t0))
            (OUT / "fresh_attempt.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
            if '"retryable": true' not in str(e):
                break
            time.sleep(600)
    (OUT / "fresh_attempt.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
