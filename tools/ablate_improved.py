"""Feel check for the improved core: track a human high-score replay (tools/track_replay.py) with the
improved core configured as close to the original as possible, then with each improvement enabled
alone, then all together. Small tracking error = a human's riding still produces the same ride."""
import argparse
import math

from dirtbike import runio as R
from dirtbike import sim as S
from track_replay import track

ORIGINAL_LIKE = dict(mu=1e9, contact_damping=0, tau_up=1e-6, tau_down=1e-6, tau_brake=1e-6,
                     contact_continuous=0, rolling_rpm=0, surface_under=0)
IMPROVEMENTS = {
    "mu": dict(mu=None), "contact_damping": dict(contact_damping=None),
    "engine_lag": dict(tau_up=None, tau_down=None, tau_brake=None),
    "contact_continuous": dict(contact_continuous=1), "rolling_rpm": dict(rolling_rpm=1), "surface_under": dict(surface_under=1),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--track", default="Speed", help="track spec")
    ap.add_argument("--replay", type=int, default=0, help="replay index")
    ap.add_argument("--time-scale", type=float, default=1.1, help="recording clock -> exact clock factor")
    ap.add_argument("--beam", type=int, default=1500, help="tracking beam width")
    ap.add_argument("--only", default=None, help="comma list of variant names to run (default all)")
    a = ap.parse_args()
    t, tr, label = R.resolve_track(a.track)
    rp = tr.replays[a.replay]
    defaults = S.get_config2()
    variants = [("original-like", {})]
    for name, kw in IMPROVEMENTS.items():
        variants.append((f"+{name}", {k: (defaults[k] if v is None else v) for k, v in kw.items()}))
    variants.append(("all improvements (defaults)", None))
    if a.only:
        keep = a.only.split(",")
        variants = [v for v in variants if v[0].lstrip("+") in keep or v[0] in keep]
    for name, kw in variants:
        S.set_config2(**(defaults if kw is None else {**defaults, **ORIGINAL_LIKE, **kw}))
        errs, frames, st = track(t, R.resolve_bike("expert"), rp, 200, a.beam, 4000, True, 100, 50, progress=False,
                                 physics="improved", time_scale=a.time_scale)
        rms = lambda j: math.sqrt(sum(e[j] ** 2 for e in errs) / len(errs))
        print(f"{name:30s} RMS dx={rms(1):6.0f} dy={rms(2):5.0f} mm dtheta={rms(3):4.0f} mrad", flush=True)
    S.set_config2(**defaults)


if __name__ == "__main__":
    main()
