import json
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from scrambled import cli

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
SMALL = ["--mode", "classical", "--sites", "6", "--depth", "8", "-q"]


@pytest.fixture
def tiny_image(tmp_path):
    y, x = np.mgrid[0:48, 0:64]
    arr = np.stack([x * 4, y * 5, (x + y) * 2], axis=-1).astype(np.uint8)
    p = tmp_path / "in.png"
    Image.fromarray(arr).save(p)
    return p


def test_help_lists_all_commands(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for cmd in ("measure", "image", "audio", "video", "replay"):
        assert cmd in out


def test_measure_classical_writes_a_loadable_map(tmp_path, capsys):
    out = tmp_path / "m.json"
    assert cli.main(["measure", *SMALL, "-o", str(out)]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["source"] == "classical" and s["shape"] == [6, 8] and s["kick_site"] == 3
    from scrambled import otoc
    assert otoc.load(out).F.shape == (6, 8)


def test_control_flag_gives_clifford_map(tmp_path, capsys):
    out = tmp_path / "c.json"
    assert cli.main(["measure", *SMALL, "--control", "-o", str(out)]) == 0
    from scrambled import otoc
    F = otoc.load(out).F
    assert np.allclose(np.abs(F), 1) and (F.real < 0).sum(axis=1).tolist() == [0, 0, 0, 8, 0, 0]


def test_image_still_classical_is_labelled_and_changed(tiny_image, tmp_path):
    out = tmp_path / "out.png"
    assert cli.main(["image", str(tiny_image), "-o", str(out), *SMALL]) == 0
    a = np.asarray(Image.open(tiny_image), np.float32)
    b = np.asarray(Image.open(out), np.float32)
    assert b.shape == a.shape and np.abs(a - b).mean() > 5
    prov = json.loads((tmp_path / "out.png.json").read_text(encoding="utf-8"))
    assert prov["mode"] == "classical" and "CLASSICAL" in prov["label"]


def test_image_rings_layout_differs_from_strips_and_is_recorded(tiny_image, tmp_path):
    strips, rings = tmp_path / "s.png", tmp_path / "r.png"
    assert cli.main(["image", str(tiny_image), "-o", str(strips), *SMALL, "--no-overlay"]) == 0
    assert cli.main(["image", str(tiny_image), "-o", str(rings), *SMALL, "--no-overlay", "--layout", "rings"]) == 0
    a = np.asarray(Image.open(strips), np.float32)
    b = np.asarray(Image.open(rings), np.float32)
    assert np.abs(a - b).mean() > 2
    assert json.loads((tmp_path / "r.png.json").read_text(encoding="utf-8"))["layout"] == "rings"


def test_audio_classical_echo_is_longer_stereo_and_finite(tmp_path):
    sr = 16000
    t = np.arange(sr // 2) / sr
    src = tmp_path / "in.wav"
    sf.write(src, (0.5 * np.sin(2 * np.pi * 440 * t) * (t < 0.1)).astype(np.float32), sr)
    out = tmp_path / "out.wav"
    assert cli.main(["audio", str(src), "-o", str(out), *SMALL, "--master-ms", "400"]) == 0
    y, r = sf.read(out, always_2d=True)
    assert r == sr and y.shape[1] == 2 and len(y) > sr // 2 and np.isfinite(y).all()
    assert np.abs(y[int(0.2 * sr):]).max() > 0.01, "echo taps should sound after the dry blip ends"


@needs_ffmpeg
def test_image_animation_and_video_classical(tiny_image, tmp_path):
    anim = tmp_path / "anim.mp4"
    assert cli.main(["image", str(tiny_image), "-o", str(anim), *SMALL, "--seconds", "1", "--fps", "8"]) == 0
    assert anim.stat().st_size > 1000
    vid = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=96x64:rate=12:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=2", "-shortest", "-pix_fmt", "yuv420p",
                    str(vid)], check=True)
    out = tmp_path / "vout.mp4"
    assert cli.main(["video", str(vid), "-o", str(out), *SMALL, "--keyframes", "2"]) == 0
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                            str(out)], capture_output=True, text=True, check=True).stdout.split()
    assert sorted(probe) == ["audio", "video"]
    prov = json.loads((tmp_path / "vout.mp4.json").read_text(encoding="utf-8"))
    assert prov["render"]["frames"] == 24 and prov["render"]["jobs"] == []


@needs_ffmpeg
def test_replay_rebuilds_the_demo_with_no_key_and_no_network(tmp_path, monkeypatch):
    from pathlib import Path

    from scrambled import client as C
    root = Path(__file__).resolve().parents[1]
    if not (root / "cache" / "files").exists():
        pytest.skip("cache/files not present (run the atlas demo once)")
    monkeypatch.chdir(root)
    monkeypatch.setenv("MOTH_API_KEY", "")

    def no_network(*a, **k):
        raise AssertionError("replay touched the network")

    monkeypatch.setattr(C.requests, "request", no_network)
    monkeypatch.setattr(C.requests, "get", no_network)
    monkeypatch.setattr(C.requests, "put", no_network)
    assert cli.main(["replay", "-o", str(tmp_path), "--seconds", "0.25", "-q"]) == 0
    for name in ("otoc_control.json", "otoc_scrambling.json", "eggs_control.mp4", "eggs_scrambling.mp4",
                 "echo_scrambling.wav"):
        assert (tmp_path / name).stat().st_size > 0, name


def test_bad_input_returns_error_code_not_traceback(tmp_path, capsys):
    assert cli.main(["image", str(tmp_path / "missing.png"), "-o", str(tmp_path / "x.png"), *SMALL]) == 2
    assert "error:" in capsys.readouterr().err


def test_classical_mode_accepts_theta_z_now_verified_against_atlas(tiny_image, tmp_path):
    out = tmp_path / "x.png"
    assert cli.main(["image", str(tiny_image), "-o", str(out), *SMALL, "--theta-z", "0.1"]) == 0
    assert out.exists()
