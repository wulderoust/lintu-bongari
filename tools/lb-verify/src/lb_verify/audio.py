"""Read the stream parameters of a segment's audio file (WAV or FLAC) without decoding it.

Only the standard library is used, so walto can run this on any PC with Python.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


class AudioFormatError(ValueError):
    pass


@dataclass
class AudioInfo:
    container: str  # "wav" or "flac"
    sample_rate: int
    bits_per_sample: int
    channels: int
    samples: int  # samples per channel (frames)


def read_info(path: Path) -> AudioInfo:
    with open(path, "rb") as f:
        head = f.read(4)
        f.seek(0)
        if head == b"fLaC":
            return _flac_info(f)
        if head == b"RIFF":
            return _wav_info(f)
    raise AudioFormatError(f"not a FLAC or WAV file (starts with {head!r})")


def _flac_info(f) -> AudioInfo:
    f.read(4)
    hdr = f.read(4)
    if len(hdr) < 4:
        raise AudioFormatError("FLAC file too short")
    block_type = hdr[0] & 0x7F
    length = int.from_bytes(hdr[1:4], "big")
    if block_type != 0 or length < 34:
        raise AudioFormatError("FLAC file does not start with a STREAMINFO block")
    si = f.read(34)
    if len(si) < 34:
        raise AudioFormatError("FLAC STREAMINFO truncated")
    # Bytes 10..17: 20 bits rate, 3 bits channels-1, 5 bits bps-1, 36 bits total samples.
    x = int.from_bytes(si[10:18], "big")
    total = x & ((1 << 36) - 1)
    bps = ((x >> 36) & 0x1F) + 1
    ch = ((x >> 41) & 0x7) + 1
    rate = x >> 44
    return AudioInfo("flac", rate, bps, ch, total)


WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


def _wav_info(f) -> AudioInfo:
    riff = f.read(12)
    if len(riff) < 12 or riff[8:12] != b"WAVE":
        raise AudioFormatError("RIFF file is not WAVE")
    fmt = None
    data_len = None
    while True:
        ck = f.read(8)
        if len(ck) < 8:
            break
        cid, clen = ck[:4], struct.unpack("<I", ck[4:])[0]
        if cid == b"fmt ":
            fmt = f.read(clen)
        elif cid == b"data":
            data_len = clen
            break
        else:
            f.seek(clen, 1)
        if clen % 2:
            f.seek(1, 1)
    if fmt is None or len(fmt) < 16:
        raise AudioFormatError("WAV has no fmt chunk")
    if data_len is None:
        raise AudioFormatError("WAV has no data chunk")
    tag, ch, rate, _byte_rate, block_align, bps = struct.unpack("<HHIIHH", fmt[:16])
    if tag == WAVE_FORMAT_EXTENSIBLE and len(fmt) >= 40:
        valid_bits = struct.unpack("<H", fmt[18:20])[0]
        sub_tag = struct.unpack("<H", fmt[24:26])[0]
        if sub_tag != WAVE_FORMAT_PCM:
            raise AudioFormatError(f"WAV subformat {sub_tag:#x} is not PCM")
        if valid_bits:
            bps = valid_bits
    elif tag != WAVE_FORMAT_PCM:
        raise AudioFormatError(f"WAV format tag {tag:#x} is not PCM")
    if block_align == 0:
        raise AudioFormatError("WAV block_align is 0")
    if data_len % block_align:
        raise AudioFormatError("WAV data length is not a whole number of frames")
    return AudioInfo("wav", rate, bps, ch, data_len // block_align)
