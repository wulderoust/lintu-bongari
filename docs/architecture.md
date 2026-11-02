# Architecture decision record

Status: proposed for walto's approval (step 2 of the plan). Owner: walto. Last updated 2026-11-02.

This is the single decision record for the lintu-bongari kit. It takes the five step-1 documents (`requirements.md`, `product-business.md`, `cloud-app.md`, `edge-software.md`, `hardware.md`), fixes the architecture, resolves the places where they disagree, and lists what is still open with a recommendation for each. It also gives the parts list for prototype v0 (one station, pre-made modules only) and the build order for step 3.

Where this document and an older step-1 document disagree, **this document wins**. The step-1 documents will be updated to match as each part is built.

Prices are in euros including VAT unless marked otherwise. Prices marked *(checked)* were read from the supplier page on 2026-11-02; prices marked *(est.)* are estimates and must be checked in the shop cart before ordering.

---

## 1. Decisions at a glance

| # | Topic | Decision | Source |
|---|---|---|---|
| D1 | Kit | 4 identical, self-contained stations per base kit; projects from 1 to 20+ stations | requirements REQ-O5, business §6 |
| D2 | v1 counting level | Count **and locate** individual birds across stations (Level 3) | walto, 2026-11-02 |
| D3 | Station compute | **Architecture B**: STM32H7 recorder MCU always on; Linux module off, woken on demand (about 2 h/day) | hardware §5.1, edge §2 |
| D4 | Supervisor | **nRF52840** (BLE for phone setup) with RTC, always on at a few mW | hardware §5.2 (edge said STM32L4, see §4 C1) |
| D5 | Linux module | **Raspberry Pi Zero 2 W** in all prototypes and the pilot; CM4 is the fallback if RAM, USB bandwidth or cold boot fail | hardware §9.4, §12.1 (see §4 C2) |
| D6 | Microphones | 4 mics per station in a tetrahedral array (about 40 cm across, top mic about 25 cm higher); wiring supports up to 6 | hardware §3.2 |
| D7 | Mic chain in prototypes | **Digital PDM MEMS mics** (Infineon IM73D122, SNR 73 dB) read by the H7's SAI PDM interface on one clock | hardware §12.1 (see §4 C3) |
| D8 | Timing | GNSS PPS **recorded inside the audio stream** as an extra PDM channel, plus timer capture as backup; inter-station target under 0.1 ms, design target under 50 µs | REQ-T1, REQ-T2 (see §4 C4) |
| D9 | Station position | One **survey GNSS per kit** (ZED-F9P, post-processed against FinnRef) plus **acoustic self-survey** chirps; station M10 GNSS for time and theft detection only | hardware §4.4, edge §7.3 |
| D10 | Audio format | 48 kHz, **24 bit**, fixed gain, lossless FLAC, 10-minute UTC-aligned segments, one multichannel file per segment | REQ-A1, REQ-A2, edge §5 (see §4 C5, C6) |
| D11 | Archive of record | **Two SD cards** on the recorder, written alternately; never deleted until the cloud has confirmed the hash | REQ-I7, REQ-I8, edge §5.2 |
| D12 | Integrity | SHA-256 per file at close, hash-chained manifests signed by an ATECC608B secure element; chain head uploaded hourly | REQ-I1 to REQ-I3, edge §10 |
| D13 | Upload | **Hybrid**: manifests + status always; reference channel as Opus 96 kbit/s; lossless FLAC for detected event windows; lossless multichannel clips requested by the cloud for localisation; full archive from SD at the service visit | edge §9.2, cloud §3.1.1 (see §4 C7) |
| D14 | 4G | LTE Cat 4 Europe modem (SIM7600E-H in prototypes, Quectel EC25-E class in series), modem's own MQTT used by the supervisor while Linux is off | hardware §6, edge §4.2 |
| D15 | Phone setup | BLE on the supervisor (always available after a magnet tap); Wi-Fi hotspot from the Linux module on request | hardware §6.5, edge §14 |
| D16 | Power | Solar + battery. LTO 6S packs, about 9 kg each; **two packs in midwinter** (three if measured pre-made power stays above 1.1 W); one pack February to October; Victron SmartSolar 75/10 in prototypes | hardware §7, §12.2 |
| D17 | Analysis location | Species ID, DOA, localisation and counting run **in the cloud or on the customer's PC** with the same versioned core; never on the station | REQ-R6, cloud §1 |
| D18 | Data ownership | Customer owns all data; local-only mode uploads only status and the signed chain; SD cards are plain exFAT + FLAC + JSON | REQ-D0 to REQ-D3 |
| D19 | Build method | Pre-made modules on a 3D-printed plate for v0, v1 and the pilot kit; one service-designed custom carrier board **before series sales** | hardware §12, business §6 |
| D20 | Winter scope | Southern and central Finland; Lapland polar night is a later version | walto, 2026-11-02 |

