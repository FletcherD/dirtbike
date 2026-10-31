"""Simulation harness: run a bike on a track with a fixed throttle (optionally changing over time) or a
saved action plan, print a state summary and write run JSON + HTML viewer."""
import argparse
import json

from dirtbike import planner as P
from dirtbike import runio as R
from dirtbike import sim as S


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    R.add_track_args(ap)
    ap.add_argument("--throttle", default="40000",
                    help="constant throttle, or schedule 't0:thr,t1:thr,...' (race seconds); 0 = brake")
    ap.add_argument("--plan", default=None, help="run JSON from tools/plan.py: replay its actions instead")
    ap.add_argument("--manual", action="store_true", help="auto transmission off (with --throttle: stays in neutral)")
    ap.add_argument("--seconds", type=float, default=60.0, help="max race seconds to simulate")
    ap.add_argument("--print-every", type=float, default=1.0, help="print state every N race seconds (0 = never)")
    ap.add_argument("--out", default=None, help="output JSON path (HTML viewer written alongside)")
    a = ap.parse_args()

    t, tr, label = R.resolve_track(a.track)
    physics = a.physics
    bike_params = R.resolve_bike(a.bike)
    if a.plan:
        run = json.load(open(a.plan))
        physics = run.get("physics", "original")
        if run.get("physics_config"):
            S.set_config2(**run["physics_config"])
        pp = P.PlanParams(**{k: v for k, v in run["plan_params"].items()})
        frames, b, g = P.replay(t, S.make_bike(bike_params, physics=physics), run["actions"], pp)
    else:
        sched = []
        for part in a.throttle.split(","):
            ts, _, thr = part.rpartition(":")
            sched.append((float(ts or 0), int(thr)))
        R.apply_config(a)
        bike = S.make_bike(bike_params, auto_trans=False if a.manual else None, physics=physics)
        race = S.Race(t, [bike], frame_units=a.frame_units)
        frames = []
        while race.g.race_time < a.seconds * 1000:
            rt = race.g.race_time / 1000
            race.bikes[0].input_throttle = [thr for ts, thr in sched if ts <= rt][-1] if race.g.state == 2 else 0
            done = race.frame()
            d = S.bike_dict(race.bikes[0])
            d.update(state=race.g.state, race_time=race.g.race_time)
            frames.append(d)
            if done:
                break
        b, g = race.bikes[0], race.g
    nxt = 0.0
    for f in frames:
        if a.print_every and f["state"] == 2 and f["race_time"] >= nxt * 1000:
            print(f"t={f['race_time'] / 1000:7.3f} x={f['x']:7.0f} y={f['y']:6.0f} ang={f['angle_deg']:3.0f} gear={f['gear']} "
                  f"rpm={f['rpm']:6.0f} vx={f['vx'] / 10000:6.2f}m/s lap={f['laps_done']} crashes={f['crashes']}")
            nxt += a.print_every
    status = f"finished {b.finish_time / 1000:.3f}s" if b.finish_time and b.finished_ok else (
        "crashed out" if b.finish_time else "not finished")
    print(f"{label} [{physics}]: {status}, progress {S.progress(b, t)} mm, crashes {b.crashes}")
    out = a.out or f"runs/sim_{label.replace(' ', '_').replace(chr(39), '')}.json"
    rec = R.run_record(t, label, bike_params, frames, {"finish_time": b.finish_time if b.finished_ok else None},
                       physics=physics)
    j, h = R.write_run(out, rec, tr.replays if tr is not None else None)
    print(f"wrote {j} and {h}")


if __name__ == "__main__":
    main()
