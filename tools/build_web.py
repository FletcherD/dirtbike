"""Build the web game in web/: compile the physics cores to WebAssembly (web/physics.js, wasm embedded),
export the sample tracks + high-score ghosts (web/tracks.js) and the original sound effects (web/sounds.js,
from web/sounds/*.wav made by tools/extract_sounds.py). Everything loads via <script> tags, so
web/index.html also works straight from the filesystem.
physics.js is not committed (CI builds it with --only wasm); tracks.js and sounds.js need the original game
files, so they are built locally and committed."""
import argparse
import base64
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_TRACKS = ["Speed", "Ups and Downs", "Watch That Drop", "Hill Climb"]
SOUNDS = {128: "engine", 129: "go", 130: "crash", 131: "lap", 132: "bottom", 133: "whoa", 134: "hooray"}
PARTS = ("wasm", "tracks", "sounds")


def build_wasm(out):
    src = [ROOT / "sim" / n for n in ("webapi.c", "dbcore.c", "db2core.c")]
    cmd = ["emcc", "-O2", "-fwrapv", *map(str, src), "-o", str(out),
           "-sMODULARIZE=1", "-sEXPORT_NAME=DirtBikePhysics", "-sSINGLE_FILE=1", "-sENVIRONMENT=web",
           "-sEXPORTED_RUNTIME_METHODS=['HEAP32','HEAPF64']", "-sALLOW_MEMORY_GROWTH=0"]
    subprocess.check_call(cmd)


def build_tracks(out):
    from dirtbike import formats as F
    tracks = []
    for name in SAMPLE_TRACKS:
        t = F.load_track(ROOT / "game" / "Dirt Bike 4.3" / "Sample Tracks" / name)
        tracks.append({"name": name, "description": t.description, "laps": t.laps, "allow_get_back": t.allow_get_back,
                       "points": [list(p) for p in t.points],
                       "ghosts": [{"name": r.name, "radii": list(r.radii), "samples": [list(s) for s in r.samples]}
                                  for r in t.replays]})
    out.write_text("window.DB_TRACKS = " + json.dumps(tracks, separators=(",", ":")) + ";\n")


def build_sounds(out, sound_dir):
    snd = {}
    for rid, key in SOUNDS.items():
        f = sound_dir / f"snd{rid}.wav"
        if f.exists():
            snd[key] = "data:audio/wav;base64," + base64.b64encode(f.read_bytes()).decode()
    out.write_text("window.DB_SOUNDS = " + json.dumps(snd) + ";\n")
    return sorted(snd)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--web", default=str(ROOT / "web"), help="web game directory")
    ap.add_argument("--only", choices=PARTS, nargs="+", default=list(PARTS), help="parts to build")
    a = ap.parse_args()
    web = Path(a.web)
    outputs = {"wasm": "physics.js", "tracks": "tracks.js", "sounds": "sounds.js"}
    if "wasm" in a.only:
        build_wasm(web / outputs["wasm"])
    if "tracks" in a.only:
        build_tracks(web / outputs["tracks"])
    if "sounds" in a.only:
        print("sounds:", build_sounds(web / outputs["sounds"], web / "sounds"))
    for part in a.only:
        print(f"{outputs[part]}: {(web / outputs[part]).stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
