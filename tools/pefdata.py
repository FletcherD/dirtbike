# /// script
# requires-python = ">=3.10"
# ///
"""Inspect the unpacked PEF data section dumped by Ghidra (work/mem). TOC base == data start."""
import argparse
import struct

BASE = 0x10024120


def load(path="work/mem/PackedData_10024120.bin"):
    return open(path, "rb").read()


def u32(d, a):
    return struct.unpack(">I", d[a - BASE:a - BASE + 4])[0]


def tv_target(d, a):
    """If a is a TVector address in data, return its code address."""
    if BASE <= a < BASE + len(d) - 4:
        c = u32(d, a)
        if 0x10000000 <= c < 0x10024120:
            return c
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--vtable", type=lambda s: int(s, 0), nargs="*", default=[], help="dump vtable words around address")
    ap.add_argument("--n", type=int, default=40, help="words to dump")
    ap.add_argument("--before", type=int, default=8, help="words before address")
    ap.add_argument("--double", type=lambda s: int(s, 0), nargs="*", default=[], help="TOC offsets of doubles to print")
    a = ap.parse_args()
    d = load()
    for v in a.vtable:
        print(f"--- {v:#x}")
        for i in range(-a.before, a.n):
            addr = v + 4 * i
            w = u32(d, addr)
            t = tv_target(d, w)
            print(f"{addr:#x} +{4*i:#5x}: {w:#010x}" + (f" -> FUN_{t:08x}" if t else ""))
    for o in a.double:
        print(hex(o), struct.unpack(">d", d[o:o + 8])[0])
