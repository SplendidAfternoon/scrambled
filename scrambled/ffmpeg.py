"""Thin ffmpeg/ffprobe helpers: probe, stream frames in, stream frames out, extract audio."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np


def require():
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RuntimeError(f"{tool} not found on PATH (needed for video and non-WAV audio)")


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool


def probe(path):
    require()
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        raise ValueError(f"{path} has no video stream")
    w, h = int(v["width"]), int(v["height"])
    rot = int((v.get("tags") or {}).get("rotate", 0) or 0)
    for sd in v.get("side_data_list") or []:
        rot = int(sd.get("rotation", rot) or rot)
    if abs(rot) % 180 == 90:
        w, h = h, w
    fps = float(Fraction(v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1")) or 30.0
    dur = float(v.get("duration") or d["format"].get("duration") or 0)
    return VideoInfo(w, h, fps, dur, any(s["codec_type"] == "audio" for s in d["streams"]))


def read_frames(path, width, height, fps, start=0.0, duration=None):
    """Yield RGB uint8 frames (h, w, 3), resampled to fps and scaled to width x height."""
    require()
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start}", "-i", str(path)]
    if duration:
        cmd += ["-t", f"{duration}"]
    cmd += ["-vf", f"fps={fps},scale={width}:{height}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = width * height * 3
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, np.uint8).reshape(height, width, 3)
    finally:
        p.stdout.close()
        p.wait()


def frame_at(path, t, width, height):
    """One RGB frame at (or just before the end, if t overshoots) time t."""
    require()
    n = width * height * 3
    for ss in (max(t, 0), max(t - 0.5, 0), 0):
        buf = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{ss}", "-i", str(path), "-frames:v", "1", "-vf",
                              f"scale={width}:{height}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(buf) >= n:
            return np.frombuffer(buf[:n], np.uint8).reshape(height, width, 3)
    raise ValueError(f"could not decode a frame of {path} near {t:.2f}s")


class Writer:
    """Pipe RGB frames into an H.264 MP4, optionally muxing an audio file."""

    def __init__(self, path, width, height, fps, audio=None, crf=18):
        require()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
               "-r", f"{fps}", "-i", "-"]
        if audio:
            cmd += ["-i", str(audio)]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf), "-preset", "medium",
                "-movflags", "+faststart"]
        if audio:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += [str(path)]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        self.frames = 0

    def write(self, frame):
        self.p.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
        self.frames += 1

    def close(self):
        self.p.stdin.close()
        if self.p.wait() != 0:
            raise RuntimeError("ffmpeg encode failed")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def extract_audio(path, out_wav, start=0.0, duration=None, sr=48000):
    """Decode any audio (or a video's audio track) to mono float WAV. Returns out_wav or None if no audio."""
    require()
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start}", "-i", str(path)]
    if duration:
        cmd += ["-t", f"{duration}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_f32le", str(out_wav)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not Path(out_wav).exists() or Path(out_wav).stat().st_size < 100:
        return None
    return Path(out_wav)
