"""Run the planner over a set of tracks and settings; print a results table (race seconds)."""
import argparse
import itertools
import time

from dirtbike import planner as P
from dirtbike import runio as R
from dirtbike import sim as S

TRACKS = ["Speed", "Hill Climb", "Ups and Downs", "Watch That Drop", "beginner", "expert"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--tracks", default=",".join(TRACKS), help="comma list of track specs (see tools/plan.py --track)")
    ap.add_argument("--bike", default="expert", help="bike spec")
    ap.add_argument("--beams", default="1000,3000", help="comma list of beam widths")
    ap.add_argument("--modes", default="auto,manual", help="comma list: auto,manual")
    ap.add_argument("--vel-weights", default="0.3", help="comma list of vel_weight values")
    ap.add_argument("--physics", default="original", help="comma list of physics cores: original,improved")
    a = ap.parse_args()
    print(f"{'track':16s} {'physics':8s} {'mode':6s} {'beam':>5s} {'velw':>5s} {'result':>10s} {'crashes':>7s} {'wall':>6s}  high scores")
    for spec in a.tracks.split(","):
        t, tr, label = R.resolve_track(spec)
        hs = ", ".join(f"{r.samples[-1][-1] / 1000:.1f}" for r in tr.replays) if tr else ""
        for phys, mode, beam, vw in itertools.product(a.physics.split(","), a.modes.split(","), map(int, a.beams.split(",")),
                                                      map(float, a.vel_weights.split(","))):
            pp = P.PlanParams(beam_width=beam, manual_shift=mode == "manual", vel_weight=vw)
            t0 = time.time()
            acts, ok, b, g = P.plan(t, S.make_bike(R.resolve_bike(a.bike), physics=phys), pp, progress=False)
            res = f"{b.finish_time / 1000:.3f}s" if ok else "DNF"
            print(f"{label[:16]:16s} {phys:8s} {mode:6s} {beam:5d} {vw:5.2f} {res:>10s} {b.crashes:7d} {time.time() - t0:5.1f}s  {hs}", flush=True)


if __name__ == "__main__":
    main()
