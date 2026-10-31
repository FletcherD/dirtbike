"""Reconstruct the original's pre-rendered scenery bitmap for a track (Track_BuildScenery @1001ac60):
  1. "Creating Scenery": a background panorama (PICT 2000 or 2001, random) stretched to the full bitmap height and
     to a tile width W/k (k even, chosen so the tile width is closest to the panorama's width), then each tile is
     followed by its mirror image, repeated across the lap.
  2. "Moving Dirt": for every pixel column, a 1-pixel black line (default pen) from the surface down to the bottom.
  3. "Laying out the Course": scenery items cut from the strip PICT 180 (mask 1180) standing on the surface:
     GO sign at the start (and at the lap seam), small plants every 125-700 points, bushes every 500-1000, cacti
     every 2000-3000, type 7 every 1000-2000.
  4. "Grooming the Track": at EVERY track point, a random 3x4 px slice of the strip's bottom band (rows 46-49,
     x 133-299: brown dirt / green grass texture) pasted with its top at the surface -> a 4 px textured crust.
Bitmap: width = pts[n-100].x / scale, height = (max y - min y) / scale + 50, scale = mm per pixel (game pref).
The item RNG here is seeded locally; the original draws from the shared game RNG, so item placement differs."""
import argparse
from pathlib import Path

from PIL import Image

from dirtbike import runio as R
from dirtbike import sim as S

STRIP_ITEMS = {1: (0, 25, 10, 45), 2: (10, 28, 20, 45), 3: (20, 32, 28, 45), 4: (31, 26, 49, 45),
               5: (51, 1, 87, 45), 6: (94, 6, 126, 46), 7: (133, 41, 147, 46)}  # QuickDraw (left, top, right, bottom)


class Rng:
    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def range(self, lo, hi):  # RandRange @10002df0
        while True:
            self.s = (self.s * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
            r = int(((self.s >> 17) / 32768.0) * ((hi + 2) - lo) + (lo - 1))
            if lo <= r <= hi:
                return r


def tdiv(a, b):
    return int(a / b)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--track", default="Speed", help="track spec (see tools/plan.py)")
    ap.add_argument("--scale", type=int, default=70, help="mm per pixel")
    ap.add_argument("--panorama", type=int, choices=(2000, 2001), default=None, help="background PICT (default: random)")
    ap.add_argument("--seed", type=int, default=1, help="seed for item placement / panorama choice")
    ap.add_argument("--images", default="work/images", help="tools/extract_images.py output")
    ap.add_argument("--out", default="work/images/scenery_reconstruction.png", help="output PNG (full lap)")
    ap.add_argument("--crop", type=int, default=600, help="also write a 3x zoom of the first N px (0 = no)")
    a = ap.parse_args()
    t, _, label = R.resolve_track(a.track)
    pts = S.track_points(t)
    n, s = len(pts), a.scale
    rng = Rng(a.seed)
    ys = [tdiv(y, s) for _, y in pts]
    H = max(ys) - min(ys) + 50
    W = tdiv(pts[n - 100][0], s)
    img = Image.new("RGB", (W, H), "white")
    pdir = Path(a.images) / "pict"

    # 1. background panorama, stretched and mirror-tiled
    pano = Image.open(pdir / f"{a.panorama or rng.range(2000, 2001)}.png").convert("RGB")
    k = 2
    while abs(pano.width - W // (k + 2)) < abs(pano.width - W // k):
        k += 2
    tw = W // k
    tile = pano.resize((tw, H))
    pair = Image.new("RGB", (2 * tw, H))
    pair.paste(tile, (0, 0))
    pair.paste(tile.transpose(Image.FLIP_LEFT_RIGHT), (tw, 0))
    for x0 in range(0, W, 2 * tw):
        img.paste(pair, (x0, 0))

    # 2. dirt: one black vertical line per column from the surface down
    px = img.load()
    prev_x, prev_v = 0, H - ys[0]
    for i in range(1, n):
        x, v = tdiv(pts[i][0], s), H - ys[i]
        if x > prev_x:
            slope = (v - prev_v) / (x - prev_x)
            for col in range(prev_x, min(x, W)):
                for row in range(max(0, int(slope * (col - prev_x) + prev_v)), H):
                    px[col, row] = (0, 0, 0)
            prev_x, prev_v = x, v

    strip = Image.open(pdir / "180.png").convert("RGB")
    mask = Image.open(pdir / "1180.png").convert("L").point(lambda m: 255 if m < 128 else 0)

    def item(kind, i):
        if kind == 8:
            r = rng.range(1, 0xA5)
            src = (r + 0x84, 0x2E, r + 0x87, 0x32)
        else:
            src = STRIP_ITEMS[kind]
        w, h = src[2] - src[0], src[3] - src[1]
        x, v = tdiv(pts[i][0], s), H - ys[i]
        top = v - h + (4 if kind == 8 else 0)
        img.paste(strip.crop(src), (x - w // 2, top), mask.crop(src))

    # 3. course items
    item(6, 0)
    if t.laps > 1:
        item(6, n - 100)
    for kind, lo, hi in ((None, 0x7D, 700), (4, 500, 1000), (5, 2000, 3000), (7, 1000, 2000)):
        i = rng.range(lo, hi)
        while i < n - 100:
            item(rng.range(1, 3) if kind is None else kind, i)
            i += rng.range(lo, hi)
    # 4. grass crust at every point
    for i in range(n):
        item(8, i)

    out = Path(a.out)
    img.save(out)
    print(f"{label}: {W}x{H} px at {s} mm/px, panorama tile {tw} px (k={k}) -> {out}")
    if a.crop:
        c = img.crop((0, 0, min(a.crop, W), H))
        c.resize((c.width * 3, c.height * 3), Image.NEAREST).save(out.with_name(out.stem + "_zoom.png"))


if __name__ == "__main__":
    main()
