# /// script
# requires-python = ">=3.10"
# dependencies = ["rsrcfork"]
# ///
"""Convert the app's Mac 'snd ' resources to WAV files (format 1/2 sound resources with standard,
extended, or MACE-compressed sampled-sound headers; MACE is decoded by ffmpeg via an AIFF-C wrapper)."""
import argparse
import math
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

import rsrcfork


def sound_header_offset(d):
    fmt = struct.unpack(">H", d[0:2])[0]
    if fmt == 1:
        nfmt = struct.unpack(">H", d[2:4])[0]
        o = 4 + 6 * nfmt
    elif fmt == 2:
        o = 4
    else:
        raise ValueError(f"snd format {fmt}")
    ncmd = struct.unpack(">H", d[o:o + 2])[0]
    o += 2
    for i in range(ncmd):
        cmd, p1, p2 = struct.unpack(">HHI", d[o + 8 * i:o + 8 * i + 8])
        if cmd & 0x7FFF in (0x50, 0x51):  # soundCmd / bufferCmd with data offset
            return p2
    raise ValueError("no sound/buffer command")


def decode(d):
    """Returns (rate_hz, channels, sample_width_bytes, pcm_bytes_for_wav)."""
    h = sound_header_offset(d)
    _, length, rate, loop_start, loop_end, encode, base = struct.unpack(">IIIIIBB", d[h:h + 22])
    rate = rate / 65536.0
    if encode == 0x00:  # standard: 8-bit unsigned mono
        return rate, 1, 1, d[h + 22:h + 22 + length], (loop_start, loop_end)
    if encode == 0xFF:  # extended
        channels = length
        nframes = struct.unpack(">I", d[h + 22:h + 26])[0]
        sample_size = struct.unpack(">H", d[h + 48:h + 50])[0]
        data = d[h + 64:]
        bps = sample_size // 8
        data = data[:nframes * channels * bps]
        if bps == 2:  # big-endian signed -> little-endian
            data = b"".join(data[i + 1:i + 2] + data[i:i + 1] for i in range(0, len(data), 2))
        return rate, channels, bps, data, (loop_start, loop_end)
    raise ValueError(f"unsupported encoding {encode:#x}")


def ieee_extended(x):
    """80-bit IEEE extended (AIFF sample rate)."""
    e = int(math.floor(math.log2(x)))
    mant = int(x / 2 ** e * (1 << 63))
    return struct.pack(">HQ", e + 16383, mant)


def mace_to_wav(d, fn):
    """Compressed header (encode 0xFE) with compressionID 3/4 (MACE 3:1 / 6:1) -> WAV via ffmpeg."""
    h = sound_header_offset(d)
    channels = struct.unpack(">I", d[h + 4:h + 8])[0]
    rate = struct.unpack(">I", d[h + 8:h + 12])[0] / 65536.0
    nframes = struct.unpack(">I", d[h + 22:h + 26])[0]
    cid = struct.unpack(">h", d[h + 56:h + 58])[0]
    ctype = {3: b"MAC3", 4: b"MAC6"}[cid]
    data = d[h + 64:]
    name = b"\x00\x00"
    comm = struct.pack(">hIh", channels, nframes, 8) + ieee_extended(rate) + ctype + name
    ssnd = struct.pack(">II", 0, 0) + data
    chunks = b"FVER" + struct.pack(">II", 4, 0xA2805140) + b"COMM" + struct.pack(">I", len(comm)) + comm
    chunks += b"SSND" + struct.pack(">I", len(ssnd)) + ssnd + (b"\x00" if len(ssnd) % 2 else b"")
    aifc = b"FORM" + struct.pack(">I", 4 + len(chunks)) + b"AIFC" + chunks
    with tempfile.NamedTemporaryFile(suffix=".aifc") as tf:
        tf.write(aifc)
        tf.flush()
        subprocess.check_call(["ffmpeg", "-loglevel", "error", "-y", "-i", tf.name, str(fn)])
    return rate, ctype.decode()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--rsrc", default="work/app.rsrc", help="raw resource fork (tools/appledouble.py output)")
    ap.add_argument("--out", default="web/sounds", help="output directory")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with rsrcfork.ResourceFile.open(a.rsrc) as rf:
        for rid, res in rf[b"snd "].items():
            name = (res.name or b"").decode("mac_roman") or str(rid)
            fn = out / f"snd{rid}.wav"
            h = sound_header_offset(res.data)
            if res.data[h + 20] == 0xFE:
                rate, codec = mace_to_wav(res.data, fn)
                print(f"{rid} {name!r}: {codec} {rate:.0f} Hz -> {fn}")
                continue
            rate, ch, bps, pcm, loop = decode(res.data)
            with wave.open(str(fn), "wb") as w:
                w.setnchannels(ch)
                w.setsampwidth(bps)
                w.setframerate(int(round(rate)))
                w.writeframes(pcm)
            print(f"{rid} {name!r}: {rate:.0f} Hz, {ch} ch, {8 * bps}-bit, {len(pcm) // (ch * bps) / rate:.2f}s, loop {loop} -> {fn}")


if __name__ == "__main__":
    main()
