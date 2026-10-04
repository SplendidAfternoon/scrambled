"""Audio: the OTOC map as a multi-tap echo.

Mapping (mirrors the documented retrocausal-echo-v1 tap map): every (site, depth) cell of F is one echo tap.
depth t -> delay t * master_ms / depth, |F| -> tap level, site -> stereo pan (left to right along the chain),
Re F < 0 -> the echo is polarity-inverted. Inside the light cone the taps decay and scatter; outside it they stay
at full level, so the echo itself is a picture of how far the kick has spread.

Two renderers:
* ``render_taps``: local numpy convolution of the measured taps (a classical DSP step, labelled as such).
* ``render_engine``: Atlas ``retrocausal-echo-v1``, which measures the echo and renders the audio server-side.
  That engine has been slow; it runs with a timeout and falls back to the local render, reporting which one ran.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

ENGINE = "retrocausal-echo-v1"


def read_mono(path, sr=48000):
    """Any audio (or a video's audio track) -> (mono float32, sample rate)."""
    path = Path(path)
    try:
        x, r = sf.read(path, always_2d=True, dtype="float32")
        return x.mean(axis=1), r
    except Exception:
        from scrambled import ffmpeg
        with tempfile.TemporaryDirectory() as td:
            wav = ffmpeg.extract_audio(path, Path(td) / "a.wav", sr=sr)
            if wav is None:
                raise ValueError(f"{path} has no decodable audio")
            x, r = sf.read(wav, always_2d=True, dtype="float32")
            return x.mean(axis=1), r


def taps_from_F(F, min_level=0.02):
    """[(site, depth, level, sign)] for every cell with |F| >= min_level."""
    out = []
    for s in range(F.shape[0]):
        for t in range(F.shape[1]):
            level = float(abs(F[s, t]))
            if level >= min_level:
                out.append((s, t + 1, level, -1.0 if F[s, t].real < 0 else 1.0))
    return out


def render_taps(dry, sr, F, master_ms=6400.0, mix=0.5, min_level=0.02, decay=0.97, tail=True):
    """Dry mono signal -> stereo (N[+tail], 2) float array, peak-normalised to -1 dBFS."""
    n_sites, depth = F.shape
    step = max(1, int(sr * master_ms / 1000 / depth))
    taps = taps_from_F(F, min_level)
    extra = step * (depth + 1) if tail else 0
    wet = np.zeros((len(dry) + extra, 2), np.float64)
    for s, t, level, sign in taps:
        g = sign * level * decay ** t / n_sites
        pan = s / max(n_sites - 1, 1)
        start = t * step
        seg = dry[: max(0, len(wet) - start)]
        wet[start:start + len(seg), 0] += g * np.cos(pan * np.pi / 2) * seg
        wet[start:start + len(seg), 1] += g * np.sin(pan * np.pi / 2) * seg
    peak = np.abs(wet).max()
    if peak > 0:
        wet /= peak
    out = wet * mix
    out[: len(dry)] += (1 - mix) * np.asarray(dry, np.float64)[:, None] / max(np.abs(dry).max(), 1e-9)
    out /= max(np.abs(out).max(), 1e-9) / 0.89
    return out.astype(np.float32)


def render_engine(client, wav_path, omap_params, out_path, mix=0.5, master_ms=6400, timeout=180):
    """Run retrocausal-echo-v1 on Atlas. Returns (out_path, job_id). Raises on failure/timeout (caller falls back)."""
    p = {k: omap_params[k] for k in ("n_sites", "depth", "theta_x", "theta_zz", "theta_z", "kick", "disorder",
                                    "machine", "exact", "lattice") if k in omap_params}
    if omap_params.get("kick_site") is not None:
        p["kick_site"] = omap_params["kick_site"]
    p.update({"mix": mix, "master_ms": master_ms, "min_level": 0.02, "emit": "audio"})
    asset = client.upload(wav_path)
    rec = client.run(ENGINE, p, {"audio": asset}, timeout=timeout)
    res = client.fetch_outputs(rec)["result"]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(Path(res).read_bytes())
    return Path(out_path), rec["job_id"]


def scramble_audio(src, dst, omap, mix=0.5, master_ms=6400.0, engine=False, client=None, timeout=180, log=print):
    """Echo `src` through the OTOC map. Returns a dict describing which renderer actually produced `dst`."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if engine and client is not None:
        try:
            with tempfile.TemporaryDirectory() as td:
                dry, sr = read_mono(src)
                wav = Path(td) / f"{Path(src).stem}_mono.wav"
                sf.write(wav, dry, sr, subtype="PCM_16")
                _, job = render_engine(client, wav, omap.params, dst, mix=mix, master_ms=master_ms, timeout=timeout)
            return {"renderer": f"Atlas {ENGINE}", "job_id": job, "path": str(dst)}
        except Exception as e:
            log(f"warning: {ENGINE} unavailable ({str(e)[:200]}); falling back to the local tap render")
    dry, sr = read_mono(src)
    out = render_taps(dry, sr, omap.F, master_ms=master_ms, mix=mix)
    sf.write(dst, out, sr, subtype="PCM_16")
    return {"renderer": "local numpy tap render of the OTOC map (classical DSP)", "job_id": None, "path": str(dst)}
