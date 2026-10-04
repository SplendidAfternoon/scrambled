"""Contact sheet: 4x4 grid of frames sampled evenly from a video (or from a folder of PNGs).

    ..\\.venv\\Scripts\\python contact_sheet.py out/quantum_egg.mp4 out/quantum_egg_contact.jpg
    ..\\.venv\\Scripts\\python contact_sheet.py out/stills out/stills_contact.jpg
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

COLS, ROWS, CELL = 4, 4, 360


def frames_from_video(path, n):
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", str(path)]).decode().strip())
    tmp = Path(tempfile.mkdtemp())
    out = []
    for k in range(n):
        t = dur * (k + 0.5) / n
        f = tmp / f"c{k:02d}.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(path),
                        "-frames:v", "1", str(f)], check=True)
        out.append((f"{t:5.1f}s", f))
    return out


def main(src, dst):
    src = Path(src)
    items = ([(p.stem.split("_")[-1].lstrip("0") + "s", p) for p in sorted(src.glob("still_*.png"))]
             if src.is_dir() else frames_from_video(src, COLS * ROWS))
    sheet = Image.new("RGB", (COLS * CELL, ROWS * CELL), "black")
    d = ImageDraw.Draw(sheet)
    for k, (label, p) in enumerate(items[:COLS * ROWS]):
        x, y = (k % COLS) * CELL, (k // COLS) * CELL
        sheet.paste(Image.open(p).convert("RGB").resize((CELL, CELL), Image.LANCZOS), (x, y))
        d.text((x + 8, y + CELL - 20), label, fill=(255, 255, 255))
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dst, quality=90)
    print("wrote", dst, len(items), "frames")


if __name__ == "__main__":
    main(*sys.argv[1:3])
