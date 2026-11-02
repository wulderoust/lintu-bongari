# lintu-bongari

Multi-microphone bird call recording kit for remote, year-round use in Finland. Stations record and upload over 4G; species identification runs in the cloud or on the user's computer.

## Repository layout

| Folder | What | Status |
|---|---|---|
| `docs/` | Design documents. Start with `architecture.md` (the decision record) and `formats.md` (the file and chain format every part shares) | |
| `tools/lb-verify/` | Python tool that checks a station SD card against `formats.md` | v0 |
| `firmware/rec-fw/` | Recorder firmware for the STM32H7 (NUCLEO-H723ZG in v0): mics, PPS timing, files on SD | planned (step 3) |
| `firmware/sup-fw/` | Supervisor firmware for the nRF52840 (XIAO in v0): power, watchdog, BLE, status over 4G | planned |
| `linux/` | Rust daemons for the Pi Zero 2 W: ingest, Opus, event detector, upload | planned |
| `analysis/` | Python bench analysis: PPS alignment, direction of arrival, timing checks | planned |

The build order is in `docs/architecture.md` section 7.