## 2. Architecture

### 2.1 One station

```
               ┌──────────────────────── Station head (IP67 box) ─────────────────────────┐
 4 PDM mic     │                                                                          │
 pods ─────────┼─► SAI1 PDM ─┐                                                            │
 GNSS PPS ─────┼─► PDM slot ─┤  STM32H7 recorder (rec-fw)        ┌─► SD A ─┐ (archive    │
 (M10 GNSS)    │  + timer ───┤  PDM→PCM, FLAC, SHA-256, chain ───┤         │  of record) │
 NMEA ─────────┼─► UART ─────┘  health per minute, event index   └─► SD B ─┘             │
               │        │  ▲            │  ATECC608B (signing)        │ SD mux (SDWire)  │
               │        │  │  UART      │                              ▼                  │
 self-survey ◄─┼── I2S amp + horn tweeter (chirps, played on GNSS time)                   │
               │        ▼  │                                                              │
               │  nRF52840 supervisor (sup-fw) ── load switches ──► Pi Zero 2 W (Linux)   │
               │   RTC, INA228, IMU, SHT45, BMP390,                  ingest, Opus, clips, │
               │   heaters, watchdog, BLE setup                      upload, OTA, Wi-Fi   │
               │        │ UART (AT/MQTT, Linux off)                       │ USB           │
               │        └────────────────► 4G modem ◄─────────────────────┘               │
               └──────────────────────────────┬───────────────────────────────────────────┘
                                              │ M12 power cable
               Power pack(s) on the ground: LTO 6S + BMS ◄── Victron MPPT ◄── solar panel
```

What runs where:

| Processor | Always on | Software | Language / framework |
|---|---|---|---|
| STM32H7 recorder | yes | `rec-fw` | C, **STM32Cube HAL + FreeRTOS** (see §5 O9) |
| nRF52840 supervisor | yes | `sup-fw` | C, Zephyr (nRF Connect SDK) |
| Pi Zero 2 W | about 2 h/day | `lb-ingest`, `lb-detector`, `lb-uploader`, `lb-scheduler`, `lb-config`, `lb-ota`, `lb-setup`, `lb-telemetry` | Rust, Raspberry Pi OS Lite for prototypes, Yocto + RAUC for the product |

The rule from the edge doc stays: **recording never depends on Linux or 4G.** Linux may crash or be off for a week and no sample is lost.

### 2.2 Kit

- 4 stations in a triangle or grid **50 to 100 m apart**, each in hearing range of at least 2 others for the target species.
- Shared kit items: survey GNSS (ZED-F9P with survey antenna and mast clamp), acoustic calibrator (94 dB, 1 kHz, ½-inch), transport cases, spare pods.
- Stations do not talk to each other. All cross-station work (event matching, clip requests, self-survey schedule, localisation) is coordinated by the cloud or done on the customer's PC from SD cards.

## 3. Data flow end to end

