"""SCRAMBLED v3: 1080x1350 @ 30 fps. Image field = one vertical strip per qubit, driven by measured F(site, t).

Per strip, at (continuous) echo step t, with f = Re F(site, t) and loss L = 1 - |f|:
  L in [0, 0.45]   : photo A (whole eggs) -> blur-v1 ladder (quantum blur, strength = reach 0.1 .. 0.3)
  L in [0.55, 0.8] : telablur-v1 A -> B ladder (direction vertical, strength 0.93 .. 0.99), ending on photo B
  L >= 0.8         : photo B (scrambled eggs): the strip's echo is down to |F| <= 0.2
  (L 0.45 .. 0.55 crossfades the last blur rung into the first telablur rung.)
Within each ladder the rungs are spaced by their CIELAB distance, so equal changes in F give equal visual change.
Each engine rung's luminance mean/contrast is moved 70 % of the way to its reference photo (A for blur, B for
telablur) and every source gets the same grade; both are classical and touch tone only, not structure.
Ladder images: renders/core/ladder/ (core/ladder_v4.py; lossless PNG input cropped from the full-res photos).
The sign of f is shown as a thin RdBu band under each strip (blue = echo returns, red = returns inverted).
F is not accumulated, so the finite-size revival (strips re-sharpening around t = 15) is visible.
Bottom panel: the act's heatmap revealed up to a cursor, live readouts, and provenance.
Compositing, the colour grade, typography and timing are classical. Frames are piped straight into ffmpeg.
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
from matplotlib import colormaps
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from data import F_of  # noqa: E402
from timeline import (ACT_PARAMS, ACT_TEXT, CARD_S, DURATION, FPS, H, SEGMENTS, W)  # noqa: E402

OUT = ROOT / "out" / "piece"
IMG = W                      # square image field
PANEL = H - IMG
BG = (12, 13, 16)
FG = (236, 236, 232)
DIM = (150, 152, 158)
RDBU = colormaps["RdBu"]

FONT_DIRS = [Path("C:/Windows/Fonts")]


def font(names, size):
    for d in FONT_DIRS:
        for n in names:
            p = d / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    import matplotlib
    return ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"), size)


LIGHT = lambda s: font(["segoeuil.ttf"], s)          # noqa: E731
REG = lambda s: font(["segoeui.ttf"], s)             # noqa: E731
SEMI = lambda s: font(["seguisb.ttf", "segoeuib.ttf"], s)  # noqa: E731


LADDER = ROOT / "renders" / "core" / "ladder"
BLUR_KEYS = ["blurR:0.1", "blurR:0.15", "blurR:0.2", "blurR:0.25", "blurR:0.3"]
TELA_KEYS = ["tela_vert:0.93", "tela_vert:0.95", "tela_vert:0.97", "tela_vert:0.99"]
L_BLUR, L_TELA, L_FULL = 0.45, 0.55, 0.8


def load(path, size=IMG):
    return np.asarray(Image.open(ROOT / path).convert("RGB").resize((size, size), Image.LANCZOS), dtype=np.float32)


def grade(x):
    """Classical look applied to every image-field source: gentle S-curve, set blacks, warm balance, +12 % chroma."""
    y = np.clip(x / 255.0, 0, 1)
    y = 0.65 * y + 0.35 * y * y * (3 - 2 * y)
    y = np.clip((y - 0.025) / 0.975, 0, 1)
    y = y * np.array([1.035, 1.0, 0.93], np.float32)
    lum = (y * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(axis=-1, keepdims=True)
    y = lum + 1.12 * (y - lum)
    return (np.clip(y, 0, 1) * 255).astype(np.float32)


def match_exposure(x, ref, amount=0.7):
    """Classical: move a rung's luminance mean/contrast part-way to a reference photo's (same affine on R, G, B)."""
    w = np.array([0.2126, 0.7152, 0.0722], np.float32)
    lx, lr = x @ w, ref @ w
    k = 1 + amount * (lr.std() / max(lx.std(), 1e-3) - 1)
    m = lx.mean() + amount * (lr.mean() - lx.mean())
    return np.clip(m + (x - lx.mean()) * k, 0, 255).astype(np.float32)


def lab(x):
    c = x / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]]).astype(np.float32)
    xyz /= np.array([0.9505, 1.0, 1.089], np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def spaced(stack, lo, hi):
    """Knot positions in [lo, hi] proportional to the cumulative mean CIELAB distance between successive rungs."""
    th = [lab(s[::8, ::8]) for s in stack]
    d = np.array([np.linalg.norm(th[i + 1] - th[i], axis=-1).mean() for i in range(len(th) - 1)])
    cum = np.concatenate([[0], np.cumsum(d)])
    return list(lo + (hi - lo) * cum / cum[-1])


def ladders():
    idx = json.loads((LADDER / "index.json").read_text(encoding="utf-8"))
    A = grade(load(LADDER.relative_to(ROOT) / "A_1080.png"))
    B = grade(load(LADDER.relative_to(ROOT) / "B_1080.png"))
    blur = [A] + [grade(match_exposure(load(idx[k]["file"]), load(LADDER.relative_to(ROOT) / "A_1080.png")))
                  for k in BLUR_KEYS]
    tela = [grade(match_exposure(load(idx[k]["file"]), load(LADDER.relative_to(ROOT) / "B_1080.png")))
            for k in TELA_KEYS] + [B]
    stack = blur + tela
    knots = spaced(blur, 0.0, L_BLUR) + spaced(tela, L_TELA, L_FULL)
    jobs = {k: idx[k]["job_id"] for k in BLUR_KEYS + TELA_KEYS}
    return A, B, stack, knots, jobs


def ladder(stack, knots, L, sl):
    x = float(np.interp(L, knots, np.arange(len(knots))))
    i = min(int(x), len(stack) - 2)
    f = x - i
    if f < 1e-4:
        return stack[i][:, sl]
    return stack[i][:, sl] * (1 - f) + stack[i + 1][:, sl] * f


def F_at(F, t):
    """Catmull-Rom through the measured steps: exact at integer t, continuous velocity in between (no stop-start)."""
    t = float(np.clip(t, 1, F.shape[1]))
    i = min(int(t) - 1, F.shape[1] - 2)
    u = t - (i + 1)
    p0, p1, p2, p3 = (F[:, max(i - 1, 0)], F[:, i], F[:, i + 1], F[:, min(i + 2, F.shape[1] - 1)])
    v = 0.5 * (2 * p1 + (p2 - p0) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3)
    re = np.clip(v.real, -1, 1)
    return re + 1j * v.imag if np.iscomplexobj(v) else re


def ease(x):
    x = float(np.clip(x, 0, 1))
    return x * x * (3 - 2 * x)


class Piece:
    def __init__(self, allow_classical=False):
        self.A, self.B, self.stack, self.knots, self.img_jobs = ladders()
        self.runs = {}
        for name, _, _, run in SEGMENTS:
            if run:
                F, ex = F_of(run, allow_classical=allow_classical)
                self.runs[name] = (F, ex)
        self.n = next(iter(self.runs.values()))[0].shape[0]
        self.edges = np.linspace(0, IMG, self.n + 1).round().astype(int)
        self.heat = {k: self._heat_img(F) for k, (F, _) in self.runs.items()}
        self.f_big = LIGHT(150)
        self.f_title = LIGHT(54)
        self.f_num = LIGHT(120)
        self.f_sub = REG(28)
        self.f_lab = SEMI(22)
        self.f_small = REG(19)
        self.f_tiny = REG(16)
        self.f_read = LIGHT(50)
        self.f_cap = SEMI(15)
        self.f_cap_b = SEMI(15)

    # ---------- image field ----------
    def strips(self, F, t):
        f = F_at(F, t).real
        frame = np.empty((IMG, IMG, 3), np.float32)
        for s in range(self.n):
            sl = slice(self.edges[s], self.edges[s + 1])
            frame[:, sl] = ladder(self.stack, self.knots, 1 - abs(f[s]), sl)
        return frame, f

    def gutters(self, im, alpha=1.0, kick=None, f=None):
        """Strip separators (2 px, every edge), qubit numbers, the nudge marker and the sign-of-F band."""
        d = ImageDraw.Draw(im, "RGBA")
        a = int(255 * alpha)
        for x in self.edges[1:-1]:
            d.rectangle([x - 1, 0, x, IMG - 1], fill=(8, 8, 10, a))
        if alpha <= 0.05:
            return
        band = 7
        for s in range(self.n):
            x0, x1 = self.edges[s] + (1 if s else 0), self.edges[s + 1] - (2 if s < self.n - 1 else 1)
            if f is not None:
                col = tuple(int(c * 255) for c in RDBU(float(np.clip((f[s] + 1) / 2, 0, 1)))[:3])
                d.rectangle([x0, IMG - band, x1, IMG - 1], fill=col + (a,))
            cx = (self.edges[s] + self.edges[s + 1]) / 2
            txt = str(s)
            w = d.textlength(txt, font=self.f_tiny)
            d.text((cx - w / 2 + 1, IMG - band - 25), txt, fill=(0, 0, 0, int(120 * alpha)), font=self.f_tiny)
            d.text((cx - w / 2, IMG - band - 26), txt, fill=(255, 255, 255, int(205 * alpha)), font=self.f_tiny)
        if kick is not None:
            cx = (self.edges[kick] + self.edges[kick + 1]) / 2
            d.polygon([(cx - 8, 14), (cx + 8, 14), (cx, 27)], fill=(255, 255, 255, int(235 * alpha)))
            w = d.textlength("nudge", font=self.f_tiny)
            d.text((cx - w / 2 + 1, 33), "nudge", fill=(0, 0, 0, int(120 * alpha)), font=self.f_tiny)
            d.text((cx - w / 2, 32), "nudge", fill=(255, 255, 255, int(230 * alpha)), font=self.f_tiny)

    # ---------- panel ----------
    CELL_W, CELL_H = 18, 11          # heatmap cell: 32 steps x 12 qubits -> 576 x 132 px, integer cells

    def _heat_img(self, F):
        rgb = RDBU(np.clip((F.real + 1) / 2, 0, 1))[..., :3]
        h, w = F.shape
        return np.asarray(Image.fromarray((rgb * 255).astype(np.uint8)).resize(
            (w * self.CELL_W, h * self.CELL_H), Image.NEAREST), np.float32)

    def caps(self, d, xy, text, fill, f=None, track=2.2):
        """Letter-spaced small caps label."""
        f = f or self.f_cap
        x, y = xy
        for c in text.upper():
            d.text((x, y), c, fill=fill, font=f)
            x += d.textlength(c, font=f) + track
        return x

    def panel(self, im, act, t, f, alpha_reveal=1.0):
        d = ImageDraw.Draw(im)
        y0, M = IMG, 48
        d.rectangle([0, y0, W, H], fill=BG)
        F, ex = self.runs[act]
        num, title, _ = ACT_TEXT[act]
        # left column: act label, heatmap with cursor, legend
        x = self.caps(d, (M, y0 + 22), f"{num}", FG, self.f_cap_b)
        self.caps(d, (x + 10, y0 + 22), title, DIM)
        hm = self.heat[act].copy()
        hh, hw = hm.shape[:2]
        cut = int(round(np.clip((t - 1) / (F.shape[1] - 1), 0, 1) * hw)) if t >= 1 else 0
        hm[:, cut:] = hm[:, cut:] * 0.14 + np.array(BG, np.float32) * 0.86
        yh = y0 + 52
        im.paste(Image.fromarray(hm.astype(np.uint8)), (M, yh))
        d.rectangle([M - 1, yh - 1, M + hw, yh + hh], outline=(44, 46, 52))
        if t >= 1:
            d.rectangle([M + cut - 1, yh - 5, M + cut, yh + hh + 4], fill=FG)
        ly = yh + hh + 12
        lx = M
        for label, v in (("returns", 0.9), ("erased", 0.5), ("inverted", 0.1)):
            d.rectangle([lx, ly + 4, lx + 10, ly + 14], fill=tuple(int(c * 255) for c in RDBU(v)[:3]))
            d.text((lx + 16, ly - 1), label, fill=DIM, font=self.f_tiny)
            lx += 16 + d.textlength(label, font=self.f_tiny) + 22
        d.text((lx + 6, ly - 1), "rows: qubits 0–11   ·   columns: echo step t = 1–32", fill=(108, 110, 116),
               font=self.f_tiny)
        # right column: readouts
        rx = M + hw + 56
        tt = max(1.0, t)
        self.caps(d, (rx, y0 + 22), "echo step", DIM)
        d.text((rx - 3, y0 + 38), f"{tt:4.1f}".strip(), fill=FG, font=self.f_read)
        d.text((rx + d.textlength(f"{tt:4.1f}".strip(), font=self.f_read) + 6, y0 + 62), "/ 32", fill=DIM,
               font=self.f_small)
        k = ex["kick_site"]
        mean = float(np.abs(np.delete(f, k)).mean()) if f is not None else 1.0
        self.caps(d, (rx, y0 + 112), "echo returning", DIM)
        d.text((rx - 3, y0 + 128), f"{100 * mean:.0f}%", fill=FG, font=self.f_read)
        bw = W - rx - M
        d.rectangle([rx, y0 + 192, rx + bw, y0 + 197], fill=(38, 40, 46))
        d.rectangle([rx, y0 + 192, rx + int(bw * mean), y0 + 197], fill=tuple(int(c * 255) for c in RDBU(0.85)[:3]))
        # provenance (the honesty line)
        d.line([(M, H - 44), (W - M, H - 44)], fill=(36, 38, 44), width=1)
        prov = f"otoc-echo-v1 · Moth Atlas · aer emulator (exact) · job {ex['job_id'][:8]}" if ex["job_id"] \
            else "classical statevector (not an Atlas run)"
        d.text((M, H - 34), f"{prov}   ·   {ACT_PARAMS[act]}   ·   {self.n} qubits, Z nudge on qubit {k}",
               fill=(120, 122, 128), font=self.f_tiny)

    def panel_text(self, im, lines, alpha=1.0):
        d = ImageDraw.Draw(im)
        d.rectangle([0, IMG, W, H], fill=BG)
        y = IMG + 40
        for txt, f, col in lines:
            col = tuple(int(BG[i] + (col[i] - BG[i]) * alpha) for i in range(3))
            d.text((40, y), txt, fill=col, font=f)
            y += f.size + 16

    # ---------- cards ----------
    def card(self, im, act, a):
        if a <= 0:
            return im
        base = im.crop((0, 0, IMG, IMG)).filter(ImageFilter.GaussianBlur(10 * a))
        dark = Image.new("RGB", (IMG, IMG), (0, 0, 0))
        base = Image.blend(base, dark, 0.62 * a)
        im.paste(base, (0, 0))
        d = ImageDraw.Draw(im, "RGBA")
        num, title, sub = ACT_TEXT[act]
        A_ = int(255 * a)
        d.text((80, 300), num, fill=(255, 255, 255, A_), font=self.f_num)
        d.text((80, 450), title, fill=(255, 255, 255, A_), font=self.f_title)
        y = 540
        for line in textwrap.wrap(sub, 52):
            d.text((82, y), line, fill=(225, 225, 225, A_), font=self.f_sub)
            y += 40
        d.text((82, y + 24), ACT_PARAMS[act], fill=(190, 190, 190, A_), font=self.f_small)
        return im

    def title_block(self, im, a, sub, y=420):
        d = ImageDraw.Draw(im, "RGBA")
        A_ = int(255 * a)
        word = "SCRAMBLED"
        spacing = 14
        widths = [d.textlength(c, font=self.f_big) for c in word]
        total = sum(widths) + spacing * (len(word) - 1)
        x = (IMG - total) / 2
        for c, w in zip(word, widths):
            d.text((x, y), c, fill=(255, 255, 255, A_), font=self.f_big)
            x += w + spacing
        sw = d.textlength(sub, font=self.f_sub)
        d.text(((IMG - sw) / 2, y + 190), sub, fill=(235, 235, 235, A_), font=self.f_sub)

    # ---------- frame ----------
    def frame(self, T):
        for name, t0, t1, run in SEGMENTS:
            if t0 <= T < t1 or (name == SEGMENTS[-1][0] and T >= t0):
                break
        u = T - t0
        seg = t1 - t0
        if name == "intro":
            fr = self.A.copy()
            im = Image.fromarray(fr.clip(0, 255).astype(np.uint8))
            im = Image.blend(Image.new("RGB", im.size), im, ease(u / 1.2)) if u < 1.2 else im
            canvas = Image.new("RGB", (W, H), BG)
            canvas.paste(im, (0, 0))
            dark = ease((u - 0.8) / 1.0) * (1 - ease((u - 4.6) / 1.0))
            if dark > 0:
                top = canvas.crop((0, 0, IMG, IMG))
                canvas.paste(Image.blend(top, Image.new("RGB", top.size), 0.45 * dark), (0, 0))
            self.title_block(canvas, dark, "the quantum butterfly effect, measured")
            self.gutters(canvas, alpha=ease((u - 4.8) / 1.0), kick=self.runs["control"][1]["kick_site"])
            self.panel_text(canvas, [
                ("Twelve qubits in a row. Nudge the middle one, run time forward, then backward.", self.f_sub, FG),
                ("If nothing scrambled, every qubit's echo comes back intact.", self.f_sub, FG),
                ("Each vertical strip of the image is one qubit; its sharpness is its measured echo.", self.f_small, DIM),
            ], alpha=ease((u - 1.0) / 1.5))
            return canvas
        if name == "end":
            canvas = Image.new("RGB", (W, H), BG)
            Fs, _ = self.runs["scrambling"]
            last, _ = self.strips(Fs, Fs.shape[1])
            x = ease(u / 2.5)
            fr = last * (1 - x) + self.B * x
            canvas.paste(Image.fromarray(fr.clip(0, 255).astype(np.uint8)), (0, 0))
            self.gutters(canvas, alpha=1 - x)
            a = ease((u - 2.0) / 1.5)
            top = canvas.crop((0, 0, IMG, IMG))
            canvas.paste(Image.blend(top, Image.new("RGB", top.size), 0.5 * a), (0, 0))
            self.title_block(canvas, a, "information scrambling, measured on Moth Atlas")
            self.panel_text(canvas, [
                ("Measured: otoc-echo-v1 on the Moth Atlas aer emulator (exact). Images: blur-v1, telablur-v1.",
                 self.f_small, FG),
                ("Music: qrc-midi-v1 + blur-midi-v1 melody; echoes rendered by retrocausal-echo-v1 from the taps.",
                 self.f_small, FG),
                ("Compositing, mixing and the synth are classical. Every F value is cross-checked by an",
                 self.f_small, DIM),
                ("independent statevector simulation (max difference < 1e-13).", self.f_small, DIM),
            ], alpha=ease((u - 2.5) / 1.5))
            fade = ease((u - (seg - 1.5)) / 1.5)
            if fade > 0:
                canvas = Image.blend(canvas, Image.new("RGB", canvas.size), fade)
            return canvas

        F, ex = self.runs[name]
        sweep = seg - CARD_S - 0.6
        t = 1 + (F.shape[1] - 1) * np.clip((u - CARD_S) / sweep, 0, 1)
        fr, f = self.strips(F, t)
        canvas = Image.new("RGB", (W, H), BG)
        canvas.paste(Image.fromarray(fr.clip(0, 255).astype(np.uint8)), (0, 0))
        self.gutters(canvas, kick=ex["kick_site"], f=f)
        card_a = 1 - ease((u - (CARD_S - 0.7)) / 0.7)
        if u < 0.5:
            card_a *= ease(u / 0.5)
            # cross-dissolve from the previous act's last frame
            prev = self._prev_last(name)
            if prev is not None:
                x = ease(u / 0.5)
                top = Image.blend(prev, canvas.crop((0, 0, IMG, IMG)), x)
                canvas.paste(top, (0, 0))
        self.card(canvas, name, card_a)
        self.panel(canvas, name, t if u >= CARD_S else 0, f if u >= CARD_S else None)
        return canvas

    def _prev_last(self, name):
        order = [s[0] for s in SEGMENTS]
        prev = order[order.index(name) - 1]
        if prev not in self.runs:
            return Image.fromarray(self.A.astype(np.uint8))
        F, _ = self.runs[prev]
        fr, _ = self.strips(F, F.shape[1])
        return Image.fromarray(fr.clip(0, 255).astype(np.uint8))


def render(allow_classical=False, audio=None, out=None, t_range=None):
    p = Piece(allow_classical)
    OUT.mkdir(parents=True, exist_ok=True)
    out = out or OUT / "scrambled_piece_v3.mp4"
    audio = audio or OUT / "scrambled_track.wav"
    n0, n1 = (0, int(DURATION * FPS)) if t_range is None else (int(t_range[0] * FPS), int(t_range[1] * FPS))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-ss", f"{n0 / FPS}", "-i", str(audio),
           "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart",
           # the native AAC encoder's default lowpass rings by ~2 dB on the stem's sharpest clank (scrambling act);
           # an explicit 20 kHz cutoff plus a 0.3 dB trim keeps the mp4 at <= -1 dBTP like the WAV
           "-af", "volume=-0.3dB", "-c:a", "aac", "-b:a", "320k", "-cutoff", "20000", "-shortest",
           "-metadata", "title=SCRAMBLED", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n0, n1):
        proc.stdin.write(np.asarray(p.frame(i / FPS).convert("RGB"), np.uint8).tobytes())
        if i % 300 == 0:
            print("frame", i, flush=True)
    proc.stdin.close()
    proc.wait()
    if proc.returncode:
        raise RuntimeError("ffmpeg failed")
    return out, p


def T_of(act, t, depth=32):
    """Piece time (s) at which an act's cursor reaches echo step t (inverse of the sweep in Piece.frame)."""
    _, t0, t1, _ = next(s for s in SEGMENTS if s[0] == act)
    sweep = (t1 - t0) - CARD_S - 0.6
    return t0 + CARD_S + (t - 1) / (depth - 1) * sweep


