"""Plan a fast race with the beam-search planner, verify by replay, and write run JSON + HTML viewer."""
import argparse
import time

from dirtbike import planner as P
from dirtbike import runio as R
from dirtbike import sim as S


def main():
    d = P.PlanParams()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    R.add_track_args(ap)
    ap.add_argument("--beam", type=int, default=d.beam_width, help="beam width")
    ap.add_argument("--frames-per-step", type=int, default=d.frames_per_step, help="frames each decision is held")
    ap.add_argument("--throttles", default=",".join(map(str, d.throttles)), help="throttle levels (0 = brake)")
    ap.add_argument("--manual-shift", action="store_true", help="planner shifts gears itself (auto transmission off)")
    ap.add_argument("--vel-weight", type=float, default=d.vel_weight, help="score bonus: seconds of forward speed")
    ap.add_argument("--bucket-x", type=int, default=d.bucket_x, help="diversity bucket: progress (mm)")
    ap.add_argument("--bucket-angle", type=int, default=d.bucket_angle, help="diversity bucket: angle (deg)")
    ap.add_argument("--bucket-vy", type=int, default=d.bucket_vy, help="diversity bucket: vertical speed (mm/s)")
    ap.add_argument("--no-crash", action="store_true", help="drop branches that crash even if the track allows getting back on")
    ap.add_argument("--crash-penalty", type=float, default=d.crash_penalty, help="score penalty per crash (mm)")
    ap.add_argument("--max-tilt", type=int, default=d.max_tilt,
                    help="reasonable-rider mode: never tilt more than this many degrees from level (0 = off)")
    ap.add_argument("--max-rpm", type=int, default=d.max_rpm,
                    help="never let rpm exceed this (0 = off); 60000 forbids the original's int overflow exploit")
    ap.add_argument("--max-seconds", type=float, default=d.max_seconds, help="give up after this much race time")
    ap.add_argument("--out", default=None, help="output JSON path (HTML viewer written alongside); default runs/<track>.json")
    a = ap.parse_args()

    R.apply_config(a)
    t, tr, label = R.resolve_track(a.track)
    bike_params = R.resolve_bike(a.bike)
    pp = P.PlanParams(throttles=[int(x) for x in a.throttles.split(",")], manual_shift=a.manual_shift,
                      frames_per_step=a.frames_per_step, beam_width=a.beam, bucket_x=a.bucket_x,
                      bucket_angle=a.bucket_angle, bucket_vy=a.bucket_vy, vel_weight=a.vel_weight,
                      allow_crash=not a.no_crash, crash_penalty=a.crash_penalty,
                      frame_units=a.frame_units, max_seconds=a.max_seconds, max_tilt=a.max_tilt, max_rpm=a.max_rpm)
    t0 = time.time()
    acts, ok, b, g = P.plan(t, S.make_bike(bike_params, physics=a.physics), pp)
    wall = time.time() - t0
    frames, b2, g2 = P.replay(t, S.make_bike(bike_params, physics=a.physics), acts, pp)
    assert (b2.finish_time, b2.x, b2.y) == (b.finish_time, b.x, b.y), "replay diverged from planner state"
    if ok:
        print(f"{label} [{a.physics}]: finished in {b.finish_time / 1000:.3f} s race time ({b.crashes} crashes), planning took {wall:.1f} s")
    else:
        print(f"{label} [{a.physics}]: NOT finished; best reached {S.progress(b, t)} mm at {g.race_time / 1000:.3f} s ({b.crashes} crashes)")
    if tr is not None and tr.replays:
        print("  recorded high scores in file:", ", ".join(f"{r.name} {r.samples[-1][-1] / 1000:.2f}s" for r in tr.replays))
    suffix = "" if a.physics == "original" else "_improved"
    out = a.out or f"runs/{label.replace(' ', '_').replace(chr(39), '')}{suffix}.json"
    rec = R.run_record(t, label, bike_params, frames, {
        "finish_time": b.finish_time if ok else None, "actions": acts,
        "action_table": pp.actions(), "plan_params": vars(pp) | {"throttles": pp.throttles}}, physics=a.physics)
    j, h = R.write_run(out, rec, tr.replays if tr is not None else None)
    print(f"  wrote {j} and {h}")


if __name__ == "__main__":
    main()
