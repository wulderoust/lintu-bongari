"""Command line: `lb-verify CARD [CARD ...]` and `lb-verify demo FOLDER`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .verify import verify_cards


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "demo":
        return _demo(argv[1:])

    ap = argparse.ArgumentParser(
        prog="lb-verify",
        description="Check lintu-bongari station SD cards: hash chain, signatures, audio files and sidecars. "
        "Give one card, or both cards (A and B) of the same station. "
        "Run 'lb-verify demo FOLDER' to make a small example card to try it on.",
    )
    ap.add_argument("cards", nargs="+", type=Path, help="card root (e.g. E:\\), its LB folder, or a station folder")
    ap.add_argument("--pubkey", help="station public key (hex) if the cards do not hold the genesis entry")
    ap.add_argument("--quick", action="store_true", help="skip SHA-256 of audio files (sizes and headers only)")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("-v", "--verbose", action="store_true", help="also print info lines")
    ap.add_argument("--version", action="version", version=f"lb-verify {__version__}")
    args = ap.parse_args(argv)

    rep = verify_cards(args.cards, args.pubkey, deep=not args.quick)

    if args.json:
        print(json.dumps({
            "ok": rep.ok, "station_id": rep.station_id, "signed": rep.signed,
            "segments_checked": rep.segments_checked, "segments_on_other_cards": rep.segments_elsewhere,
            "errors": rep.errors, "warnings": rep.warnings, "info": rep.info,
        }, indent=2))
        return 0 if rep.ok else 1

    print(f"Station: {rep.station_id or '?'}")
    if args.verbose:
        for m in rep.info:
            print(f"  info:    {m}")
    for m in rep.warnings:
        print(f"  WARNING: {m}")
    for m in rep.errors:
        print(f"  ERROR:   {m}")
    print(f"Segments checked on these cards: {rep.segments_checked}"
          + (f" (plus {rep.segments_elsewhere} on another card)" if rep.segments_elsewhere else ""))
    if rep.ok:
        how = "signed and hash-chained" if rep.signed else "hash-chained, NOT signed"
        print(f"RESULT: OK ({how}), {len(rep.warnings)} warning(s)")
        return 0
    print(f"RESULT: FAILED, {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1


def _demo(argv: list[str]) -> int:
    from .writer import demo_card

    ap = argparse.ArgumentParser(prog="lb-verify demo", description="Write a small example card to FOLDER.")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--unsigned", action="store_true", help="no signing key (like early firmware)")
    args = ap.parse_args(argv)
    if args.folder.exists() and any(args.folder.iterdir()):
        print(f"{args.folder} is not empty; give an empty or new folder", file=sys.stderr)
        return 2
    st = demo_card(args.folder, signed=not args.unsigned)
    print(f"Example card written to {args.folder} (station folder {st}).")
    print(f"Now try:  lb-verify {args.folder}")
    return 0