1. **Capture.** The recorder clocks all PDM mics and the PPS pseudo-channel from one clock, decimates to 48 kHz / 24 bit, and keeps about 2 s in a DMA double buffer.
2. **Segment.** Every 10 minutes, on the UTC boundary, it closes a multichannel FLAC file and writes a JSON sidecar: station, firmware and config hashes, channel map with pod serials and calibration, gain, PPS table (sample index to UTC second), GNSS lock and position, gaps, temperatures, battery.
3. **Seal.** SHA-256 of FLAC and sidecar goes into a manifest entry that includes the previous entry's hash; the ATECC608B signs it. The chain is written to both cards and kept in recorder flash for a few days. Config changes, gaps, card switches, heater periods, self-tests and support sessions go into the same chain.
4. **Health.** Per channel and per minute: RMS, peak, clipping, DC, band noise floors, wind indicator. Faults become chain entries and reduce counted effort (REQ-A4, REQ-C2).
5. **Status (Linux off).** Every hour the supervisor sends status plus the current chain head through the modem's own MQTT (REQ-O3). This fixes history in the cloud even before any audio arrives.
6. **Wake.** The supervisor boots Linux on schedule (2 to 3 windows a day), on a cloud wake request, or on a backlog. It pre-heats first if the box is below -20 °C.
7. **Ingest on the station.** The recorder switches the idle card to Linux through the SD mux at a segment boundary. Linux mounts it read-only, re-hashes each new file against the chain, and catalogues it.
8. **Derive.** Linux makes the reference-channel Opus stream (96 kbit/s), runs the band-energy event detector, and cuts lossless event windows. Each derived file records its source hash.
9. **Upload** (HTTPS, resumable S3 multipart, objects named by SHA-256, mutual TLS with the secure-element key), in priority order:
   1. manifests, sidecars, health, event index;
   2. Opus reference stream and lossless event windows;
   3. lossless multichannel clips the cloud asked for;
   4. full archive only when power and coverage allow.
   A daily data and energy budget caps items 2 to 4.
10. **Cloud ingest.** Each object is accepted only if its hash matches the signed chain already in the cloud (REQ-I8). Originals go to write-once storage (REQ-I4); every action goes into the audit log (REQ-I5).
11. **Species ID.** The pluggable classifier (BirdNET for evaluation, Perch, later a Finnish model) runs on the reference stream; results labelled *preliminary* while based on Opus. Speech detection hides human speech (REQ-P1).
12. **Localisation.** The cloud matches events across neighbouring stations within the sound travel time, requests the same window from every station that heard it (all channels, lossless, with PPS table), computes DOA per array and TDOA across stations, and clusters positions into individuals with uncertainty.
13. **Service visit.** SD cards are swapped. The cloud or the desktop app ingests them, verifies every file against the chain, and reruns ID and localisation on the full lossless archive. **Reports use this run.**
14. **Local-only customers.** Steps 5 and 9.1 still run (status and chain only, so integrity can be proven), and steps 10 to 13 run in the desktop app with the same core version.
15. **Export.** FLAC + JSON + chain, CSV, Darwin Core, GeoPackage, PDF report with a verification package (REQ-B2 to REQ-B4, REQ-I6).

## 4. Conflicts between the step-1 documents and how they are resolved

