"""Image ladders (quantum blur-v1 / telablur-v1 on Atlas, or a labelled classical stand-in) and strip compositing.

A *ladder* is a short list of renders of one picture at increasing effect strength. Frames are composed per strip:
the strip's blur level picks a point on the blur ladder (level 0 = the untouched picture), then its morph level
picks a point on the morph ladder (level 0 = that blurred strip), then the echo polarity may flip it.

Blur ladder: blur-v1 with reach = strength, so as the echo loses memory the quantum blur also becomes less local.
Morph ladder with a pair image (e.g. whole eggs -> scrambled eggs): telablur-v1, which morphs image1 toward image2
through quantum rotation gates; its middle strengths are an unreadable quantum texture and ~0.98 lands on the
target. Without a pair: the same blur-v1 family continued toward reach = 1, the fully non-local quantum blur where
every pixel can be affected by every other one (information spread across the whole canvas).
"""
from __future__ import annotations

import hashlib
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from scrambled import mapping

BLUR_LEVELS = (0.1, 0.2, 0.3, 0.4)
MORPH_LEVELS = (0.02, 0.5, 0.9, 0.98)
NONLOCAL_LEVELS = (0.6, 0.8, 1.0)
MAX_SIDE = 1024


@dataclass
class Ladders:
    blur: list            # float32 (h, w, 3) arrays, increasing strength, excluding level 0
    morph: list           # float32 arrays, increasing strength, excluding level 0
    source: str           # atlas | classical
    jobs: list = field(default_factory=list)   # (engine_id, params, job_id)


def load_rgb(path, size=None):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if size and im.size != tuple(size):
        im = im.resize(tuple(size), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32)


def working_size(path, max_side=MAX_SIDE):
    w, h = ImageOps.exif_transpose(Image.open(path)).size
    s = min(1.0, max_side / max(w, h))
    return (max(2, int(round(w * s / 2)) * 2), max(2, int(round(h * s / 2)) * 2))


def to_upload(src, size, work_dir):
    """Write a deterministic PNG/JPEG copy at `size` (stable bytes -> stable asset id -> cache hits)."""
    src = Path(src)
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    if src.suffix.lower() in (".jpg", ".jpeg", ".png") and im.size == tuple(size):
        return src
    im = im.resize(tuple(size), Image.LANCZOS)
    digest = hashlib.sha256(src.read_bytes()).hexdigest()[:12]
    out = Path(work_dir) / f"{src.stem}_{digest}_{size[0]}x{size[1]}.png"
    if not out.exists():
        im.save(out, optimize=False)
    return out


# -- ladders --------------------------------------------------------------------------------------------------
def classical_ladders(img, pair=None, blur_levels=BLUR_LEVELS, morph_levels=MORPH_LEVELS,
                      nonlocal_levels=NONLOCAL_LEVELS):
    """Gaussian blur + crossfade stand-in. Not quantum; outputs made with it are labelled classical."""
    h, w = img.shape[:2]
    scale = max(w, h) / 1024
    pil = Image.fromarray(img.clip(0, 255).astype(np.uint8))
    blur = [np.asarray(pil.filter(ImageFilter.GaussianBlur(60 * s * scale)), np.float32) for s in blur_levels]
    if pair is not None:
        morph = [img * (1 - s) + pair * s for s in morph_levels]
    else:
        morph = [np.asarray(pil.filter(ImageFilter.GaussianBlur(120 * s * scale)), np.float32)
                 for s in nonlocal_levels]
    return Ladders(blur=blur, morph=morph, source="classical")


