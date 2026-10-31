# /// script
# requires-python = ">=3.10"
# ///
"""Extract the resource fork from an AppleDouble (.rsrc as written by unar) file."""
import argparse
import struct


def resource_fork(path):
    data = open(path, "rb").read()
    magic, version = struct.unpack(">II", data[:8])
    assert magic == 0x00051607, hex(magic)
    n = struct.unpack(">H", data[24:26])[0]
    for i in range(n):
        eid, off, ln = struct.unpack(">III", data[26 + 12 * i:38 + 12 * i])
        if eid == 2:
            return data[off:off + ln]
    raise ValueError("no resource fork entry")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args()
    open(a.dst, "wb").write(resource_fork(a.src))