| # | Conflict | Resolution | Why |
|---|---|---|---|
| C1 | Supervisor MCU: edge §2 says STM32L4; hardware §5.2 says nRF52840 | **nRF52840** | BLE phone setup is a v1 requirement and the nRF52840 does both jobs. Zephyr is still the RTOS, so edge's `sup-fw` design carries over. |
| C2 | Linux module: edge and hardware §5.2 say CM4; hardware §9.4 and §12.1 say Pi Zero 2 W | **Pi Zero 2 W** for v0, v1 and the pilot; **CM4** (wireless, eMMC) as the fallback | Pre-made build: no carrier board needed, has Wi-Fi/BLE, about €50 cheaper. Linux only does on-demand jobs, so 512 MB RAM is enough. Same Rust daemons on either. Switch if: Opus + detector for one day do not finish within one wake window, USB bandwidth is too low, or it fails the cold boot test. |
| C3 | Mic chain: hardware §3 and §4 and edge §5.1 use analog MEMS + 2× TLV320ADC6140 (ch 8 = PPS); hardware §12.1 uses PDM mics for the pre-made build | **PDM mics (IM73D122) in prototypes and the pilot.** The analog + ADC6140 chain returns only if the custom carrier (O1) is built and the pilot shows PDM range or cable noise is not good enough | There is no pre-made 8-channel TDM ADC board that fits. The IM73D122 is a digital mic with the same 73 dB SNR as the analog IM73A135 the hardware doc preferred, so the "4 dB noisier" penalty in hardware §12.2 mostly disappears *(verify the kit contents and cable behaviour on the bench)*. |
| C4 | PPS: edge §7 says PPS on ADC ch 8; hardware §12.1 says timer input only (no spare audio channel with PDM) | **Both.** The PPS logic signal goes into a free half-slot of a SAI PDM data line, where the decimation filter turns it into a step on its own channel, with exactly the same filter delay as the mics. A timer capture on the same clock is the backup | Keeps edge's design (time reference inside the audio, independent of software) without an ADC. The PPS-as-PDM trick must be proven on the bench in v0, week 1. If it fails, timer capture alone still gives sample-level timing. |
| C5 | Segment length: edge 10 min; cloud §3.2 5 min | **10 minutes**, UTC-aligned | Fewer files and manifest entries; clips for localisation are cut out anyway. Cloud chunking is independent of station segments. |
| C6 | Bit depth: edge and hardware §3.5 say 24 bit; cloud §3.1 and hardware §9.4 say 16 bit | **24 bit** in prototypes; decide 16 vs 24 for the series after measuring (O7) | REQ-A1 prefers 24 bit. With PDM mics the cost is card size, not hardware. A 28-day 4-channel deployment needs about 1 TB at 24 bit. |
| C7 | Default upload: business §6 assumes 1 lossless reference channel (about 240 GB/month); edge §9.2 and cloud §3.1.1 recommend Opus + lossless events | **Hybrid (D13)**, confirmed only after the REQ-I9 test on Finnish recordings | About 45 to 75 GB per station per month instead of 240, and about 3 Wh/day less in winter. Business doc's 4G cost line should be updated to the lower figure. |
| C8 | Inter-station timing: requirements REQ-T2 under 0.1 ms; cloud §5.2 "under 1 ms"; hardware §4.4 under 50 µs | **REQ-T2 (under 0.1 ms) is the requirement**; hardware's 50 µs is the design target | Cloud doc used an older figure. |
| C9 | Station positions: edge §7.3 leads with long GNSS averaging; hardware §4.4 with a shared survey GNSS | **Survey GNSS per kit is the primary method** (about 10 cm), acoustic self-survey checks positions and gives headings, M10 averaging is only a fallback flagged as "not good enough for Level 3" | REQ-L3 needs 0.5 m or better; the M10 averaging alone is not reliably there. |
| C10 | Idle-card handover: edge §5.2 needs an SD mux, open with hardware | **SDWire SD mux boards** (pre-made, USB 2 card reader + mux) between the recorder's SD slots and the Pi | Reading a day's audio through the recorder's USB full-speed port (about 1 MB/s) would take hours of Linux time. The SDWire is the pre-made form of edge's design *(verify that SDMMC works through the SDWire plug at the needed clock in v0)*. |
| C11 | Kit price: requirements memo and business §0 mention €6 to 8k; business §6 decision is €9 to 12k | **€9 to 12k** (walto's decision) | Parts with pre-made modules miss the €700 to 900 per station target; the custom carrier (O1) is how the series gets there. |
| C12 | v0 plan: edge §16 says v0 is architecture A (CM4 records via ALSA); hardware §12.3 says v0 is an STM32H7 board on the bench | **v0 is architecture B on dev boards** (§7) | With PDM mics Linux cannot easily read 4+ mics, and building `lb-recorder` would be throwaway work. The file format and Linux daemons are the same either way. |
| C13 | rec-fw framework: edge §3 says Zephyr | **STM32Cube HAL + FreeRTOS for `rec-fw`** (edge's own fallback); Zephyr stays for `sup-fw` | ST's SAI PDM, DFSDM and PDM-to-PCM library are mature in Cube; Zephyr's DMIC support on STM32H7 is not. MCUboot works with both. |

Follow-up: the step-1 docs keep their history, but each gets a one-line note pointing here for the items above when it is next edited.

## 5. Open decisions, each with a recommendation

| # | Question | Recommendation | Decide by |
|---|---|---|---|
| O1 | Custom carrier board before series sales? Who designs it (walto in KiCad, or a freelancer/service)? | **Yes, a freelancer or design service, assembled by JLCPCB**, after the pilot. walto does not need to learn KiCad. It is what brings parts to about €700 to 900 and the power to about 0.9 W | after the field pilot (step 4) |
| O2 | 4 or 6 mics | **4** in the base kit. The prototype wiring supports 6 so they can be compared in v1 | end of v1 |
| O3 | Lite 1 to 2 mic hobbyist variant | **Defer** to phase 2; it has no effect on v1 | after first sales |
| O4 | Hybrid upload as default | **Yes**, if the REQ-I9 test (FLAC vs Opus 96 vs Opus 64 on Finnish recordings) shows no meaningful loss; otherwise lossless reference | during v0/v1 |
| O5 | Battery chemistry | **LTO** for the pilot. Test a sodium-ion pack side by side outdoors in January; switch the series if it passes | January 2027 test |
| O6 | Number of winter packs | Plan for **two**; measure v1 power. Three only if measured average stays above 1.1 W | end of v1 |
| O7 | 16 or 24 bit archive in the series | **24 bit** until the pilot shows the 16-bit floor is never reached at the fixed gain; then decide on card cost | end of pilot |
| O8 | Classifier | Prototype with BirdNET (research use) and Perch side by side; walto sends the licensing emails already drafted. Product default: whichever has a commercial licence and better Finnish precision | before pricing is final |
| O9 | `rec-fw` framework | **Cube HAL + FreeRTOS** (C13) | now |
| O10 | Cloud hosting | **Hetzner Helsinki** for the prototype (cheapest, EU, S3 + Postgres portable); review UpCloud before the pilot if customers ask for a Finnish-owned provider | before pilot |
| O11 | Desktop OS | **Windows first** | before pilot |
| O12 | Company form | Form an **Oy** with product liability insurance before the first sale (business §5a) | before first sale |
| O13 | Self-survey chirp at sensitive sites | Daily chirp at a fixed quiet hour, about 100 ms, logged; check with the pilot partner whether it is acceptable near breeding sites | before pilot |

## 6. Prototype v0 parts list (one station, pre-made modules only)

Goal of v0: real 4-channel recordings with PPS timing, files in the final format, measured power per block, and the first Linux upload path. It is a **bench and balcony station**; the weatherproof parts and the battery come in v1 (§6.3).

Supplier notes: **Electrokit** (Sweden, EU, ships to Finland in 1 to 3 days) carries most maker boards; **DigiKey, Mouser, Farnell, RS** carry the ST, Infineon and SparkFun parts with free shipping over a threshold; **3mdeb** (Poland) sells the SDWire; **ArduSimple** (Spain) sells the survey GNSS; **Offgridtec** (Germany) sells Victron. Finnish shops (Partco, Verkkokauppa.com, Jimm's, Motonet) cover cards, tools and solar.

### 6.1 Core electronics (order now)

| # | Item | Part | Qty | Supplier | Price each | Line |
|---|---|---|---|---|---|---|
| 1 | Recorder MCU board | ST **NUCLEO-H723ZG** (550 MHz Cortex-M7, SAI PDM, 2× SDMMC, on-board ST-LINK debugger) | 1 | [ST eStore](https://estore.st.com/en/products/evaluation-tools/product-evaluation-tools/mcu-mpu-eval-tools/stm32-mcu-mpu-eval-tools/stm32-nucleo-boards/nucleo-h723zg.html), [DigiKey](https://www.digikey.fi/en/products/detail/stmicroelectronics/NUCLEO-H723ZG/13171214), [Farnell](https://es.farnell.com/stmicroelectronics/nucleo-h723zg/placa-des-stm32-32bit-arm-cortex/dp/3576973) | €30 to 40 *(est.)* | €35 |
| 2 | PDM MEMS microphone | Infineon **KIT_IM73D122V01_FLEX** (IM73D122, SNR 73 dB, on flex board) | 5 (4 + 1 spare) | [DigiKey](https://www.digikey.fi/en/products/detail/infineon-technologies/KITIM73D122V01FLEXTOBO1/16999573), [RS](https://se.rs-online.com/web/p/analogue-development-tools/2601014) | €15 to 25 *(est.; verify kit contents)* | €100 |
| 3 | Station GNSS (time + theft) | **SparkFun MAX-M10S** breakout, u.FL antenna connector, PPS pin | 1 | [DigiKey](https://www.digikey.de/en/products/detail/sparkfun-electronics/18037/16719314), [SparkFun](https://www.sparkfun.com/sparkfun-gnss-receiver-breakout-max-m10s-qwiic.html) | €45 to 55 *(est.)* | €50 |
| 4 | GNSS antenna | Active L1 magnetic antenna, SMA, 5 m, + u.FL to SMA pigtail | 1 + 1 | [Electrokit](https://www.electrokit.com/en/gnss-/-gps-antenn-l1-magnetfaste-sma) | €15 to 20 *(est.)* | €20 |
| 5 | SD card breakout (SDIO, 3 V, no level shifter) | **Adafruit 4682** | 2 | [Electrokit](https://www.electrokit.com/produkt/microsd-lasare-3v-spi-sdio) | 59 SEK ≈ €5 *(checked)* | €10 |
| 6 | Archive cards | microSDXC 512 GB, A2/V30, high endurance or PRO Plus class (rated -25 °C) | 2 | Verkkokauppa.com, Jimm's, Proshop | €40 to 60 *(est.)* | €100 |
| 7 | SD mux for idle-card handover | **SDWire** (USB 2 card reader + mux, controlled over USB) | 1 (second one in v1) | [3mdeb shop](https://shop.3mdeb.com/product/sdwire/) | €89 ex VAT ≈ €112 *(checked)* | €112 |
| 8 | Linux module | **Raspberry Pi Zero 2 W** | 1 | [Electrokit](https://www.electrokit.com/en/raspberry-pi-zero-2-w-no-pin-header), Partco | €18 to 22 *(est.)* | €20 |
| 9 | Linux boot card | microSD 32 GB high endurance | 1 | Verkkokauppa.com | €10 *(est.)* | €10 |
| 10 | USB hub for the Pi | **Zero4U** 4-port USB 2 hub (modem + SDWire) | 1 | [Electrokit](https://www.electrokit.com/en/zero4u-4-port-usb-hub-for-raspberry-pi-zero) | €12 to 15 *(est.)* | €14 |
| 11 | 4G modem | **Waveshare SIM7600E-H 4G HAT** (LTE Cat 4, Europe bands, USB + UART, built-in MQTT AT commands, LTE antenna included) | 1 | [Electrokit](https://electrokit.com/en/4g-/-gnss-hat-for-raspberry-pi-sim7600e-h), [exp-tech](https://exp-tech.de/en/products/sim7600e-h-4g-hat) | 999 SEK ≈ €87 *(checked)* | €87 |
| 12 | Data SIM | Prepaid data SIM (DNA, Elisa or Telia) | 1 | operator | €10 to 20/month | (opex) |
| 13 | Supervisor + BLE | **Seeed XIAO nRF52840** | 1 | [Electrokit](https://www.electrokit.com/en/xiao-nrf52840-seeed-studio) | €10 to 13 *(est.)* | €12 |
| 14 | Power monitor | **INA228** Qwiic breakout (85 V, 10 A) | 2 (one on battery input, one movable for per-block measurement) | [Electrokit](https://www.electrokit.com/en/stromsensor-ina228-85v-10a-i2c) | €15 *(est.)* | €30 |
| 15 | RTC | SparkFun **RV-3028** Qwiic | 1 | DigiKey, SparkFun | €20 *(est.)* | €20 |
| 16 | Secure element | SparkFun **ATECC608A/B** Qwiic cryptographic co-processor | 1 | DigiKey, SparkFun | €8 to 12 *(est.)* | €10 |
| 17 | IMU + magnetometer | Adafruit LSM6DSOX + LIS3MDL 9-DoF (STEMMA QT) | 1 | DigiKey, Electrokit | €20 *(est.)* | €20 |
| 18 | Temperature / RH | Adafruit **SHT45** (STEMMA QT) | 1 | DigiKey, Electrokit | €13 *(est.)* | €13 |
| 19 | Pressure | Adafruit **BMP390** (STEMMA QT) | 1 | [Electrokit](https://www.electrokit.com/en/product/adafruit-bmp390-barometer-and-altimeter/) | €12 *(est.)* | €12 |
| 20 | Self-survey / self-test amplifier | Adafruit **MAX98357A** I2S class-D 3 W (driven by the H7's second SAI, so chirps are sample-timed) | 1 | [Electrokit](https://www.electrokit.com/en/forstarkare-klass-d-3w-mono-i2s) | €7 *(est.)* | €7 |
| 21 | Emitter | Small piezo horn tweeter (Visaton or Monacor class, 2 to 20 kHz) | 1 | Partco, Thomann | €10 to 20 *(est.)* | €15 |
| 22 | 5 V rail (Pi, modem) | Pololu **D36V28F5** step-down 5 V 3.2 A | 1 | Botland, Kiwi Electronics, Electrokit | €18 *(est.)* | €18 |
| 23 | 3.3 V rail (recorder, sensors) | Pololu **D36V6F3** step-down 3.3 V 0.6 A | 1 | as above | €8 *(est.)* | €8 |
| 24 | Load switches | Pololu **Mini Pushbutton Power Switch LV** (has ON/OFF control pins) for Pi, modem, recorder | 3 | as above | €6 *(est.)* | €18 |
| 25 | Wiring | Qwiic/STEMMA QT cable set, 4-core shielded cable 10 m (mic leads), Dupont/JST kit, headers, heat-shrink | 1 set | Electrokit, Partco | | €40 |
| 26 | Mounting plate, mic holders | PETG or ASA filament 1 kg (walto's printer) | 1 | Prusa, 3DJake | €30 *(est.)* | €30 |
| | **v0 core total** | | | | | **about €810** |

Expect about €700 to 900 once real cart prices and shipping are in.

### 6.2 Bench tools (skip what walto already has)

| Item | Price *(est.)* | Why |
|---|---|---|
| Adjustable bench power supply 0 to 30 V, 3 A | €50 to 90 | stands in for the battery in v0 |
| Multimeter | €25 to 50 | |
| Soldering iron (temperature controlled) + solder | €40 to 80 | headers and cable joints only |
| USB logic analyser (8 channel, sigrok-compatible) | €15 to 25 | checking PDM clock, PPS and UART |
| Small speaker + phone tone app, tape measure | | timing and DOA tests on the bench |

### 6.3 Added for v1 (field station; order after v0 records cleanly)

| Item | Example | Qty | Price *(est. unless checked)* |
|---|---|---|---|
| IP67 polycarbonate box about 250 × 180 × 110 mm | Spelsberg TK PS or Fibox | 1 | €35 to 50 |
| Cable glands M12/M16 set, Gore-type vent, desiccant | | 1 set | €25 |
| ASA filament for outdoor pods, hub and brackets | | 1 kg | €30 |
| ePTFE acoustic membranes + open-cell foam windscreens | | 5 | €20 to 40 |
| Pod heaters (resistor) + MOSFET switch board | | 4 + 1 | €15 |
| Second SDWire | [3mdeb](https://shop.3mdeb.com/product/sdwire/) | 1 | €112 *(checked, incl. VAT)* |
| 2 × 1 TB microSDXC (replaces the 512 GB cards for 28-day runs) | | 2 | €160 to 220 |
| LTO 6S pack with BMS, about 14 V, 40 Ah (about 550 Wh, about 9 kg) | GS Audio / Yinlong 66160 based packs; the [GS Audio 6S 20 Ah pack](https://www.gsaudio.it/en/lto-titanium-14-4v-40ah-battery-12-cells-with-bms-and-bars-23x6-5x11cm.html) is €203 *(checked)*, a 40 Ah pack about twice that | 1 for the 2-week test, 2 for January | €350 to 450 each |
| Solar charger | Victron SmartSolar MPPT 75/10, rated -30 to +60 °C | 1 | [€63.72 at Offgridtec](https://www.offgridtec.com/en/victron-smartsolar-mppt-75-10-10a-12v-24v-solar-charge-controller.html) *(checked)* |
| Solar panel 50 to 100 Wp + near-vertical bracket + MC4 cable | Sunwind, Motonet | 1 | €80 to 140 |
| Insulated pack box (XPS-lined plastic crate) | | 1 | €30 to 50 |
| Mast / tripod 2 to 3 m, aluminium tube for array arms, strap, cable lock | Motonet, K-Rauta | 1 | €60 to 100 |
| Conformal coating spray | MG Chemicals 422 | 1 | €20 |
| **v1 additions total** | | | **about €1,150 with one pack, about €1,550 with two** |

### 6.4 Shared kit items (needed once two or more stations exist, v2)

| Item | Example | Price |
|---|---|---|
| Survey GNSS | ArduSimple **simpleRTK2B** (ZED-F9P) | [€177](https://www.ardusimple.com/product/simplertk2b-m-2/) *(checked, M.2 version; carrier board extra)* + €13 pigtail |
| Multiband survey antenna + mast clamp + power bank | ArduSimple or u-blox ANN-MB | €80 to 150 *(est.)* |
| Acoustic calibrator 94 dB / 1 kHz, ½-inch, with printed pod adapter | class 2 | €300 to 700 *(est.)* |

## 7. Step 3 build order

v0 is architecture B on dev boards from day one (C12), so nothing built is thrown away.

### 7.1 What walto builds

| Week | Build | Done when |
|---|---|---|
| 1 | Order §6.1 (and §6.2 if needed). Print a flat mounting plate and 4 simple mic holders. | parts arrive |
| 2 | Solder headers. Wire the 4 mics to the Nucleo with the shielded cable (0.5 m first) following Claude's pin map; wire GNSS PPS and UART, the two SD breakouts, the I2S amp and tweeter. | Claude's test firmware sees all 4 mics, PPS and both cards |
| 3 | Pi Zero 2 W + Zero4U + SIM7600 HAT + SDWire; XIAO with the Qwiic chain (INA228, RV-3028, ATECC608, IMU, SHT45, BMP390); Pololu rails and load switches from the bench supply at 13 V. | supervisor reports power per block over BLE |
| 4 | Balcony or garden test: 72 h continuous recording; tape-measure a speaker at known spots for a DOA check; a click test against a second phone recording for timing. | files verify, DOA within a few degrees |
| 5 to 6 | v1 parts (§6.3): IP67 box, outdoor pods with membranes and heaters, power pack, panel, mast. | station runs 2 weeks outdoors |
| 7+ | Second station (same list) for a cross-station timing test; then January cold test with 2 packs, LTO beside sodium-ion if available. | inter-station error under 0.1 ms |

### 7.2 What Claude codes first

1. **File and chain format spec + reference verifier** (`docs/formats.md`, `tools/lb-verify` in Python): FLAC segment, sidecar JSON schema, PPS table, manifest chain and signature. Everything else (firmware, Linux, cloud, desktop) builds on this, and walto can verify SD cards from the first day.
2. **`rec-fw` milestone 1** (Cube HAL + FreeRTOS on the Nucleo): 4 PDM mics + PPS pseudo-channel → 48 kHz/24-bit WAV on SD A, with PPS table. Bench test of the PPS-in-PDM trick in week 2.
3. **`rec-fw` milestone 2:** FLAC encoder, SHA-256, signed chain (software key first, ATECC608 next), alternate cards, per-minute health, gap logging, power-cut recovery.
4. **Analysis tools on bench recordings** (Python): PPS alignment, GCC-PHAT direction of arrival for the 4-mic array, timing check between two stations. This gives early proof that localisation works.
5. **`sup-fw` on the XIAO** (Zephyr): load switches, watchdog, INA228 power log, BLE status, hourly MQTT status through the SIM7600 with Linux off.
6. **Linux daemons** (Rust on the Pi Zero 2 W): `lb-ingest` via SDWire, Opus reference, event detector, `lb-uploader` to a test bucket.
7. **Cloud prototype** per cloud-app §13: ingest with manifest verification, BirdNET + Perch batch runs, simple review UI, REQ-I9 lossless-vs-Opus test.

## 8. What this changes in the step-1 documents

- `edge-software.md`: supervisor is nRF52840; Linux module is Pi Zero 2 W in prototypes; v0 is architecture B; `rec-fw` uses Cube HAL + FreeRTOS; PPS goes in as a PDM pseudo-channel; SD mux is the SDWire.
- `hardware.md`: PPS keeps an in-audio channel in the pre-made build; mic is IM73D122 rather than IM69D130.
- `cloud-app.md`: segments are 10 minutes, 24 bit; inter-station timing requirement is 0.1 ms.
- `product-business.md`: 4G cost line uses the hybrid volume (about 45 to 75 GB per station per month).
