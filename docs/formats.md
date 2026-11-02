# Station file and chain format

Status: v1 of the format, written for prototype v0 (step 3). Owner: walto. Last updated 2026-11-02.

This document is the contract between everything that writes or reads station data: the recorder firmware (`rec-fw`), the Linux daemons, the cloud and the desktop app. The reference reader is `tools/lb-verify`. If this document and `lb-verify` disagree, that is a bug in one of them and must be fixed in the same pull request.

It implements architecture decisions D10 (audio format), D11 (archive of record), D12 (integrity) and D18 (customer-owned, plain files) from `architecture.md`.

---

## 1. Principles

- **Plain files.** exFAT, FLAC (or WAV in early firmware), JSON. A customer can open a card on any PC without our software.
- **The chain proves integrity, not the filesystem.** Every closed file is hashed into a hash-chained, signed log. A file that matches its chain entry is the file the station recorded.
- **Easy to write on a microcontroller.** No canonical-JSON rules: the hash covers the exact bytes the recorder wrote. Fixed line layout, so the recorder can build a line with `snprintf`.
- **Forward compatible.** Readers ignore unknown JSON fields and unknown chain entry types (they still check the hash and the link).

## 2. Card layout

Each archive card (SD A and SD B) is exFAT and holds:

```
/LB/<station_id>/
    card.json                       which card this is (section 3)
    chain/
        20261102.jsonl              chain entries, one file per UTC day (section 5)
        20261103.jsonl
    audio/
        20261102/
            LB0001_20261102T051000Z_000123.flac    one segment (section 4)
            LB0001_20261102T051000Z_000123.json    its sidecar (section 6)
            ...
```

- `station_id`: 1 to 32 characters from `A-Z a-z 0-9 -`. Prototypes use `LB0001`, `LB0002`, and so on.
- The audio folder name is the UTC date of the segment start.
- The recorder writes segments to one card at a time and switches cards at segment boundaries (D11). So a segment is on **one** card, but **every chain entry is on both cards**: when a card comes back from Linux or from a fault, the recorder first appends the entries it missed (it keeps the last few days in its own flash).
- Nothing else is required on the card. Other files (Linux catalogue, desktop app cache) must live outside `/LB/`.

## 3. `card.json`

Written once when the recorder formats or first adopts a card.

```json
{
  "format": "lb-card",
  "format_version": 1,
  "station_id": "LB0001",
  "card": "A",
  "adopted_utc": "2026-11-20T09:31:12Z",
  "card_serial": "0x1a2b3c4d"
}
```

