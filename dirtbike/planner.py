"""Python driver for the C beam-search planner (sim/dbplan_impl.h) and action-sequence replay.
The physics core used is the one the bike object belongs to (sim.make_bike(..., physics=...))."""
import ctypes as C
from dataclasses import dataclass, field

from tqdm import tqdm

from . import sim as S


@dataclass
class PlanParams:
    throttles: list = field(default_factory=lambda: [0, 6000, 12000, 18000, 24000, 30000, 36000, 42000, 48000, 58800])
    manual_shift: bool = False  # add shift up/down actions (bike auto_trans forced off)
    frames_per_step: int = 3
    beam_width: int = 1000
    bucket_x: int = 150
    bucket_angle: int = 4
    bucket_vy: int = 300
    vel_weight: float = 0.3
    allow_crash: bool = True  # only takes effect on tracks that allow getting back on
    crash_penalty: float = 1000.0
    frame_units: int = 200
    max_seconds: float = 300.0
    max_tilt: int = 0  # "reasonable rider": prune branches tilting more than this from level (deg); 0 = off
    max_rpm: int = 0  # prune branches over-revving past this (0 = off); forbids the original's overflow exploit

    def actions(self):
        acts = [(t, 0) for t in self.throttles]
        if self.manual_shift:
            acts += [(t, s) for s in (1, -1) for t in self.throttles]
        return acts

    def cfg(self, t):
        c = S.PlanCfg()
        acts = self.actions()
        c.n_actions = len(acts)
        for i, (thr, sh) in enumerate(acts):
            c.throttle[i], c.shift[i] = thr, sh
        c.frames_per_step = self.frames_per_step
        c.beam_width = self.beam_width
        c.bucket_x, c.bucket_angle, c.bucket_vy = self.bucket_x, self.bucket_angle, self.bucket_vy
        c.vel_weight = self.vel_weight
        c.allow_crash = int(self.allow_crash and t.allow_get_back != 0)
        c.crash_penalty = self.crash_penalty
        c.max_tilt = self.max_tilt
        c.max_rpm = self.max_rpm
        return c


def race_length(t):
    """Progress (mm) from the start position to the finishing lap crossing."""
    return (t.laps - 1) * S.lap_length(t) + t.pts[t.n_points - 40].x - 2500


def start_state(t, bike, pp):
    """Game and bike right after Game_NewRace."""
    race = S.Race(t, [bike], frame_units=pp.frame_units)
    return race.g, race.bikes[0]


def plan(t, bike, pp, chunk=20, progress=True):
    """Full-race beam search. Returns (actions, finished, end_bike, end_game)."""
    if pp.manual_shift:
        bike.p.auto_trans = 0
    g0, b0 = start_state(t, bike, pp)
    cfg = pp.cfg(t)
    frame_ms = pp.frame_units / 10 * pp.frames_per_step  # game ms per decision step
    max_steps = int(pp.max_seconds * 1000 / frame_ms)
    co = S.core(S.physics_of(bike))
    h = co.planner_new(C.byref(t), C.byref(g0), C.byref(b0), C.byref(cfg), max_steps)
    acts = (S.I * max_steps)()
    g, b = co.Game(), co.Bike()
    total = race_length(t)
    bar = tqdm(total=total, unit="mm", disable=not progress, unit_scale=True)
    try:
        while True:
            st = co.planner_run(h, chunk)
            n = co.planner_best(h, acts, C.byref(g), C.byref(b))
            done = min(total, S.progress(b, t) - 2500)
            bar.n = max(0, done)
            bar.set_postfix(t=f"{g.race_time / 1000:.2f}s", crashes=b.crashes)
            bar.refresh()
            if st != 0:
                break
    finally:
        bar.close()
        co.planner_free(h)
    return list(acts[:n]), st == 1, b, g


def replay(t, bike, actions, pp):
    """Re-run an action sequence frame by frame. Returns (frames, bike, game); frames is a list of
    per-frame dicts (race state + bike state) for analysis/visualisation."""
    if pp.manual_shift:
        bike.p.auto_trans = 0
    race = S.Race(t, [bike], frame_units=pp.frame_units)
    acts = pp.actions()
    frames = []
    for a in actions:
        thr, sh = acts[a]
        race.shift(sh)
        race.bikes[0].input_throttle = thr
        for _ in range(pp.frames_per_step):
            race.frame()
            d = S.bike_dict(race.bikes[0])
            d.update(state=race.g.state, race_time=race.g.race_time, action=a)
            frames.append(d)
            if race.bikes[0].finish_time:
                break
        if race.bikes[0].finish_time:
            break
    return frames, race.bikes[0], race.g
