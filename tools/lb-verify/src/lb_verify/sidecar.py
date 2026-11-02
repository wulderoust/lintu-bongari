"""Check a segment sidecar against its file name, audio header and PPS table (formats.md section 6)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .audio import AudioInfo

NAME_RE = re.compile(r"^([A-Za-z0-9-]{1,32})_(\d{8}T\d{6}Z)_(\d{6,})\.(flac|wav)$")
PPS_TOLERANCE_PPM = 200.0


def parse_utc(s: str) -> float:
    """Parse ISO 8601 UTC ('...Z') to unix seconds as float (microsecond precision kept)."""
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError(f"time {s!r} is not ISO 8601 UTC ending in Z")
    body = s[:-1]
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(body, fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"time {s!r} is not ISO 8601 UTC")
    # Avoid float rounding of the microseconds by building from integer parts.
    whole = int(dt.replace(microsecond=0).timestamp())
    return whole + dt.microsecond / 1e6


def check_sidecar(sc: dict, audio_name: str, info: AudioInfo | None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    def err(msg):
        errors.append(msg)

    if sc.get("format") != "lb-segment":
        err("format is not 'lb-segment'")
    if sc.get("format_version") != 1:
        warnings.append(f"format_version {sc.get('format_version')!r} is not 1")

    m = NAME_RE.match(audio_name)
    if not m:
        err(f"file name {audio_name!r} does not follow <station>_<YYYYMMDDTHHMMSSZ>_<seq>.<ext>")
    else:
        station, _stamp, seq, ext = m.groups()
        if sc.get("file") != audio_name:
            err(f"sidecar 'file' is {sc.get('file')!r}, expected {audio_name!r}")
        if sc.get("station_id") != station:
            err(f"sidecar station_id {sc.get('station_id')!r} does not match file name")
        if sc.get("seq") != int(seq):
            err(f"sidecar seq {sc.get('seq')!r} does not match file name ({int(seq)})")
        if sc.get("container") != ext:
            err(f"sidecar container {sc.get('container')!r} does not match extension .{ext}")

    rate = sc.get("sample_rate")
    for k in ("sample_rate", "bits_per_sample", "channels", "samples"):
        if not isinstance(sc.get(k), int):
            err(f"'{k}' missing or not an integer")
    if info is not None:
        for k, actual in (
            ("sample_rate", info.sample_rate),
            ("bits_per_sample", info.bits_per_sample),
            ("channels", info.channels),
            ("samples", info.samples),
        ):
            if isinstance(sc.get(k), int) and sc[k] != actual:
                err(f"'{k}' is {sc[k]} but the audio file says {actual}")
        if info.container != sc.get("container"):
            err(f"audio file is {info.container} but sidecar says {sc.get('container')!r}")

    cmap = sc.get("channel_map")
    if not isinstance(cmap, list):
        err("'channel_map' missing")
    else:
        if isinstance(sc.get("channels"), int) and len(cmap) != sc["channels"]:
            err(f"channel_map has {len(cmap)} items for {sc['channels']} channels")
        for i, c in enumerate(cmap, 1):
            if not isinstance(c, dict) or c.get("ch") != i:
                err(f"channel_map item {i} must have ch={i}")
            elif c.get("role") not in ("mic", "pps", "unused"):
                err(f"channel_map ch {i} has unknown role {c.get('role')!r}")

    start = None
    try:
        start = parse_utc(sc.get("start_utc"))
    except ValueError as ex:
        err(f"start_utc: {ex}")
    src = sc.get("start_utc_source")
    if src not in ("pps", "rtc", "none"):
        err(f"start_utc_source {src!r} is not pps/rtc/none")

    pps = sc.get("pps") or {}
    edges = pps.get("edges") or []
    if src == "pps" and not edges:
        err("start_utc_source is 'pps' but the PPS table is empty")
    if pps.get("source") == "pdm":
        ch = pps.get("channel")
        if isinstance(cmap, list) and isinstance(ch, int):
            if not (1 <= ch <= len(cmap)) or cmap[ch - 1].get("role") != "pps":
                err(f"pps.channel {ch} is not a 'pps' channel in channel_map")
    for name in ("edges", "timer_edges"):
        tbl = pps.get(name) or []
        e2, w2 = _check_pps_table(tbl, rate, start, name, src == "pps" and name == "edges")
        errors += e2
        warnings += w2
    return errors, warnings


def _check_pps_table(tbl, rate, start, name, start_from_pps):
    errors, warnings = [], []
    if not isinstance(rate, int) or rate <= 0:
        return errors, warnings
    prev = None
    worst_ppm = 0.0
    worst_start_err = 0.0
    for i, item in enumerate(tbl):
        if not (isinstance(item, list) and len(item) == 2 and all(isinstance(x, (int, float)) for x in item)):
            errors.append(f"pps.{name}[{i}] is not [sample_index, utc_seconds]")
            return errors, warnings
        idx, utc = item
        if not isinstance(utc, int) and not float(utc).is_integer():
            errors.append(f"pps.{name}[{i}] UTC {utc} is not a whole second")
        if prev is not None:
            pidx, putc = prev
            if idx <= pidx or utc <= putc:
                errors.append(f"pps.{name}[{i}] is not after the previous edge")
                return errors, warnings
            expect = (utc - putc) * rate
            ppm = abs((idx - pidx) - expect) / expect * 1e6
            worst_ppm = max(worst_ppm, ppm)
        prev = item
    if start is not None and tbl:
        # Extrapolate from the first edge to sample 0 using the measured local rate
        # (the clock may be tens of ppm off, which adds up over a 10-minute file).
        idx0, utc0 = tbl[0]
        local_rate = rate
        if len(tbl) >= 2 and tbl[1][1] > utc0:
            local_rate = (tbl[1][0] - idx0) / (tbl[1][1] - utc0)
        worst_start_err = abs((utc0 - idx0 / local_rate) - start) * rate
    if worst_ppm > PPS_TOLERANCE_PPM:
        warnings.append(
            f"pps.{name}: edge spacing is off by up to {worst_ppm:.0f} ppm (limit {PPS_TOLERANCE_PPM:.0f}); "
            "missed PPS pulses or a clock fault"
        )
    if start_from_pps and worst_start_err > 1.0:
        errors.append(
            f"start_utc disagrees with pps.{name} by up to {worst_start_err:.1f} samples (limit 1)"
        )
    return errors, warnings
