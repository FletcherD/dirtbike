"""Validation: search for throttle inputs that make the simulated bike follow a high-score replay
recorded by the original game (positions/angle every ~100 ms). Small tracking error over a whole race
means the ported physics reproduces the original."""
import argparse
import ctypes as C
import math

from tqdm import tqdm

from dirtbike import planner as P
from dirtbike import runio as R
from dirtbike import sim as S


def track(t, bike_params, replay, frame_units, beam, throttle_step, manual, pos_scale, theta_scale, progress=True,
          physics="original", time_scale=1.0):
    # time_scale converts the recording's race clock to this core's clock (the original under-counted
    # race time when dt was not a multiple of 10; the improved core's clock is exact)
    samples = [s[:7] + (int(round(s[7] * time_scale)),) for s in replay.samples]
    tg = (S.Target * len(samples))(*[S.Target(s[7], s[0], s[1], s[6]) for s in samples])
    throttles = list(range(0, 58800, throttle_step)) + [58800]
    pp = P.PlanParams(throttles=throttles, manual_shift=manual, frames_per_step=1, beam_width=beam,
                      frame_units=frame_units, allow_crash=True, crash_penalty=0, vel_weight=0)
    bike = S.make_bike(bike_params, auto_trans=False if manual else None, physics=physics)
    co = S.core(physics)
    g0, b0 = P.start_state(t, bike, pp)
    cfg = pp.cfg(t)
    cfg.targets = C.cast(tg, C.c_void_p)
    cfg.n_targets = len(samples)
    cfg.pos_scale, cfg.theta_scale = pos_scale, theta_scale
    max_steps = int(2 * (samples[-1][7] + 3000) / (frame_units / 10)) + 10  # race time truncation: < frame_units/10 per frame
    h = co.planner_new(C.byref(t), C.byref(g0), C.byref(b0), C.byref(cfg), max_steps)
    acts = (S.I * max_steps)()
    g, b = co.Game(), co.Bike()
    bar = tqdm(total=samples[-1][7], unit="ms", disable=not progress, desc=f"fu={frame_units}")
    while True:
        st = co.planner_run(h, 25)
        n = co.planner_best(h, acts, C.byref(g), C.byref(b))
        bar.n = min(g.race_time, samples[-1][7])
        bar.refresh()
        if st != 0:
            break
    bar.close()
    co.planner_free(h)
    actions = list(acts[:n])
    # replay and measure per-sample errors
    race = S.Race(t, [S.make_bike(bike_params, auto_trans=False if manual else None, physics=physics)], frame_units=frame_units)
    table = pp.actions()
    errs, k, frames = [], 0, []
    for a in actions:
        thr, sh = table[a]
        race.shift(sh)
        race.bikes[0].input_throttle = thr
        while True:
            r = race.substep()
            bk = race.bikes[0]
            while k < len(samples) and race.g.race_started and race.g.race_time >= samples[k][7]:
                s = samples[k]
                dth = (bk.theta_mrad - s[6] + 3141) % 6283 - 3141
                errs.append((s[7], bk.x - s[0], bk.y - s[1], dth))
                k += 1
            if r & 2:
                break
        d = S.bike_dict(race.bikes[0])
        d.update(state=race.g.state, race_time=race.g.race_time)
        frames.append(d)
    return errs, frames, st


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    R.add_track_args(ap)
    ap.add_argument("--replay", type=int, default=0, help="index of the high-score replay in the track file")
    ap.add_argument("--frame-units-list", default="200", help="comma list of frame_units to try (overrides --frame-units)")
    ap.add_argument("--beam", type=int, default=2000, help="beam width")
    ap.add_argument("--throttle-step", type=int, default=4000, help="throttle level spacing")
    ap.add_argument("--manual", action="store_true", help="also search gear shifts (auto transmission off)")
    ap.add_argument("--pos-scale", type=float, default=100.0, help="mm per unit of tracking error")
    ap.add_argument("--theta-scale", type=float, default=50.0, help="mrad per unit of tracking error")
    ap.add_argument("--time-scale", type=float, default=1.0,
                    help="multiply recorded race times (e.g. 1.1 for --physics improved vs a 66-dt-unit recording)")
    ap.add_argument("--out", default=None, help="write run JSON/HTML of the best tracking run here")
    a = ap.parse_args()
    R.apply_config(a)
    t, tr, label = R.resolve_track(a.track)
    rp = tr.replays[a.replay]
    print(f"{label}: replay {a.replay} by {rp.name}, {len(rp.samples)} samples, finish {rp.samples[-1][7] / 1000:.2f}s, radii {rp.radii}")
    best = None
    for fu in [int(x) for x in a.frame_units_list.split(",")]:
        errs, frames, st = track(t, R.resolve_bike(a.bike), rp, fu, a.beam, a.throttle_step, a.manual, a.pos_scale,
                                 a.theta_scale, physics=a.physics, time_scale=a.time_scale)
        n = len(errs)
        rms = lambda j: math.sqrt(sum(e[j] ** 2 for e in errs) / max(1, n))
        dpos = [math.hypot(e[1], e[2]) for e in errs]
        within = sum(d < 100 for d in dpos) / max(1, n)
        print(f"  frame_units={fu}: matched {n}/{len(rp.samples)} samples; RMS dx={rms(1):.0f} dy={rms(2):.0f} mm, "
              f"dtheta={rms(3):.0f} mrad; max |dpos|={max(dpos, default=0):.0f} mm; {within:.0%} within 100 mm")
        score = rms(1) + rms(2) + (1e9 if n < len(rp.samples) else 0)
        if best is None or score < best[0]:
            best = (score, fu, frames)
    if a.out:
        rec = R.run_record(t, label, R.resolve_bike(a.bike), best[2], {"finish_time": None, "frame_units": best[1]},
                           physics=a.physics)
        print("wrote", *R.write_run(a.out, rec, [rp]))


if __name__ == "__main__":
    main()
