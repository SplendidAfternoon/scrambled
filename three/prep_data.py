"""Bundle everything the renderer needs into web/scene_data.js.

- entanglement-shader-v1 R/T lookup tables (decoded from the engine's Radiance .hdr files)
- measured OTOC F(site, t) for the scrambling run and the Clifford control
- blur-core-v1 radius grids of the egg mesh (engine_outputs/blurcore_*.json)
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import fmap  # noqa: E402

SHADER_DIR = HERE / "engine_outputs" / "shader_9214cb9d"
SHADER_JOB = "9214cb9d-e1ab-413d-80c1-2bd4c00c2f20"


def read_hdr(path):
    """Minimal Radiance RGBE reader (flat or new-style RLE scanlines). Returns float32 (H, W, 3)."""
    data = Path(path).read_bytes()
    pos = 0
    while True:                                    # header ends with an empty line
        end = data.index(b"\n", pos)
        line = data[pos:end]
        pos = end + 1
        if line == b"":
            break
    end = data.index(b"\n", pos)
    res = data[pos:end].decode().split()
    pos = end + 1
    assert res[0] == "-Y" and res[2] == "+X", res
    h, w = int(res[1]), int(res[3])
    img = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        if data[pos] == 2 and data[pos + 1] == 2 and (data[pos + 2] << 8 | data[pos + 3]) == w:
            pos += 4
            for c in range(4):
                x = 0
                while x < w:
                    n = data[pos]
                    pos += 1
                    if n > 128:
                        n -= 128
                        img[y, x:x + n, c] = data[pos]
                        pos += 1
                    else:
                        img[y, x:x + n, c] = np.frombuffer(data[pos:pos + n], np.uint8)
                        pos += n
                    x += n
        else:
            img[y] = np.frombuffer(data[pos:pos + 4 * w], np.uint8).reshape(w, 4)
            pos += 4 * w
    e = img[..., 3].astype(np.int32)
    scale = np.where(e > 0, np.ldexp(1.0, e - 136), 0.0)
    return (img[..., :3] * scale[..., None]).astype(np.float32)


def crack_seeds(seed=7, n=90):
    """Voronoi seeds identical to egg_mesh.crack_field (shell fragments line up with the blurred relief)."""
    pts = np.random.default_rng(seed).normal(size=(n, 3))
    return pts / np.linalg.norm(pts, axis=1, keepdims=True)


def main():
    R = read_hdr(SHADER_DIR / "R_lut.hdr")[..., 0]   # single-channel data stored in RGB
    T = read_hdr(SHADER_DIR / "T_lut.hdr")[..., 0]
    otoc = {}
    for name, f in [("scrambling", "otoc_scrambling.json"), ("clifford", "otoc_control_clifford.json")]:
        rec = json.loads((ROOT / "probes" / f).read_text(encoding="utf-8"))
        F, ex = fmap.load_F(rec)
        otoc[name] = {"job_id": rec.get("job_id"), "absF": np.round(np.abs(F), 4).tolist(),
                      "reF": np.round(F.real, 4).tolist(), "kick_site": ex["kick_site"],
                      "theta_x": rec["params"]["theta_x"], "theta_zz": rec["params"]["theta_zz"]}
    grids = json.loads((HERE / "meshes" / "egg_grids.json").read_text(encoding="utf-8"))
    summary = json.loads((HERE / "engine_outputs" / "blurcore_summary.json").read_text(encoding="utf-8"))
    scene = {
        "lut": {"w": int(R.shape[1]), "h": int(R.shape[0]),
                "R": np.round(R, 5).ravel().tolist(), "T": np.round(T, 5).ravel().tolist(),
                "job_id": SHADER_JOB},
        "otoc": otoc,
        "grid": summary["grid"],
        "radii": {k: grids[k] for k in ["base", "crack_input", "crack_mask", "crack_s000",
                                        "crack_s035", "crack_s060", "crack_s060_r05", "crack_s090_r10"]},
        "blur_jobs": {r["label"]: r["job_id"] for r in summary["runs"]},
        "crack_seeds": np.round(crack_seeds(), 6).tolist(),
    }
    out = HERE / "web" / "scene_data.js"
    out.parent.mkdir(exist_ok=True)
    out.write_text("window.SCENE = " + json.dumps(scene, separators=(",", ":")) + ";\n", encoding="utf-8")
    print("R range", float(R.min()), float(R.max()), "T range", float(T.min()), float(T.max()))
    print("wrote", out, out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
