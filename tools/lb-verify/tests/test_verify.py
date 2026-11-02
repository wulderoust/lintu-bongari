import json
import shutil
from pathlib import Path

import pytest

from lb_verify.audio import read_info
from lb_verify.cli import main
from lb_verify.verify import verify_cards
from lb_verify.writer import demo_card


@pytest.fixture
def card(tmp_path):
    demo_card(tmp_path / "A", segments=2, seconds=2)
    return tmp_path / "A"


def station(card: Path) -> Path:
    return card / "LB" / "LB0000"


def chain_file(card: Path) -> Path:
    return next((station(card) / "chain").glob("*.jsonl"))


def test_clean_card_passes(card):
    rep = verify_cards([card])
    assert rep.ok, rep.errors
    assert rep.signed
    assert rep.segments_checked == 2
    assert rep.warnings == []


def test_unsigned_card_passes_but_reports_unsigned(tmp_path):
    demo_card(tmp_path, segments=1, seconds=1, signed=False)
    rep = verify_cards([tmp_path])
    assert rep.ok, rep.errors
    assert not rep.signed


def test_wav_header(card):
    wav = next(station(card).rglob("*.wav"))
    info = read_info(wav)
    assert (info.container, info.sample_rate, info.bits_per_sample, info.channels, info.samples) == (
        "wav", 48000, 24, 5, 96000)


def test_flac_streaminfo(tmp_path):
    # Minimal FLAC: marker + last-block STREAMINFO for 48 kHz, 5 ch, 24 bit, 28 800 000 samples.
    rate, ch, bps, total = 48000, 5, 24, 28_800_000
    x = (rate << 44) | ((ch - 1) << 41) | ((bps - 1) << 36) | total
    si = bytes(10) + x.to_bytes(8, "big") + bytes(16)
    p = tmp_path / "x.flac"
    p.write_bytes(b"fLaC" + bytes([0x80]) + (34).to_bytes(3, "big") + si)
    info = read_info(p)
    assert (info.container, info.sample_rate, info.channels, info.bits_per_sample, info.samples) == (
        "flac", rate, ch, bps, total)


def test_changed_audio_byte_is_caught(card):
    wav = next(station(card).rglob("*.wav"))
    b = bytearray(wav.read_bytes())
    b[-1] ^= 1
    wav.write_bytes(bytes(b))
    rep = verify_cards([card])
    assert not rep.ok
    assert any("SHA-256 does not match" in e for e in rep.errors)


def test_edited_chain_entry_is_caught(card):
    cf = chain_file(card)
    text = cf.read_text()
    cf.write_text(text.replace('"reset_reason":"power_on"', '"reset_reason":"watchdog"'))
    rep = verify_cards([card])
    assert any("hash mismatch" in e for e in rep.errors)


def test_rehashed_but_unsigned_edit_is_caught_by_signature(card):
    """Someone edits an entry and recomputes its hash: the signature no longer matches."""
    import hashlib

    cf = chain_file(card)
    lines = cf.read_text().splitlines(keepends=True)
    line = lines[1]
    entry = line[len('{"e":'): line.index(',"h":"')]
    new_entry = entry.replace('"power_on"', '"watchdog"')
    new_h = hashlib.sha256(new_entry.encode()).hexdigest()
    sig = line[line.index(',"s":"') + 6: -3]
    lines[1] = '{"e":' + new_entry + ',"h":"' + new_h + '","s":"' + sig + '"}\n'
    cf.write_text("".join(lines))
    rep = verify_cards([card])
    assert any("signature is NOT valid" in e for e in rep.errors)
    assert any("prev does not match" in e for e in rep.errors)


def test_deleted_entry_is_caught(card):
    cf = chain_file(card)
    lines = cf.read_text().splitlines(keepends=True)
    del lines[2]
    cf.write_text("".join(lines))
    rep = verify_cards([card])
    assert any("missing entries" in e for e in rep.errors)


def test_unchained_file_warns(card):
    d = next(station(card).rglob("*.wav")).parent
    (d / "LB0000_20261102T060000Z_000099.wav").write_bytes(b"RIFF")
    rep = verify_cards([card])
    assert any("unchained" in w for w in rep.warnings)


def test_sidecar_mismatch_is_caught(card):
    side = next(station(card).rglob("*.json"))
    if side.name == "card.json":
        side = sorted(station(card).rglob("*_*.json"))[0]
    sc = json.loads(side.read_text())
    sc["channels"] = 4
    side.write_text(json.dumps(sc))
    rep = verify_cards([card])
    errs = "\n".join(rep.errors)
    assert "SHA-256 does not match" in errs
    assert "'channels' is 4 but the audio file says 5" in errs


def test_two_cards_segments_split(tmp_path):
    """Segments on one card, chain on both: verifying both cards checks everything."""
    a = tmp_path / "A"
    demo_card(a, segments=2, seconds=1)
    b = tmp_path / "B"
    shutil.copytree(a, b)
    # Move segment 2 to card B only, segment 1 stays on A only.
    sa, sb = station(a), station(b)
    for f in sorted(sa.rglob("*_000002.*")):
        f.unlink()
    for f in sorted(sb.rglob("*_000001.*")):
        f.unlink()
    rep_a = verify_cards([a])
    assert rep_a.ok and rep_a.segments_checked == 1 and rep_a.segments_elsewhere == 1
    rep_ab = verify_cards([a, b])
    assert rep_ab.ok, rep_ab.errors
    assert rep_ab.segments_checked == 2 and rep_ab.segments_elsewhere == 0


def test_cards_with_different_copies_of_an_entry(tmp_path):
    a = tmp_path / "A"
    demo_card(a, segments=1, seconds=1)
    b = tmp_path / "B"
    shutil.copytree(a, b)
    cf = chain_file(b)
    cf.write_text(cf.read_text().replace('"power_on"', '"brownout"'))
    rep = verify_cards([a, b])
    assert any("differs from the copy" in e for e in rep.errors)


def test_pps_start_mismatch(card):
    side = sorted(station(card).rglob("*_000001.json"))[0]
    sc = json.loads(side.read_text())
    sc["start_utc"] = sc["start_utc"][:-7] + "100000Z"  # move start by ~0.1 s
    side.write_text(json.dumps(sc))
    rep = verify_cards([card])
    assert any("disagrees with pps.edges" in e for e in rep.errors)


def test_cli_demo_and_verify(tmp_path, capsys):
    target = tmp_path / "demo"
    assert main(["demo", str(target)]) == 0
    assert main([str(target)]) == 0
    out = capsys.readouterr().out
    assert "RESULT: OK" in out
