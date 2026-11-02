"""Verify one or more station cards (formats.md section 7)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .audio import AudioFormatError, read_info
from .chain import ChainResult, read_chain_dir, verify_chain
from .sidecar import check_sidecar


@dataclass
class Report:
    station_id: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    segments_checked: int = 0
    segments_elsewhere: int = 0
    signed: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def find_station_dirs(root: Path) -> list[Path]:
    """Accept a card root, its /LB folder, or a station folder directly."""
    root = Path(root)
    if (root / "chain").is_dir():
        return [root]
    lb = root / "LB" if (root / "LB").is_dir() else root
    return sorted(p for p in lb.iterdir() if p.is_dir() and (p / "chain").is_dir()) if lb.is_dir() else []


def verify_cards(paths: list[Path], pubkey_hex: str | None = None, deep: bool = True) -> Report:
    rep = Report()
    station_dirs: list[Path] = []
    for p in paths:
        found = find_station_dirs(Path(p))
        if not found:
            rep.errors.append(f"{p}: no /LB/<station>/chain folder found")
        station_dirs += found
    if not station_dirs:
        return rep
    stations = {d.name for d in station_dirs}
    if len(stations) > 1:
        rep.errors.append(f"cards hold different stations: {', '.join(sorted(stations))}; verify one station at a time")
        return rep
    rep.station_id = station_dirs[0].name

    # Card labels.
    for d in station_dirs:
        cj = d / "card.json"
        if cj.exists():
            try:
                card = json.loads(cj.read_text(encoding="utf-8"))
                if card.get("station_id") != rep.station_id:
                    rep.errors.append(f"{cj}: station_id {card.get('station_id')!r} does not match folder")
                rep.info.append(f"{d}: card {card.get('card')}")
            except (ValueError, OSError) as ex:
                rep.errors.append(f"{cj}: cannot read ({ex})")
        else:
            rep.warnings.append(f"{d}: no card.json")

    # Chain.
    tmp = ChainResult()
    per_card = {str(d): read_chain_dir(d / "chain", tmp) for d in station_dirs}
    chain = verify_chain(per_card, pubkey_hex)
    rep.errors += tmp.errors + chain.errors
    rep.warnings += tmp.warnings + chain.warnings
    rep.info += chain.info
    rep.signed = chain.signed

    for ent in chain.entries.values():
        if ent.e.get("type") == "genesis" and ent.e.get("station_id") not in (None, rep.station_id):
            rep.errors.append(f"{ent.source}: genesis station_id {ent.e.get('station_id')!r} does not match folder")

    # Segments in the chain.
    chained: set[str] = set()
    for n in sorted(chain.entries):
        ent = chain.entries[n]
        e = ent.e
        if e.get("type") != "segment":
            continue
        rel_audio, rel_side = e.get("file"), e.get("sidecar")
        if not isinstance(rel_audio, str) or not isinstance(rel_side, str):
            rep.errors.append(f"{ent.source}: segment entry without file/sidecar")
            continue
        chained.update((rel_audio, rel_side))
        home = next((d for d in station_dirs if (d / rel_audio).exists() or (d / rel_side).exists()), None)
        if home is None:
            rep.segments_elsewhere += 1
            continue
        _check_segment(rep, home, ent.source, e, deep)

    # Files on the cards that the chain does not mention.
    for d in station_dirs:
        audio_root = d / "audio"
        if not audio_root.is_dir():
            continue
        for f in sorted(audio_root.rglob("*")):
            if f.is_file() and f.suffix in (".flac", ".wav", ".json"):
                rel = f.relative_to(d).as_posix()
                if rel not in chained:
                    rep.warnings.append(f"{f}: file is not in the chain (unchained)")
    return rep


def _check_segment(rep: Report, home: Path, src: str, e: dict, deep: bool) -> None:
    audio = home / e["file"]
    side = home / e["sidecar"]
    rep.segments_checked += 1
    where = f"{e['file']}"
    if not audio.exists():
        rep.errors.append(f"{where}: audio file missing (sidecar is on the card)")
    if not side.exists():
        rep.errors.append(f"{where}: sidecar missing")
    if audio.exists():
        if e.get("size") is not None and audio.stat().st_size != e.get("size"):
            rep.errors.append(f"{where}: size {audio.stat().st_size} does not match chain ({e.get('size')})")
        elif deep and sha256_file(audio) != e.get("sha256"):
            rep.errors.append(f"{where}: SHA-256 does not match the chain (file changed or corrupted)")
    if side.exists() and deep and sha256_file(side) != e.get("sidecar_sha256"):
        rep.errors.append(f"{e['sidecar']}: SHA-256 does not match the chain")

    info = None
    if audio.exists():
        try:
            info = read_info(audio)
        except (AudioFormatError, OSError) as ex:
            rep.errors.append(f"{where}: {ex}")
    if side.exists():
        try:
            sc = json.loads(side.read_text(encoding="utf-8"))
        except (ValueError, OSError) as ex:
            rep.errors.append(f"{e['sidecar']}: not valid JSON ({ex})")
            return
        errs, warns = check_sidecar(sc, audio.name, info)
        rep.errors += [f"{e['sidecar']}: {m}" for m in errs]
        rep.warnings += [f"{e['sidecar']}: {m}" for m in warns]
        for k in ("seq", "start_utc", "samples"):
            if k in e and sc.get(k) != e[k]:
                rep.errors.append(f"{src}: chain {k}={e[k]!r} but sidecar has {sc.get(k)!r}")
