# Edge software design (on-station)

Status: **Draft for step 1 (design)**. No code yet. Requirement IDs (REQ-…) refer to `docs/requirements.md` (PR #1); see §17 for traceability. Decisions marked **[Proposed]** need walto's review; items marked **[Open]** are waiting on answers or on the Hardware / Requirements docs.

## 1. Scope and principles

This document covers the software that runs on each recording station: capturing multi-channel audio, deciding when to record, flagging acoustic activity, keeping time, storing data with an audit trail, uploading over 4G, reporting health, and taking remote config and updates.

Out of scope here: species identification (runs in the cloud or on the user's computer), the cloud backend and app, and the electronics themselves (Hardware doc).

Design principles, in priority order:

1. **Never lose or silently corrupt a recording.** Data is the product, and it may be used as evidence in regulatory work. Every file is checksummed, logged, and traceable from microphone to cloud.
2. **Survive unattended for 2-4 weeks in any Finnish season.** Assume power cuts, -30 °C, no 4G for days, and nobody on site.
3. **Degrade gracefully.** Low battery or no network reduces what we do, in a predictable order. It never crashes the station.
4. **Easy for the buyer.** Field setup is "mount, power on, scan QR". Everything else is remote.
5. **Recoverable remotely.** Any software fault can be fixed without a site visit (watchdogs, A/B updates, rollback).

## 2. System overview

```
             ┌────────────────────── Station ───────────────────────┐
 Mics ──► ADC (TDM) ──► recorder ──► segment files (FLAC) ──► store/ledger
 (4ch)          ▲          │                                     │
 GNSS PPS ──────┘          ▼                                     ▼
 (spare channel)        detector ──► event index ──────────► uploader ──► 4G ──► Cloud
                                                                 ▲
  scheduler ── decides when recorder/modem/uploader run          │
  telemetry ── health metrics ───────────────────────────────────┤
  config-agent ◄── desired config ◄──────────────────────────────┤
  RAUC (OTA) ◄── signed bundles ◄────────────────────────────────┘
  supervisor MCU ── power, RTC, watchdog, battery, heater, wakes SoC
             └───────────────────────────────────────────────────────┘
```

Two processors **[Proposed, pending Hardware doc]**:

- **Linux SoC** (main computer): recording, compression, detection, storage, upload, OTA.
- **Supervisor MCU** (always on, a few mW): owns the power rails, RTC, hardware watchdog, battery/solar monitoring, heater control, and wakes or power-cycles the SoC and modem. It can hard-reset a hung Linux or modem, which is what makes 4-week unattended runs safe.

## 3. OS and stack [Proposed]

| Layer | Prototype (step 3) | Product (step 4) |
|---|---|---|
| Compute | Raspberry Pi CM4 or CM5 on a carrier board | Same, unless Hardware doc picks a lower-power SoC (e.g. i.MX8M Mini, STM32MP2) |
| OS | Raspberry Pi OS Lite (Debian) 64-bit | Yocto-built minimal Linux, read-only rootfs |
| Updates | RAUC A/B from the start | RAUC A/B, signed bundles |
| Init / supervision | systemd (watchdog, restart policies) | same |
| Core daemons | **Rust** | Rust |
| Tooling, tests, field scripts | Python | Python (dev only, not on device in product) |
| Local catalog & queue | SQLite (WAL mode) | same |
| Time | chrony + gpsd with PPS | same |
| Cellular | ModemManager + NetworkManager | same |
| Telemetry / control channel | MQTT over TLS (mutual auth) | same |
| Remote support shell | WireGuard tunnel, opened on demand | same |
| Supervisor MCU firmware | C with Zephyr RTOS | same |

Why these:

- **Linux** because multi-channel TDM audio, FLAC/Opus encoders, a cellular stack, TLS, and an A/B updater all exist and are proven there. Writing all of that on a bare MCU would cost months and still be less robust.
- **Raspberry Pi first** because walto can get it running fast and the ecosystem is huge. Moving to Yocto later gives a small, reproducible, read-only image for the sold product. The daemons do not change between the two.
- **Rust** for the daemons that run for weeks: memory safety, no garbage collector pauses during audio capture, low CPU (which is low power), single static binaries that are simple to ship in OTA bundles.
- **RAUC** for updates: mature, A/B with automatic fallback, signed bundles, works on both Raspberry Pi OS and Yocto. Mender is the main alternative; RAUC has no server lock-in.
- **SQLite** as the single local source of truth for files, events, upload state and the ledger. It survives power loss when used in WAL mode with `synchronous=FULL`.

## 4. Software components

Each is a systemd service with `WatchdogSec=` and restart limits.

| Service | Job |
|---|---|
| `lb-recorder` | Captures all channels from ALSA, writes fixed-length FLAC segments, writes per-segment metadata, records the PPS-to-sample alignment. |
| `lb-detector` | Reads finished segments, computes activity/noise features, writes an event index. No species ID. |
| `lb-store` | Hashes, catalogs and ledgers every file; enforces retention and disk-full policy; verifies integrity in the background. |
| `lb-uploader` | Prioritised, resumable, budgeted uploads over 4G; manages modem on/off windows with the scheduler. |
| `lb-scheduler` | Computes recording windows (sun-based, fixed, duty-cycle) and power-aware degradation; tells the supervisor when to wake next. |
| `lb-telemetry` | Collects health metrics and sends them over MQTT; raises alerts. |
| `lb-config` | Receives, validates and atomically applies remote config, with rollback. |
| `lb-setup` | First-boot and field-setup flow (QR pairing, self-test). |
| RAUC + `lb-health` | OTA install and post-update health check that marks the new slot good or rolls back. |
| `supervisor-fw` | MCU firmware: power, RTC, watchdog, battery, heater, wake timer. Talks to the SoC over UART or I²C. |

Components talk through the SQLite catalog (tables for segments, events, upload queue, ledger) plus a small local Unix-socket API for live status. No message broker on the device; fewer moving parts.

## 5. Multi-channel recording

### 5.1 Capture

- **Interface:** one multi-channel TDM/I²S ADC (for example TI TLV320ADC6140, 4 channels, or two of them for 8) to the SoC's I²S port. All channels share one sample clock, which is what makes direction-finding between mics on the same station possible. **[Open: Hardware doc picks the ADC.]**
- **Format:** 48 kHz, 24-bit (stored as 24-bit FLAC). 48 kHz covers all Finnish bird vocalisations with margin and matches what common classifiers (e.g. BirdNET) expect. Configurable down to 32 kHz to save storage and power.
- **Channels:** N microphone channels plus, if the ADC has a spare one, the **GNSS PPS pulse fed into a spare channel** (see §7). Channel map (which mic is where, its serial number and calibration) is part of the station config and goes into every file's metadata.
- **Gain:** fixed analog gain per deployment profile (no automatic gain control, because AGC destroys the ability to compare loudness for counting and distance estimation). Gain and calibration values are logged per file.
- **Buffering:** a lock-free ring buffer of ~10 s in RAM between ALSA and the encoder, so a slow SD card write never drops samples. Any overrun is logged as an explicit gap with exact sample counts, never hidden.

### 5.2 Segment files

- Fixed-length segments, default **5 minutes**, aligned to UTC wall-clock (e.g. 05:00:00, 05:05:00). Short enough that a power cut loses at most a few seconds of one file, long enough to keep file count manageable.
- One multi-channel FLAC per segment. FLAC is lossless (needed for legal use and for re-analysis with future classifiers), open, and stores an MD5 of the decoded audio internally.
- File name: `{station_id}_{YYYYMMDDTHHMMSSZ}_{seq}.flac`, plus a JSON sidecar with: station ID, firmware version, config hash, channel map, mic serials, gain, sample rate, first-sample UTC time, time-sync quality, PPS alignment table, GNSS position, enclosure temperature, battery voltage, gap list.
- Writes go to a `.partial` file that is fsynced and atomically renamed when complete. A crash leaves at most one `.partial`, which is repaired (truncated to the last valid FLAC frame) and logged on next boot.

### 5.3 Data volume (why we can't upload everything)

| Setting | Raw | FLAC (≈55 %) | Per day if continuous |
|---|---|---|---|
| 4 ch × 48 kHz × 24 bit | 576 kB/s | ~320 kB/s | ~27 GB |
| 4 ch, dawn+dusk only (~8 h/day) | | | ~9 GB |
| 1 ch × 48 kHz × 24 bit | 144 kB/s | ~80 kB/s | ~7 GB |

So the station **keeps full lossless audio locally** (retrieved on pickup or on request) and **uploads a selected subset** over 4G (§9). REQ-O1/O2 require 28 days continuous on all channels with the whole deployment held locally: for 4 channels that is ~750 GB, so **1 TB industrial storage is the minimum** for a 4-channel station (2 TB for 8 channels). Local masters are deleted only after the cloud has verified their hash (REQ-I3) or the station is collected.

Power consequence: 28 days continuous at ~1.5 W is ~1 kWh. Without useful winter solar that means a large battery (e.g. ~100 Ah at 12 V LiFePO4 with margin). This is the main input to the Hardware doc's power budget.

## 6. Scheduling and power saving

### 6.1 Recording profiles

Profiles are config, selectable per deployment from the app. **Continuous is the default** whenever power allows (REQ-C3, REQ-O1); the other profiles exist for low-power deployments and standard survey methods.

- **Continuous** 24/7.
- **Sun-based** windows computed on the station from its GNSS position and date: e.g. dawn chorus from 1 h before civil dawn to 4 h after sunrise, dusk from 1 h before sunset to 1 h after civil dusk. Works through Finnish summer (sun barely sets in Lapland) and winter (polar night) because the rule falls back to fixed clock windows when the sun event does not occur.
- **Nocturnal migration (nocmig)** window: dusk to dawn, typically spring and autumn.
- **Duty cycle**, e.g. 1 min on / 4 min off, for long low-power deployments and for standard protocols.
- **Custom** list of windows, combinable with the above.

The schedule for the next 48 h is computed ahead and shown in the app, so the buyer sees exactly what will be recorded.

### 6.2 Sleep and wake

Between windows the SoC is powered off completely; the supervisor MCU keeps the RTC and wakes it ~2 min before the next window (boot + time sync + mic check). Modem is powered only during upload windows. Target figures to check with Hardware:

| State | Target power |
|---|---|
| Sleeping (MCU + RTC only) | < 10 mW |
| Recording + detection, modem off | < 1.5 W |
| Uploading over 4G | 2.5-4 W, short bursts |

### 6.3 Power-aware degradation

The scheduler reads battery state of charge, solar input and temperature from the supervisor and steps down in a fixed order as energy runs short:

1. Reduce upload windows (keep telemetry).
2. Upload only event index and telemetry, no audio.
3. Shrink recording to priority windows (dawn chorus first).
4. Reduce channels (keep the reference mic).
5. Telemetry heartbeat only, recording paused.
6. Safe shutdown; MCU wakes daily to check if charge recovered.

Every step change is logged and reported, so the data user knows why a gap exists. Thresholds are config.

### 6.4 Winter specifics

- LiFePO4 must not be charged below 0 °C: the supervisor blocks charging and uses the heater (if fitted) before charging. **[Open: battery chemistry from Hardware.]**
- Boot is gated on enclosure temperature being inside the SoC/SD card rated range; the MCU can pre-heat.
- Mic icing or snow cover shows up as loss of high frequencies and lower noise floor; the detector flags this as a data quality issue (§8).

## 7. Time synchronisation

Accurate time matters for three things: legal timestamps, combining counts across stations, and **localising a bird from arrival-time differences between stations** (sound travels ~34 cm per ms, so 1 ms error ≈ 34 cm position error).

**[Proposed]** design:

1. **GNSS receiver with PPS** on every station. gpsd + chrony discipline the system clock to well under 1 µs from PPS. Position is logged too.
2. **Sample-accurate alignment.** System time alone is not enough because the ADC's crystal drifts (tens of ppm, temperature dependent). Two ways, best first:
   - **PPS in an audio channel:** the PPS pulse, attenuated, goes into a spare ADC channel. Each second's pulse is found in the audio itself, so every sample has a GNSS-traceable timestamp, immune to software latency. This is the method used by research microphone arrays.
   - **Software alignment:** the recorder logs the sample counter at each PPS interrupt. Accurate to roughly 10-100 µs, depending on kernel latency.
   Either way the sidecar carries a table of (sample index → UTC) once per second, so the cloud can resample and align stations exactly.
3. **Fallback:** if GNSS has no fix (dense forest, indoors), chrony uses NTP over 4G (~5-50 ms) and the RTC. Each file records which source and estimated error were in effect, so analysis knows which data is good enough for localisation.
4. The supervisor MCU's RTC (TCXO-grade, ±2 ppm) keeps time across sleep so schedules are right even before GNSS fixes.

## 8. On-device event detection (no species ID)

Purpose: decide **what to upload first** and give a cheap activity overview. It must be conservative: it flags, it never deletes, because all audio is kept locally.

Per channel, per segment, computed on a short-time spectrum (e.g. 1024-point FFT, 50 % overlap):

- **Band energy detector**, 1-12 kHz, against an adaptive noise floor (running median per frequency band). Above-threshold regions longer than ~50 ms become candidate events, merged across channels, padded by 1-2 s.
- **Noise/weather classification** using spectral flatness, low-frequency energy and inter-channel coherence: wind, rain, and anthropogenic noise (traffic, aircraft) get flagged so they're not uploaded as "events" and so data quality is known.
- **Per-minute summary:** RMS level, noise floor, event count, acoustic indices (e.g. ACI, NDSI). Small, always uploaded, gives the app a live activity heatmap.
- **Mic health:** dead channel, clipping, DC offset, channel imbalance, high-frequency loss (icing/wet membrane).

CPU cost is small (well under 10 % of one core on a CM4) and runs after each segment closes, not in the capture path. Thresholds are config so they can be tuned per site from the cloud.

## 9. Compression and upload over 4G

### 9.1 What gets uploaded, in priority order

1. Telemetry and alerts (tiny, always).
2. Ledger head and file manifests (tiny, always; see §10).
3. Per-minute summaries and event index.
4. **Event clips**: detected events with padding, all channels, FLAC (lossless) by default.
5. **Reference stream**: one channel of everything recorded, Opus at ~64 kbit/s (≈0.7 GB/day continuous), for cloud species ID over the full period. Configurable on/off.
6. **On-demand requests** from the cloud: specific time ranges in full FLAC (user asks "give me 05:10-05:20, all channels").
7. Full-archive trickle upload if budget allows.

A **daily data budget** (e.g. 1 GB/day, set to match the SIM plan) caps 4-7. When the budget runs out, items wait. **[Open: SIM plan and budget.]**

### 9.2 Transport

- **HTTPS uploads with resumable chunks** (S3-compatible multipart via pre-signed URLs, or the tus protocol; decided with the Cloud doc). A chunk interrupted by 4G dropout resumes from where it stopped.
- **Idempotent by content hash:** every object is named by its SHA-256, so retries never create duplicates and the cloud can verify integrity on arrival.
- Cloud acknowledges each object; only acknowledged objects are marked uploaded. Local copies are kept regardless until retention policy and pickup say otherwise.
- TLS with a per-device client certificate (private key in a secure element if Hardware fits one, e.g. ATECC608 or TPM).

### 9.3 Buffering during outages

The upload queue lives in SQLite and on disk, so it survives reboots and multi-day outages. Retry with exponential backoff and jitter; when the link comes back, priorities above are respected (telemetry first). Disk space accounting reserves room so recordings never stop because of a full upload queue (oldest *already uploaded* Opus copies are evicted first; master FLAC is never evicted automatically unless config says so, and that is logged).

### 9.4 Connectivity

- LTE Cat-1 or Cat-4 modem (Cat-M1/NB-IoT are too slow for audio). ModemManager handles attach; signal metrics go to telemetry.
- No inbound connections (4G is usually behind carrier NAT). All channels are outbound: MQTT for control, HTTPS for data, WireGuard for support shell.

## 10. Storage integrity and audit trail

Goal: anyone receiving the data can verify that **a given file was recorded by station X at time T and has not been changed since**.

- **Per file:** SHA-256 of the FLAC and sidecar, plus FLAC's internal MD5 of audio samples.
- **Hash-chained ledger:** an append-only log in SQLite (also exported as JSON lines) where each entry contains: file hash, metadata hash, time, sequence number, and the **hash of the previous entry**. Removing or editing any past entry breaks the chain.
- **Signed:** entries (or batches) are signed with the station's private key (Ed25519). The public key is registered with the cloud at manufacturing/pairing.
- **Anchored:** the current chain head is sent with telemetry every few minutes. Since the cloud holds earlier heads, even physical access to the station cannot rewrite history without detection.
- Non-audio events are in the ledger too: config changes, updates, gaps, time-source changes, degradation steps, manual operations. This is the audit trail for legal use.
- **Background scrub:** `lb-store` re-reads and re-hashes stored files at low priority and reports any mismatch (SD/flash bit rot).
- **Filesystem:** separate data partition on industrial-grade storage (pSLC microSD/eMMC or SSD), ext4 with journaling; read-only root filesystem. On low battery the supervisor signals the SoC to close the current segment and shut down cleanly before cutting power.

## 11. Health telemetry

Sent over MQTT/TLS every 15 min during awake periods (heartbeat every 1-6 h while asleep, by MCU-triggered wake), batched when offline.

- **Power:** battery voltage, current, state of charge, solar input, temperature of battery.
- **Environment:** enclosure temperature and humidity, heater state.
- **Audio:** per-channel RMS, noise floor, clipping count, mic health flags.
- **Storage:** free space, write errors, scrub results, upload queue size.
- **Network:** RSRP/RSRQ/SINR, operator, bytes used today vs budget.
- **Time:** source (GNSS/NTP/RTC), offset estimate, GNSS fix and satellites.
- **System:** uptime, boot reason, service restarts, CPU temp, firmware version and slot, config version.

Alerts (sent immediately): mic failure, storage near full or errors, battery critical, enclosure open (if a switch is fitted), time sync lost for > N hours, update rolled back.

## 12. Remote config and remote access

- **Desired/reported state:** the cloud publishes a desired config document; the station reports what it is actually running. Mismatch is visible in the app.
- Config is a single versioned JSON document validated against a schema, signed by the cloud, and **applied atomically** at the next safe point (between segments). If services are unhealthy within 10 min after applying, the station reverts to the previous config and reports why.
- Everything the buyer can change in the app (profiles, windows, gain preset, budget, detector thresholds, telemetry interval) is config, not code.
- **Support access:** a WireGuard tunnel to our support hub, opened only on request from the cloud, auto-closes after a time limit, logged in the ledger. SSH key-only, no passwords.

## 13. Safe OTA updates

- **A/B root filesystem with RAUC:** the update is written to the inactive slot while the station keeps recording. Bundles are signed; the station refuses unsigned or wrongly-signed bundles.
- **Boot counting:** the bootloader tries the new slot a limited number of times. `lb-health` marks it good only after recorder, detector, uploader and time sync all report healthy and a test segment is written. Otherwise it falls back to the old slot automatically and reports.
- **Timing:** installs only outside recording windows, with enough battery, and downloads are resumable over the budgeted 4G.
- **Staged rollout:** cloud releases to a canary group of stations first, then the fleet.
- **Data is never touched** by updates (separate partition). Config schema migrations ship with the update and are reversible.
- **Supervisor MCU firmware** updates are rare, done through a dual-bank MCU bootloader (e.g. MCUboot under Zephyr) with the same sign-and-fallback rule.

## 14. Field setup (buyer experience)

1. Buyer mounts station and mics, connects battery, presses power.
2. Station boots, self-tests (each mic, storage, GNSS, modem) and shows result on a status LED pattern.
3. Buyer scans the QR code on the station with the app; station is claimed to their account (pairing uses the device certificate, no passwords typed).
4. App shows live levels from each mic (short test clips uploaded) and the recording plan for the next 48 h. Buyer confirms.
5. If no 4G at the spot, setup works over the phone via BLE or Wi-Fi hotspot, and the station records offline. **[Open: which local link the Hardware doc fits.]**

## 15. Testing strategy

- **Unit and property tests** for the ledger, scheduler (sun times for all of Finland across a whole year, including polar day/night), and upload queue.
- **Fault injection rig:** repeated random power cuts during writes (target: zero corrupted files over 1000 cuts), 4G dropouts of minutes to days, full disk, GNSS loss, clock jumps.
- **Soak test:** 30 days continuous on the bench before every release.
- **Cold chamber:** boot, record and update at -30 °C.
- **Time sync verification:** two stations recording the same click from a known position; measured arrival-time difference vs geometry.
- **Reference audio regression:** known recordings replayed through the pipeline; detector output must stay within tolerance across releases.

## 16. Prototype plan (input to step 3)

1. Bench: CM4/CM5 + 4-ch TDM ADC + GNSS with PPS. `lb-recorder` writing 5-min FLAC segments with sidecar and PPS alignment.
2. Add `lb-store` ledger and `lb-uploader` with a test bucket; power-cut and outage tests.
3. Add scheduler + supervisor MCU sleep/wake; measure real power in each state.
4. Add detector, telemetry, config; then RAUC A/B.
5. Two-station outdoor trial for time-sync and detector tuning.

## 17. Requirements traceability

| Requirement | Where handled |
|---|---|
| REQ-T1 GNSS-disciplined time, <10 ms to UTC, lock state logged | §7 (GNSS + PPS, chrony, per-file time source and error) |
| REQ-T2 shared clock in array <0.1 ms, <1 ms between stations | §5.1 single TDM ADC per station, §7 PPS-in-audio alignment |
| REQ-T3 UTC everywhere, sun times from station position | §5.2 file naming/sidecar, §6.1 |
| REQ-A1 lossless FLAC archive ≥48 kHz | §5.1, §5.2; Opus only for reference stream (§9.1) |
| REQ-A2 fixed recorded gain, no AGC | §5.1 |
| REQ-A3 mic sensitivity per unit | §5.1 channel map with serial and calibration in every sidecar |
| REQ-A4 per-mic health, faults reduce effort | §8 mic health, §11 telemetry |
| REQ-A5 weather context | §8 wind/rain flags, §11 enclosure temperature |
| REQ-C2 exact survey effort incl. gaps | §5.1 explicit gap logging, §6.3 degradation steps logged, §10 ledger |
| REQ-C3 schedule presets, continuous default | §6.1 |
| REQ-I1 SHA-256 at file close | §10 |
| REQ-I2 signed, chained manifests, key in secure element | §10, §9.2 |
| REQ-I3 cloud verifies hash before local delete | §9.2, §5.3 |
| REQ-I5 audit log | §10 (station side: config, updates, gaps, access) |
| REQ-P1 speech detection | Runs in the cloud on uploaded audio. Station side: support-tunnel and raw-audio access are logged (§12). An optional on-device speech flag to hold back clips from upload is possible later. |
| REQ-P5 encryption in transit | §9.2 TLS with device certificate; data partition encryption at rest **[Open: key handling vs. field retrieval]** |
| REQ-O1 28 days continuous, -30 °C | §5.3 storage, §6.4 winter, §15 cold chamber and soak tests |
| REQ-O2 record when 4G down, catch up | §9.3 |
| REQ-O3 status at least hourly | §11 (every 15 min when connected) |
| REQ-O4 config changes logged, effective at recorded time | §12 (applied between segments, ledger entry with effective time) |
| REQ-O5 1-20+ stations | No per-station coupling on the device; fleet handled in cloud (§12, §13 staged rollout) |

## 18. Open questions for walto

1. **What is "multi-microphone" for?** (a) Wider coverage / redundancy, (b) direction-finding on one station, (c) locating birds across several stations, or several? (b) needs a fixed mic array with one shared clock; (c) needs sample-accurate GNSS time on every station. This drives the ADC choice and whether the PPS-in-audio method is required.
2. **How many mics per station** do you picture, and mounted on the enclosure or on cables?
3. **Power source:** solar + battery, or battery only swapped at each 2-4 week visit? Solar is near zero in northern Finland in December, which strongly affects the default recording profile.
4. **Must all raw audio be kept** for legal use (record everything lossless locally), or are event clips enough for some buyers?
5. **4G data budget:** roughly how much per station per month would buyers accept paying for (e.g. 10 GB vs 50 GB)?
6. **Are you OK starting on a Raspberry Pi CM4/CM5** for the prototype? Or do you have another board in mind?
7. **Setup without 4G coverage:** is BLE or a Wi-Fi hotspot for phone setup acceptable on the hardware side?
