# Edge software design (on-station)

Status: **Draft for step 1 (design)**. No code yet. Decisions marked **[Proposed]** need walto's review; items marked **[Open]** are waiting on answers or on another doc. Requirement IDs (REQ-…) refer to `docs/requirements.md` (PR #1). Hardware references (§x.y of hardware) refer to `docs/hardware.md` (PR #5). See §18 for traceability.

**Decided by walto (2026-11-02):** version 1 must **count and locate individual birds across multiple stations**; stations use **solar plus battery**; **Bluetooth/Wi-Fi phone setup** is included; stations **record continuously**; **SD cards are not encrypted**; **the customer owns the data**. These shape §6.1, §7.3, §8.3, §9, §12 and §14.

This version follows the hardware doc's **architecture B**: a low-power recorder MCU records around the clock, and a Linux module wakes only when needed. Prototype v0 is architecture A (Linux records everything), and the software is split so that v0 work carries over (§16).

## 1. Scope and principles

This document covers the software and firmware on each recording station: capturing multi-channel audio, deciding when to record, flagging acoustic activity, keeping time, storing data with an audit trail, uploading over 4G, reporting health, and taking remote config and updates.

Out of scope: species identification (cloud or the user's computer), the cloud backend and app, and the electronics (hardware doc).

Principles, in priority order:

1. **Never lose or silently corrupt a recording.** Data is the product and may be evidence in regulatory work. Every file is hashed, signed into a chain, and traceable from microphone to cloud.
2. **Recording never depends on Linux or 4G.** The recorder MCU keeps recording if the Linux module, the modem or the network fails.
3. **Survive unattended for 28 days in any Finnish season** (REQ-O1). Assume power cuts, -30 °C, no 4G for days, and nobody on site.
4. **Degrade gracefully and visibly.** Low battery or no network reduces what we do in a fixed order, every step is logged, and effort records show it (REQ-C2).
5. **Easy for the buyer, recoverable remotely.** Field setup is "mount, power on, scan QR". Any software fault can be fixed without a site visit.

## 2. System overview

Three processors, each with one job (hardware §5):

| Processor | Always on? | Software | Job |
|---|---|---|---|
| **Recorder MCU** (STM32H733/H735) | Yes | `rec-fw`, C on Zephyr | TDM capture from 2 ADCs, FLAC encoding, SHA-256, signed manifest chain, write to SD archive, per-minute audio health summaries. |
| **Supervisor MCU** (STM32L4 + RTC) | Yes, a few mW | `sup-fw`, C on Zephyr | Power switches, watchdog for everything, battery/temperature/heaters, hourly status via the modem's built-in MQTT, wake schedule for Linux. |
| **Linux module** (Raspberry Pi CM4) | No, ~2 h/day | Rust daemons on Linux | Uploads, event detection over the backlog, remote config, OTA for all three processors, remote support sessions. |

```
 Mics (4-6) ─► 2x ADC6140 (TCXO) ─TDM─► Recorder MCU ─► SD A / SD B (archive of record)
 GNSS PPS ───► ADC ch 8                   │  SHA-256, signed chain (secure element)
 GNSS PPS/NMEA ──────────────────────────►│
                                          │ UART/SPI: status, manifests, config
 Supervisor MCU ◄──────────────────────────┘
   │ power switches, watchdog, wake timer, modem ring line
   ├─► 4G modem ── hourly status (modem's own MQTT, Linux off) ──► Cloud
   └─► Linux module (on demand) ── reads closed files from idle SD ── uploads ──► Cloud
```

Key consequence: the always-on part is small, deterministic firmware. Everything complex (TLS uploads, detection, updates, VPN) lives in Linux, which is allowed to crash, be rebooted, or be off for days without losing a sample.

## 3. OS and stack [Proposed]

| Layer | Prototype v0 (architecture A) | Product (architecture B) |
|---|---|---|
| Recording | `lb-recorder` on the CM4 (Rust, ALSA) | `rec-fw` on STM32H7 (C, Zephyr) |
| Supervisor | lab supply, no supervisor | `sup-fw` on STM32L4 (C, Zephyr) |
| Linux OS | Raspberry Pi OS Lite 64-bit | Yocto minimal image, read-only rootfs |
| Linux daemons | Rust | Rust (same code) |
| Linux updates | RAUC A/B | RAUC A/B, signed bundles |
| MCU updates | n/a | MCUboot dual-slot, signed images, installed by Linux |
| Local catalog & queue (Linux) | SQLite, WAL mode | same |
| Time on Linux | chrony + gpsd with PPS | same, but recorder time is authoritative (§7) |
| Cellular | ModemManager + NetworkManager | same, plus modem's built-in MQTT used by the supervisor |
| Control channel | MQTT over TLS, mutual auth | same |
| Remote support shell | WireGuard, on demand | same |
| Tooling and tests | Python | Python (dev only) |

Why:

- **Zephyr on both MCUs:** one RTOS, one build system, STM32 drivers for SAI, SDMMC, HASH and UART, and MCUboot built in for safe firmware updates. Fallback if the SAI/TDM driver is not good enough on the bench: ST HAL + FreeRTOS for `rec-fw` only.
- **C for MCU firmware** because that is what Zephyr, ST's drivers and walto's existing skills share. Rust (Embassy) is a possible later move for `rec-fw`, not for v1.
- **Rust for Linux daemons:** memory safety, low CPU (= less energy in the short wake windows), single static binaries in OTA bundles. Written once in v0 and kept in the product.
- **Yocto + RAUC** for the product: small, reproducible, read-only image with A/B fallback. v0 uses Raspberry Pi OS to get started fast; the daemons do not change.

## 4. Software components

### 4.1 Recorder MCU (`rec-fw`)

- **Capture:** SAI in TDM mode reads 8 slots from the two ADC6140s into a DMA double buffer (~2 s of audio in RAM). Overruns are counted and logged as explicit gaps with exact sample counts.
- **Encode:** a small fixed-predictor FLAC encoder (fixed orders 0-4, Rice coding, 4096-sample blocks). This gets close to libFLAC's default compression at a fraction of the CPU, and the output is standard FLAC. Real-time 6-8 channels at 48 kHz/24-bit on an H7 must be proven on the bench (hardware risk list). Fallback: write 24-bit WAV and let Linux transcode, at the cost of ~1.5x storage.
- **Files:** one multi-channel FLAC per segment (default 10 min, UTC-aligned), plus a sidecar (§5.2).
- **Hash and sign:** SHA-256 on the HASH peripheral while writing; at file close, a manifest entry is appended to the chain and signed by the secure element (§10).
- **Health:** per-channel, per-minute RMS, noise floor in a few bands, peak, clipping count, DC offset (§8.1). Cheap, computed on the capture buffers.
- **Commands:** over UART/SPI from the supervisor and Linux: get status, get manifests, set config at next segment boundary, start self-test chirp, switch archive card, enter firmware update.

### 4.2 Supervisor MCU (`sup-fw`)

- Watchdog for recorder, Linux module and modem; power-cycles any that stops answering, and logs why.
- Battery, solar, temperatures, humidity, heater control (hardware §3.3, §7).
- **Hourly status** (REQ-O3) through the modem's built-in TCP/MQTT stack with Linux off.
- **Wake logic:** boots Linux on the schedule table, on a cloud wake request (modem ring line, SMS or MQTT message), or when the upload backlog or a fault needs it. Pre-heats before booting Linux in the cold.
- **Power degradation** steps (§6.3).

### 4.3 Linux module services

Each is a systemd service with `WatchdogSec=` and restart limits.

| Service | Job |
|---|---|
| `lb-recorder` | **v0 only:** records via ALSA exactly as `rec-fw` will (same file format, sidecar and chain). In the product it becomes a test tool that checks `rec-fw` output. |
| `lb-ingest` | Reads closed files and manifest entries from the idle SD card, verifies each hash against the chain, and catalogs them in SQLite. |
| `lb-detector` | Event detection over newly ingested audio (§8.2). No species ID. |
| `lb-uploader` | Prioritised, resumable, budgeted uploads (§9). |
| `lb-scheduler` | Computes the next 7 days of recording, wake and upload windows (sun times from GNSS position) and loads them into the supervisor and recorder (§6). |
| `lb-telemetry` | Detailed health and diagnostics while Linux is up (§11). |
| `lb-config` | Receives, validates and applies remote config to all three processors (§12). |
| `lb-ota` | RAUC for Linux, MCUboot images for the MCUs (§13). |
| `lb-setup` | First-boot and field-setup flow (§14). |

Linux services share state through SQLite plus a small Unix-socket API. No broker on the device.

## 5. Recording

### 5.1 Capture

- **Channels:** per hardware §4.1: ch 1-6 microphones (4 fitted by default, tetrahedral array), ch 7 spare, **ch 8 GNSS PPS**. Channel map (position in the array, pod serial, calibration and frequency correction) is station config and is written into every sidecar.
- **Format:** 48 kHz, 24-bit, lossless FLAC (REQ-A1). All channels sample-locked on one TCXO (REQ-T2).
- **Gain:** fixed per deployment, no AGC (REQ-A2). Gain and calibration logged per file. Gain changes only at a segment boundary and are ledgered with the effective time (REQ-O4).
- **Recording profile:** continuous by default (REQ-C3, REQ-O1). Other profiles in §6.1.

### 5.2 Segment files and storage

- Fixed-length segments, default **10 minutes**, aligned to UTC (00:00, 00:10, …). A power cut loses at most the unflushed buffer of one file; the file is repaired to its last valid FLAC frame on restart and the gap logged.
- File name: `{station_id}_{YYYYMMDDTHHMMSSZ}_{seq}.flac`, plus a small sidecar (`.json`) with station ID, firmware versions, config hash, channel map, gain, sample rate, first-sample UTC from the PPS marker, GNSS lock state and position, time-quality estimate, gap list, enclosure temperature, battery voltage.
- **Two SD cards** (hardware §5.3). [Proposed] The recorder writes to one card (active) for a block of time (e.g. 6 h), then switches. The **idle card is handed to Linux through an SD mux**, read-only, so Linux can ingest and upload closed files without ever touching the card being written. If a card fails, the recorder continues on the other and raises an alarm. **[Open: confirm the SD mux with hardware; the alternative is reading files through the recorder over USB, which is too slow (USB FS ~1 MB/s) for the reference stream.]**
- **Filesystem:** exFAT, so cards can be read on any PC at a service visit. exFAT is not power-loss safe on its own, so the recorder pre-allocates each file, writes FAT/directory entries only at open and close, and relies on the hash chain (not the filesystem) to prove integrity. A damaged directory can be rebuilt from the chain plus the FLAC frame headers.
- **Never deleted on the station** unless the cloud has confirmed the hash (REQ-I3) and retention config allows it; normally cards are swapped at service visits.

### 5.3 Data volume

From hardware §5.3: about 35 GB/day for 4 channels (about 1 TB per 28 days), about 52 GB/day for 6 channels, about 8 GB/day for one reference channel. This is why the archive of record is the SD cards and the upload is a chosen subset (§9).

## 6. Scheduling and power

### 6.1 Recording profiles

**Continuous recording is the product default (decided by walto).** The other profiles stay available as options for special cases such as a long low-power deployment, and per REQ-C3:

- **Continuous** 24/7 (default).
- **Sun-based** windows from the station's GNSS position: e.g. "breeding season dawn" from 1 h before sunrise for 4 h, dusk windows. Polar day and polar night fall back to fixed clock windows when the sun event does not occur.
- **Night singers / nocturnal migration:** dusk to dawn.
- **Duty cycle**, e.g. 1 min on / 4 min off.
- **Custom** windows, combinable.

`lb-scheduler` computes 7 days ahead and loads the table into the recorder and supervisor, so the MCUs never need sun maths. If the table runs out (Linux has not booted for a week), the recorder falls back to continuous recording, never to stopping. The plan is shown in the app.

### 6.2 Linux wake windows

Linux is the expensive part (about 1.5 W while up; hardware §7.2 budgets about 2 h/day). It boots for:

- Scheduled upload windows (default: two or three per day, placed when signal and battery are usually best, and outside the most important recording windows to keep modem noise away; modem RF does not affect the archive but some users will want the quietest possible station).
- A cloud wake request (on-demand clip, support session, urgent config).
- Backlog or fault conditions raised by the recorder or supervisor.

Linux shuts itself down when the window's work is done, or the supervisor cuts it at the window end after a clean shutdown request.

### 6.3 Power-aware degradation

The supervisor steps down in a fixed order when energy runs short; each step is logged in the chain and reported:

1. Shorter or fewer Linux wake windows.
2. No audio upload; manifests and status only.
3. Reduce recorded channels (keep the array's reference mic and PPS) or switch to the priority profile, as the project config says.
4. Recording stops; status heartbeat only.
5. Recorder closes files, final manifest goes up, everything off except the supervisor, which checks daily for recovered charge.

Thresholds are config. With the 6S2P LTO winter pack the hardware budget is about 34 days continuous with no sun, so this is a safety net, not normal operation.

### 6.4 Winter specifics

- Linux is booted only after the supervisor has warmed the CM4 into its rated range (hardware: -20 °C for CM4).
- Mic pod heaters follow hardware §3.3; heater-on periods are logged because heater noise or changed response may affect detection.
- Ice or snow on a pod shows up as high-frequency loss and in the self-test chirp result; it is flagged as reduced effort (REQ-A4, REQ-C2).

## 7. Time synchronisation

Hardware §4.2 gives the method; the software side:

1. **PPS in the audio (ch 8)** is the timing reference. The recorder detects the PPS edge in ch 8 for each second and pairs it with the UTC second from NMEA. The sidecar stores a (sample index → UTC second) table, so any sample has a GNSS-traceable time, independent of software latency. This meets REQ-T1 and the cross-station part of REQ-T2 with a large margin (one sample is about 21 µs).
2. **Backup:** the recorder also timestamps PPS on a timer input, so timing survives if ch 8 is ever lost.
3. **No GNSS lock:** the recorder keeps time on the TCXO, logs the lock loss, and the sidecar records the estimated drift since last lock (REQ-T1). Linux, when up, uses chrony with NTP as a coarse check only.
4. All stored times are UTC ISO 8601 (REQ-T3).
5. The cloud does the precise cross-station alignment from the tables; nothing on the station resamples audio.

### 7.3 Station positions for cross-station localisation

Locating birds between stations needs each station's array position known far better than a normal GNSS fix (a few metres). Sound travels ~34 cm per ms, so a 2 m position error is as bad as a 6 ms timing error. [Proposed] three layers, best available is used and recorded:

1. **Long GNSS averaging:** the recorder logs GNSS position continuously; the cloud averages over the deployment (typically ~1 m or better *(est., verify with the M10 in v0)*). If the module supports raw measurements, they are logged for post-processing against the National Land Survey's FinnRef reference stations (could reach decimetres *(verify)*).
2. **Measured at setup:** the app accepts a surveyed position (RTK rover, or a tape measurement from a known point) and the array heading from the hardware's orientation sensor (hardware §4.3).
3. **Acoustic self-survey:** each station's self-test chirp (hardware §3.4) is also scheduled so neighbouring stations hear it. With sample-exact PPS timing on both sides, the arrival times give inter-station distances directly, which the cloud uses to refine positions. Chirp times are coordinated by the cloud and ledgered.

Position, its source and estimated accuracy go into every sidecar, so analysis knows which data is good enough for Level 3 counting.

## 8. Health and event detection (no species ID)

### 8.1 On the recorder, always (REQ-A4)

Per channel, per minute: RMS, peak, clipping count, DC offset, noise floor in 3-4 bands (e.g. <1 kHz, 1-4, 4-8, 8-16 kHz), and a simple wind indicator (low-frequency energy with low inter-channel coherence). Fault rules (dead channel, clipping, abnormal noise floor, high-frequency loss suggesting ice or water) raise flags that go into the chain and the hourly status. A few hundred bytes per minute.

The **daily self-test chirp** (hardware §3.4) is triggered by the recorder at a quiet hour; its result per channel (sensitivity, delay) is logged and the chirp interval marked so analysis ignores it.

### 8.2 On Linux, over the backlog

When Linux is up, `lb-detector` processes ingested files it has not seen yet:

- **Band-energy event detector** (1-12 kHz) against an adaptive noise floor, merged across channels, events padded by 1-2 s.
- **Noise and weather flags:** rain, wind, anthropogenic noise (traffic, aircraft, chainsaws) from spectral flatness, low-frequency energy and coherence.
- **Per-minute acoustic indices** (e.g. ACI, NDSI) for the app's activity heatmap.

The output is an event index used to prioritise uploads (§9.1), to pick events for localisation (§8.3), and to answer "anything interesting here?" before the full data arrives. It flags, it never deletes. CPU cost: a few minutes of CM4 time per day of audio *(est., confirm in v0)*. Thresholds are config.

Speech detection (REQ-P1) runs in the cloud on whatever is uploaded; see §18.

### 8.3 Coordinated multichannel clips for localisation

Locating a bird needs the **same time window, all channels, from every station that heard it**. [Proposed] flow:

1. Each station uploads its event index at each wake (small).
2. The cloud finds events that overlap in time across neighbouring stations (allowing for sound travel time between them) and, optionally, the cloud species ID on the reference channel.
3. The cloud requests those windows (all channels, lossless FLAC, PPS table) from each station; stations add them to the on-demand queue (§9.1 item 4).
4. A per-project **localisation budget** (clips or MB per day) keeps this within the data and energy budget. Events of target species or high-priority windows go first.

Full multichannel audio for everything remains on the SD cards, so a project can run complete localisation after the service visit.

## 9. Upload over 4G

### 9.1 Upload policy (agreed with hardware §6.4)

Per project config, in priority order:

1. **Always, via the supervisor (Linux off):** hourly status, alarms, the current chain head.
2. **Always, at each Linux wake:** all new signed manifest entries and sidecars, health summaries and the event index (kilobytes to a few MB per day). The cloud then knows exactly which files exist and can verify any file that arrives later (REQ-I2, REQ-I3).
3. **Default audio (recommended, see §9.2):** one **reference channel as Opus at 96 kbit/s** for the whole recording (about 1 GB/day) for live cloud species ID and listening, **plus that channel in lossless FLAC for every detected event window** (about 0.5-1.5 GB/day *(est.)*, depends on activity). A project can switch to full lossless reference (about 8 GB/day) when power and data allow, e.g. summer with solar and an unlimited SIM.
4. **On demand / localisation:** multichannel clips the cloud requests for cross-station localisation (§8.3), and time ranges requested from the app.
5. **When power and coverage allow:** the full multichannel archive, oldest first.
6. **At service visit:** the SD cards are ingested in the cloud and every file is verified against the signed chain.

A **daily data and energy budget** caps 3-5 (set from the SIM plan and battery state). Items wait when the budget is used up.

### 9.2 Lossless vs compressed upload: comparison and recommendation

walto asked whether lossless upload is worth it. Short answer: **not for the continuous live stream; yes for event clips and localisation.**

| | Lossless FLAC reference | Opus 96 kbit/s reference | Recommended hybrid |
|---|---|---|---|
| Data per station per month | ~240 GB | ~30 GB | ~45-75 GB *(est.)* |
| Upload energy per day *(at ~0.5 Wh/GB, good signal)* | ~4 Wh (~110 Wh per 28 days, ~15 % of the winter pack's usable energy) | ~0.5 Wh | ~1-1.5 Wh |
| Upload time per day at a weak site (~2 Mbit/s) | ~9 h of modem time | ~1.2 h | ~2-3 h |
| Species ID accuracy | Reference | Close to lossless at ≥96 kbit/s for common classifiers; faint, distant and high-pitched calls are the first to suffer at lower bitrates *(verify with our own test set in v0)* | Lossless on every window where a bird was detected |
| Cross-station localisation | Usable | **Not usable**: lossy codecs alter fine timing and phase between channels | Localisation always uses lossless multichannel clips (§8.3) |
| Legal / archive (REQ-A1) | Archive is the SD card either way | Same | Same |
| Cloud and local results identical (REQ-R) | Yes | Only if both run on the same Opus copy | Final report results are computed on lossless audio (event clips now, full archive after SD ingest); live results on Opus are labelled preliminary |

Why the hybrid:

- Most of a 24 h stream is silence, wind and rain. Paying 8 GB/day to move it losslessly buys almost nothing for ID, because what matters (the calls) is already sent lossless as event clips.
- Localisation, which walto chose for v1, cannot use lossy audio at all, so it needs its own lossless multichannel clips regardless of the reference stream format.
- The full lossless archive is always on the SD cards and ingested after the service visit, so nothing is lost for re-analysis or legal use.
- 240 GB/month per station times 4-20 stations is a real SIM cost and doubles winter upload energy; the hybrid keeps a 4-station kit around 200-300 GB/month in total.

Risk to check in v0: the event detector must not miss quiet calls; if it does, faint birds would only exist in the Opus stream until SD ingest. Test: run the classifier on the same recordings as FLAC, Opus 96 kbit/s and Opus 64 kbit/s, and measure detector recall for faint calls.

### 9.3 Customer-owned data

The customer owns the data (decided by walto). On the station side this means:

- Uploads go only to the **customer's own project**; we do not use customer audio for anything else without a separate written agreement.
- A per-project **local-only mode**: the station uploads only status, health and the signed manifest chain (needed so integrity can be proven later), and no audio. The customer collects the SD cards and analyses on their own computer.
- SD cards are plain exFAT FLAC + sidecars + chain files, readable without our software, so customers are never locked in (REQ-D2).

### 9.4 Transport

- **HTTPS with resumable chunked upload** (S3-compatible multipart via pre-signed URLs, or tus; decided with the Cloud doc). Interrupted chunks resume.
- **Content-addressed:** objects are named by SHA-256, so retries never duplicate and the cloud verifies on arrival. Only cloud-verified objects are marked received (REQ-I3).
- **TLS with a per-device client certificate** whose key is in the secure element.
- No inbound connections (carrier NAT); everything is outbound: MQTT, HTTPS, WireGuard.

### 9.5 Outages

The upload queue lives in SQLite on the Linux eMMC; the source data is on the SD cards, so nothing needs to be buffered twice. If 4G is down for days, the recorder just keeps writing; the next window resumes in priority order (status and manifests first). The supervisor's hourly status is queued in its own RAM/flash and sent when the modem reconnects.

## 10. Storage integrity and audit trail

Goal: anyone receiving the data can verify that **a file was recorded by station X at time T and has not been changed since** (REQ-I1 to REQ-I6).

- **At file close, on the recorder:** SHA-256 of the FLAC and the sidecar (REQ-I1); FLAC also carries its own MD5 of the decoded audio.
- **Chain:** each manifest entry holds the file hashes, segment time, sequence number, firmware/config hashes and **the hash of the previous entry**, and is **signed by the secure element** (REQ-I2). The key never leaves the secure element; its public key is registered with the cloud at manufacture.
- **Copies of the chain:** written to both SD cards (so either card alone is verifiable), held in recorder flash for the last few days, and uploaded at each Linux wake. The **chain head goes up hourly** with the supervisor's status, so even physical access to the station cannot rewrite history unnoticed.
- **Non-audio entries** in the same chain: config changes with effective time (REQ-O4), firmware updates, gaps, GNSS lock changes, card switches, degradation steps, heater periods, self-test results, support sessions. This is the station side of the audit log (REQ-I5).
- **Background verification:** `lb-ingest` re-hashes every file it reads from the idle card and reports any mismatch (card bit rot) immediately.

## 11. Health telemetry

- **Hourly, from the supervisor with Linux off (REQ-O3):** recording state, battery (V, I, SoC, remaining days), temperatures and humidity, heater state, GNSS lock, mic health flags, free space on each card, last successful upload, chain head, signal strength. Under 1 kB.
- **Alarms immediately:** mic failure, card failure or near full, battery critical, recorder restart, time lock lost for > N h, update rolled back, enclosure open (if fitted).
- **Detailed, while Linux is up:** per-minute health history, upload queue and budget, CPU temperature, service restarts, detector summary, full logs on request.

## 12. Remote config and remote access

- **Desired/reported state:** the cloud publishes a versioned, schema-validated, signed config document; the station reports what each processor is running. Mismatch is visible in the app.
- Small, urgent changes (e.g. "wake Linux now", gain preset) can arrive through the supervisor while Linux is off; it queues them, logs them, and passes recorder settings on at the next segment boundary (hardware §6.3). Everything else is applied by `lb-config` at the next wake.
- **Atomic with rollback:** recorder settings apply at a segment boundary; if health checks fail within 10 min, the previous config is restored and the reason reported. Every change is ledgered with its effective time (REQ-O4).
- Everything the buyer can set in the app (profiles, windows, gain preset, budgets, detector thresholds, wake windows) is config, not code.
- **Support access:** WireGuard tunnel opened only on a cloud request, time-limited, logged in the chain. Key-only SSH.

## 13. Safe updates (OTA)

- **Linux:** RAUC A/B. The bundle is downloaded over several wake windows if needed, written to the inactive slot, and booted with a boot counter. `lb-ota` marks it good only after all services are healthy and it has talked to the recorder and the cloud; otherwise the bootloader falls back.
- **Recorder and supervisor firmware:** signed MCUboot images, delivered by Linux. The new image is written to the secondary slot while the old one keeps running; the swap happens at a segment boundary, and MCUboot reverts if the new image does not confirm itself. The recorder swap costs a recording gap of a few seconds, which is ledgered as reduced effort; updates are scheduled outside the project's priority windows.
- **Never touches data:** SD cards and the chain are outside all update paths.
- **Staged rollout:** canary stations first, then the fleet. Battery and temperature gates before any install.

## 14. Field setup (buyer experience)

1. Buyer mounts the array and power pack, connects, presses power.
2. Station self-tests (each mic with the chirp, both cards, GNSS, modem) and shows the result on a status LED.
3. Buyer scans the station's QR code in the app; the station is claimed to their project using its device certificate.
4. App shows live levels per mic (short clips uploaded), the GNSS position, and the recording plan. Buyer confirms; calibration with the acoustic calibrator is guided by the app for consultant kits (REQ-A3).
5. Without 4G at the spot, setup works through the phone (approved by walto). [Proposed] **BLE on the supervisor** (always available, low power) for claiming, self-test results, live levels and config; **Wi-Fi on the Linux module** (CM4 variant with wireless, hotspot only on request) for downloading clips or larger data on site. Both are off unless a button press or the app wakes them, and every local session is ledgered. **[Hardware to confirm parts: hardware doc currently lists a CM4 without wireless.]**
6. For multi-station projects, the app walks through station placement and records surveyed positions and array heading (§7.3).

## 15. Testing strategy

- **Unit and property tests:** chain building and verification, FLAC encoder output vs libFLAC decode (bit-exact), scheduler for all of Finland across a full year (polar day and night), upload queue.
- **Recorder on the bench:** 72 h continuous at max channels with zero overruns; compare `rec-fw` files with `lb-recorder` files of the same input.
- **Fault injection:** 1000 random power cuts during writes with zero unverifiable files; card removal and failure; 4G down for days; Linux killed mid-upload; GNSS loss.
- **Soak:** 30 days on the bench before each release.
- **Cold chamber:** record at -30 °C; boot Linux after pre-heat; update all three processors in the cold.
- **Timing:** two stations record the same click from a known position; compare measured arrival difference with geometry.
- **Reference audio regression** for the detector.

## 16. Prototype plan (input to step 3)

**v0 (architecture A, bench, per hardware §12):** CM4 on IO board, ADC6140 EVM, MEMS mics, GNSS with PPS on ch 8, EG25-G.

1. `lb-recorder` writes FLAC segments, sidecars and the signed chain in the **final product format** (software key until the secure element is fitted).
2. `lb-ingest`, `lb-uploader` to a test bucket; outage and power-cut tests.
3. `lb-detector`, `lb-scheduler`, `lb-config`, RAUC.
4. Real recordings go to the Cloud thread to start the analysis pipeline.

**v1 (architecture B, field):**

5. `rec-fw` on an H7 dev board first (Nucleo-H735 + ADC EVM), proving real-time FLAC and SHA-256; then on the custom carrier.
6. `sup-fw`, SD mux handover, MCUboot updates.
7. 2-week outdoor test, then 4-week January test.

Because the file format, chain and Linux daemons are the same in v0 and v1, everything except `lb-recorder` carries over unchanged.

## 17. Risks (software side)

| Risk | Mitigation |
|---|---|
| H7 can't FLAC-encode 6-8 ch in real time | Fixed-predictor encoder; fallback to WAV + Linux transcode; drop to 4 ch |
| exFAT corruption on power loss | Pre-allocation, minimal metadata writes, chain-based recovery, supervisor clean shutdown |
| SD mux handover bugs | Card switch only at segment boundary, handshaked through the supervisor; Linux mounts read-only |
| Three firmware images to keep compatible | One release bundle with all three, versioned protocol between processors, compatibility check before swap |
| Upload energy exceeds budget at weak signal | Energy budget per window, measured Wh/GB per site, automatic step down (§6.3) |

## 18. Requirements traceability

| Requirement | Where handled |
|---|---|
| REQ-T1 GNSS-disciplined time, lock state logged | §7 |
| REQ-T2 shared clock, <1 ms between stations | §5.1 (one TCXO), §7 (PPS in ch 8) |
| REQ-T3 UTC, sun times from position | §5.2, §6.1 |
| REQ-A1 lossless FLAC ≥48 kHz | §5.1; Opus only as optional listening/ID copy (§9.1) |
| REQ-A2 fixed recorded gain | §5.1 |
| REQ-A3 mic sensitivity per unit | §5.1 channel map, §14 guided calibration |
| REQ-A4 per-mic health, faults reduce effort | §8.1, §11 |
| REQ-A5 weather context | §8.1 wind, §8.2 rain/wind flags, §11 temperatures |
| REQ-C2 exact effort incl. gaps | §5.1-5.2 gap logging, §6.3, §10 chain entries |
| REQ-C3 presets, continuous default | §6.1 |
| REQ-I1 SHA-256 at file close | §4.1, §10 |
| REQ-I2 signed chained manifests, key in secure element | §10 |
| REQ-I3 cloud verifies before local delete | §5.2, §9.4; upload scope per §9.1 (agreed with hardware §6.4; requirements wording to be aligned) |
| REQ-I5 audit log (station side) | §10 non-audio entries |
| REQ-P1 speech detection | Cloud, on uploaded audio. SD cards collected at service visits are ingested through the same pipeline. An on-device speech flag to hold back clips is possible later on Linux. |
| REQ-P5 encryption in transit / at rest | §9.4 TLS. SD cards are **not encrypted** (walto's decision), so cards stay readable on any PC; lost-card risk is handled by physical security and site signage (REQ-P3). Requirements doc to note this. |
| REQ-O1 28 days continuous, -30 °C, no silent loss | §2 architecture B, §5.2 two cards, §6.3, §15 |
| REQ-O2 record when 4G down, catch up | §9.5 |
| REQ-D2 export, customer owns data | §9.3 |
| REQ-O3 hourly status | §11 via supervisor |
| REQ-O4 config changes logged with effective time | §12 |
| REQ-O5 1-20+ stations | Nothing station-to-station on the device; fleet handled in cloud (§12, §13) |
| Level 3 counting, cross-station localisation (walto, 2026-11-02) | §7 timing, §7.3 positions, §8.3 coordinated clips |

## 19. Open questions for walto

All questions from this doc are answered (2026-11-02): locate across stations, solar + battery, phone setup via BLE/Wi-Fi, CM4, continuous recording, no SD encryption, customer owns the data. The upload format is the hybrid recommended in §9.2 unless walto prefers otherwise.

Still to settle with other threads:

- **Hardware:** SD mux for idle-card handover (§5.2); CM4 variant with Wi-Fi and a BLE part on the supervisor (§14); whether the GNSS module gives raw measurements (§7.3).
- **Cloud:** upload protocol (S3 multipart vs tus), coordinated clip requests for localisation (§8.3), local-only project mode (§9.3).
