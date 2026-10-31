"""Calibrate the improved core's traction limit mu: reproduce human high-score races in the original
(validated) physics with tools/track_replay.py's tracker and report the distribution of
|drive force| / |normal force| at the rear wheel while it is touching and driving. A mu above what
humans use leaves normal riding unchanged and only caps exploits (light contact, full drive)."""
import argparse

import numpy as np

from dirtbike import runio as R
from track_replay import track

DEFAULT_RUNS = "Speed:0:330,Ups and Downs:0:330,Watch That Drop:0:330"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--runs", default=DEFAULT_RUNS, help="comma list of track:replay_index:frame_units")
    ap.add_argument("--beam", type=int, default=800, help="tracking beam width")
    a = ap.parse_args()
    ratios, pairs = [], []
    for spec in a.runs.split(","):
        name, idx, fu = spec.split(":")
        t, tr, label = R.resolve_track(name)
        errs, frames, st = track(t, R.resolve_bike("expert"), tr.replays[int(idx)], int(fu), a.beam, 4000, True, 100, 50,
                                 progress=False)
        rms = np.sqrt(np.mean([e[1] ** 2 + e[2] ** 2 for e in errs])) if errs else float("nan")
        sel = [(abs(f["last_drive"]), f["last_normal"]) for f in frames
               if f["state"] == 2 and f["rear_touch"] and f["last_normal"] > 0 and f["gear"] > 0]
        r = [d / n for d, n in sel]
        ratios += r
        pairs += sel
        q = np.percentile(r, [50, 90, 95, 99, 99.9]) if r else []
        print(f"{label} replay {idx}: tracking RMS {rms:.0f} mm; |drive|/|N| p50/90/95/99/99.9 = "
              + " / ".join(f"{v:.2f}" for v in q), flush=True)
    q = np.percentile(ratios, [50, 90, 95, 99, 99.9])
    print("all: p50/90/95/99/99.9 = " + " / ".join(f"{v:.2f}" for v in q))
    d, n = np.array(pairs).T
    print("share of total drive impulse kept if capped at mu*|N|:")
    for mu in (1, 1.5, 2, 3, 5, 10, 20, 50):
        print(f"  mu={mu:5}: {np.minimum(d, mu * n).sum() / d.sum():.1%} (frames capped: {np.mean(d > mu * n):.0%})")


if __name__ == "__main__":
    main()
