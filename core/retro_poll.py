"""Background poller for the long-running retrocausal-echo-v1 jobs.

Polls every job id every POLL seconds, appends status transitions to measurements/retro/status_log.jsonl,
keeps the latest snapshot in measurements/retro/status.json, and on completion stores the full result record
in measurements/retro/<job>.json and downloads outputs into renders/core/retro/.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

OUT = ROOT / "measurements" / "retro"
DL = ROOT / "renders" / "core" / "retro"
JOBS = [
    "5618ae22-4aad-4a82-97ea-c76e821bf436",
    "aa558cac-7abd-4ddd-a43c-b7d87ae524e0",
    "bc6516c5-c5c5-430d-a66a-fa2785a8ceb4",
    "c4eefe4b-402a-4da8-8f54-259114c39e3f",
]
POLL = 120


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(hours=10.0):
    OUT.mkdir(parents=True, exist_ok=True)
    pending = set(JOBS)
    snap, last = {}, {}
    t_end = time.time() + hours * 3600
    while pending and time.time() < t_end:
        for jid in sorted(pending):
            try:
                st = moth.get(f"/jobs/{jid}/status")
            except Exception as e:
                st = {"status": "poll_error", "error": str(e)[:300]}
            brief = {"status": st.get("status"), "progress": st.get("progress"), "error": st.get("error"),
                     "checked": now()}
            snap[jid] = brief
            sig = json.dumps([brief["status"], brief["progress"], brief["error"]], default=str)
            if last.get(jid) != sig:
                last[jid] = sig
                with (OUT / "status_log.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"job_id": jid, **brief}, default=str) + "\n")
            if brief["status"] == "completed":
                res = moth.get(f"/jobs/{jid}/result")
                rec = {"engine_id": "retrocausal-echo-v1", "job_id": jid, "response": res}
                (OUT / f"{jid[:8]}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
                try:
                    paths = moth.fetch_outputs(rec, DL)
                    snap[jid]["outputs"] = {k: str(v.relative_to(ROOT)) for k, v in paths.items()}
                except Exception as e:
                    snap[jid]["outputs_error"] = str(e)[:300]
                pending.discard(jid)
            elif brief["status"] in ("failed", "cancelled"):
                pending.discard(jid)
        (OUT / "status.json").write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        if pending:
            time.sleep(POLL)


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 10.0)
