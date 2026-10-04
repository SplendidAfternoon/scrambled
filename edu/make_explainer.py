"""'Why you can't unscramble an egg (quantum edition)' — animated explainer built from measured otoc-echo-v1 data.

Usage (from the repo root, ffmpeg on PATH):
    .venv\\Scripts\\python edu\\make_explainer.py           # full render -> edu/out/*.mp4, *.srt, contact sheet
    .venv\\Scripts\\python edu\\make_explainer.py stills    # one PNG per beat -> edu/build/stills/

Narration/captions are parsed from edu/script.md (blockquote lines). The placeholder voice is offline Windows
SAPI text-to-speech; animation, compositing, music and mixing are classical. Quantum content: the two measured
otoc-echo-v1 results in probes/ and the blur-v1 / telablur-v1 image ladders in renders/v2/ (all from Atlas).
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fmap  # noqa: E402

EDU = ROOT / "edu"
BUILD = EDU / "build"
OUT = EDU / "out"
W, H, FPS, SR = 1920, 1080, 30, 48000

BG = (20, 17, 15)
CREAM = (243, 234, 216)
DIM = (150, 140, 125)
GOLD = (242, 182, 50)
BLUE = (74, 143, 231)
MID = (52, 45, 40)
EMPTY = (32, 28, 25)

FONTS = Path("C:/Windows/Fonts")


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


F_REG = lambda s: font("segoeui.ttf", s)  # noqa: E731
F_BOLD = lambda s: font("segoeuib.ttf", s)  # noqa: E731
F_LIGHT = lambda s: font("segoeuil.ttf", s)  # noqa: E731
F_MONO = lambda s: font("consola.ttf", s)  # noqa: E731


# ---------------------------------------------------------------- data

def load(name, path=None):
    path = path or ROOT / "probes" / f"otoc_{name}.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    F, ex = fmap.load_F(rec)
    s = rec["response"]["result"]["output"]["data"]["series"]
    ratio = (np.array(s["X_kick"]) + 1j * np.array(s["Y_kick"])) / (np.array(s["X_ref"]) + 1j * np.array(s["Y_ref"]))
    assert np.allclose(F, ratio, atol=1e-9), "F should equal (X+iY)_kick / (X+iY)_ref"
    return rec, F, ex


REC_S, F_S, EX_S = load("scrambling")
REC_C, F_C, EX_C = load("control_clifford")
REC_Z, F_Z, EX_Z = load("zfield", ROOT / "cache" / "otoc-echo-v1" / "c534d155e09a2a92.json")
assert REC_Z["job_id"].startswith("7a4ccdfa") and EX_Z["kick_site"] == EX_S["kick_site"] and F_Z.shape == F_S.shape
KICK = EX_S["kick_site"]
NS, NT = F_S.shape
CONE = np.array(EX_S["light_cone"])
ARRIVAL = [int(np.argmax(r)) + 1 for r in CONE]


def offkick_mean(F):
    return np.delete(np.abs(F), KICK, axis=0).mean(axis=0)


MEAN_S, MEAN_C, MEAN_Z = offkick_mean(F_S), offkick_mean(F_C), offkick_mean(F_Z)


def cmap(v):
    v = np.clip(np.asarray(v, dtype=float), -1, 1)[..., None]
    pos = np.array(MID) + (np.array(GOLD) - np.array(MID)) * np.clip(v, 0, 1)
    neg = np.array(MID) + (np.array(BLUE) - np.array(MID)) * np.clip(-v, 0, 1)
    return np.where(v >= 0, pos, neg)


# ---------------------------------------------------------------- script / timeline

def parse_script():
    beats, cur = [], None
    for line in (EDU / "script.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (\d+)\. (.+)$", line)
        if m:
            cur = {"n": int(m.group(1)), "title": m.group(2).strip(), "lines": []}
            beats.append(cur)
        elif line.startswith("> ") and cur is not None:
            cur["lines"].append(line[2:].strip())
    assert len(beats) == 9 and all(b["lines"] for b in beats), "script.md must have 9 beats with narration"
    return beats


PS_TTS = r"""
Add-Type -AssemblyName System.Speech
$items = Get-Content -Raw -Encoding UTF8 $args[0] | ConvertFrom-Json
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Zira Desktop')
$s.Rate = 1
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($it in $items) {
  $s.SetOutputToWaveFile($it.path, $fmt)
  $s.Speak($it.text)
  $s.SetOutputToNull()
}
"""


def tts_lines(beats):
    vo_dir = BUILD / "vo"
    vo_dir.mkdir(parents=True, exist_ok=True)
    todo = []
    for b in beats:
        b["wavs"] = []
        for text in b["lines"]:
            p = vo_dir / (hashlib.sha1((PS_TTS + text).encode("utf-8")).hexdigest()[:12] + ".wav")
            b["wavs"].append(p)
            if not p.exists():
                todo.append({"path": str(p), "text": text})
    if todo:
        (BUILD / "tts_todo.json").write_text(json.dumps(todo), encoding="utf-8")
        (BUILD / "tts.ps1").write_text(PS_TTS, encoding="utf-8")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(BUILD / "tts.ps1"), str(BUILD / "tts_todo.json")], check=True)


def trim(x, thr=0.004):
    idx = np.flatnonzero(np.abs(x) > thr)
    return x[max(idx[0] - 240, 0): idx[-1] + 2400] if len(idx) else x


LEAD, GAP, TAIL = 0.5, 0.3, 0.9
MIN_DUR = {1: 12.0, 2: 7.0, 4: 10.0, 5: 11.0, 6: 14.0, 7: 9.0, 8: 10.0, 9: 13.0}


def build_timeline(beats):
    t = 0.0
    for b in beats:
        clips = [trim(sf.read(p, dtype="float32")[0]) for p in b["wavs"]]
        b["clips"] = clips
        u, cues = LEAD, []
        for text, c in zip(b["lines"], clips):
            d = len(c) / SR
            cues.append((u, u + d, text))
            u += d + GAP
        b["cues"] = cues
        b["dur"] = max(MIN_DUR.get(b["n"], 6.0), u - GAP + TAIL)
        b["t0"] = t
        t += b["dur"]
    return t


# ---------------------------------------------------------------- drawing helpers

def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ramp(u, a, b):
    return ease((u - a) / (b - a)) if b > a else float(u >= a)


def text_c(d, xy, s, f, fill=CREAM, anchor="mm"):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def wrap(d, s, f, maxw):
    words, lines, cur = s.split(), [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if d.textlength(nxt, font=f) <= maxw:
            cur = nxt
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def fade(col, a, bg=BG):
    return tuple(int(bg[i] + (col[i] - bg[i]) * a) for i in range(3))


_egg_cache = {}


def egg_sprite(w, h, rgb, ring=None):
    key = (w, h, rgb, ring)
    if key in _egg_cache:
        return _egg_cache[key]
    S = 4
    pad = 12
    img = Image.new("RGBA", ((w + 2 * pad) * S, (h + 2 * pad) * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    th = np.linspace(0, 2 * np.pi, 160, endpoint=False)
    cx, cy = (w / 2 + pad) * S, (h / 2 + pad) * S
    xs = cx + (w / 2) * S * np.sin(th) * (1 - 0.16 * np.cos(th))
    ys = cy - (h / 2) * S * np.cos(th)
    pts = list(zip(xs, ys))
    if ring:
        rx = [(cx + (x - cx) * 1.22, cy + (y - cy) * 1.17) for x, y in pts]
        d.polygon(rx, fill=None, outline=ring + (255,), width=3 * S)
    d.polygon(pts, fill=rgb + (255,), outline=CREAM + (255,), width=2 * S)
    img = img.resize((w + 2 * pad, h + 2 * pad), Image.LANCZOS)
    _egg_cache[key] = (img, pad)
    return img, pad


def paste_egg(frame, cx, cy, w, h, rgb, ring=None, alpha=1.0):
    q = tuple(int(c) // 4 * 4 for c in rgb)
    spr, pad = egg_sprite(w, h, q, ring)
    if alpha < 1:
        spr = spr.copy()
        spr.putalpha(spr.getchannel("A").point(lambda v: int(v * alpha)))
    frame.paste(spr, (int(cx - w / 2 - pad), int(cy - h / 2 - pad)), spr)


def load_img(path, size):
    return Image.open(path).convert("RGB").resize((size, size), Image.LANCZOS)


IDX = json.loads((ROOT / "renders" / "v2" / "index.json").read_text(encoding="utf-8"))
A_PATH, B_PATH = ROOT / "media" / "prep" / "A_sq.jpg", ROOT / "media" / "prep" / "B_sq.jpg"
TELA = [0.02, 0.05, 0.1, 0.15, 0.5, 0.85, 0.9, 0.95, 0.98]
BLURR = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4]
MORPH = [load_img(A_PATH, 720)] + [load_img(ROOT / IDX[f"telablur:{s}"]["file"], 720) for s in TELA] + [load_img(B_PATH, 720)]
LADDER = [load_img(A_PATH, 360)] + [load_img(ROOT / IDX[f"blurR:{s}"]["file"], 360) for s in BLURR]
B_FULL = (Image.open(B_PATH).convert("RGB").resize((W, W), Image.LANCZOS)
          .crop((0, (W - H) // 2, W, (W - H) // 2 + H)).filter(ImageFilter.GaussianBlur(8)))


def seq_frame(frames, x):
    x = min(max(x, 0.0), 1.0) * (len(frames) - 1)
    i = int(np.floor(x))
    if i >= len(frames) - 1:
        return frames[-1]
    return Image.blend(frames[i], frames[i + 1], ease(x - i))


# heatmap geometry
HX, HY, CW, CH = 300, 250, 34, 40


def heat_layer(F, cols):
    """Re F as a cell grid; columns beyond `cols` (float) are empty."""
    rgb = cmap(F.real)
    full = int(np.floor(cols))
    frac = cols - full
    grid = np.empty((NS, NT, 3))
    grid[:] = EMPTY
    grid[:, :full] = rgb[:, :full]
    if full < NT and frac > 0:
        grid[:, full] = np.array(EMPTY) + (rgb[:, full] - np.array(EMPTY)) * frac
    big = np.repeat(np.repeat(grid, CH, axis=0), CW, axis=1)
    big[CH - 2::CH, :] = BG
    big[:, CW - 2::CW] = BG
    return Image.fromarray(big.astype(np.uint8))


def draw_heat(frame, d, F, cols, cone=False, eggs=True):
    frame.paste(heat_layer(F, cols), (HX, HY))
    for k in (1, 8, 16, 24, 32):
        x = HX + (k - 0.5) * CW
        text_c(d, (x, HY + NS * CH + 22), str(k), F_MONO(24), DIM)
    text_c(d, (HX + NT * CW / 2, HY + NS * CH + 60), "echo step  t  →", F_REG(28), DIM)
    text_c(d, (HX - 150, HY - 30), "qubit", F_REG(26), DIM)
    for s in range(NS):
        text_c(d, (HX - 120, HY + (s + 0.5) * CH), str(s), F_MONO(22), DIM)
    if cone:
        pts = []
        for s in range(NS):
            x = HX + (ARRIVAL[s] - 1) * CW - 1
            pts += [(x, HY + s * CH), (x, HY + (s + 1) * CH - 2)]
        d.line(pts, fill=CREAM, width=4, joint="curve")
    col = int(min(max(np.ceil(cols), 1), NT)) - 1
    if eggs:
        for s in range(NS):
            v = F.real[s, col] if cols > 0 else 1.0
            paste_egg(frame, HX - 60, HY + (s + 0.5) * CH - 1, 26, 34, tuple(cmap(v).astype(int)),
                      ring=GOLD if s == KICK else None)
    if 0 < cols < NT + 1:
        x = HX + min(cols, NT) * CW
        d.line([(x, HY - 10), (x, HY + NS * CH + 2)], fill=CREAM, width=2)
    return col


def legend(d, x, y, w=420):
    for i in range(w):
        v = -1 + 2 * i / (w - 1)
        d.line([(x + i, y), (x + i, y + 16)], fill=tuple(cmap(v).astype(int)))
    text_c(d, (x, y + 36), "−1 flipped", F_REG(22), DIM, "lm")
    text_c(d, (x + w / 2, y + 36), "0 smeared", F_REG(22), DIM, "mm")
    text_c(d, (x + w, y + 36), "+1 unchanged", F_REG(22), DIM, "rm")


def side_panel(frame, d, F, col, mean_series, label):
    x0, y0 = 1460, 250
    m = mean_series[col]
    s = (1 - m) / (1 - MEAN_S.min())
    frame.paste(seq_frame(LADDER, s), (x0, y0))
    d.rectangle([x0, y0, x0 + 359, y0 + 359], outline=MID, width=2)
    text_c(d, (x0, y0 + 384), "Atlas blur-v1 frame picked by mean |F|", F_REG(20), DIM, "lm")
    text_c(d, (x0, y0 + 440), f"t = {col + 1}", F_BOLD(56), CREAM, "lm")
    text_c(d, (x0, y0 + 500), f"mean |F|, other qubits: {m:.2f}", F_REG(26), CREAM, "lm")
    text_c(d, (x0, y0 + 536), label, F_REG(22), DIM, "lm")


def header(d, title):
    text_c(d, (60, 44), "WHY YOU CAN'T UNSCRAMBLE AN EGG  ·  quantum edition", F_REG(22), DIM, "lm")
    text_c(d, (W - 60, 44), "measured on Moth Atlas · otoc-echo-v1 · aer emulator", F_REG(22), DIM, "rm")
    if title:
        text_c(d, (60, 130), title, F_BOLD(56), CREAM, "lm")


# ---------------------------------------------------------------- beats

def cue_t(b, i, part=0.0):
    a, e, _ = b["cues"][min(i, len(b["cues"]) - 1)]
    return a + (e - a) * part


def beat1(fr, d, b, u):
    dur = b["dur"]
    fr.paste(seq_frame(MORPH, (u - 0.18 * dur) / (0.62 * dur)), (140, 140))
    d.rectangle([140, 140, 859, 859], outline=MID, width=2)
    text_c(d, (140, 884), "whole → scrambled, through Atlas telablur-v1 frames", F_REG(22), DIM, "lm")
    a = ramp(u, 0.4, 1.6)
    text_c(d, (980, 380), "Why you can't", F_BOLD(84), fade(CREAM, a), "lm")
    text_c(d, (980, 480), "unscramble an egg", F_BOLD(84), fade(CREAM, a), "lm")
    text_c(d, (984, 570), "(quantum edition)", F_LIGHT(54), fade(GOLD, ramp(u, 1.2, 2.4)), "lm")
    text_c(d, (984, 680), "a 2-minute explainer built from real", F_REG(30), fade(DIM, ramp(u, 2.0, 3.0)), "lm")
    text_c(d, (984, 722), "quantum measurements", F_REG(30), fade(DIM, ramp(u, 2.0, 3.0)), "lm")


def egg_row(fr, d, u, y=470, values=None, appear_from=0.0, nudge_at=None):
    gap, w, h = 128, 84, 110
    x0 = W / 2 - gap * (NS - 1) / 2
    for s in range(NS):
        a = ramp(u, appear_from + 0.08 * s, appear_from + 0.08 * s + 0.4)
        if a <= 0:
            continue
        v = 1.0 if values is None else values[s]
        ring = None
        dy = 0
        if s == KICK and nudge_at is not None and u > nudge_at:
            ring = GOLD
            dy = -14 * np.exp(-3 * (u - nudge_at)) * np.sin(14 * (u - nudge_at))
        paste_egg(fr, x0 + gap * s, y + dy, w, h, tuple(cmap(v).astype(int)), ring=ring, alpha=a)
        text_c(d, (x0 + gap * s, y + 92), str(s), F_MONO(26), fade(DIM, a))
    return x0, gap


def beat2(fr, d, b, u):
    header(d, "A row of twelve qubits")
    nud = cue_t(b, 1, 0.6)
    x0, gap = egg_row(fr, d, u, appear_from=0.3, nudge_at=nud)
    if u > nud:
        a = ramp(u, nud, nud + 0.5)
        x = x0 + gap * KICK
        d.line([(x, 290), (x, 380)], fill=fade(GOLD, a), width=5)
        d.polygon([(x - 14, 372), (x + 14, 372), (x, 398)], fill=fade(GOLD, a))
        text_c(d, (x, 260), "nudge  (a Z flip on qubit 6)", F_REG(32), fade(GOLD, a))
    text_c(d, (W / 2, 690), "each egg = one qubit · gold = still in its starting state",
           F_REG(28), fade(DIM, ramp(u, 1.5, 2.5)))


def beat3(fr, d, b, u):
    header(d, "The echo test")
    steps = ["Run forward", "Nudge qubit 6", "Run backward", "Compare with a\nno-nudge run"]
    starts = [cue_t(b, 1, 0.0), cue_t(b, 1, 0.45), cue_t(b, 1, 0.75), cue_t(b, 2, 0.0)]
    bw, bh, gap = 330, 150, 80
    x0 = W / 2 - (4 * bw + 3 * gap) / 2
    for i, s in enumerate(steps):
        on = ramp(u, starts[i], starts[i] + 0.4)
        x = x0 + i * (bw + gap)
        d.rounded_rectangle([x, 230, x + bw, 230 + bh], 22, fill=fade((48, 40, 30), max(on, 0.35)),
                            outline=fade(GOLD, max(on, 0.25)), width=3)
        for j, ln in enumerate(s.split("\n")):
            nl = len(s.split("\n"))
            text_c(d, (x + bw / 2, 230 + bh / 2 + (j - (nl - 1) / 2) * 40), ln, F_BOLD(32), fade(CREAM, max(on, 0.4)))
        if i < 3:
            ax = x + bw + 12
            d.line([(ax, 305), (ax + gap - 28, 305)], fill=fade(DIM, max(on, 0.3)), width=4)
            d.polygon([(ax + gap - 28, 295), (ax + gap - 14, 305), (ax + gap - 28, 315)], fill=fade(DIM, max(on, 0.3)))
    sub = ["U", "Z", "U†", "÷ reference"]
    for i, s in enumerate(sub):
        x = x0 + i * (bw + gap) + bw / 2
        text_c(d, (x, 420), s, F_MONO(30), fade(DIM, ramp(u, starts[i], starts[i] + 0.4)))
    a = ramp(u, cue_t(b, 2, 0.55), cue_t(b, 2, 0.75))
    text_c(d, (W / 2, 520), "F(qubit, t)  =  echo with nudge  ÷  echo without nudge", F_MONO(38), fade(CREAM, a))
    for i, v in enumerate([1.0, 0.0, -1.0]):
        p0 = (0.0, 0.33, 0.75)[i]
        ai = ramp(u, cue_t(b, 3, p0), cue_t(b, 3, p0 + 0.12))
        if ai <= 0:
            continue
        cx = W / 2 + (i - 1) * 380
        paste_egg(fr, cx, 650, 70, 92, tuple(cmap(v).astype(int)), alpha=ai)
        lab = ["+1  nudge never reached it", "≈0  smeared across many", "−1  flipped"][i]
        text_c(d, (cx, 730), lab, F_REG(28), fade(CREAM, ai))
    a = ramp(u, cue_t(b, 4, 0.0), cue_t(b, 4, 0.4))
    text_c(d, (W / 2, 820), "out-of-time-order correlator  ·  OTOC", F_BOLD(40), fade(GOLD, a))


def beat4(fr, d, b, u):
    header(d, "The light cone")
    cols = 8 * ramp(u, 0.8, b["dur"] - 2.0)
    col = draw_heat(fr, d, F_S, cols, cone=u > cue_t(b, 2, 0.0))
    side_panel(fr, d, F_S, col, MEAN_S, "scrambling setting · θzz = 0.35π")
    legend(d, HX + NT * CW - 420, HY + NS * CH + 110)
    if u > cue_t(b, 2, 0.0):
        text_c(d, (HX + 8 * CW + 20, HY + 6 * CH), "← light cone: one neighbour per step", F_REG(28),
               fade(CREAM, ramp(u, cue_t(b, 2, 0.0), cue_t(b, 2, 0.3))), "lm")


def beat5(fr, d, b, u):
    header(d, "Control: a Clifford setting")
    cols = NT * ramp(u, cue_t(b, 1, 0.5), b["dur"] - 1.5)
    col = draw_heat(fr, d, F_C, cols)
    side_panel(fr, d, F_C, col, MEAN_C, "control · θzz = π (Clifford)")
    legend(d, HX + NT * CW - 420, HY + NS * CH + 110)


def beat6(fr, d, b, u):
    header(d, "Scrambling")
    cols = NT * ramp(u, 0.6, b["dur"] - 1.8)
    col = draw_heat(fr, d, F_S, cols, cone=True)
    side_panel(fr, d, F_S, col, MEAN_S, "scrambling setting · θzz = 0.35π")
    legend(d, HX + NT * CW - 420, HY + NS * CH + 110)
    a = ramp(u, cue_t(b, 4, 0.3), cue_t(b, 4, 0.5))
    if a > 0:
        text_c(d, (400, 136), "\u201cquantum butterfly effect\u201d is a nickname, a metaphor", F_REG(28), fade(DIM, a), "lm")


def beat7(fr, d, b, u):
    header(d, "The honest wobble")
    x0, y0, w, h = 200, 220, 1300, 560
    tx = lambda t: x0 + (t - 1) / (NT - 1) * w  # noqa: E731
    ty = lambda v: y0 + h - v * h  # noqa: E731
    band = ramp(u, cue_t(b, 0, 0.2), cue_t(b, 0, 0.5))
    if band > 0:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rectangle([tx(13), y0, tx(16), y0 + h], fill=GOLD + (int(46 * band),))
        fr.paste(ov, (0, 0), ov)
        text_c(d, ((tx(13) + tx(16)) / 2, y0 + 40), "t = 13–16: partial revival", F_REG(26), fade(GOLD, band))
    d.line([(x0, y0), (x0, y0 + h), (x0 + w, y0 + h)], fill=DIM, width=2)
    for v in (0, 0.5, 1.0):
        text_c(d, (x0 - 20, ty(v)), f"{v:.1f}", F_MONO(24), DIM, "rm")
        d.line([(x0, ty(v)), (x0 + w, ty(v))], fill=(40, 35, 31), width=1)
    for k in (1, 8, 16, 24, 32):
        text_c(d, (tx(k), y0 + h + 28), str(k), F_MONO(24), DIM)
    text_c(d, (x0 + w / 2, y0 + h + 70), "echo step  t  →", F_REG(28), DIM)
    text_c(d, (x0 - 20, y0 - 40), "mean |F| over the 11 un-nudged qubits", F_REG(26), DIM, "lm")
    p = ramp(u, 0.3, 4.0)
    n = max(2, int(round(p * NT)))
    t = np.arange(1, NT + 1)
    d.line([(tx(a), ty(v)) for a, v in zip(t[:n], MEAN_C[:n])], fill=DIM, width=4)
    d.line([(tx(a), ty(v)) for a, v in zip(t[:n], MEAN_S[:n])], fill=GOLD, width=5)
    for a, v in zip(t[:n], MEAN_S[:n]):
        d.ellipse([tx(a) - 5, ty(v) - 5, tx(a) + 5, ty(v) + 5], fill=GOLD)
    text_c(d, (x0 + w + 16, ty(MEAN_C[-1])), "control (Clifford)", F_REG(26), DIM, "lm")
    text_c(d, (x0 + w + 16, ty(MEAN_S[-1]) + 16), "scrambling, solvable", F_REG(26), GOLD, "lm")
    zs = cue_t(b, 2, 0.0)
    nz = int(round(ramp(u, zs, zs + 2.5) * NT))
    if nz >= 2:
        d.line([(tx(a), ty(v)) for a, v in zip(t[:nz], MEAN_Z[:nz])], fill=BLUE, width=5)
        a = ramp(u, zs, zs + 0.6)
        text_c(d, (x0 + w + 16, ty(MEAN_Z[-1]) - 16), "+ z-field, not solvable", F_REG(26), fade(BLUE, a), "lm")
        text_c(d, (x0 + w + 16, ty(MEAN_Z[-1]) - 46), f"θz = 0.25π · job {REC_Z['job_id'][:8]}", F_REG(20), fade(DIM, a), "lm")


def icon_blackhole(d, cx, cy):
    for r, c in ((92, (90, 62, 20)), (78, (170, 115, 30)), (66, GOLD)):
        d.ellipse([cx - r * 1.6, cy - r * 0.45, cx + r * 1.6, cy + r * 0.45], outline=c, width=5)
    d.ellipse([cx - 55, cy - 55, cx + 55, cy + 55], fill=(0, 0, 0), outline=(90, 62, 20), width=3)


def icon_chaos(d, cx, cy):
    t = np.linspace(0, 1, 200)
    for k, c in enumerate((GOLD, BLUE, CREAM)):
        xs = cx - 130 + 260 * t
        ys = cy + 50 * np.sin(2 * np.pi * (2 + k * 0.17) * t + k) * (0.3 + t)
        d.line(list(zip(xs, ys)), fill=c, width=4)


def icon_chip(d, cx, cy):
    d.rounded_rectangle([cx - 80, cy - 80, cx + 80, cy + 80], 14, outline=CREAM, width=4)
    for i in range(4):
        for j in range(4):
            x, y = cx - 54 + 36 * i, cy - 54 + 36 * j
            d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=GOLD if (i + j) % 3 else BLUE)
    for i in range(5):
        o = -64 + 32 * i
        for (a, bb) in (((cx + o, cy - 80), (cx + o, cy - 104)), ((cx + o, cy + 80), (cx + o, cy + 104)),
                        ((cx - 80, cy + o), (cx - 104, cy + o)), ((cx + 80, cy + o), (cx + 104, cy + o))):
            d.line([a, bb], fill=DIM, width=3)


def beat8(fr, d, b, u):
    header(d, "Why it matters")
    cards = [("Black holes", ["thought to be nature's", "fastest scramblers"], icon_blackhole),
             ("Quantum chaos", ["tells chaotic quantum", "systems from solvable ones"], icon_chaos),
             ("Testing quantum computers", ["checks for genuinely", "complex quantum work"], icon_chip)]
    cw, gap = 500, 60
    x0 = W / 2 - (3 * cw + 2 * gap) / 2
    for i, (title, lines, icon) in enumerate(cards):
        a = ramp(u, cue_t(b, i + 1, 0.0), cue_t(b, i + 1, 0.0) + 0.6)
        if a <= 0:
            continue
        x = x0 + i * (cw + gap)
        d.rounded_rectangle([x, 220, x + cw, 820], 26, fill=fade((34, 29, 25), a), outline=fade(MID, a), width=2)
        if a > 0.5:
            icon(d, x + cw / 2, 400)
        text_c(d, (x + cw / 2, 610), title, F_BOLD(38), fade(CREAM, a))
        for j, ln in enumerate(lines):
            text_c(d, (x + cw / 2, 670 + 42 * j), ln, F_REG(30), fade(DIM, a))


def small_heat(fr, d, F, x, y, label, sub):
    cw, ch = 17, 20
    rgb = cmap(F.real)
    big = np.repeat(np.repeat(rgb, ch, axis=0), cw, axis=1)
    big[ch - 1::ch, :] = BG
    big[:, cw - 1::cw] = BG
    fr.paste(Image.fromarray(big.astype(np.uint8)), (x, y))
    text_c(d, (x, y - 50), label, F_BOLD(34), CREAM, "lm")
    text_c(d, (x, y - 16), sub, F_REG(22), DIM, "lm")


def beat9(fr, d, b, u):
    dur = b["dur"]
    end = ramp(u, dur - 4.0, dur - 3.0)
    if end < 1:
        header(d, "Made on Moth Atlas")
        small_heat(fr, d, F_C, 160, 300, "Control  (θzz = π, Clifford)", f"otoc-echo-v1 · job {REC_C['job_id'][:8]}")
        small_heat(fr, d, F_S, 1000, 300, "Scrambling  (θzz = 0.35π)", f"otoc-echo-v1 · job {REC_S['job_id'][:8]}")
        info = ["12-qubit chain · Z nudge on qubit 6 · θx = 0.3π · 32 echo steps · exact expectation values",
                f"z-field comparison (beat 7): θz = 0.25π, job {REC_Z['job_id'][:8]}",
                "Quantum: otoc-echo-v1 (aer emulator, noiseless, not hardware) · egg frames: blur-v1, telablur-v1",
                "Classical: animation, compositing, music, captions, placeholder voice (offline text-to-speech)"]
        for i, s in enumerate(info):
            text_c(d, (W / 2, 640 + 46 * i), s, F_REG(26), DIM if i else CREAM)
    if end > 0:
        bgimg = Image.blend(Image.new("RGB", (W, H), BG), B_FULL, 0.45 * end)
        fr.paste(Image.blend(fr, bgimg, end))
        dd = ImageDraw.Draw(fr)
        text_c(dd, (W / 2, 420), "Why you can't", F_BOLD(84), fade(CREAM, end))
        text_c(dd, (W / 2, 520), "unscramble an egg", F_BOLD(84), fade(CREAM, end))
        text_c(dd, (W / 2, 610), "(quantum edition)", F_LIGHT(50), fade(GOLD, end))
        text_c(dd, (W / 2, 700), "data: Moth Quantum Atlas · otoc-echo-v1", F_REG(30), fade(CREAM, end))


BEAT_FN = {1: beat1, 2: beat2, 3: beat3, 4: beat4, 5: beat5, 6: beat6, 7: beat7, 8: beat8, 9: beat9}


def caption(fr, b, u):
    for a, e, text in b["cues"]:
        if a - 0.1 <= u <= e + 0.3:
            d = ImageDraw.Draw(fr, "RGBA")
            f = F_REG(42)
            lines = wrap(d, text, f, 1500)
            lh = 56
            bh = lh * len(lines) + 36
            bw = max(d.textlength(ln, font=f) for ln in lines) + 80
            top = 1040 - bh
            d.rounded_rectangle([W / 2 - bw / 2, top, W / 2 + bw / 2, 1040], 18, fill=(0, 0, 0, 185))
            for i, ln in enumerate(lines):
                d.text((W / 2, top + 18 + lh * i + lh / 2), ln, font=f, fill=CREAM, anchor="mm")
            return


def render_frame(beats, total, tg):
    b = next((x for x in beats if x["t0"] <= tg < x["t0"] + x["dur"]), beats[-1])
    u = tg - b["t0"]
    fr = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(fr)
    BEAT_FN[b["n"]](fr, d, b, u)
    a = min(ramp(u, 0, 0.35), 1 - ramp(u, b["dur"] - 0.35, b["dur"])) if b["n"] not in (1,) else 1 - ramp(u, b["dur"] - 0.35, b["dur"])
    if b["n"] == 1:
        a = min(ramp(u, 0, 0.6), a)
    if b["n"] == 9:
        a = min(ramp(u, 0, 0.35), 1 - ramp(u, b["dur"] - 0.8, b["dur"]))
    if a < 1:
        fr = Image.blend(Image.new("RGB", (W, H), BG), fr, max(a, 0))
    caption(fr, b, u)
    d = ImageDraw.Draw(fr)
    d.rectangle([0, H - 5, int(W * tg / total), H], fill=GOLD)
    return fr


# ---------------------------------------------------------------- audio

def tone_bed(total, beats):
    """Soft classical pad; in the scrambling beat its detune follows the measured mean |F| (a classical mapping)."""
    n = int(total * SR)
    t = np.arange(n) / SR
    chords = {1: [146.83, 220.0, 293.66], 2: [130.81, 196.0, 261.63], 3: [146.83, 220.0, 349.23],
              4: [116.54, 174.61, 233.08], 5: [130.81, 196.0, 261.63], 6: [110.0, 164.81, 220.0],
              7: [116.54, 174.61, 233.08], 8: [130.81, 196.0, 293.66], 9: [146.83, 220.0, 293.66]}
    out = np.zeros(n)
    for b in beats:
        i0, i1 = int(b["t0"] * SR), min(n, int((b["t0"] + b["dur"]) * SR))
        seg_t = t[i0:i1] - b["t0"]
        L = i1 - i0
        env = np.minimum(1, seg_t / 1.2) * np.minimum(1, (b["dur"] - seg_t) / 1.2)
        det = np.zeros(L)
        if b["n"] == 6:
            cols = NT * np.clip((seg_t - 0.6) / (b["dur"] - 2.4), 0, 1)
            det = np.interp(cols, np.arange(NT) + 1, 1 - MEAN_S) * 0.02
        seg = np.zeros(L)
        for k, f0 in enumerate(chords[b["n"]]):
            for dv in (-1, 1):
                fr = f0 * (1 + dv * (0.0015 + det))
                ph = 2 * np.pi * np.cumsum(fr) / SR
                seg += (0.5 / (k + 1)) * (np.sin(ph) + 0.25 * np.sin(2 * ph))
        out[i0:i1] += seg * env
    xf = int(1.0 * SR)
    sm = np.convolve(out, np.ones(64) / 64, mode="same")
    sm[:xf] *= np.linspace(0, 1, xf)
    return sm / np.max(np.abs(sm))


def moving_avg(x, k):
    c = np.concatenate([[0.0], np.cumsum(x)])
    lo = np.clip(np.arange(len(x)) - k // 2, 0, len(x))
    hi = np.clip(lo + k, 0, len(x))
    return (c[hi] - c[lo]) / k


def build_audio(beats, total):
    music = tone_bed(total, beats) * 0.22
    n = len(music)
    stem, sr = sf.read(ROOT / "media" / "stem_full.wav", dtype="float32", always_2d=True)
    assert sr == SR
    stem = stem.mean(axis=1)
    b1 = beats[0]
    L = int(b1["dur"] * SR)
    st = stem[int(20 * SR): int(20 * SR) + L]
    st = st / (np.max(np.abs(st)) + 1e-9) * 0.35
    env = np.minimum(1, np.arange(len(st)) / (0.5 * SR)) * np.minimum(1, (len(st) - np.arange(len(st))) / (2.5 * SR))
    music[:len(st)] += st * env
    vo = np.zeros(n)
    for b in beats:
        for (a, _, _), c in zip(b["cues"], b["clips"]):
            i = int((b["t0"] + a) * SR)
            vo[i:i + len(c)] += c[: n - i]
    vo = vo / (np.max(np.abs(vo)) + 1e-9) * 0.85
    duck = moving_avg((np.abs(vo) > 0.01).astype(float), int(0.4 * SR))
    duck = 1 - 0.55 * np.clip(duck * 4, 0, 1)
    mix_vo = vo + music[:n] * duck
    mix_music = music[:n] * 1.6
    for x in (mix_vo, mix_music):
        x /= max(1.0, np.max(np.abs(x)) / 0.95)
    sf.write(EDU / "vo_placeholder.wav", vo.astype(np.float32), SR, subtype="PCM_16")
    sf.write(BUILD / "mix_vo.wav", mix_vo.astype(np.float32), SR, subtype="PCM_16")
    sf.write(BUILD / "mix_music.wav", mix_music.astype(np.float32), SR, subtype="PCM_16")


def srt(beats, path):
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    rows, k = [], 1
    for b in beats:
        for a, e, text in b["cues"]:
            rows.append(f"{k}\n{ts(b['t0'] + a)} --> {ts(b['t0'] + e + 0.3)}\n{text}\n")
            k += 1
    path.write_text("\n".join(rows), encoding="utf-8")


# ---------------------------------------------------------------- main

def main(mode="full"):
    BUILD.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    beats = parse_script()
    tts_lines(beats)
    total = build_timeline(beats)
    timeline = [{"n": b["n"], "title": b["title"], "t0": round(b["t0"], 3), "dur": round(b["dur"], 3),
                 "cues": [[round(a, 3), round(e, 3), s] for a, e, s in b["cues"]]} for b in beats]
    (BUILD / "timeline.json").write_text(json.dumps({"total": total, "beats": timeline}, indent=1), encoding="utf-8")
    print(f"total {total:.2f} s; beats " + ", ".join(f"{b['n']}:{b['dur']:.1f}" for b in beats))
    if mode == "stills":
        sd = BUILD / "stills"
        sd.mkdir(exist_ok=True)
        for b in beats:
            for frac in (0.5, 0.92):
                render_frame(beats, total, b["t0"] + b["dur"] * frac).save(sd / f"b{b['n']}_{int(frac * 100)}.png")
        return
    build_audio(beats, total)
    srt(beats, OUT / "scrambled_explained.srt")
    video = BUILD / "video.mp4"
    nframes = int(round(total * FPS))
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                          "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video)],
                         stdin=subprocess.PIPE)
    for i in range(nframes):
        p.stdin.write(render_frame(beats, total, i / FPS).tobytes())
        if i % 300 == 0:
            print(f"frame {i}/{nframes}", flush=True)
    p.stdin.close()
    assert p.wait() == 0
    for wav, name in ((BUILD / "mix_music.wav", "scrambled_explained.mp4"), (BUILD / "mix_vo.wav", "scrambled_explained_vo.mp4")):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(wav),
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                        "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                        str(OUT / name)], check=True)
    step = total / 12
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "scrambled_explained_vo.mp4"),
                    "-vf", f"fps=1/{step:.4f},scale=640:-1,tile=4x3", "-frames:v", "1",
                    str(OUT / "contact_sheet.jpg")], check=True)
    print("done", OUT)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "full")
