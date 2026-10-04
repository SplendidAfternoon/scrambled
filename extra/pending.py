"""Check engine jobs that were submitted but had not finished when their script gave up waiting.

Jobs are listed in extra/pending.json. Completed results are downloaded into extra/<engine>/late/ and
the statuses written back, so extra/README.md can be updated by hand. Read-only on the API (GET only).

Run:  .venv\\Scripts\\python extra\\pending.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

PENDING = Path(__file__).with_name("pending.json")


def main():
    jobs = json.loads(PENDING.read_text(encoding="utf-8"))
    for j in jobs:
        if j.get("status") in ("completed", "failed", "cancelled"):
            continue
        st = moth.get(f"/jobs/{j['job_id']}/status")
        j["status"] = st.get("status")
        j["progress"] = st.get("progress") or {}
        j["error"] = st.get("error")
        j["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if j["status"] == "completed":
            res = moth.get(f"/jobs/{j['job_id']}/result")
            rec = {"job_id": j["job_id"], "response": res}
            files = moth.fetch_outputs(rec, ROOT / "extra" / j["dir"] / "late")
            j["files"] = {k: v.relative_to(ROOT).as_posix() for k, v in files.items()}
            if res.get("result") is not None:
                j["inline_result"] = res["result"]
        print(j["engine_id"], j["job_id"][:8], j["status"], j["progress"].get("detail", ""))
    PENDING.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
