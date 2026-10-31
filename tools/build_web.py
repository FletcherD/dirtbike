"""Build the web game's generated files in web/:
  wasm   - web/physics.js + web/physics.wasm from sim/ (emcc); not committed, CI builds it (--only wasm)
  tracks - web/tracks/index.json (menu summary) + one JSON per sample track (points + high-score ghosts)
  sounds - web/sounds/<event>.wav from the WAVs extracted by tools/extract_sounds.py
tracks/ and sounds/ need the original game files, so they are built locally and committed.
The game fetches these files, so serve web/ over HTTP (e.g. python3 -m http.server -d web)."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_TRACKS = ["Speed", "Ups and Downs", "Watch That Drop", "Hill Climb"]
SOUNDS = {128: "engine", 129: "go", 130: "crash", 131: "lap", 132: "bottom", 133: "whoa", 134: "hooray"}
PARTS = ("wasm", "tracks", "sounds")


def build_wasm(web):
    src = [ROOT / "sim" / n for n in ("webapi.c", "dbcore.c", "db2core.c")]
    cmd = ["emcc", "-O2", "-fwrapv", *map(str, src), "-o", str(web / "physics.js"),
           "-sMODULARIZE=1", "-sEXPORT_NAME=DirtBikePhysics", "-sENVIRONMENT=web",
           "-sEXPORTED_RUNTIME_METHODS=['HEAP32','HEAPF64']", "-sALLOW_MEMORY_GROWTH=0"]
    subprocess.check_call(cmd)
    return [web / "physics.js", web / "physics.wasm"]


def slug(name):
    return name.lower().replace(" ", "-")


def build_tracks(web):
    from dirtbike import formats as F
    out = web / "tracks"
    out.mkdir(exist_ok=True)
    index, files = [], []
    for name in SAMPLE_TRACKS:
        t = F.load_track(ROOT / "game" / "Dirt Bike 4.3" / "Sample Tracks" / name)
        fn = out / f"{slug(name)}.json"
        fn.write_text(json.dumps({
            "points": [list(p) for p in t.points],
            "ghosts": [{"name": r.name, "radii": list(r.radii), "samples": [list(s) for s in r.samples]} for r in t.replays],
        }, separators=(",", ":")))
        index.append({"name": name, "file": fn.name, "description": t.description, "laps": t.laps,
                      "allow_get_back": t.allow_get_back, "records": [r.samples[-1][7] for r in t.replays]})
        files.append(fn)
    (out / "index.json").write_text(json.dumps(index, indent=1))
    return files + [out / "index.json"]


def build_sounds(web, src_dir):
    out = web / "sounds"
    out.mkdir(exist_ok=True)
    files = []
    for rid, key in SOUNDS.items():
        shutil.copyfile(src_dir / f"snd{rid}.wav", out / f"{key}.wav")
        files.append(out / f"{key}.wav")
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--web", default=str(ROOT / "web"), help="web game directory")
    ap.add_argument("--sound-src", default=str(ROOT / "work" / "sounds"), help="WAVs from tools/extract_sounds.py")
    ap.add_argument("--only", choices=PARTS, nargs="+", default=list(PARTS), help="parts to build")
    a = ap.parse_args()
    web = Path(a.web)
    files = []
    if "wasm" in a.only:
        files += build_wasm(web)
    if "tracks" in a.only:
        files += build_tracks(web)
    if "sounds" in a.only:
        files += build_sounds(web, Path(a.sound_src))
    for f in files:
        print(f"{f.relative_to(web)}: {f.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