def atlas_ladders(client, image_path, pair_path=None, size=None, blur_levels=BLUR_LEVELS,
                  morph_levels=MORPH_LEVELS, nonlocal_levels=NONLOCAL_LEVELS, timeout=900, workers=4, log=print):
    """Render the ladders with blur-v1 / telablur-v1 on Atlas (cached; replayable)."""
    size = size or working_size(image_path)
    with tempfile.TemporaryDirectory() as td:
        a = client.upload(to_upload(image_path, size, td))
        jobs = [("blur", "blur-v1", {"strength": s, "reach": s}, {"image": a}) for s in blur_levels]
        if pair_path:
            b = client.upload(to_upload(pair_path, size, td))
            jobs += [("morph", "telablur-v1", {"strength": s}, {"image1": a, "image2": b}) for s in morph_levels]
        else:
            jobs += [("morph", "blur-v1", {"strength": s, "reach": s}, {"image": a}) for s in nonlocal_levels]

    def go(job):
        kind, eid, params, files = job
        rec = client.run(eid, params, files, timeout=timeout)
        path = client.fetch_outputs(rec)["result"]
        return kind, eid, params, rec["job_id"], load_rgb(path, size)

    out = {"blur": [], "morph": []}
    done = []
    errors = []
    with ThreadPoolExecutor(workers) as pool:
        futs = [pool.submit(go, j) for j in jobs]
        for j, f in zip(jobs, futs):
            try:
                kind, eid, params, job_id, arr = f.result()
                out[kind].append(arr)
                done.append((eid, params, job_id))
            except Exception as e:  # one failed rung degrades the ladder; it does not kill the render
                errors.append(f"{j[1]} {j[2]}: {str(e)[:300]}")
    for e in errors:
        log(f"warning: ladder rung failed: {e}")
    if not out["blur"] or not out["morph"]:
        raise RuntimeError("Atlas ladder rendering failed; rerun later (finished jobs are cached) or use "
                           "--mode classical. " + "; ".join(errors))
    return Ladders(blur=out["blur"], morph=out["morph"], source="atlas", jobs=done)


# -- compositing ----------------------------------------------------------------------------------------------
def lerp_stack(stack, x):
    """Crossfade along a ladder; x in [0, 1] spans the whole stack."""
    if len(stack) == 1:
        return stack[0]
    x = float(np.clip(x, 0, 1)) * (len(stack) - 1)
    i = min(int(x), len(stack) - 2)
    f = x - i
    return stack[i] if f == 0 else stack[i] * (1 - f) + stack[i + 1] * f


LAYOUTS = ("strips", "rings")


@lru_cache(maxsize=8)
def ring_index(h, w, n_rings):
    """Ring number of every pixel: equal-width rings from the centre out to the farthest pixel."""
    y, x = np.mgrid[0:h, 0:w]
    r = np.hypot(x + 0.5 - w / 2, y + 0.5 - h / 2)
    return np.minimum((r / r.max() * n_rings).astype(int), n_rings - 1)


def ring_states(states, kick):
    """Ring r holds the sites r steps from the kicked one (one or two of them), averaged."""
    n = len(states)
    kick = int(np.clip(kick, 0, n - 1))
    out = []
    for r in range(max(kick, n - 1 - kick) + 1):
        grp = [states[s] for s in sorted({kick - r, kick + r}) if 0 <= s < n]
        out.append(mapping.StripState(blur=float(np.mean([g.blur for g in grp])),
                                      morph=float(np.mean([g.morph for g in grp])),
                                      flipped=np.mean([g.flipped for g in grp]) >= 0.5))
    return out


def _compose_rings(frame, ladders: Ladders, states, kick):
    h, w = frame.shape[:2]
    rs = ring_states(states, kick)
    idx = ring_index(h, w, len(rs))
    out = np.empty((h, w, 3), np.float32)
    for r, st in enumerate(rs):
        m = idx == r
        tile = lerp_stack([frame] + ladders.blur, st.blur)
        if st.morph > 0:
            tile = lerp_stack([tile] + ladders.morph, st.morph)
        if st.flipped:
            tile = tile[::-1, ::-1]   # a half turn keeps every ring on itself
        out[m] = tile[m]
    return out


