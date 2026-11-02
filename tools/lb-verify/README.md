# lb-verify

Checks a lintu-bongari station SD card: the signed hash chain, every audio file and sidecar on the card, and the PPS timing table. It is the reference reader for [`docs/formats.md`](../../docs/formats.md).

## Install (once)

You need Python 3.9 or newer ([python.org](https://www.python.org/downloads/); on Windows tick "Add python.exe to PATH" in the installer). Then, in a terminal in this repository folder:

```
pip install ./tools/lb-verify[sig]
```

`[sig]` adds the `cryptography` package so signatures are checked. Without it the tool still checks hashes and files and says that signatures were not checked.

## Use

```
lb-verify E:\              one card (Windows drive letter, or /media/... on Linux, /Volumes/... on Mac)
lb-verify E:\ F:\          both cards of one station (A and B), checked together
lb-verify --quick E:\      sizes and headers only, no SHA-256 (fast check of a full card)
lb-verify --json E:\       machine-readable report
```

The last line says `RESULT: OK` or `RESULT: FAILED`, and the exit code is 0 or 1.

Try it before any hardware exists:

```
lb-verify demo my-demo-card
lb-verify my-demo-card
```

## Tests

```
pip install ./tools/lb-verify[test]
pytest tools/lb-verify/tests
```
