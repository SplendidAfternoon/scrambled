"""scrambled command line: measure quantum information scrambling on Moth Atlas and apply it to your media."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

from scrambled import MODES, __version__, otoc
from scrambled.client import AtlasClient, AtlasError

DEMO_A = Path("media/prep/A_sq.jpg")
DEMO_B = Path("media/prep/B_sq.jpg")
DEMO_VIDEO = {"src": Path("media/clip_720.mp4"), "audio": Path("media/stem_full.wav"), "keyframes": 4}


def _log(args):
    return (lambda msg: None) if getattr(args, "quiet", False) else (lambda msg: print(msg, file=sys.stderr, flush=True))


def _client(args):
    if args.mode == "classical":
        return None
    return AtlasClient(mode=args.mode, cache_dir=args.cache_dir, log=_log(args))


def _params(args):
    p = otoc.OTOCParams(n_sites=args.sites, depth=args.depth, theta_x=args.theta_x,
                        theta_zz=math.pi if args.control else args.theta_zz, theta_z=args.theta_z, kick=args.kick,
                        kick_site=args.kick_site, machine=args.machine)
    return p


def _otoc_map(args, client):
    if getattr(args, "otoc", None):
        return otoc.load(args.otoc)
    return otoc.measure(_params(args), mode=args.mode, client=client, timeout=args.timeout)


def _label(omap, ladder_source, paired=True):
    if omap.source == "classical" and ladder_source in (None, "classical"):
        return "CLASSICAL MODE: numpy OTOC simulation + Gaussian blur (no quantum)"
    q = "Atlas otoc-echo-v1" + (" (emulator)" if (omap.backend or "aer") == "aer" else f" ({omap.backend})")
    if omap.source == "classical":
        q = "numpy OTOC (classical)"
    if ladder_source == "atlas":
        return f"{q} + blur-v1/telablur-v1" if paired else f"{q} + blur-v1"
    if ladder_source == "classical":
        return f"{q} + Gaussian blur (classical)"
    return q


def _provenance(path, args, omap, extra):
    side = Path(str(path) + ".json")
    d = {"tool": f"scrambled {__version__}", "command": args.command, "mode": args.mode,
         "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "otoc": omap.summary(), **extra}
    side.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
    return side


# -- commands -------------------------------------------------------------------------------------------------
def cmd_measure(args):
    client = _client(args)
    m = otoc.measure(_params(args), mode=args.mode, client=client, timeout=args.timeout)
    m.save(args.output)
    s = m.summary()
    s.pop("params", None)
    print(json.dumps({**s, "saved": str(args.output)}, indent=2))
    return 0


def _ladders(args, client, src, pair):
    from scrambled import image
    size = image.working_size(src, args.max_side)
    if args.mode == "classical":
        return image.classical_ladders(image.load_rgb(src, size), image.load_rgb(pair, size) if pair else None)
    return image.atlas_ladders(client, src, pair, size=size, timeout=args.timeout, log=_log(args))


def cmd_image(args):
    from scrambled import image
    client = _client(args)
    omap = _otoc_map(args, client)
    lad = _ladders(args, client, args.input, args.pair)
    label = _label(omap, lad.source, paired=bool(args.pair))
    out = image.scramble_image(args.input, args.output, omap, lad, seconds=args.seconds, fps=args.fps, at=args.at,
                               show_overlay=not args.no_overlay, label=label)
    side = _provenance(out, args, omap, {"input": str(args.input), "pair": str(args.pair) if args.pair else None,
                                         "label": label, "ladder_jobs": lad.jobs})
    print(f"wrote {out}\nprovenance {side}")
    return 0


def cmd_audio(args):
    from scrambled.audio import scramble_audio
    client = _client(args)
    omap = _otoc_map(args, client)
    rep = scramble_audio(args.input, args.output, omap, mix=args.mix, master_ms=args.master_ms,
                         engine=args.engine and client is not None, client=client, timeout=args.engine_timeout,
                         log=_log(args))
    side = _provenance(args.output, args, omap, {"input": str(args.input), "audio": rep})
    print(f"wrote {args.output} ({rep['renderer']})\nprovenance {side}")
    return 0


def cmd_video(args):
    from scrambled.video import scramble_video
    client = _client(args)
    omap = _otoc_map(args, client)
    label = _label(omap, "classical" if args.mode == "classical" else "atlas", paired=args.pair != "none")
    rep = scramble_video(args.input, args.output, omap, mode=args.mode, client=client, start=args.start,
                         duration=args.duration, keyframes=args.keyframes, pair=args.pair, max_side=args.max_side,
                         fps=args.fps, show_overlay=not args.no_overlay, label=label, audio_mix=args.audio_mix,
                         audio_engine=args.audio_engine, timeout=args.timeout, audio_src=args.audio,
                         log=_log(args))
    side = _provenance(args.output, args, omap, {"input": str(args.input), "label": label, "render": rep})
    print(f"wrote {args.output} ({rep['frames']} frames, {len(rep['jobs'])} ladder jobs)\nprovenance {side}")
    return 0


def cmd_replay(args):
    """Rebuild the demo outputs from the committed cache only: no API key, no network, no credits."""
    from scrambled import image
    from scrambled.audio import scramble_audio
    from scrambled.client import ReplayMiss
    args.mode = "replay"
    client = AtlasClient(mode="replay", cache_dir=args.cache_dir, log=_log(args))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    done = []
    for name, p in (("control", otoc.OTOCParams(theta_zz=math.pi)), ("scrambling", otoc.OTOCParams())):
        omap = otoc.measure(p, mode="replay", client=client)
        omap.save(out / f"otoc_{name}.json")
        print(f"[{name}] otoc-echo-v1 job {omap.job_id}: arrivals {omap.summary()['light_cone_arrival_t']}")
        done.append(out / f"otoc_{name}.json")
        if DEMO_A.exists() and DEMO_B.exists():
            try:
                lad = image.atlas_ladders(client, DEMO_A, DEMO_B, timeout=1, log=_log(args))
                v = image.scramble_image(DEMO_A, out / f"eggs_{name}.mp4", omap, lad, seconds=args.seconds,
                                         label=_label(omap, "atlas"))
                done.append(v)
            except (ReplayMiss, RuntimeError) as e:
                print(f"skip image demo: {str(e)[:200]}")
        stem = Path("media/prep/stem_20s.wav")
        if stem.exists():
            scramble_audio(stem, out / f"echo_{name}.wav", omap)
            done.append(out / f"echo_{name}.wav")
    if args.video and DEMO_VIDEO["src"].exists():
        from scrambled.video import scramble_video
        try:
            rep = scramble_video(DEMO_VIDEO["src"], out / "eggs_scrambled.mp4", omap, mode="replay", client=client,
                                 keyframes=DEMO_VIDEO["keyframes"], audio_src=DEMO_VIDEO["audio"],
                                 label=_label(omap, "atlas"), log=_log(args))
            done.append(out / "eggs_scrambled.mp4")
            print(f"[video] {rep['frames']} frames from {len(rep['jobs'])} cached ladder jobs")
        except (ReplayMiss, RuntimeError) as e:
            print(f"skip video demo: {str(e)[:200]}")
    print("replayed (no network):\n  " + "\n  ".join(str(d) for d in done))
    return 0


# -- parser ---------------------------------------------------------------------------------------------------
def _angle(text):
    try:
        return otoc.parse_angle(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--mode", choices=MODES, default=os.environ.get("SCRAMBLED_MODE", "atlas"),
                        help="atlas: Moth Atlas API (cached); replay: cache only, no key/network; "
                             "classical: numpy OTOC + Gaussian blur, no quantum (labelled). Default: atlas")
    common.add_argument("--cache-dir", default=None, help="job cache (default ./cache or $SCRAMBLED_CACHE)")
    common.add_argument("--timeout", type=float, default=900, help="seconds to wait for an Atlas job (default 900)")
    common.add_argument("-q", "--quiet", action="store_true")

    phys = argparse.ArgumentParser(add_help=False)
    g = phys.add_argument_group("OTOC (otoc-echo-v1) parameters")
    g.add_argument("--otoc", type=Path, help="use a saved map (scrambled measure -o) or raw job record instead")
    g.add_argument("--sites", type=int, default=12, help="qubits in the chain = strips (default 12)")
    g.add_argument("--depth", type=int, default=32, help="echo depths t = 1..depth (max 32, default 32)")
    g.add_argument("--theta-x", type=_angle, default=0.3 * math.pi, help="transverse kick angle (default 0.3pi)")
    g.add_argument("--theta-zz", type=_angle, default=0.35 * math.pi, help="ZZ coupling angle (default 0.35pi)")
    g.add_argument("--theta-z", type=_angle, default=0.0, help="longitudinal field, breaks integrability (default 0)")
    g.add_argument("--kick", choices=("Z", "Y", "X"), default="Z")
    g.add_argument("--kick-site", type=int, default=None, help="default: centre of the chain")
    g.add_argument("--machine", default="aer", help="aer (emulator, default) or an IBM backend name")
    g.add_argument("--control", action="store_true", help="Clifford control: theta_zz = pi (cannot scramble)")

    ap = argparse.ArgumentParser(prog="scrambled", description=__doc__)
    ap.add_argument("--version", action="version", version=f"scrambled {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    m = sub.add_parser("measure", parents=[common, phys], help="measure F(site, t) and save it as JSON")
    m.add_argument("-o", "--output", type=Path, default=Path("out/otoc_map.json"))
    m.set_defaults(func=cmd_measure)

    i = sub.add_parser("image", parents=[common, phys], help="scramble an image -> PNG (one echo step) or MP4")
    i.add_argument("input", type=Path)
    i.add_argument("--pair", type=Path, help="target picture, same framing (e.g. the 'after' photo)")
    i.add_argument("-o", "--output", type=Path, required=True, help=".png/.jpg = still at --at; .mp4 = animation")
    i.add_argument("--seconds", type=float, default=8.0)
    i.add_argument("--fps", type=int, default=24)
    i.add_argument("--at", type=float, default=None, help="echo step for stills (default: last)")
    i.add_argument("--max-side", type=int, default=1024)
    i.add_argument("--no-overlay", action="store_true", help="omit the F heatmap and provenance label")
    i.set_defaults(func=cmd_image)

    a = sub.add_parser("audio", parents=[common, phys], help="echo audio through the OTOC tap map -> WAV")
    a.add_argument("input", type=Path)
    a.add_argument("-o", "--output", type=Path, required=True)
    a.add_argument("--mix", type=float, default=0.5, help="wet/dry (default 0.5)")
    a.add_argument("--master-ms", type=float, default=6400, help="delay of the deepest echo step (default 6400)")
    a.add_argument("--engine", action="store_true", help="render on Atlas retrocausal-echo-v1 (falls back locally)")
    a.add_argument("--engine-timeout", type=float, default=180)
    a.set_defaults(func=cmd_audio)

    v = sub.add_parser("video", parents=[common, phys], help="scramble a video (frames + echoed audio) -> MP4")
    v.add_argument("input", type=Path)
    v.add_argument("-o", "--output", type=Path, required=True)
    v.add_argument("--start", type=float, default=0.0)
    v.add_argument("--duration", type=float, default=None)
    v.add_argument("--keyframes", type=int, default=4, help="quantum-rendered keyframes (cost: 6 jobs each)")
    v.add_argument("--pair", default="last", help="'last' frame of the excerpt (default), 'none', or an image")
    v.add_argument("--max-side", type=int, default=720)
    v.add_argument("--fps", type=float, default=None)
    v.add_argument("--audio", type=Path, default=None, help="soundtrack to use instead of the video's own")
    v.add_argument("--audio-mix", type=float, default=0.5)
    v.add_argument("--audio-engine", action="store_true", help="try retrocausal-echo-v1 for the soundtrack")
    v.add_argument("--no-overlay", action="store_true")
    v.set_defaults(func=cmd_video)

    r = sub.add_parser("replay", parents=[common], help="rebuild the demo from the committed cache (no key)")
    r.add_argument("-o", "--output", type=Path, default=Path("out/replay"))
    r.add_argument("--seconds", type=float, default=8.0)
    r.add_argument("--video", action="store_true", help="also rebuild the 58 s scrambled cooking video (~2 min)")
    r.set_defaults(func=cmd_replay)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (AtlasError, ValueError, RuntimeError, NotImplementedError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