def compose(frame, ladders: Ladders, states, edges=None, layout="strips", kick=None):
    """One output frame: per-strip (or per-ring) blur / morph / polarity from the OTOC states.

    strips: one vertical strip per qubit, left to right along the chain.
    rings: concentric rings around the centre, ring r = the qubits r steps from the kicked one, so the light cone
    spreads outward from the middle of the picture.
    """
    if layout == "rings":
        return _compose_rings(frame, ladders, states, len(states) // 2 if kick is None else kick)
    h, w = frame.shape[:2]
    edges = mapping.strip_edges(w, len(states)) if edges is None else edges
    out = np.empty((h, w, 3), np.float32)
    for s, st in enumerate(states):
        a, b = edges[s], edges[s + 1]
        tile = lerp_stack([frame[:, a:b]] + [L[:, a:b] for L in ladders.blur], st.blur)
        if st.morph > 0:
            tile = lerp_stack([tile] + [M[:, a:b] for M in ladders.morph], st.morph)
        if st.flipped:
            tile = tile[::-1]
        out[:, a:b] = tile
    return out


_RDBU = np.array([[5, 48, 97], [33, 102, 172], [67, 147, 195], [146, 197, 222], [209, 229, 240], [247, 247, 247],
                  [253, 219, 199], [244, 165, 130], [214, 96, 77], [178, 24, 43], [103, 0, 31]], np.float32)[::-1]


def colormap(v):
    """RdBu-style map for v in [-1, 1] (red = -1, blue = +1, like matplotlib's RdBu)."""
    x = (np.clip(v, -1, 1) + 1) / 2 * (len(_RDBU) - 1)
    i = np.minimum(x.astype(int), len(_RDBU) - 2)
    f = (x - i)[..., None]
    return (_RDBU[i] * (1 - f) + _RDBU[i + 1] * f).astype(np.uint8)


def _font(px):
    for name in ("arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def overlay(frame, F, t, label):
    """Heatmap of the measured Re F(site, t) with a cursor at the current echo step, plus a provenance label."""
    im = Image.fromarray(np.asarray(frame).clip(0, 255).astype(np.uint8))
    W, H = im.size
    hw = max(96, W // 4)
    hh = max(36, int(hw * F.shape[0] / F.shape[1] * 1.2))
    hm = Image.fromarray(colormap(F.real)).resize((hw, hh), Image.NEAREST)
    d = ImageDraw.Draw(hm)
    x = int((float(np.clip(t, 1, F.shape[1])) - 1) / max(F.shape[1] - 1, 1) * (hw - 1))
    d.line([(x, 0), (x, hh)], fill=(255, 255, 255), width=max(1, hw // 120))
    pad = max(6, W // 80)
    im.paste(hm, (W - hw - pad, pad))
    d = ImageDraw.Draw(im)
    fs = max(10, W // 48)
    font = _font(fs)
    d.text((W - hw - pad, pad + hh + 2), f"F(qubit, t)  t = {t:4.1f}/{F.shape[1]}", fill="white", font=font,
           stroke_width=max(1, fs // 8), stroke_fill="black")
    d.rectangle([0, H - fs * 2, W, H], fill=(0, 0, 0))
    d.text((pad, H - fs * 2 + fs // 3), label, fill=(225, 225, 225), font=font)
    return np.asarray(im)


def echo_times(depth, n_frames):
    return 1 + (depth - 1) * np.arange(n_frames) / max(n_frames - 1, 1)


def scramble_image(src, dst, omap, ladders: Ladders, seconds=8.0, fps=24, at=None, show_overlay=True, label="",
                   layout="strips"):
    """Write a PNG/JPEG of one echo step (default: the last) or an MP4 animating t = 1..T."""
    from scrambled import ffmpeg
    dst = Path(dst)
    size = ladders.blur[0].shape[1], ladders.blur[0].shape[0]
    img = load_rgb(src, size)

    def frame_at(t):
        return compose(img, ladders, mapping.strip_states(omap.F, t), layout=layout, kick=omap.kick_site)
    if dst.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        t = omap.depth if at is None else at
        fr = frame_at(t)
        fr = overlay(fr, omap.F, t, label) if show_overlay else fr
        dst.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.asarray(fr).clip(0, 255).astype(np.uint8)).save(dst)
        return dst
    n = max(2, int(seconds * fps))
    with ffmpeg.Writer(dst, size[0], size[1], fps) as wr:
        for t in echo_times(omap.depth, n):
            fr = frame_at(t)
            wr.write(overlay(fr, omap.F, t, label) if show_overlay else fr.clip(0, 255))
    return dst
