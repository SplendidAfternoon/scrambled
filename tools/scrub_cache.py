"""Strip presigned URLs (temporary AWS credentials) from cached job records before publishing.

Replay never needs them: outputs are re-read from cache/files or re-signed via /assets/{id}/download.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIGNED = re.compile(r"https://[^\s\"']*X-Amz-[^\s\"']*")


def scrub(obj):
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    if isinstance(obj, str) and "X-Amz-" in obj:
        return SIGNED.sub(lambda m: m.group(0).split("?", 1)[0] + "?<signature-removed>", obj)
    return obj


def main(dirs):
    changed = 0
    for d in dirs:
        for p in (ROOT / d).rglob("*.json"):
            text = p.read_text(encoding="utf-8")
            if "X-Amz-" not in text:
                continue
            p.write_text(json.dumps(scrub(json.loads(text)), indent=2), encoding="utf-8")
            changed += 1
    left = [str(p) for d in dirs for p in (ROOT / d).rglob("*") if p.is_file() and p.suffix in {".json", ".ipynb", ".html", ".md", ".jsonl"} and "X-Amz-Signature" in p.read_text(encoding="utf-8", errors="ignore")]
    print(f"scrubbed {changed} files; remaining signed URLs: {len(left)}")
    for p in left:
        print("  ", p)
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["cache", "probes", "measurements", "renders", "web/public/data", "three", "notebook", "plugin/tools", "edu", "out"]))
