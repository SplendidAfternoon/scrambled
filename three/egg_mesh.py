"""Procedural egg mesh + blur-core-v1 round trip (obj -> JSON grid -> blur-core -> JSON grid -> obj).

The egg is a surface of revolution with a Hügelschäffer egg profile, sampled on a
(lat x lon) grid. Its geometry is stored as a 2-D grid of radii r[i, j] measured
from the egg centre along fixed unit directions d[i, j]. That grid is exactly the
`values` array blur-core-v1 accepts (non-negative, rectangular), so the mesh can be
sent through the engine and rebuilt from the returned radii with the same faces.

Usage:  ..\\.venv\\Scripts\\python egg_mesh.py      (from three/)
Writes engine_outputs/blurcore_*.json, meshes/*.obj, meshes/egg_grids.json
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import moth  # noqa: E402

NLAT, NLON = 128, 128          # 16 384 vertices, 2^14 grid -> 14 qubits in blur-core
L, B, W = 1.0, 0.74, 0.085     # egg length, breadth, Hügelschäffer asymmetry


def egg_profile(z):
    """Radius of the egg cross-section at height z in [-L/2, L/2] (pointy end at +z)."""
    num = np.clip(L * L - 4 * z * z, 0, None)
    den = L * L + 8 * W * z + 4 * W * W
    return 0.5 * B * np.sqrt(num / den)


def egg_grid():
    """Directions d[i,j] (unit, from centre) and radii r[i,j] for the base egg."""
    theta = np.linspace(0, np.pi, NLAT)               # polar angle from +z
    phi = np.linspace(0, 2 * np.pi, NLON, endpoint=False)
    # sample the profile densely, then invert to radius-along-direction
    zs = np.linspace(-L / 2, L / 2, 20001)
    rho = egg_profile(zs)
    ang = np.arctan2(rho, zs)                         # polar angle of each profile point
    dist = np.hypot(rho, zs)
    order = np.argsort(ang)
    r_theta = np.interp(theta, ang[order], dist[order])
    st, ct = np.sin(theta)[:, None], np.cos(theta)[:, None]
    d = np.stack([st * np.cos(phi)[None, :], st * np.sin(phi)[None, :],
                  np.repeat(ct, NLON, axis=1)], axis=-1)
    r = np.repeat(r_theta[:, None], NLON, axis=1)
    return theta, phi, d, r


def faces():
    f = []
    for i in range(NLAT - 1):
        for j in range(NLON):
            a, b = i * NLON + j, i * NLON + (j + 1) % NLON
            c, e = (i + 1) * NLON + j, (i + 1) * NLON + (j + 1) % NLON
            f.append((a, c, b))
            f.append((b, c, e))
    return np.array(f)


def write_obj(path, verts, F):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# quantum egg {NLAT}x{NLON}\n")
        for v in verts:
            fh.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for t in F + 1:
            fh.write(f"f {t[0]} {t[1]} {t[2]}\n")


def read_obj_radii(path, d):
    """obj -> grid of radii along the known directions (the 'obj -> JSON' step)."""
    v = np.array([[float(x) for x in ln.split()[1:4]]
                  for ln in open(path, encoding="utf-8") if ln.startswith("v ")])
    r = np.linalg.norm(v, axis=1).reshape(NLAT, NLON)
    return r


def blur(r, label, **params):
    """Send the radius grid through blur-core-v1; returns rescaled radii (same shape)."""
    vals = np.round(r, 6).tolist()
    p = {"values": vals, **params}
    rec = moth.run("blur-core-v1", p, timeout=900)
    out = np.array(rec["response"]["result"]["output"] if "result" in rec["response"]
                   else rec["response"]["output"], dtype=float)
    out = out * (r.max() / out.max())                 # engine rescales to input max -> undo
    meta = {k: v for k, v in params.items()}
    (HERE / "engine_outputs").mkdir(exist_ok=True)
    (HERE / "engine_outputs" / f"blurcore_{label}.json").write_text(json.dumps({
        "engine_id": "blur-core-v1", "job_id": rec["job_id"], "seconds": rec["seconds"],
        "params": meta, "grid_shape": list(r.shape), "radii": np.round(out, 6).tolist()}),
        encoding="utf-8")
    return out, rec["job_id"]


def crack_field(theta, phi, seed=7, n=90):
    """Voronoi-edge crack relief on the shell (0 = intact, 1 = in a crack)."""
    rng = np.random.default_rng(seed)
    pts = rng.normal(size=(n, 3))
    pts /= np.linalg.norm(pts, axis=1, keepdims=True)
    st, ct = np.sin(theta)[:, None], np.cos(theta)[:, None]
    p = np.stack([st * np.cos(phi), st * np.sin(phi), np.repeat(ct, len(phi), 1)], -1)
    dots = p @ pts.T
    s = np.sort(dots, axis=-1)
    edge = s[..., -1] - s[..., -2]                    # small near a Voronoi boundary
    return np.exp(-(edge / 0.02) ** 2)


def main():
    theta, phi, d, r0 = egg_grid()
    F = faces()
    base_obj = HERE / "meshes" / "egg_base.obj"
    write_obj(base_obj, (d * r0[..., None]).reshape(-1, 3), F)
    r_in = read_obj_radii(base_obj, d)

    results = {"grid": [NLAT, NLON], "profile": {"L": L, "B": B, "W": W}, "runs": []}

    # 1) zero-blur round trip on the plain egg: must reproduce the input
    r_rt, jid = blur(r_in, "s0_roundtrip", strength=0.0)
    err = float(np.abs(r_rt - r_in).max())
    results["roundtrip"] = {"job_id": jid, "max_abs_err": err, "max_rel_err": err / float(r_in.max())}
    write_obj(HERE / "meshes" / "egg_roundtrip.obj", (d * r_rt[..., None]).reshape(-1, 3), F)
    print("round-trip max abs err", err)
    if err > 1e-4:
        raise SystemExit("zero-blur round trip failed; refusing to continue")

    # 2) cracked shell relief, then a strength ladder (local and non-local reach)
    crack = crack_field(theta, phi)
    r_crack = r_in * (1 - 0.06 * crack)
    ladder = [("crack_s000", dict(strength=0.0)),
              ("crack_s015", dict(strength=0.15)),
              ("crack_s035", dict(strength=0.35)),
              ("crack_s060", dict(strength=0.6)),
              ("crack_s060_r05", dict(strength=0.6, reach=0.5)),
              ("crack_s090_r10", dict(strength=0.9, reach=1.0))]
    grids = {"base": r_in.tolist(), "crack_input": r_crack.tolist(), "crack_mask": crack.tolist()}
    for label, prm in ladder:
        out, jid = blur(r_crack, label, **prm)
        results["runs"].append({"label": label, "params": prm, "job_id": jid,
                                "mean_abs_change": float(np.abs(out - r_crack).mean()),
                                "max_abs_change": float(np.abs(out - r_crack).max())})
        grids[label] = np.round(out, 6).tolist()
        write_obj(HERE / "meshes" / f"egg_{label}.obj", (d * out[..., None]).reshape(-1, 3), F)
        print(label, jid, results["runs"][-1]["mean_abs_change"])

    (HERE / "meshes" / "egg_grids.json").write_text(json.dumps(grids), encoding="utf-8")
    (HERE / "engine_outputs" / "blurcore_summary.json").write_text(json.dumps(results, indent=2),
                                                                   encoding="utf-8")


if __name__ == "__main__":
    main()
