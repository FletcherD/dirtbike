"""ctypes wrapper around the C cores (built on demand into sim/build/libdbcore.so).

Two physics cores share tracks, bike parameters, controls and the planner:
  "original" - sim/dbcore.c, bit-exact port of Dirt Bike 4.3
  "improved" - sim/db2core.c, double precision with physics fixes (see db2core.h)
Get one with core("original") / core("improved"); each exposes Bike/Game types and the C functions.
"""
import ctypes as C
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = [ROOT / "sim" / n for n in ("dbcore.c", "dbplan.c", "db2core.c", "db2plan.c")]
HDR = [ROOT / "sim" / n for n in ("dbcore.h", "dbplan.h", "dbplan_impl.h", "db2core.h")]
LIB = ROOT / "sim" / "build" / "libdbcore.so"
I = C.c_int32
D = C.c_double
P = C.POINTER

MAX_PTS = 4019
THROTTLE_MAX = 58800
PLAYER_LOCAL, PLAYER_COMPUTER = 1, 8
PHYSICS = ("original", "improved")


def _build():
    if LIB.exists() and all(LIB.stat().st_mtime > s.stat().st_mtime for s in SRC + HDR):
        return
    LIB.parent.mkdir(exist_ok=True)
    subprocess.check_call(["cc", "-O2", "-fwrapv", "-fPIC", "-shared", "-fopenmp", "-o", str(LIB), *map(str, SRC), "-lm"])


class Pt(C.Structure):
    _fields_ = [("x", I), ("y", I)]


class TrackC(C.Structure):
    _fields_ = [("n_points", I), ("laps", I), ("allow_get_back", I), ("pts", Pt * MAX_PTS)]


BIKE_PARAM_FIELDS = [
    "front_radius", "front_spring", "front_rebound", "front_compression", "front_travel",
    "front_wheel_mass", "front_dist", "front_height",
    "rear_radius", "rear_spring", "rear_rebound", "rear_compression", "rear_travel",
    "rear_wheel_mass", "rear_dist", "rear_height", "rake_deg", "body_mass", "power", "brake_power",
]


class BikeParams(C.Structure):
    _fields_ = [(f, I) for f in BIKE_PARAM_FIELDS] + [("gear_ratio", I * 6), ("auto_trans", I)]


_DISPLAY = ["wheel_angle_f", "wheel_angle_r", "wheel_rate_f", "wheel_rate_r"]
_BIKE1_INTS = [
    "player_type", "x", "y", "fwx", "fwy", "rwx", "rwy", "angle_deg", "engine_started", "finish_time",
    "max_seg", "laps_done", "finished_ok", "vx", "vy", "front_susp_vel", "rear_susp_vel", "front_ext",
    "rear_ext", "rpm", "front_seg", "rear_seg", "theta_mrad", "omega", "rear_wheel_spin", "front_r2",
    "rear_r2", "inertia", "rear_wheel_inertia", "total_mass", "fork_arm_angle", "fork_arm_len",
    "fork_angle_deg", "throttle", "gear", "rear_touch", "front_touch", "input_throttle", "crashes",
]


class Bike(C.Structure):
    _fields_ = [("p", BikeParams)] + [(f, I) for f in _BIKE1_INTS] + [(f, D) for f in _DISPLAY + ["last_normal", "last_drive"]]


class Game(C.Structure):
    _fields_ = [("state", I), ("race_started", I), ("race_time", I), ("countdown", I), ("acc", I),
                ("nsub", I), ("rand_seed", C.c_uint32), ("frame_units", I)]


_BIKE2_INTS = ["player_type", "engine_started", "finish_time", "laps_done", "finished_ok", "front_seg", "rear_seg",
               "gear", "rear_touch", "front_touch", "input_throttle", "crashes"]
_BIKE2_DBLS = ["x", "y", "fwx", "fwy", "rwx", "rwy", "angle_deg", "theta_mrad", "omega", "vx", "vy",
               "front_susp_vel", "rear_susp_vel", "front_ext", "rear_ext", "rpm", "throttle", "rear_wheel_spin",
               "inertia", "rear_wheel_inertia", "total_mass", "fork_arm_angle", "fork_arm_len", "fork_angle_deg",
               "last_normal", "last_drive"] + _DISPLAY


class Bike2(C.Structure):
    _fields_ = [("p", BikeParams)] + [(f, I) for f in _BIKE2_INTS] + [(f, D) for f in _BIKE2_DBLS]


class Game2(C.Structure):
    _fields_ = [("state", I), ("race_started", I), ("race_time", I), ("countdown", I), ("frame_units", I),
                ("rand_seed", C.c_uint32), ("acc", D)]


CONFIG2_FIELDS = ["h", "contact_k", "contact_spacing", "contact_damping", "mu", "tau_up", "tau_down", "tau_brake",
                  "contact_continuous", "rolling_rpm", "surface_under", "hold_brake"]


class Config2(C.Structure):
    _fields_ = [(f, D) for f in CONFIG2_FIELDS]


MAX_ACTIONS = 64


class PlanCfg(C.Structure):
    _fields_ = [("n_actions", I), ("throttle", I * MAX_ACTIONS), ("shift", I * MAX_ACTIONS),
                ("frames_per_step", I), ("beam_width", I), ("bucket_x", I), ("bucket_angle", I),
                ("bucket_vy", I), ("vel_weight", D), ("allow_crash", I), ("crash_penalty", D),
                ("targets", C.c_void_p), ("n_targets", I), ("pos_scale", D), ("theta_scale", D), ("max_tilt", I), ("max_rpm", I)]


