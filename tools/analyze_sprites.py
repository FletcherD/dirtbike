"""Investigate the original bike+rider sprites (PICT 128-157): are they plain rotations of one image about the
centre of gravity? Each sprite is drawn with its top-left at CG + (x_off, y_off) mm (tables at g_game+0xf8 /
+0x170, set in FUN_1000f574), 30 mm per sprite pixel, and is selected by angle bucket (InitTrigTables).
For every sprite, rotate it back to level about the CG and search rotation/translation for the best match with
the level sprite (143), separately for the bike (below the CG + 300 mm) and the rider (above). Writes a table and
a contact sheet (work/images/sprite_analysis.png) of the de-rotated sprites over the level sprite's outline.
Needs work/images/sprites from tools/extract_images.py."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

X_OFF = [-750, -720, -960, -1110, -1230, -870, -690, -540, -690, -780, -870, -870, -870, -840, -810, -780, -780, -750,
         -720, -600, -510, -360, -270, -240, -270, -210, -270, -330, -510, -690]
Y_OFF = [-300, -360, -390, -540, -720, -720, -900, -990, -990, -1170, -1200, -1140, -1140, -1140, -1140, -1140, -1140,
         -1140, -1080, -990, -900, -840, -750, -840, -780, -780, -630, -480, -300, -270]
# angle buckets (degrees, 180 = level, <180 nose up) from InitTrigTables' FUN_1000b5b0 calls
BUCKETS = [(351, 369), (10, 28), (29, 45), (46, 62), (63, 77), (78, 92), (93, 105), (106, 118), (119, 129), (130, 140),
           (141, 149), (150, 158), (159, 165), (166, 172), (173, 177), (178, 182), (183, 188), (189, 194), (195, 202),
           (203, 210), (211, 220), (221, 230), (231, 242), (243, 254), (255, 268), (269, 282), (283, 298), (299, 314),
           (315, 322), (323, 350)]
MM = 30  # mm per sprite pixel
SPLIT = 300 // MM  # rows above CG+300 mm count as rider
C = 64  # canvas half-size (px)


def placed(sprites, i, rot):
    """Sprite i on a 2C x 2C canvas with its CG at the centre, rotated CCW by rot degrees about the CG."""
    img = Image.open(sprites / f"{128 + i}.png").convert("RGBA")
    cgx, cgy = -X_OFF[i] / MM, -Y_OFF[i] / MM
    canvas = Image.new("RGBA", (2 * C, 2 * C))
    canvas.paste(img, (int(round(C - cgx)), int(round(C - cgy))), img)
    return canvas.rotate(rot, resample=Image.BILINEAR, center=(C, C))


def alpha(im):
    return np.asarray(im)[:, :, 3] > 127


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def best_match(sprites, i, ref, region, nominal):
    """Search rotation (+-25 deg around nominal) and shift (+-8 px) maximising IoU with ref within region rows."""
    best = (-1, 0, 0, 0)
    for rot in np.arange(nominal - 25, nominal + 25.1, 1.0):
        a = alpha(placed(sprites, i, rot))
        for dy in range(-8, 9):
            for dx in range(-8, 9):
                s = np.roll(np.roll(a, dy, 0), dx, 1)
                r = (slice(0, C - SPLIT) if region == "rider" else slice(C - SPLIT, 2 * C), slice(None))
                v = iou(s[r], ref[r])
                if v > best[0]:
                    best = (v, rot, dx, dy)
    return best


def analyse(sprites, ref, i):
    lo, hi = BUCKETS[i]
    centre = ((lo + hi) / 2) % 360
    nominal = ((180 - centre + 180) % 360) - 180  # CCW visual rotation of this sprite relative to level
    # de-rotating = rotating by -nominal; search around that
    return i, nominal, best_match(sprites, i, ref, "bike", -nominal), best_match(sprites, i, ref, "rider", -nominal)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--images", default="work/images", help="tools/extract_images.py output directory")
    a = ap.parse_args()
    sprites = Path(a.images) / "sprites"
    ref = alpha(placed(sprites, 15, 0))
    print(f"{'idx':>3} {'pict':>4} {'bucket':>9} {'nominal':>7} | {'bike: rot':>9} {'shift mm':>13} {'IoU':>5} | "
          f"{'rider: rot':>10} {'shift mm':>13} {'IoU':>5} | rider-bike rot")
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(partial(analyse, sprites, ref), range(30)))
    for i, nominal, bb, rr in rows:
        lo, hi = BUCKETS[i]
        print(f"{i:3d} {128 + i:4d} {lo:3d}-{hi % 360:3d} {nominal:7.1f} | {-bb[1]:9.0f} {bb[2] * MM:6d},{-bb[3] * MM:6d} "
              f"{bb[0]:5.2f} | {-rr[1]:10.0f} {rr[2] * MM:6d},{-rr[3] * MM:6d} {rr[0]:5.2f} | {rr[1] - bb[1]:+5.0f}")
    # contact sheet: each sprite de-rotated by its best bike rotation, over the level sprite outline (red)
    sheet = Image.new("RGB", (10 * 2 * C, 3 * 2 * C), "white")
    edge = Image.fromarray((ref ^ np.roll(ref, 1, 0) | ref ^ np.roll(ref, 1, 1)).astype(np.uint8) * 255)
    for i, nominal, bb, rr in rows:
        tile = Image.new("RGB", (2 * C, 2 * C), "white")
        sp = placed(sprites, i, bb[1])
        tile.paste(sp, (bb[2], bb[3]), sp)
        tile.paste((255, 0, 0), (0, 0), edge)
        d = ImageDraw.Draw(tile)
        d.ellipse((C - 2, C - 2, C + 2, C + 2), fill=(0, 0, 255))
        d.text((2, 2), f"{128 + i} ({nominal:+.0f})", fill=(0, 0, 0))
        sheet.paste(tile, ((i % 10) * 2 * C, (i // 10) * 2 * C))
    out = Path(a.images) / "sprite_analysis.png"
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