STILLS = [("1_title", lambda: 3.4), ("2_control_t20", lambda: T_of("control", 20)),
          ("3_gentle_t16", lambda: T_of("lowx", 16)), ("4_scrambling_tsat9", lambda: T_of("scrambling", 9)),
          ("5_scrambling_revival_t15", lambda: T_of("scrambling", 15.5)), ("6_end", lambda: 83.0)]


def stills(p, times, dest):
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for label, T in times:
        path = dest / f"still_{label}.png"
        p.frame(T).save(path)
        paths.append(path)
    return paths


COMPARE = [("gentle_t16", "still_3_gentle_t16.png"), ("scrambling_t9", "still_4_scrambling_tsat9.png"),
           ("scrambling_t15", "still_5_scrambling_revival_t15.png")]


def compare(dest=OUT / "compare"):
    """Side-by-side before/after at the same timestamps. 'before_*.png' are the previous v3 stills (kept as-is)."""
    out = []
    f = REG(30)
    for label, still in COMPARE:
        before, after = Image.open(dest / f"before_{label}.png"), Image.open(OUT / "stills" / still)
        sheet = Image.new("RGB", (2 * W + 24, H + 64), BG)
        sheet.paste(before, (0, 64))
        sheet.paste(after, (W + 24, 64))
        d = ImageDraw.Draw(sheet)
        d.text((16, 16), "before (v3)", fill=DIM, font=f)
        d.text((W + 40, 16), "after (v3 craft pass)", fill=FG, font=f)
        p = dest / f"compare_{label}.jpg"
        sheet.save(p, quality=92)
        out.append(p)
    return out


