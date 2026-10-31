"""Shared CLI helpers: resolve track/bike arguments, write run JSON, render the HTML viewer."""
import json
from pathlib import Path

from . import formats as F
from . import sim as S

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "game" / "Dirt Bike 4.3" / "Sample Tracks"
FRAME_KEYS = ["race_time", "state", "x", "y", "fwx", "fwy", "rwx", "rwy", "angle_deg", "theta_mrad", "gear",
              "rpm", "throttle", "vx", "vy", "front_ext", "rear_ext", "laps_done", "crashes", "rear_touch", "front_touch",
              "engine_started", "wheel_angle_f", "wheel_angle_r"]


def add_track_args(ap):
    ap.add_argument("--track", default="Speed",
                    help="track file path, a sample track name, 'beginner', 'expert', or 'seed:N' (random generator)")
    ap.add_argument("--bike", default="expert", help="'expert', 'beginner', or a BIKE/setup file path")
    ap.add_argument("--frame-units", type=int, default=200,
                    help="time per frame in dt units (83us each on the original; 200 = 4 substeps of dt=50)")
    ap.add_argument("--physics", choices=S.PHYSICS, default="original",
                    help="physics core: bit-exact original, or improved (sim/db2core.h)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help=f"improved-core tunable override, repeatable; keys: {', '.join(S.CONFIG2_FIELDS)}")


def apply_config(a):
    """Apply --set overrides to the improved core; returns its config."""
    kw = {}
    for item in a.set:
        k, _, v = item.partition("=")
        kw[k] = float(v)
    return S.set_config2(**kw)


def resolve_track(arg):
    """Returns (TrackC, formats.Track or None, label)."""
    low = arg.lower()
    if low == "beginner":
        return S.make_track(seed=F.BEGINNER_SEED), None, "Beginner's Track"
    if low == "expert":
        return S.make_track(seed=F.EXPERT_SEED), None, "Expert's Track"
    if low.startswith("seed:"):
        s = int(arg[5:], 0) & 0xFFFFFFFF
        return S.make_track(seed=s), None, f"Random track {s}"
    p = Path(arg)
    if not p.exists():
        p = SAMPLE_DIR / arg
    tr = F.load_track(p)
    return S.make_track(tr), tr, p.name


def resolve_bike(arg):
    if arg == "expert":
        return F.expert_bike()
    if arg == "beginner":
        return F.beginner_bike()
    return F.load_bike(arg)


def _round(v):
    return round(v, 3) if isinstance(v, float) else v


def run_record(t, label, bike_params, frames, extra, physics="original"):
    return {
        "physics": physics,
        "physics_config": S.get_config2() if physics == "improved" else None,
        "track": {"label": label, "laps": t.laps, "allow_get_back": t.allow_get_back,
                  "lap_length": S.lap_length(t), "points": S.track_points(t)},
        "bike": bike_params,
        "frames": [[_round(f[k]) for k in FRAME_KEYS] for f in frames],
        "frame_keys": FRAME_KEYS,
        **extra,
    }


def write_run(path, rec, replays=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    if replays:
        rec["ghosts"] = [{"name": r.name, "samples": r.samples} for r in replays]
    path.write_text(json.dumps(rec))
    html = path.with_suffix(".html")
    html.write_text(VIEWER_TEMPLATE.read_text().replace("__DATA__", json.dumps(rec)))
    return path, html


VIEWER_TEMPLATE = Path(__file__).resolve().parent / "viewer.html"
