"""Loaders for Dirt Bike 4.3 data files (data fork only; files are chunked).

Chunk = u32 tag, u32 length, payload. Tags: 2 track (0x7e64), 3 high-score replay (0x882c),
4 local player (0xf4), 5? computer player, 7 ?, 9/10/11 window/prefs. A bike file (BIKE) holds the
0x60-byte parameter block. In memory, chunk payload offset = object offset - 4.
"""
import struct
from dataclasses import dataclass, field

BIKE_FIELDS = [
    "front_radius", "front_spring", "front_rebound", "front_compression", "front_travel",
    "front_wheel_mass", "front_dist", "front_height",
    "rear_radius", "rear_spring", "rear_rebound", "rear_compression", "rear_travel",
    "rear_wheel_mass", "rear_dist", "rear_height",
]
EXPERT_SEED = 0x25DD37D2
BEGINNER_SEED = 0x5B694DA2


def read_chunks(data):
    o, out = 0, []
    while o + 8 <= len(data):
        tag, ln = struct.unpack(">II", data[o:o + 8])
        if ln == 0 or o + 8 + ln > len(data):
            break
        out.append((tag, data[o + 8:o + 8 + ln]))
        o += 8 + ln
    return out


def parse_bike_params(b):
    """0x60-byte block (bike+0x88) -> dict."""
    v = struct.unpack(">16ihhiii6hhh", b[:0x60])
    d = dict(zip(BIKE_FIELDS, v[:16]))
    d["rake_deg"] = v[16]
    d["body_mass"], d["power"], d["brake_power"] = v[18:21]
    d["gear_ratio"] = list(v[21:27])
    d["auto_trans"] = v[27]
    return d


def expert_bike():
    return dict(front_radius=0x167, front_spring=40, front_rebound=800, front_compression=0x128,
                front_travel=600, front_wheel_mass=5, front_dist=0x23B, front_height=0x32,
                rear_radius=0x167, rear_spring=40, rear_rebound=800, rear_compression=0x128,
                rear_travel=600, rear_wheel_mass=5, rear_dist=0x28A, rear_height=0x32,
                rake_deg=0x16, body_mass=40, power=10000, brake_power=2000,
                gear_ratio=[0, 0x84, 0x3D, 0x24, 0x17, 0xE], auto_trans=1)


def beginner_bike():
    d = expert_bike()
    d.update(power=5000, front_travel=400, rear_travel=400, rear_dist=0x2EE, front_spring=0x46, rear_spring=0x46)
    return d


@dataclass
class Replay:
    name: str
    radii: tuple
    # rows: x, y, fwx-x, fwy-y, rwx-x, rwy-y, theta_mrad, race_time
    samples: list = field(default_factory=list)


@dataclass
class Track:
    description: str
    laps: int
    allow_get_back: int
    points: list  # [(x, y)]
    seed: int = 0
    replays: list = field(default_factory=list)


def parse_replay(c):
    cnt = struct.unpack(">h", c[0:2])[0]
    radii = struct.unpack(">hh", c[4:8])
    rows = []
    for i in range(cnt):
        x, y, fdx, fdy, rdx, rdy, th, _, t = struct.unpack_from(">iihhhhhhi", c, 8 + 0x18 * i)
        rows.append((x, y, fdx, fdy, rdx, rdy, th, t))
    name = c[0x87F8:0x87F8 + 32].split(b"\0")[0].decode("mac_roman")
    return Replay(name, radii, rows)


def parse_track_chunk(c):
    m = lambda off, fmt: struct.unpack_from(fmt, c, off - 4)
    n = m(0xF8, ">h")[0]
    pts = [m(0xFC + 8 * i, ">ii") for i in range(n)]
    desc = c[2:0xE4].split(b"\0")[0].decode("mac_roman")
    return Track(desc, m(0xE8, ">h")[0], m(0xEC, ">h")[0], pts, m(0x7E64, ">I")[0])


def load_track(path):
    chunks = read_chunks(open(path, "rb").read())
    t = None
    for tag, c in chunks:
        if tag == 2:
            t = parse_track_chunk(c)
        elif tag == 3 and t is not None:
            t.replays.append(parse_replay(c))
    if t is None:
        raise ValueError(f"{path}: no track chunk")
    return t


def load_bike(path):
    """A BIKE file, or a setup/player file: returns the first bike parameter block found."""
    for tag, c in read_chunks(open(path, "rb").read()):
        if len(c) >= 0x60 and tag != 2 and tag != 3:
            return parse_bike_params(c)
    raise ValueError(f"{path}: no bike chunk")