`card` is `"A"` or `"B"` (the recorder's slot). `card_serial` is the SD card's CID serial number.

## 4. Audio segments

- File name: `<station_id>_<YYYYMMDDTHHMMSSZ>_<seq>.<ext>`, where the time is the segment's nominal UTC start, `seq` is the station's segment sequence number as 6 or more digits with leading zeros (it never resets), and `ext` is `flac` or `wav`.
- Length: 10 minutes, starting on a UTC 10-minute boundary (00:00, 00:10, ...). The first segment after boot and the last before a power loss are shorter.
- Format: **48 000 Hz, 24 bit, all channels in one file**. FLAC in the product; `rec-fw` milestone 1 writes plain WAV (RIFF, `WAVE_FORMAT_EXTENSIBLE`, PCM, little-endian, 3 bytes per sample), which `lb-verify` reads the same way.
- Channels: microphones first, then the **PPS channel last**. With 4 mics a file has 5 channels. The sidecar's `channel_map` is authoritative.
- If GNSS time is not yet known at boot, the recorder uses the RTC time and says so in the sidecar (`start_utc_source`). If there is no RTC time either, the time part is `19700101T000000Z` plus the boot's seconds, and `seq` keeps file names unique.

### 4.1 The PPS channel

The GNSS module's PPS output is wired into a spare PDM data line on the same SAI clock as the microphones (architecture C4). The decimation filter turns it into a pulse in its own channel: close to full-scale positive while PPS is high (about 100 ms), close to full-scale negative while it is low. Because it goes through exactly the same filter as the microphones, it has exactly the same delay, so a PPS edge found in this channel is the true time of the matching sample in the mic channels.

The recorder finds each rising edge (the point where the signal crosses zero, interpolated between samples) and writes it to the sidecar's PPS table. Anyone can re-derive the table from the audio itself.

## 5. The chain

### 5.1 Line format

Each chain file is UTF-8 text with one entry per line, ending in `\n`. Every line has exactly this layout:

```
{"e":ENTRY,"h":"HASH","s":"SIG"}
```

- `ENTRY` is a JSON object (no line breaks inside).
- `HASH` is the lowercase hex SHA-256 of the **exact bytes** of `ENTRY` as they appear in the line, from its opening `{` to its closing `}`.
- `SIG` is the lowercase hex ECDSA P-256 signature of the 32-byte `HASH` value (raw `r` then `s`, 32 bytes each, so 128 hex characters), or the empty string if the station has no signing key yet (section 5.4).

A reader finds `ENTRY` by matching the line against `^\{"e":(.*),"h":"([0-9a-f]{64})","s":"([0-9a-f]*)"\}$`. No canonical JSON is needed: the recorder hashes what it wrote.

### 5.2 Fields every entry has

| Field | Type | Meaning |
|---|---|---|
| `v` | int | Entry format version, `1` |
| `n` | int | Entry number, starting at 0 at the station's genesis, +1 per entry, never reset |
| `prev` | hex string | `HASH` of entry `n-1`; 64 zeros for `n = 0` |
| `t` | string | UTC time the entry was written, ISO 8601 with `Z` |
| `type` | string | Entry type (section 5.3) |

### 5.3 Entry types

| `type` | Extra fields | Written when |
|---|---|---|
| `genesis` | `station_id`, `key` (`{"alg": "ecdsa-p256" or "none", "pub": hex of the 65-byte uncompressed public key, "source": "atecc608" or "software"}`), `rec_fw` | once, when the station is first set up (`n = 0`) |
| `boot` | `rec_fw`, `rec_fw_sha256`, `config_sha256`, `reset_reason` | each recorder start |
| `segment` | `file`, `size`, `sha256`, `sidecar`, `sidecar_sha256`, `seq`, `start_utc`, `samples`, `card` | a segment and its sidecar are closed |
| `gap` | `from_utc`, `to_utc`, `reason` | audio was lost (power cut, card error, buffer overrun) |
| `config` | `config_sha256`, `effective_utc`, `summary` | configuration changed (takes effect at a segment boundary) |
| `card` | `card`, `event` (`adopted`, `switched_to`, `handed_to_linux`, `returned`, `failed`, `removed`) | card events |
| `gnss` | `event` (`lock`, `lost`), `fix` | GNSS lock changes |
| `key` | `key` (same shape as in `genesis`) | signing key changes (software key replaced by the ATECC608) |
| `note` | `text` | anything else worth an audit line |

`file` and `sidecar` are paths relative to `/LB/<station_id>/`, with `/` separators. `sha256` values are lowercase hex.

Readers check every entry's hash, link and signature whatever its type, and ignore types they do not know.

### 5.4 Signing

- The key is ECDSA P-256. In the product it lives in the ATECC608B and never leaves it; the ATECC608 signs a 32-byte digest, which is why the signature is over `HASH` directly.
- The public key is in the `genesis` entry, which is itself signed with that key, and is registered with the cloud when the station is made. A `key` entry, signed by the old key, introduces a new key for all later entries.
- Early `rec-fw` milestones have no key: `genesis.key.alg` is `"none"` and `SIG` is empty. `lb-verify` reports such a chain as "hash-chained, not signed". The chain still detects edits and gaps; it does not yet prove *who* wrote it.

### 5.5 Which entries a card holds

A card's chain files hold a contiguous run of entries `n0, n0+1, ... n_last`. A card that has been in the station since genesis starts at `n0 = 0`. A card inserted at a service visit starts later: its first entry's `prev` must match the last card's chain (or the cloud's), which `lb-verify` reports so it can be checked. Entries are written to the file for the UTC day of their `t`.

If the same entry number appears on two cards, the two lines must be identical byte for byte.

## 6. Sidecar JSON

One per segment, same name as the audio file with `.json`. Example (4 mics, PPS on channel 5):