def contact(p, path=OUT / "contact_v3.jpg", cols=6, every=4.0):
    times = np.arange(1.0, DURATION, every)
    tw = W // 4
    th = H // 4
    rows = int(np.ceil(len(times) / cols))
    sheet = Image.new("RGB", (cols * tw, rows * (th + 22)), BG)
    d = ImageDraw.Draw(sheet)
    for i, T in enumerate(times):
        x, y = (i % cols) * tw, (i // cols) * (th + 22)
        sheet.paste(p.frame(float(T)).resize((tw, th), Image.LANCZOS), (x, y + 22))
        d.text((x + 6, y + 3), f"{T:4.1f} s", fill=DIM, font=REG(14))
    sheet.save(path, quality=90)
    return path


if __name__ == "__main__":
    allow = "--allow-classical" in sys.argv
    if "--frames" in sys.argv:
        p = Piece(allow)
        ts = [float(x) for x in sys.argv[sys.argv.index("--frames") + 1].split(",")]
        for T in ts:
            p.frame(T).save(ROOT / "renders" / "core" / f"test_{T:05.1f}.png")
        print("ok")
    elif "--stills" in sys.argv:
        p = Piece(allow)
        print(stills(p, [(k, f()) for k, f in STILLS], OUT / "stills"))
    else:
        out, p = render(allow)
        print(out, stills(p, [(k, f()) for k, f in STILLS], OUT / "stills"))
        print(compare(), contact(p))
