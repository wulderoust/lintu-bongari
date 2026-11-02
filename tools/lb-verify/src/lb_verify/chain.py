"""Parse and verify the hash chain (docs/formats.md section 5)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

LINE_RE = re.compile(r'^\{"e":(.*),"h":"([0-9a-f]{64})","s":"([0-9a-f]*)"\}$', re.DOTALL)
ZERO_HASH = "0" * 64


@dataclass
class Entry:
    raw_line: str
    entry_bytes: bytes
    h: str
    sig: str
    e: dict
    source: str  # "file:line" for messages

    @property
    def n(self) -> int:
        return self.e["n"]


@dataclass
class ChainResult:
    entries: dict[int, Entry] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    signed: bool = False
    no_crypto: bool = False


def parse_line(line: str, source: str) -> Entry:
    m = LINE_RE.match(line)
    if not m:
        raise ValueError(f"{source}: line does not have the {{\"e\":...,\"h\":...,\"s\":...}} layout")
    entry_text, h, sig = m.group(1), m.group(2), m.group(3)
    entry_bytes = entry_text.encode("utf-8")
    try:
        e = json.loads(entry_text)
    except json.JSONDecodeError as ex:
        raise ValueError(f"{source}: entry is not valid JSON ({ex})") from None
    if not isinstance(e, dict):
        raise ValueError(f"{source}: entry is not a JSON object")
    for k, typ in (("v", int), ("n", int), ("prev", str), ("t", str), ("type", str)):
        if not isinstance(e.get(k), typ):
            raise ValueError(f"{source}: entry field '{k}' missing or wrong type")
    return Entry(line, entry_bytes, h, sig, e, source)


def read_chain_dir(chain_dir: Path, result: ChainResult) -> list[Entry]:
    """Read all chain files of one card, in file-name (UTC date) order."""
    out: list[Entry] = []
    for path in sorted(chain_dir.glob("*.jsonl")):
        with open(path, "r", encoding="utf-8", newline="") as f:
            data = f.read()
        lines = data.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        elif lines:
            result.warnings.append(
                f"{path.name}: last line has no newline (write interrupted?); it is still checked"
            )
        for i, line in enumerate(lines, 1):
            src = f"{path.name}:{i}"
            if line.endswith("\r"):
                result.errors.append(f"{src}: line ends with CR; chain lines must end with LF only")
                line = line[:-1]
            try:
                out.append(parse_line(line, src))
            except ValueError as ex:
                result.errors.append(str(ex))
    return out


def _load_verifier(pub_hex: str):
    try:
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        from cryptography.hazmat.primitives import hashes
    except ImportError:
        return None
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(pub_hex))

    def verify(digest_hex: str, sig_hex: str) -> bool:
        from cryptography.exceptions import InvalidSignature

        sig = bytes.fromhex(sig_hex)
        if len(sig) != 64:
            return False
        r = int.from_bytes(sig[:32], "big")
        s = int.from_bytes(sig[32:], "big")
        try:
            pub.verify(
                utils.encode_dss_signature(r, s),
                bytes.fromhex(digest_hex),
                ec.ECDSA(utils.Prehashed(hashes.SHA256())),
            )
            return True
        except InvalidSignature:
            return False

    return verify


def verify_chain(card_entries: dict[str, list[Entry]], pubkey_hex: str | None = None) -> ChainResult:
    """Verify the chain read from one or more cards.

    card_entries maps a card label (e.g. its path) to the entries read from it.
    pubkey_hex optionally supplies the station's public key when the cards do not
    hold the genesis entry (a card inserted at a service visit).
    """
    res = ChainResult()

    # Merge cards: the same n on two cards must be byte-identical.
    for card, entries in card_entries.items():
        seen_here: set[int] = set()
        for ent in entries:
            n = ent.n
            if n in seen_here:
                res.errors.append(f"[{card}] {ent.source}: entry n={n} appears twice on this card")
                continue
            seen_here.add(n)
            other = res.entries.get(n)
            if other is None:
                res.entries[n] = ent
            elif other.raw_line != ent.raw_line:
                res.errors.append(
                    f"[{card}] {ent.source}: entry n={n} differs from the copy at {other.source}"
                )

    if not res.entries:
        res.errors.append("no chain entries found")
        return res

    ns = sorted(res.entries)
    n0, n_last = ns[0], ns[-1]
    missing = [n for n in range(n0, n_last + 1) if n not in res.entries]
    if missing:
        shown = ", ".join(map(str, missing[:10])) + (" ..." if len(missing) > 10 else "")
        res.errors.append(f"chain has missing entries: {shown}")
    if n0 == 0:
        res.info.append(f"chain entries 0..{n_last} (from genesis)")
    else:
        res.warnings.append(
            f"chain starts at entry {n0}, not at genesis; its prev hash "
            f"{res.entries[n0].e['prev']} must match the previous card or the cloud"
        )
        res.info.append(f"chain entries {n0}..{n_last}")

    # Keys: from genesis / key entries as we walk, or the supplied one.
    key_alg = None
    verifier = None
    if pubkey_hex:
        key_alg = "ecdsa-p256"
        verifier = _load_verifier(pubkey_hex)
        if verifier is None:
            _warn_no_crypto(res)
    unsigned_count = 0
    sig_bad = 0

    for n in ns:
        ent = res.entries[n]
        e = ent.e
        calc = hashlib.sha256(ent.entry_bytes).hexdigest()
        if calc != ent.h:
            res.errors.append(f"{ent.source}: entry n={n} hash mismatch (entry was changed)")
        if e.get("v") != 1:
            res.warnings.append(f"{ent.source}: entry version v={e.get('v')} is newer than this tool knows")
        if n == 0:
            if e["prev"] != ZERO_HASH:
                res.errors.append(f"{ent.source}: genesis entry prev must be all zeros")
            if e["type"] != "genesis":
                res.errors.append(f"{ent.source}: entry 0 must have type 'genesis'")
        elif (n - 1) in res.entries:
            if e["prev"] != res.entries[n - 1].h:
                res.errors.append(f"{ent.source}: entry n={n} prev does not match entry {n-1} (chain broken)")

        # The genesis entry is signed by the key it introduces.
        if e["type"] == "genesis":
            key_alg, verifier = _key_from_entry(ent, res, key_alg, verifier)

        # Signature check (with the key in force for this entry).
        if key_alg == "ecdsa-p256":
            if not ent.sig:
                res.errors.append(f"{ent.source}: entry n={n} is not signed but the station has a key")
            elif verifier is not None and not verifier(ent.h, ent.sig):
                sig_bad += 1
                res.errors.append(f"{ent.source}: entry n={n} signature is NOT valid")
        else:
            if ent.sig:
                res.warnings.append(f"{ent.source}: entry n={n} has a signature but no key is known")
            unsigned_count += 1

        # A 'key' entry is signed by the old key; the new key applies to later entries.
        if e["type"] == "key":
            key_alg, verifier = _key_from_entry(ent, res, key_alg, verifier)

    res.signed = unsigned_count == 0 and sig_bad == 0 and not res.no_crypto
    if unsigned_count:
        res.info.append(f"{unsigned_count} entries hash-chained but not signed (no station key yet)")
    return res


def _warn_no_crypto(res: ChainResult) -> None:
    if not res.no_crypto:
        res.warnings.append(
            "Python 'cryptography' package not installed: signatures NOT checked "
            "(pip install cryptography)"
        )
        res.no_crypto = True


def _key_from_entry(ent: Entry, res: ChainResult, key_alg, verifier):
    key = ent.e.get("key") or {}
    alg = key.get("alg")
    if alg == "none":
        return None, None
    if alg != "ecdsa-p256":
        res.errors.append(f"{ent.source}: unknown key alg {alg!r}")
        return key_alg, verifier
    try:
        v = _load_verifier(key["pub"])
    except Exception as ex:  # malformed key
        res.errors.append(f"{ent.source}: public key is not valid ({ex})")
        return key_alg, verifier
    if v is None:
        _warn_no_crypto(res)
    return "ecdsa-p256", v