```json
{
  "format": "lb-segment",
  "format_version": 1,
  "station_id": "LB0001",
  "file": "LB0001_20261102T051000Z_000123.flac",
  "seq": 123,
  "container": "flac",
  "sample_rate": 48000,
  "bits_per_sample": 24,
  "channels": 5,
  "samples": 28800000,
  "start_utc": "2026-11-02T05:10:00.000012Z",
  "start_utc_source": "pps",
  "channel_map": [
    {"ch": 1, "role": "mic", "mic": "M1", "pod_serial": null, "position_m": [0.20, 0.0, 0.0], "sens_dbfs_94db": null},
    {"ch": 2, "role": "mic", "mic": "M2", "pod_serial": null, "position_m": [-0.10, 0.173, 0.0], "sens_dbfs_94db": null},
    {"ch": 3, "role": "mic", "mic": "M3", "pod_serial": null, "position_m": [-0.10, -0.173, 0.0], "sens_dbfs_94db": null},
    {"ch": 4, "role": "mic", "mic": "M4", "pod_serial": null, "position_m": [0.0, 0.0, 0.25], "sens_dbfs_94db": null},
    {"ch": 5, "role": "pps"}
  ],
  "gain_db": 0,
  "rec_fw": "0.1.0",
  "rec_fw_sha256": "…",
  "config_sha256": "…",
  "pps": {
    "source": "pdm",
    "channel": 5,
    "edges": [[47999.42, 1793596201], [95999.44, 1793596202]],
    "timer_edges": [[47999.4, 1793596201], [95999.4, 1793596202]]
  },
  "gnss": {"fix": "3d", "lat": 60.1699, "lon": 24.9384, "alt_m": 25.1, "hacc_m": 1.8, "sats": 14},
  "time_quality": {"locked": true, "since_lock_s": 0, "est_error_us": 1.0},
  "gaps": [],
  "env": {"enclosure_c": 4.5, "battery_v": 13.2},
  "card": "A"
}
```

Field rules:

| Field | Rule |
|---|---|
| `format`, `format_version` | `"lb-segment"`, `1` |
| `file`, `seq`, `station_id` | must match the file name |
| `container` | `"flac"` or `"wav"`, must match the file |
| `sample_rate`, `bits_per_sample`, `channels`, `samples` | must match the audio file's own header |
| `start_utc` | UTC time of sample 0, microseconds, `Z` |
| `start_utc_source` | `"pps"` (from the PPS table), `"rtc"` (RTC only, no lock) or `"none"` |
| `channel_map` | one item per channel, in channel order; `role` is `"mic"`, `"pps"` or `"unused"`; `position_m` is the mic's position in the array frame (x east, y north, z up when the array heading is 0), `null` if not yet measured |
| `pps.edges` | list of `[sample_index, utc_unix_seconds]`: the sample (fractional, counted from sample 0 of this file) where the PPS channel rises, and the UTC second that starts at that edge. Strictly increasing. |
| `pps.timer_edges` | the same from the timer capture backup; may be empty |
| `time_quality.est_error_us` | the recorder's estimate of the error of `start_utc` |
| `gaps` | list of `{"start_sample": int, "samples": int, "reason": str}` where samples inside the file are zero-filled |
| `env` | optional; any sensor values available |

All other fields are optional for readers. Writers may add fields.

`start_utc` follows from the PPS table: `start_utc = utc - index / sample_rate` for any edge. Consecutive edges must be `sample_rate` samples apart per second, within the clock's tolerance (`lb-verify` warns beyond 200 ppm).

## 7. What `lb-verify` checks

1. Every chain line has the layout of section 5.1, its hash is right, `n` increases by one, and `prev` matches the previous entry's hash.
2. Signatures, when there is a key (needs the Python `cryptography` package).
3. Lines that appear on two cards are identical.
4. Each `segment` entry whose file is on the card: size and SHA-256 of the audio file and the sidecar match.
5. Each sidecar: required fields, matches its file name and the audio header, PPS table is increasing and spaced one second apart within 200 ppm, `start_utc` agrees with the PPS table within one sample.
6. Audio files and sidecars on the card that no chain entry mentions (warning: unchained file).

It prints a summary and exits with 0 if no errors were found, 1 otherwise.

## 8. Versioning

A change that old readers would get wrong raises `format_version` (sidecar, card) or `v` (chain entry). Adding optional fields does not.
