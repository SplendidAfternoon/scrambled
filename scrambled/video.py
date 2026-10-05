"""Video: every frame is cut into per-qubit strips driven by F(site, t), with media time running along echo depth.

Quantum ladders cannot be rendered for every frame (one Atlas job per rung per frame would cost thousands of
credits), so they are rendered on K evenly spaced keyframes and crossfaded in time. Level 0 of every blur ladder
is always the live frame, so strips the kick has not reached play the original video untouched; strips inside the
light cone fade into the quantum renders of the nearest keyframes.

API cost per run: K * (len(blur levels) + len(morph levels)) jobs, by default 4 * (3 + 3) = 24 one-credit jobs,
plus one otoc-echo-v1 measurement (free if cached). Re-runs hit the cache and cost nothing.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from scrambled import ffmpeg, image, mapping
from scrambled.audio import scramble_audio

VIDEO_BLUR = (0.1, 0.2, 0.3)
VIDEO_MORPH = (0.02, 0.5, 0.98)


def even_size(w, h, max_side):
    s = min(1.0, max_side / max(w, h))
    return max(2, int(round(w * s / 2)) * 2), max(2, int(round(h * s / 2)) * 2)


def _mix(a: image.Ladders, b: image.Ladders, w):
    if w <= 0 or a is b:
        return a
    if w >= 1:
        return b
    return image.Ladders(blur=[x * (1 - w) + y * w for x, y in zip(a.blur, b.blur)],
                         morph=[x * (1 - w) + y * w for x, y in zip(a.morph, b.morph)], source=a.source)


def scramble_video(src, dst, omap, mode="atlas", client=None, start=0.0, duration=None, keyframes=4, pair="last",
                   max_side=720, fps=None, show_overlay=True, label="", audio_mix=0.5, audio_engine=False,
                   timeout=900, audio_src=None, layout="strips", log=print):
    """Render the scrambled video. `pair`: 'last' (final frame of the excerpt), 'none' (non-local blur), or a path.

    The soundtrack (the video's own, or `audio_src` if given, cut to the same excerpt) keeps its dry signal and gains
    the OTOC echo."""
    info = ffmpeg.probe(src)
    dur = float(duration or (info.duration - start))
    dur = min(dur, info.duration - start)
    if dur <= 0:
        raise ValueError(f"excerpt start={start}s is past the end of {src} ({info.duration:.1f}s)")
    w, h = even_size(info.width, info.height, max_side)
    fps = float(fps or min(info.fps, 30.0))
    K = max(1, int(keyframes))
    key_times = [start + dur * (k + 0.5) / K for k in range(K)]
    report = {"size": [w, h], "fps": fps, "start": start, "duration": dur, "keyframes": key_times, "layout": layout,
              "jobs": []}

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        pair_path = None
        if pair == "last":
            pair_path = td / "pair_last.png"
            Image.fromarray(ffmpeg.frame_at(src, max(start, start + dur - 0.2), w, h)).save(pair_path)
        elif pair and pair != "none":
            pair_path = Path(pair)
        ladders = []
        for k, kt in enumerate(key_times):
            kf = td / f"key_{k}.png"
            Image.fromarray(ffmpeg.frame_at(src, kt, w, h)).save(kf)
            if mode == "classical":
                pr = image.load_rgb(pair_path, (w, h)) if pair_path else None
                lad = image.classical_ladders(image.load_rgb(kf), pr, VIDEO_BLUR, VIDEO_MORPH)
            else:
                lad = image.atlas_ladders(client, kf, pair_path, size=(w, h), blur_levels=VIDEO_BLUR,
                                          morph_levels=VIDEO_MORPH, timeout=timeout, log=log)
                report["jobs"] += [{"engine": e, "params": p, "job_id": j} for e, p, j in lad.jobs]
            ladders.append(lad)
            log(f"keyframe {k + 1}/{K} at {kt:.2f}s: ladders ready ({lad.source})")

        audio_out = None
        if audio_src or info.has_audio:
            wav = ffmpeg.extract_audio(audio_src or src, td / "dry.wav", start=start, duration=dur)
            if wav is not None:
                audio_out = td / "echo.wav"
                rep = scramble_audio(wav, audio_out, omap, mix=audio_mix, engine=audio_engine, client=client,
                                     log=log)
                report["audio"] = rep["renderer"] if not rep["job_id"] else f"{rep['renderer']} job {rep['job_id']}"

        n_frames = 0
        edges = mapping.strip_edges(w, omap.n_sites)
        with ffmpeg.Writer(dst, w, h, fps, audio=audio_out) as wr:
            for i, fr in enumerate(ffmpeg.read_frames(src, w, h, fps, start=start, duration=dur)):
                tau = i / fps
                t = 1 + (omap.depth - 1) * min(tau / dur, 1.0)
                p = float(np.clip(tau / dur * K - 0.5, 0, K - 1))
                k0 = min(int(p), K - 1)
                k1 = min(k0 + 1, K - 1)
                lad = _mix(ladders[k0], ladders[k1], p - k0)
                out = image.compose(fr.astype(np.float32), lad, mapping.strip_states(omap.F, t), edges,
                                    layout=layout, kick=omap.kick_site)
                wr.write(image.overlay(out, omap.F, t, label) if show_overlay else out.clip(0, 255))
                n_frames += 1
        report["frames"] = n_frames
    return report
