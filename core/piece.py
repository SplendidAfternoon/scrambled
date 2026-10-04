"""SCRAMBLED v3: 1080x1350 @ 30 fps. Image field = one vertical strip per qubit, driven by measured F(site, t).

Per strip, at (continuous) echo step t, with f = Re F(site, t) and loss L = 1 - |f|:
  L in [0, 0.5]  : photo A (whole eggs) -> blur-v1 ladder (quantum blur, increasing strength)
  L in [0.5, 1]  : strongest blur -> telablur-v1 ladder A -> B (quantum morph into the scrambled-eggs photo)
  tint           : RdBu colour of f (blue = echo returns intact, red = returns inverted), alpha ~ |f|
F is not accumulated, so the finite-size revival (strips re-sharpening around t = 15) is visible.
Bottom panel: the act's heatmap revealed up to a cursor, live readouts, and provenance.
Compositing, typography and timing are classical. Frames are piped straight into ffmpeg.
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


def load(path, size=IMG):
    return np.asarray(Image.open(ROOT / path).convert("RGB").resize((size, size), Image.LANCZOS), dtype=np.float32)


def ladders():
    idx = json.loads((ROOT / "renders" / "v2" / "index.json").read_text(encoding="utf-8"))
    A = load("media/prep/A_sq.jpg")
    B = load("media/prep/B_sq.jpg")
    blur = [A] + [load(idx[f"blurR:{s}"]["file"]) for s in (0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4)]
    tela = [blur[-1]] + [load(idx[f"telablur:{s}"]["file"]) for s in (0.5, 0.85, 0.9, 0.95, 0.98)] + [B]
    jobs = {k: idx[k]["job_id"] for k in idx}
    return A, B, blur, tela, jobs


def ladder(stack, x, sl):
    x = float(np.clip(x, 0, 1)) * (len(stack) - 1)
    i = min(int(x), len(stack) - 2)
    f = x - i
    return stack[i][:, sl] * (1 - f) + stack[i + 1][:, sl] * f


def F_at(F, t):
    t = float(np.clip(t, 1, F.shape[1]))
    i = min(int(t) - 1, F.shape[1] - 2)
    f = t - (i + 1)
    f = f * f * (3 - 2 * f)            # smoothstep between measured steps
    return F[:, i] * (1 - f) + F[:, i + 1] * f


def ease(x):
    x = float(np.clip(x, 0, 1))
    return x * x * (3 - 2 * x)


class Piece:
    def __init__(self, allow_classical=False):
        self.A, self.B, self.blur, self.tela, self.img_jobs = ladders()
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
        self.f_read = LIGHT(46)

    # ---------- image field ----------
    def strips(self, F, t):
        f = F_at(F, t).real
        frame = np.empty((IMG, IMG, 3), np.float32)
        for s in range(self.n):
            sl = slice(self.edges[s], self.edges[s + 1])
            L = 1 - abs(f[s])
            tile = ladder(self.blur, L / 0.5, sl) if L <= 0.5 else ladder(self.tela, (L - 0.5) / 0.5, sl)
            col = np.array(RDBU((f[s] + 1) / 2)[:3], np.float32) * 255
            a = 0.06 + 0.16 * abs(f[s])
            frame[:, sl] = tile * (1 - a) + col * a
        return frame, f

    def gutters(self, im, alpha=1.0, kick=None):
        d = ImageDraw.Draw(im, "RGBA")
        a = int(200 * alpha)
        for x in self.edges[1:-1]:
            d.line([(x, 0), (x, IMG)], fill=(10, 10, 12, a), width=2)
        if alpha > 0.05:
            for s in range(self.n):
                cx = (self.edges[s] + self.edges[s + 1]) // 2
                txt = str(s)
                w = d.textlength(txt, font=self.f_tiny)
                d.text((cx - w / 2, IMG - 26), txt, fill=(255, 255, 255, int(170 * alpha)), font=self.f_tiny)
            if kick is not None:
                cx = (self.edges[kick] + self.edges[kick + 1]) // 2
                d.polygon([(cx - 9, 10), (cx + 9, 10), (cx, 24)], fill=(255, 255, 255, int(230 * alpha)))
                w = d.textlength("nudge", font=self.f_tiny)
                d.text((cx - w / 2, 28), "nudge", fill=(255, 255, 255, int(220 * alpha)), font=self.f_tiny)

    # ---------- panel ----------
    def _heat_img(self, F, w=640, h=150):
        rgb = RDBU(np.clip((F.real + 1) / 2, 0, 1))[..., :3]
        return np.asarray(Image.fromarray((rgb * 255).astype(np.uint8)).resize((w, h), Image.NEAREST), np.float32)

    def panel(self, im, act, t, f, alpha_reveal=1.0):
        d = ImageDraw.Draw(im)
        y0 = IMG
        d.rectangle([0, y0, W, H], fill=BG)
        F, ex = self.runs[act]
        hm = self.heat[act].copy()
        hw = hm.shape[1]
        cut = int(np.clip((t - 1) / (F.shape[1] - 1), 0, 1) * hw) if t >= 1 else 0
        hm[:, cut:] = hm[:, cut:] * 0.18 + np.array(BG, np.float32) * 0.82
        x0, yh = 40, y0 + 52
        im.paste(Image.fromarray(hm.astype(np.uint8)), (x0, yh))
        if t >= 1:
            d.line([(x0 + cut, yh - 6), (x0 + cut, yh + hm.shape[0] + 6)], fill=FG, width=2)
        num, title, _ = ACT_TEXT[act]
        d.text((x0, y0 + 16), f"{num}  {title}", fill=FG, font=self.f_lab)
        d.text((x0, yh + hm.shape[0] + 6), "measured echo F(qubit, t)   ·   blue = returns   red = inverted   white = erased",
               fill=DIM, font=self.f_tiny)
        rx = x0 + hw + 44
        tt = max(1.0, t)
        d.text((rx, y0 + 16), "echo step", fill=DIM, font=self.f_small)
        d.text((rx, y0 + 38), f"t = {tt:4.1f}", fill=FG, font=self.f_read)
        k = ex["kick_site"]
        mean = float(np.abs(np.delete(f, k)).mean()) if f is not None else 1.0
        d.text((rx, y0 + 108), "echo returning", fill=DIM, font=self.f_small)
        d.text((rx, y0 + 130), f"{100 * mean:3.0f} %", fill=FG, font=self.f_read)
        bw = W - rx - 40
        d.rectangle([rx, y0 + 192, rx + bw, y0 + 200], fill=(40, 42, 48))
        d.rectangle([rx, y0 + 192, rx + int(bw * mean), y0 + 200], fill=tuple(int(c * 255) for c in RDBU(0.85)[:3]))
        prov = f"otoc-echo-v1 · Moth Atlas · aer emulator (exact) · job {ex['job_id'][:8]}" if ex["job_id"] \
            else "classical statevector (not an Atlas run)"
        d.text((x0, H - 28), f"{prov}   ·   {ACT_PARAMS[act]}   ·   {self.n} qubits, Z nudge on qubit {k}",
               fill=DIM, font=self.f_tiny)

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
                ("Music: qrc-midi-v1 + blur-midi-v1 on a seed from the cooking audio; echoes from the measured taps.",
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
        self.gutters(canvas, kick=ex["kick_site"])
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
