"""Reference writer for the station format.

Used by the tests and by `lb-verify demo`, and as a readable example of what
rec-fw must write byte for byte. Not used on the station itself.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from datetime import datetime, timezone
from pathlib import Path

from .chain import ZERO_HASH


def utc_iso(t: float, micro: bool = False) -> str:
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    if micro:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class SoftwareKey:
    """ECDSA P-256 key in software (rec-fw milestone 2 before the ATECC608)."""

    def __init__(self):
        from cryptography.hazmat.primitives.asymmetric import ec

        self._ec = ec
        self._key = ec.generate_private_key(ec.SECP256R1())

    @property
    def pub_hex(self) -> str:
        from cryptography.hazmat.primitives import serialization

        return self._key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        ).hex()

    def sign_digest(self, digest_hex: str) -> str:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import utils

        der = self._key.sign(bytes.fromhex(digest_hex), self._ec.ECDSA(utils.Prehashed(hashes.SHA256())))
        r, s = utils.decode_dss_signature(der)
        return (r.to_bytes(32, "big") + s.to_bytes(32, "big")).hex()


class ChainWriter:
    """Appends chain lines to every card's chain folder, like rec-fw does."""

    def __init__(self, station_dirs: list[Path], key: SoftwareKey | None = None):
        self.dirs = [Path(d) for d in station_dirs]
        self.key = key
        self.n = 0
        self.prev = ZERO_HASH

    def append(self, t: float, type_: str, **fields) -> str:
        e = {"v": 1, "n": self.n, "prev": self.prev, "t": utc_iso(t), "type": type_}
        e.update(fields)
        entry = json.dumps(e, separators=(",", ":"), ensure_ascii=False)
        h = hashlib.sha256(entry.encode("utf-8")).hexdigest()
        sig = self.key.sign_digest(h) if self.key else ""
        line = '{"e":' + entry + ',"h":"' + h + '","s":"' + sig + '"}\n'
        day = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y%m%d")
        for d in self.dirs:
            (d / "chain").mkdir(parents=True, exist_ok=True)
            with open(d / "chain" / f"{day}.jsonl", "a", encoding="utf-8", newline="") as f:
                f.write(line)
        self.n += 1
        self.prev = h
        return h

    def genesis(self, t: float, station_id: str, rec_fw: str = "demo") -> str:
        key = (
            {"alg": "ecdsa-p256", "pub": self.key.pub_hex, "source": "software"}
            if self.key
            else {"alg": "none", "pub": "", "source": "none"}
        )
        return self.append(t, "genesis", station_id=station_id, key=key, rec_fw=rec_fw)


def write_wav24(path: Path, channels: list[list[int]], rate: int = 48000) -> None:
    """Write WAVE_FORMAT_EXTENSIBLE 24-bit PCM, the layout rec-fw milestone 1 uses."""
    nch = len(channels)
    frames = len(channels[0])
    block = 3 * nch
    data = bytearray(frames * block)
    pos = 0
    for i in range(frames):
        for c in range(nch):
            data[pos : pos + 3] = (channels[c][i] & 0xFFFFFF).to_bytes(3, "little")
            pos += 3
    ch_mask = 0  # no speaker positions: these are array mics
    guid_pcm = bytes.fromhex("0100000000001000800000aa00389b71")
    fmt = struct.pack("<HHIIHHHHI", 0xFFFE, nch, rate, rate * block, block, 24, 22, 24, ch_mask) + guid_pcm
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", len(data)) + bytes(data))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def demo_card(root: Path, segments: int = 3, seconds: int = 5, signed: bool = True,
              station_id: str = "LB0000", start: float = 1793596200.0) -> Path:
    """Make a small fake card: short 5-channel WAV segments with a real PPS channel."""
    rate = 48000
    st = Path(root) / "LB" / station_id
    (st / "audio").mkdir(parents=True, exist_ok=True)
    (st / "card.json").write_text(json.dumps({
        "format": "lb-card", "format_version": 1, "station_id": station_id,
        "card": "A", "adopted_utc": utc_iso(start), "card_serial": "0x00000000",
    }, indent=2) + "\n", encoding="utf-8")
    key = None
    if signed:
        try:
            key = SoftwareKey()
        except ImportError:
            key = None
    cw = ChainWriter([st], key)
    cw.genesis(start, station_id)
    cw.append(start, "boot", rec_fw="demo", rec_fw_sha256=ZERO_HASH, config_sha256=ZERO_HASH, reset_reason="power_on")
    offset_s = 12e-6  # sample 0 is 12 us after the nominal second
    for k in range(segments):
        t0 = start + k * seconds + offset_s
        n = seconds * rate
        mics = []
        for m in range(4):
            f = 1000.0 * (m + 1)
            mics.append([int(200000 * math.sin(2 * math.pi * f * i / rate)) for i in range(n)])
        pps = []
        edges = []
        for i in range(n):
            tt = t0 + i / rate
            pps.append(7_000_000 if (tt - math.floor(tt)) < 0.1 else -7_000_000)
        first_sec = math.ceil(t0)
        for s in range(first_sec, int(t0 + n / rate) + 1):
            idx = (s - t0) * rate
            if 0 <= idx < n:
                edges.append([round(idx, 2), s])
        name = f"{station_id}_{datetime.fromtimestamp(start + k * seconds, tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{k + 1:06d}"
        day = name.split("_")[1][:8]
        d = st / "audio" / day
        d.mkdir(parents=True, exist_ok=True)
        wav = d / f"{name}.wav"
        write_wav24(wav, mics + [pps], rate)
        sc = {
            "format": "lb-segment", "format_version": 1, "station_id": station_id,
            "file": wav.name, "seq": k + 1, "container": "wav", "sample_rate": rate,
            "bits_per_sample": 24, "channels": 5, "samples": n,
            "start_utc": utc_iso(t0, micro=True), "start_utc_source": "pps",
            "channel_map": [{"ch": i + 1, "role": "mic", "mic": f"M{i + 1}", "pod_serial": None,
                             "position_m": None, "sens_dbfs_94db": None} for i in range(4)]
                           + [{"ch": 5, "role": "pps"}],
            "gain_db": 0, "rec_fw": "demo", "rec_fw_sha256": ZERO_HASH, "config_sha256": ZERO_HASH,
            "pps": {"source": "pdm", "channel": 5, "edges": edges, "timer_edges": []},
            "gnss": {"fix": "3d", "lat": 60.17, "lon": 24.94, "alt_m": 25.0, "hacc_m": 2.0, "sats": 12},
            "time_quality": {"locked": True, "since_lock_s": 0, "est_error_us": 1.0},
            "gaps": [], "env": {}, "card": "A",
        }
        side = d / f"{name}.json"
        side.write_text(json.dumps(sc, indent=2) + "\n", encoding="utf-8")
        cw.append(start + (k + 1) * seconds, "segment",
                  file=wav.relative_to(st).as_posix(), size=wav.stat().st_size, sha256=sha256_file(wav),
                  sidecar=side.relative_to(st).as_posix(), sidecar_sha256=sha256_file(side),
                  seq=k + 1, start_utc=sc["start_utc"], samples=n, card="A")
    return st
