"""Build Scrambled Echo (core tests + VST3) for Windows x64 with no Visual Studio needed.

Toolchain: zig's bundled clang targeting x86_64-windows-gnu (pip package `ziglang`), DPF for the plugin
framework. Everything is statically linked.

    .venv\\Scripts\\python plugin\\build.py            # core tests, then the VST3
    .venv\\Scripts\\python plugin\\build.py --clean
"""
import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
DPF = HERE / "third_party" / "DPF"
SRC = HERE / "src"
BUILD = HERE / "build"
DIST = HERE / "dist"
VERSION = "2.0.0"
ZIG = [sys.executable, "-m", "ziglang"]
TARGET = ["-target", "x86_64-windows-gnu"]
OPT = ["-O2", "-DNDEBUG", "-ffunction-sections", "-fdata-sections"]

DGL_COMMON = ["Application", "ApplicationPrivateData", "Color", "EventHandlers", "Geometry", "ImageBase",
              "ImageBaseWidgets", "Layout", "Resources", "SubWidget", "SubWidgetPrivateData", "TopLevelWidget",
              "TopLevelWidgetPrivateData", "Widget", "WidgetPrivateData", "Window", "WindowPrivateData",
              "OpenGL", "OpenGL2", "NanoVG", "pugl"]
GL_DEFS = ["-DDGL_OPENGL", "-DHAVE_OPENGL", "-DHAVE_DGL", "-DDGL_USE_FILE_BROWSER"]
DGL_FLAGS = GL_DEFS + ["-DDONT_SET_USING_DGL_NAMESPACE", "-Wno-unused-parameter", "-Wno-deprecated-declarations",
                       f"-I{DPF / 'dgl'}", f"-I{DPF / 'dgl' / 'src'}",
                       f"-I{DPF / 'dgl' / 'src' / 'pugl-upstream' / 'include'}"]
PLUGIN_FLAGS = GL_DEFS + ["-DDISTRHO_PLUGIN_TARGET_VST3", f"-I{SRC}", f"-I{DPF / 'distrho'}", f"-I{DPF / 'dgl'}",
                          f"-I{DPF / 'dgl' / 'src' / 'pugl-upstream' / 'include'}",
                          "-Wno-unused-parameter", "-Wno-deprecated-declarations"]
SYS_LIBS = ["-lopengl32", "-lgdi32", "-ldwmapi", "-lcomdlg32", "-lole32", "-luuid", "-lshlwapi", "-luser32",
            "-lshell32", "-lwinmm"]


DPF_URL = "https://github.com/DISTRHO/DPF.git"
DPF_COMMIT = "4238e1c7f0351bbe488d79f0899c540543ac7583"


def fetch_dpf():
    if (DPF / "distrho" / "DistrhoPlugin.hpp").exists():
        return
    DPF.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--filter=blob:none", DPF_URL, str(DPF)], check=True)
    subprocess.run(["git", "-C", str(DPF), "checkout", DPF_COMMIT], check=True)
    subprocess.run(["git", "-C", str(DPF), "submodule", "update", "--init", "--depth", "1"], check=True)


def run(cmd, label):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    errors = "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "error" in l.lower() or r.returncode)
    if r.returncode:
        raise SystemExit(f"FAILED {label}\n{errors[-6000:]}")
    return label


def compile_one(src, obj, flags, lang="c++"):
    obj.parent.mkdir(parents=True, exist_ok=True)
    std = ["-std=gnu++17"] if lang == "c++" else ["-std=gnu11"]
    return run(ZIG + [lang if lang == "c++" else "cc"] + TARGET + OPT + std + flags + ["-c", src, "-o", obj],
               src.name)


def build_tests():
    exe = BUILD / "test_core.exe"
    run(ZIG + ["c++"] + TARGET + OPT + ["-std=c++17", "-Wall", f"-I{SRC}", HERE / "tests" / "test_core.cpp",
                                         "-o", exe], "test_core")
    real = []
    for preset in sorted((HERE / "presets").glob("*.json")):
        meta = json.loads(preset.read_text(encoding="utf-8"))
        real.append(f"{preset}={meta['n_sites']}x{meta['depth']}")
    measured = HERE / "tools" / "measured.json"
    if measured.exists():
        for info in json.loads(measured.read_text(encoding="utf-8")).values():
            rec = HERE.parent / info["path"]
            if rec.exists():
                real.append(f"{rec}={info['params']['n_sites']}x{info['params']['depth']}")
    r = subprocess.run([str(exe)] + real, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode:
        raise SystemExit("core tests failed")


def build_vst3():
    fetch_dpf()
    jobs = [(DPF / "dgl" / "src" / f"{n}.cpp", BUILD / "dgl" / f"{n}.o", DGL_FLAGS) for n in DGL_COMMON]
    jobs += [(DPF / "distrho" / "DistrhoPluginMain.cpp", BUILD / "vst3" / "DistrhoPluginMain.o", PLUGIN_FLAGS),
             (DPF / "distrho" / "DistrhoUIMain.cpp", BUILD / "vst3" / "DistrhoUIMain.o", PLUGIN_FLAGS),
             (SRC / "ScrambledEchoPlugin.cpp", BUILD / "vst3" / "ScrambledEchoPlugin.o", PLUGIN_FLAGS),
             (SRC / "ScrambledEchoUI.cpp", BUILD / "vst3" / "ScrambledEchoUI.o", PLUGIN_FLAGS),
             (SRC / "EggRenderer.cpp", BUILD / "vst3" / "EggRenderer.o", [f"-I{SRC}", "-Wall", "-Wno-unused-parameter"])]

    def needs(job):
        src, obj, _ = job
        if not obj.exists():
            return True
        newest = max([src.stat().st_mtime] + [p.stat().st_mtime for p in SRC.glob("*.h*")])
        return obj.stat().st_mtime < newest if src.parent == SRC or "Main" in src.name else False

    todo = [j for j in jobs if needs(j)]
    with ThreadPoolExecutor(8) as ex:
        for label in ex.map(lambda j: compile_one(*j), todo):
            print("  cc", label)

    bundle = DIST / "ScrambledEcho.vst3"
    binary = bundle / "Contents" / "x86_64-win" / "ScrambledEcho.vst3"
    binary.parent.mkdir(parents=True, exist_ok=True)
    objs = [j[1] for j in jobs]
    run(ZIG + ["c++"] + TARGET + ["-shared", "-Wl,--gc-sections", "-s"] + objs + SYS_LIBS
        + ["-o", binary], "link ScrambledEcho.vst3")
    for stray in binary.parent.glob("*.lib"):
        stray.unlink()
    for stray in binary.parent.glob("*.pdb"):
        stray.unlink()
    print("built", binary.relative_to(HERE), f"{binary.stat().st_size // 1024} KiB")
    for old in DIST.glob("ScrambledEcho-*-win64-vst3.zip"):
        old.unlink()
    archive = DIST / f"ScrambledEcho-{VERSION}-win64-vst3.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(bundle.rglob("*")):
            z.write(f, f.relative_to(DIST))
    print("zipped", archive.relative_to(HERE), f"{archive.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--only", choices=["tests", "vst3"])
    a = ap.parse_args()
    if a.clean:
        shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(exist_ok=True)
    steps = {"tests": build_tests, "vst3": build_vst3}
    for name, fn in steps.items():
        if a.only in (None, name):
            fn()
