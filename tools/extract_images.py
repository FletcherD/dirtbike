"""Extract every image from the app's resource fork into a browsable folder:
  pict/<id>.png     all PICT resources (decoded by ImageMagick)
  sprites/<id>.png  PICTs that have a mask PICT (id + 1000), with the mask applied as transparency
  icons/<type>_<id>.png  Finder icons (ICN#, ics#, icl4, icl8, ics4, ics8) with their masks
  index.html        gallery of all of the above
"""
import argparse
import html
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import rsrcfork
from PIL import Image, ImageOps
from tqdm import tqdm

# Mac OS default 4-bit colour table
CLUT4 = [0xFFFFFF, 0xFCF305, 0xFF6402, 0xDD0806, 0xF20884, 0x4600A5, 0x0000D4, 0x02ABEA,
         0x1FB714, 0x006411, 0x562C05, 0x90713A, 0xC0C0C0, 0x808080, 0x404040, 0x000000]


def clut8():
    """Mac OS default 8-bit colour table: 6x6x6 cube (minus black), red/green/blue/gray ramps, black."""
    lv = [0xFF, 0xCC, 0x99, 0x66, 0x33, 0x00]
    c = [(lv[i // 36] << 16) | (lv[i // 6 % 6] << 8) | lv[i % 6] for i in range(215)]
    ramp = [0xEE, 0xDD, 0xBB, 0xAA, 0x88, 0x77, 0x55, 0x44, 0x22, 0x11]
    c += [v << 16 for v in ramp] + [v << 8 for v in ramp] + ramp + [(v << 16) | (v << 8) | v for v in ramp] + [0]
    return c


def rgb(v):
    return (v >> 16) & 255, (v >> 8) & 255, v & 255


def bits_image(data, size):
    """1-bit big-endian bitmap -> list of 0/1."""
    out = []
    for byte in data[:size * size // 8]:
        out += [(byte >> (7 - k)) & 1 for k in range(8)]
    return out


def icon_png(kind, data, mask_bits, size, path):
    img = Image.new("RGBA", (size, size))
    if kind == "bw":
        px = [(0, 0, 0) if b else (255, 255, 255) for b in bits_image(data, size)]
    elif kind == 4:
        px = [rgb(CLUT4[(data[i // 2] >> (4 if i % 2 == 0 else 0)) & 15]) for i in range(size * size)]
    else:
        pal = clut8()
        px = [rgb(pal[data[i]]) for i in range(size * size)]
    img.putdata([p + (255 if m else 0,) for p, m in zip(px, mask_bits)])
    img.resize((size * 4, size * 4), Image.NEAREST).save(path)


def unpackbits(src, n):
    out, i = bytearray(), 0
    while len(out) < n:
        c = src[i]
        i += 1
        if c < 128:
            out += src[i:i + c + 1]
            i += c + 1
        elif c > 128:
            out += bytes([src[i]]) * (257 - c)
            i += 1
    return bytes(out[:n]), i


def find_bitmap(data):
    """Walk the PICT opcodes up to the first image opcode. Returns (offset_of_opcode_data, packed) for a
    1-bit BitsRect/PackBitsRect, or None for anything else (colour PixMaps etc., left to ImageMagick)."""
    v2 = data[10:12] == b"\x00\x11"
    o = 12 if not v2 else 14  # after version opcode (v1: 0x1101, v2: 0x0011 0x02FF)
    while True:
        if v2:
            o += o % 2
            op = int.from_bytes(data[o:o + 2], "big")
            o += 2
        else:
            op = data[o]
            o += 1
        if op in (0x90, 0x98):
            if int.from_bytes(data[o:o + 2], "big") & 0x8000:
                return None
            return o, op == 0x98
        if op == 0x01:  # clipRgn
            o += int.from_bytes(data[o:o + 2], "big")
        elif op in (0x00, 0x1E):  # nop, defHilite
            pass
        elif op == 0x0C00:  # v2 header
            o += 24
        elif op == 0xA0:  # shortComment
            o += 2
        elif op == 0xA1:  # longComment
            o += 4 + int.from_bytes(data[o + 2:o + 4], "big")
        else:  # other drawing opcodes: not a plain bitmap PICT, ImageMagick handles it
            return None


def decode_bitmap(data, o, packed):
    """1-bit BitsRect (0x90) / PackBitsRect (0x98) at opcode-data offset o. These are the sprite masks
    (black = draw). ImageMagick misreads them."""
    rowbytes = int.from_bytes(data[o:o + 2], "big") & 0x3FFF
    top, left, bottom, right = (int.from_bytes(data[o + 2 + 2 * k:o + 4 + 2 * k], "big", signed=True) for k in range(4))
    o += 2 + 8 + 8 + 8 + 2  # rowBytes, bounds, srcRect, dstRect, mode
    w, h = right - left, bottom - top
    pix = []
    for _ in range(h):
        if packed and rowbytes >= 8:
            count = data[o] if rowbytes <= 250 else int.from_bytes(data[o:o + 2], "big")
            o += 1 if rowbytes <= 250 else 2
            row, _ = unpackbits(data[o:o + count], rowbytes)
            o += count
        else:  # rows narrower than 8 bytes are stored unpacked
            row = data[o:o + rowbytes]
            o += rowbytes
        pix += [0 if (row[x // 8] >> (7 - x % 8)) & 1 else 255 for x in range(w)]  # 1 = black
    img = Image.new("L", (w, h))
    img.putdata(pix)
    return img


def convert_pict(data, png):
    bm = find_bitmap(data)
    if bm is not None:
        decode_bitmap(data, *bm).save(png)
        return
    with tempfile.NamedTemporaryFile(suffix=".pict") as tf:
        tf.write(b"\0" * 512 + data)
        tf.flush()
        subprocess.check_call(["convert", tf.name, str(png)])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--rsrc", default="work/app.rsrc", help="raw resource fork (tools/appledouble.py output)")
    ap.add_argument("--out", default="work/images", help="output directory")
    ap.add_argument("--jobs", type=int, default=8, help="parallel ImageMagick conversions")
    a = ap.parse_args()
    out = Path(a.out)
    for d in ("pict", "sprites", "icons"):
        (out / d).mkdir(parents=True, exist_ok=True)
    with rsrcfork.ResourceFile.open(a.rsrc) as rf:
        picts = {rid: (res.name or b"").decode("mac_roman") for rid, res in rf[b"PICT"].items()}
        data = {rid: res.data for rid, res in rf[b"PICT"].items()}
        icons = {t.decode(): {rid: res.data for rid, res in rf[t].items()}
                 for t in (b"ICN#", b"ics#", b"icl4", b"icl8", b"ics4", b"ics8") if t in rf}

    with ThreadPoolExecutor(a.jobs) as ex:
        list(tqdm(ex.map(lambda rid: convert_pict(data[rid], out / "pict" / f"{rid}.png"), data),
                  total=len(data), desc="PICT"))

    sprites = []
    for rid in sorted(data):
        if rid + 1000 in data and rid < 1000:
            img = Image.open(out / "pict" / f"{rid}.png").convert("RGBA")
            mask = Image.open(out / "pict" / f"{rid + 1000}.png").convert("L").resize(img.size)
            img.putalpha(ImageOps.invert(mask))  # mask black = opaque (CopyMask)
            img.save(out / "sprites" / f"{rid}.png")
            sprites.append(rid)

    icon_files = []
    for rid, d in icons.get("ICN#", {}).items():
        mask32 = bits_image(d[128:], 32)
        icon_png("bw", d, mask32, 32, out / "icons" / f"ICN#_{rid}.png")
        icon_files.append(f"ICN#_{rid}.png")
        for t, kind in (("icl4", 4), ("icl8", 8)):
            if rid in icons.get(t, {}):
                icon_png(kind, icons[t][rid], mask32, 32, out / "icons" / f"{t}_{rid}.png")
                icon_files.append(f"{t}_{rid}.png")
    for rid, d in icons.get("ics#", {}).items():
        mask16 = bits_image(d[32:], 16)
        icon_png("bw", d, mask16, 16, out / "icons" / f"ics#_{rid}.png")
        icon_files.append(f"ics#_{rid}.png")
        for t, kind in (("ics4", 4), ("ics8", 8)):
            if rid in icons.get(t, {}):
                icon_png(kind, icons[t][rid], mask16, 16, out / "icons" / f"{t}_{rid}.png")
                icon_files.append(f"{t}_{rid}.png")

    def card(src, label):
        w, h = Image.open(out / src).size
        return (f'<figure><a href="{src}"><img src="{src}" style="max-width:{min(w * 2, 640)}px"></a>'
                f'<figcaption>{html.escape(label)}<br>{w}×{h}</figcaption></figure>')

    sections = [
        ("Sprites with masks applied (PICT id + mask id+1000)", [card(f"sprites/{r}.png", f"PICT {r}") for r in sprites]),
        ("All PICT resources", [card(f"pict/{r}.png", f"PICT {r} {picts[r]}".strip()) for r in sorted(data)]),
        ("Finder icons (4x)", [card(f"icons/{f}", f) for f in icon_files]),
    ]
    body = "".join(f"<h2>{t}</h2><div class=g>{''.join(c)}</div>" for t, c in sections)
    (out / "index.html").write_text(
        "<!DOCTYPE html><meta charset=utf-8><title>Dirt Bike 4.3 images</title><style>"
        "body{font:13px sans-serif;background:#ddd}figure{display:inline-block;margin:6px;padding:6px;"
        "background:repeating-conic-gradient(#ccc 0 25%,#fff 0 50%) 0 0/16px 16px;vertical-align:top}"
        "img{image-rendering:pixelated;display:block}figcaption{background:#fff;padding:2px}</style>"
        f"<h1>Dirt Bike 4.3 resource images</h1>{body}")
    print(f"{len(data)} PICTs, {len(sprites)} masked sprites, {len(icon_files)} icons -> {out}/index.html")


if __name__ == "__main__":
    main()