class Target(C.Structure):
    _fields_ = [("race_time", I), ("x", I), ("y", I), ("theta_mrad", I)]


_build()
lib = C.CDLL(str(LIB))
lib.db_init()
lib.db_track_generate.argtypes = [P(TrackC), C.c_uint32]
lib.db2_set_config.argtypes = [P(Config2)]
lib.db2_get_config.argtypes = [P(Config2)]
lib.db2_default_config.argtypes = [P(Config2)]


class Core:
    """Function table for one physics core."""

    def __init__(self, name, prefix, bike_t, game_t):
        self.name, self.Bike, self.Game = name, bike_t, game_t
        f = lambda n: getattr(lib, prefix + n)
        self.new_race, self.substep_fn, self.frame_fn = f("game_new_race"), f("game_substep"), f("game_frame")
        self.shift_up, self.shift_down = f("shift_up"), f("shift_down")
        self.planner_new, self.planner_run = f("planner_new"), f("planner_run")
        self.planner_best, self.planner_free = f("planner_best"), f("planner_free")
        self.new_race.argtypes = [P(game_t), P(bike_t), I, P(TrackC), I]
        for fn in (self.substep_fn, self.frame_fn):
            fn.argtypes = [P(game_t), P(bike_t), I, P(TrackC)]
            fn.restype = I
        self.shift_up.argtypes = [P(bike_t), P(game_t)]
        self.shift_down.argtypes = [P(bike_t)]
        self.planner_new.argtypes = [P(TrackC), P(game_t), P(bike_t), P(PlanCfg), I]
        self.planner_new.restype = C.c_void_p
        self.planner_run.argtypes = [C.c_void_p, I]
        self.planner_run.restype = I
        self.planner_best.argtypes = [C.c_void_p, P(I), P(game_t), P(bike_t)]
        self.planner_best.restype = I
        self.planner_free.argtypes = [C.c_void_p]
        self.state_fields = [n for n, _ in bike_t._fields_ if n != "p"]


_CORES = {"original": Core("original", "db_", Bike, Game), "improved": Core("improved", "db2_", Bike2, Game2)}


def core(physics="original"):
    return _CORES[physics]


def get_config2():
    c = Config2()
    lib.db2_get_config(C.byref(c))
    return {f: getattr(c, f) for f in CONFIG2_FIELDS}


def set_config2(**kw):
    """Update improved-core tunables (see sim/db2core.h). Returns the full config."""
    c = Config2()
    lib.db2_get_config(C.byref(c))
    for k, v in kw.items():
        if k not in CONFIG2_FIELDS:
            raise KeyError(k)
        setattr(c, k, v)
    lib.db2_set_config(C.byref(c))
    return get_config2()


def make_track(track=None, seed=None):
    """TrackC from a formats.Track, or generated from a seed (Beginner/Expert/random tracks)."""
    t = TrackC()
    if seed is not None:
        lib.db_track_generate(C.byref(t), seed)
        return t
    t.n_points, t.laps, t.allow_get_back = len(track.points), track.laps, track.allow_get_back
    for i, (x, y) in enumerate(track.points):
        t.pts[i].x, t.pts[i].y = x, y
    return t


def track_points(t):
    return [(t.pts[i].x, t.pts[i].y) for i in range(t.n_points)]


def make_bike(params, player_type=PLAYER_LOCAL, auto_trans=None, physics="original"):
    b = core(physics).Bike()
    for f in BIKE_PARAM_FIELDS:
        setattr(b.p, f, params[f])
    for i, r in enumerate(params["gear_ratio"]):
        b.p.gear_ratio[i] = r
    b.p.auto_trans = params["auto_trans"] if auto_trans is None else int(auto_trans)
    b.player_type = player_type
    return b


def physics_of(bike):
    return "improved" if isinstance(bike, Bike2) else "original"


def lap_length(t):
    """x distance one lap advances (the lap wrap maps x by pts[n-100].x - pts[0].x)."""
    return t.pts[t.n_points - 100].x - t.pts[0].x


def progress(b, t):
    return b.x + b.laps_done * lap_length(t)


def bike_dict(b):
    return {f: getattr(b, f) for f in core(physics_of(b)).state_fields}


class Race:
    """One or more bikes (all of the same core) on a track, advanced frame by frame."""

    def __init__(self, track_c, bikes, frame_units=200, rand_seed=1):
        self.core = core(physics_of(bikes[0]))
        self.t = track_c
        self.n = len(bikes)
        self.bikes = (self.core.Bike * self.n)(*bikes)
        self.g = self.core.Game()
        self.g.rand_seed = rand_seed
        self.core.new_race(C.byref(self.g), self.bikes, self.n, C.byref(self.t), frame_units)

    def frame(self):
        return self.core.frame_fn(C.byref(self.g), self.bikes, self.n, C.byref(self.t))

    def substep(self):
        return self.core.substep_fn(C.byref(self.g), self.bikes, self.n, C.byref(self.t))

    def shift(self, direction, i=0):
        b = self.bikes[i]
        if direction > 0:
            self.core.shift_up(C.byref(b), C.byref(self.g))
        elif direction < 0:
            self.core.shift_down(C.byref(b))
