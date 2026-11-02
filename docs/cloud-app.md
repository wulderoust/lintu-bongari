# Cloud analysis & user app — design (step 1)

Status: draft for review · Owner area: cloud + user app · Date: 2026-11-02

This document proposes how recordings get from a station to a trustworthy,
exportable bird dataset. It covers ingest, species identification, counting and
localization, the offline desktop option, the dashboard, human verification,
exports, hosting/GDPR and running cost per station. Hardware, edge firmware and
business model are covered by sibling documents; where this design depends on
them, the dependency is listed in [§14](#14-interfaces-to-sibling-documents).
Requirement IDs (REQ-…) refer to `docs/requirements.md`.

Numbers marked *(est.)* are planning estimates, to be measured in the prototype.

---

## 1. Design principles

1. **The station records; analysis happens elsewhere.** Species ID runs in the
   cloud or on the customer's own computer, never on the device.
2. **One analysis core, two places to run it.** The same versioned processing
   package runs in the cloud and in the desktop app, so results are identical
   regardless of where they were produced.
3. **Evidence-grade by default.** Data may be used for permits, environmental
   impact assessments (YVA) and legal disputes. Every result must be traceable
   to the original audio, the exact model and settings, and the people who
   reviewed it.
4. **Honest about uncertainty.** Detections carry confidence, reports carry
   measured precision, and "counts" are labelled with what they really measure.
5. **Easy for a hobbyist, deep enough for a researcher.** Sensible defaults,
   with every parameter exposed for those who want it.
6. **EU-only data, Finnish-first.** Hosted in the EU (preferably Finland),
   Finnish and English UI, Finnish species list and Finnish map data.

## 2. System overview

```
 Station(s)                    Cloud (EU)                                  Users
 ──────────                    ──────────                                  ─────
 mic array ─► SD card (full    ┌─────────────┐   ┌──────────────┐
   record, authoritative)      │ Device API  │──►│ Telemetry DB │──► Dashboard / alerts
     │                         │ (MQTT/TLS)  │◄──│ Config store │◄── Remote config
     │ 4G                      └─────────────┘   └──────────────┘
     ├─ telemetry/heartbeat ──►       ▲
     ├─ config/commands ◄─────────────┘
     └─ audio chunks + signed ─►┌─────────────┐   ┌──────────────┐   ┌─────────────┐
        manifests (HTTPS,       │ Ingest API  │──►│ Object store │──►│ Job queue   │
        resumable)              │ verify hash │   │ (immutable)  │   └──────┬──────┘
                                └─────────────┘   └──────────────┘          ▼
                                                                    ┌──────────────┐
 SD card from field ─► Desktop app (same core) ─ optional sync ───► │ Analysis     │
                                                                    │ workers:     │
                                                                    │ ID, DOA,     │
                                                                    │ localization │
                                                                    └──────┬───────┘
                                                                           ▼
                                        PostgreSQL + PostGIS  ◄── detections, reviews,
                                                                   audit log
                                               │
                                               ▼
                              Web app: map, review queue, results, exports, reports
```

## 3. Ingest

### 3.1 Data volume — the deciding constraint

Continuous recording at 48 kHz / 16-bit (needed for BirdNET/Perch, which use
up to ~15 kHz):

| Stream | Raw | FLAC *(est. 55–70 %)* | Per 4-week deployment |
|---|---|---|---|
| 1 channel | 8.3 GB/day | ~5 GB/day | ~140 GB |
| 4 channels | 33 GB/day | ~20 GB/day | ~560 GB |

(The hardware doc, §6.4, estimates ~35 GB/day for 4 channels; the exact
figure depends on bit depth and FLAC ratio on real field audio, to be measured.)

20 GB/day is ~1.9 Mbit/s of sustained uplink. Finnish unlimited 4G plans can
carry that, but the **modem's power draw in winter** is likely the real limit
(hardware/edge decision). So the cloud supports three **upload modes**, chosen
per deployment in remote config:

| Mode | What goes over 4G | What stays on SD | Use when |
|---|---|---|---|
| **Full** | All channels, FLAC | Copy of everything | Good power, need near-real-time localization |
| **Reference + opportunistic** | 1 reference channel; other channels when battery/solar and coverage allow (hardware doc §6.4) | All channels | Summer, good sites |
| **Reference** *(recommended default)* | 1 reference channel, FLAC | All channels | Most deployments: ID in near-real-time, localization after retrieval or on request |
| **Harvest** | Telemetry only | Everything | Very low power / poor coverage |

In Reference mode the cloud can **request specific time windows of the other
channels** (e.g. "send all channels for detections of Capercaillie on
2026-04-12") so localization of interesting events still works remotely.
In every mode the **SD cards are the archive of record**; see §3.3 for how
they are ingested at service visits.

Recording schedules (e.g. dawn chorus + night migration only) reduce all of
the above proportionally and are part of remote config.

### 3.2 Upload protocol

- **Chunks:** fixed-length files (proposal: 5 min, one FLAC per chunk with all
  channels of that stream). Filenames carry station id + UTC start time.
- **Transport:** HTTPS with resumable uploads (S3 multipart via presigned URLs
  or the tus protocol). 4G drops are normal; a chunk is never lost, only delayed.
- **Device identity:** each station has a unique key pair generated at
  manufacture (ideally in a secure element, see hardware doc). Mutual TLS for
  both MQTT and upload. A stolen or lost station can be revoked in the dashboard.
- **Backlog:** the station uploads newest telemetry first, then audio oldest
  first; the dashboard shows the backlog size.

### 3.3 SD archive ingest at service visits

Manifests and status go up continuously over 4G, so the cloud always knows
which chunks exist and their hashes, even for audio that has not been uploaded.
At a service visit (card swap or station retrieval):

1. **Card swap:** the technician swaps in a fresh, pre-registered card. The
   dashboard shows the swap from the station's telemetry, and the deployment
   record notes card serials and swap time.
2. **Upload from the office:** the card is read with the desktop app (or a
   small ingest tool) on a computer with a fixed connection. It uploads only the
   chunks the cloud does not yet have, resumable over several days if needed
   (~0.5–1 TB per 4-week, 4-channel deployment). Customers who do not use the
   cloud import the card locally instead (§6), with the same checks.
3. **Verification against manifests:** each chunk's SHA-256 is recomputed and
   compared with the signed, hash-chained manifest the station already sent. The
   ingest report lists: chunks verified, chunks already present from 4G (hashes
   must match), missing chunks, and any mismatches. A mismatch or gap is flagged
   on the deployment and in its reports, never silently filled.
4. **Merge:** verified multi-channel chunks replace the reference-only coverage
   for that period, and queued analyses (DOA, localization, best-channel ID)
   run automatically on them.
5. **Card release:** only when every chunk on the card is verified in
   write-once storage does the app mark the card safe to wipe and reuse
   (REQ-I3). The release is written to the audit log.

Optional later: a **mail-in service** where customers post cards to us and we
ingest them, for customers with slow office connections.

### 3.4 Chain of custody (evidence grade)

1. Station computes SHA-256 of every chunk at write time and writes a
   **manifest** (chunk hash, start time, time-sync quality, GPS position,
   config version, firmware version, sensor readings) signed with the station key.
   Manifests are hash-chained (each includes the previous manifest's hash), so a
   missing or altered chunk is detectable.
2. Ingest verifies signature and hash before accepting a chunk, and only then
   confirms receipt to the station (REQ-I3).
3. Audio is stored in **write-once object storage** (S3 Object Lock in
   compliance mode or equivalent) for the agreed retention period.
4. Every later step (analysis run, review decision, export) is written to an
   append-only **audit log** with user, time and inputs.
   (Steps 1–4 implement REQ-I1 to REQ-I5.)
5. Reports include a verification appendix (REQ-I6) (hashes, model versions) so a third
   party can reproduce the result.

## 4. Species identification

### 4.1 Model options

| Option | Strengths | Concerns |
|---|---|---|
| **BirdNET** (Cornell / TU Chemnitz) | Well known, widely cited, good European coverage, fast on CPU | **Model weights are CC BY-NC-SA 4.0: commercial use needs a licence** from the BirdNET team |
| **Perch 2.0** (Google DeepMind) | Strong embeddings, good for few-shot custom classifiers, permissive licence *(verify exact terms before use)* | Less turnkey; we build the Finnish species head ourselves |
| **Finnish domain model** (Univ. Helsinki / Muuttolintujen kevät, Sirkku on laji.fi) | Trained on Finnish data, shown to beat generic models locally | Licensing/partnership needed; may not be available as a component |
| **Our own classifier** on top of Perch embeddings | Full control, commercial-safe, tunable to Finnish species and to our mics | Needs labelled Finnish data (which our review workflow will produce) |

**Recommendation:** build a **model-agnostic pipeline** with pluggable
classifiers. Start the prototype with BirdNET (research/evaluation use) and
Perch side by side, measure both against a Finnish validation set, and decide
before selling whether to (a) license BirdNET commercially, (b) ship a
Perch-based classifier, or (c) partner with the Finnish research group.
Contacting both BirdNET and Univ. Helsinki early is cheap and de-risks this.

### 4.2 Pipeline

1. Decode chunk, split into 3 s windows (model-dependent), overlap configurable.
2. Run classifier on the reference channel (or best-SNR channel).
3. Filter with a **species list**: Finnish regularly occurring species
   (~250) + rarities from the Finnish checklist, optionally narrowed by
   location and season (FinBIF occurrence data).
4. Apply **per-species thresholds** (not one global threshold), calibrated on
   reviewed Finnish data. Ships with defaults; experts can override.
5. Merge consecutive windows into **detection events** (start, end, freq band,
   species, max/mean score, channel).
6. Separately flag **human speech** and noise classes (wind, rain, traffic) for
   privacy handling and data-quality reporting.

### 4.3 Versioning and reprocessing

Every detection stores a `run_id`. A run records: model name + version + weights
hash, species list version, threshold set version, pipeline software version
(container image digest), and parameters. Reprocessing old audio with a new
model creates a new run; old runs stay available, so a report can always be
regenerated exactly as it was delivered. The UI can compare two runs.
This implements REQ-R1, REQ-R2 and REQ-R5; REQ-R6 (cloud = local) follows from
the shared core in §6, enforced by a CI test that runs both on the same audio
and compares outputs.

## 5. Counting and localization

"Counting birds" from sound means different things at different scales. The
app offers these products, each clearly labelled:

| Product | What it measures | Needs |
|---|---|---|
| **Presence / species list** per site, day, period | Was the species detected | Single mic |
| **Vocal activity** (detections per hour, calling minutes) | How much calling, not how many birds | Single mic |
| **Occupancy** across stations | Share of sites occupied, with detection probability | Many stations, repeat visits (scheduled) |
| **Minimum number of simultaneous individuals** | Distinct bearings of the same species calling at the same time | Mic array on one station (DOA) |
| **Localized calls / territory maps** | Position of each calling bird | ≥3–4 time-synced stations covering the same area |
| **Nocturnal migration counts** | Flight calls per hour, by species | Single mic, night schedule |

### 5.1 Direction of arrival (one station, multi-mic)

GCC-PHAT / SRP-PHAT on the detection's time window across the station's
channels gives a bearing (and elevation, if the array is 3-D). Requires known
array geometry (stored per station model and checked at deployment) and
channels sampled synchronously by one ADC.

### 5.2 Multi-station localization (TDOA)

Time differences of arrival across stations give a position estimate with an
error ellipse. Requirements on hardware/edge: **GPS-disciplined timestamps
(PPS), under 1 ms between stations and under 0.1 ms between channels of one
array (REQ-T1, REQ-T2)**; 1 ms is ~34 cm of sound travel, fine for territory work; surveyed station positions (GPS is
enough for ~tens of metres; better for fine work), and temperature for speed of
sound. Station spacing must be within hearing distance of the target species
(typically 50–200 m). Localization runs only on detection windows, so compute
stays small.

### 5.3 Counting individuals (v1 scope)

**Decision (walto, 2026-11-02): version 1 must count and locate individual
birds using multiple stations.** So TDOA localization is a v1 feature, not a
later one. How the counting works:

1. **Event matching:** a detection on one station is matched to detections of
   the same species on neighbouring stations within the maximum travel time
   (distance / speed of sound + timing error).
2. **Localize:** TDOA across stations (and DOA within each array, which helps
   when only 2 stations hear a call) gives a position and an error ellipse.
   Positions with too-large ellipses are kept but marked "not localized".
3. **Cluster into individuals:** positions of the same species are clustered in
   space and time (singing posts, territories). Calls that overlap in time from
   clearly separate positions are proof of separate birds.
4. **Report counts with uncertainty:** minimum number of individuals (from
   simultaneous separated calls) and estimated number (from clusters), with a
   confidence range. A reviewer can merge or split clusters on the map.
5. **Validate:** the field pilot compares counts with a human territory mapping
   survey and with test sounds played from known positions (also checks the
   timing chain end to end).

**Effect on uploads:** localization needs all channels from every station that
heard the call. With the Reference default, localization runs in two ways:
- *Near real time, selective:* when a detection is found on the reference
  channel, the cloud automatically requests the matching all-channel window from
  that station and its neighbours (a few seconds of audio each, small enough
  even in winter).
- *Complete:* after SD ingest at the service visit (§3.3), the whole deployment
  is localized. Reports used for counts are based on this complete run.

**Station layout:** the app includes a planning tool on the map that suggests
station spacing for the target species group and shows the area where
localization is expected to work (at least 3 stations in hearing range).

## 6. Desktop / offline processing

For customers who cannot or will not use the cloud, or who retrieve SD cards.

- **Same core:** the analysis core is a Python package distributed as a
  container image (cloud) and as a bundled desktop app (Windows first, then
  macOS/Linux). Same version number ⇒ same results.
- **UI:** the desktop app runs the same web UI locally (a local server + embedded
  browser window, e.g. Tauri), so users learn one interface.
- **Workflow:** import SD card ➝ hashes verified against manifests ➝ analysis
  ➝ review ➝ export. Works fully offline; models are downloaded once and
  updated when online.
- **Optional sync:** push results (and optionally audio) to a cloud project to
  share with colleagues or to unify with 4G stations.
- **Performance** *(est.)*: BirdNET-class models process roughly 1 hour of
  mono audio per minute or less on a modern laptop CPU, so a 4-week single-channel
  deployment is a few hours. GPU optional. To be benchmarked.

## 7. Dashboard and device management

### 7.1 Structure

Organization ➝ Projects ➝ Sites ➝ Deployments (a station at a place for a
period) ➝ Recordings ➝ Detections. A station can move between deployments;
history is kept.

**Phone setup flow:** at the site, the installer connects to the station over
Bluetooth from the phone (web app or small companion app), which registers the
station to the deployment, records its GPS position and mic array heading,
takes photos, runs a test (plays a sound, checks all channels and time sync)
and attaches the landowner permission (REQ-P4). Accurate positions and heading
are essential for localization.

### 7.2 Device status

Per station: last heartbeat, battery voltage and state of charge, solar input,
enclosure temperature and humidity, storage free, 4G signal and operator,
upload backlog, GPS fix and time-sync quality, firmware/config version, and a
**per-channel mic health check** (noise floor and level vs. other channels) to
catch a failed, wet or iced microphone early. Winter-specific: show heater
state and snow/ice warnings if the hardware provides them.

**Alerts** (email, push, optional SMS): station offline > N hours, battery
low, storage nearly full, mic failure, time sync lost, upload backlog growing.

### 7.3 Remote config

A versioned config document per station (desired vs. reported state, the
"device shadow" pattern): recording schedule, sample rate, gain, upload mode,
heartbeat interval, on-demand clip requests. Changes are queued and applied
when the station next connects; the dashboard shows "pending" until confirmed.
Config history is part of the audit trail. Firmware updates (OTA) are triggered
from here but designed in the edge document.

### 7.4 Maps

MapLibre with Finnish National Land Survey (Maanmittauslaitos) open
background maps and aerial imagery. Layers: stations with live status,
detections per species (heat map / bubbles by period), DOA bearings,
localized calls with error ellipses, and project boundaries (import
GeoJSON/Shapefile). **Sensitive species** (per the FinBIF sensitive-species
list) have their locations coarsened in shared views and exports unless the
user has explicit permission.

## 8. Human verification

Automatic ID is not enough for legal or scientific use; review is a core
feature, not an add-on.

- **Review UI:** spectrogram + audio playback of the detection with context,
  channel switching, model's top-N suggestions, keyboard shortcuts for fast
  accept / reject / relabel / "unsure".
- **Review strategies:**
  - *Validate all* for rare or legally relevant species (configurable list).
  - *Stratified sample* by species and confidence for common species, from
    which the app **estimates precision per species** and shows it in reports.
  - *Second reviewer* required for flagged species (four-eyes principle), with
    disagreement resolution.
- **Reviewer accounts** with expertise level; every decision is in the audit log.
- **Feedback loop:** reviewed detections become labelled Finnish training and
  calibration data (with customer consent in the contract), improving
  thresholds and any custom classifier over time. This is a long-term moat.

## 9. Exports and reports

| Format | Contents |
|---|---|
| **CSV / Excel** | Detections or reviewed observations, with station, coords, UTC + local time, species (scientific, Finnish, English, FinBIF taxon id), score, review status, run id |
| **Raven Pro selection tables** | Tab-separated, one file per recording, for experts who re-check in Raven |
| **Audacity labels** | Simple label tracks |
| **Audio clips** | WAV/FLAC snippets of detections, zipped with an index |
| **Laji.fi / FinBIF** | Reviewed observations in a FinBIF-compatible import format, with taxon ids from the FinBIF taxonomy API. Exact format and whether automated submission via API is allowed must be confirmed with Luomus/FinBIF |
| **Darwin Core Archive** | For GBIF and international research use |
| **GeoJSON / GeoPackage** | Stations, detections, localizations for GIS |
| **PDF report** | Per deployment or project: methods, effort (hours recorded per station), species list and activity charts, maps, review coverage and precision, model and software versions, data-integrity appendix. Template aimed at consultants' YVA / wind-power assessments |

All exports record which run and which review state they came from.

## 10. Proposed technology

| Layer | Proposal | Why |
|---|---|---|
| Device messaging | MQTT over mutual TLS (EMQX or Mosquitto) | Light on power and 4G, standard for IoT |
| Uploads | S3-compatible multipart via presigned URLs | Resumable, no custom server in the data path |
| Object storage | S3-compatible with object lock | Immutability, cheap, portable between providers |
| Database | PostgreSQL + PostGIS (+ TimescaleDB for telemetry) | One reliable DB for spatial, time-series and relational data |
| API | Python (FastAPI) | Same language as the analysis core |
| Analysis core | Python package; ONNX/TFLite runtime for models | Runs identically in containers and desktop |
| Jobs | Queue + autoscaling CPU workers | Cheap, bursty workloads |
| Web app | React + MapLibre + client-side spectrograms | Works in the desktop shell too |
| Desktop | Tauri wrapper around local server + web UI | Small installer, one UI |
| Infra | Containers on managed Kubernetes or plain VMs, IaC (Terraform/OpenTofu) | Portable between EU providers |

## 11. Hosting, GDPR and data protection

### 11.1 Hosting

All data stays in the EU. Candidates: **UpCloud** (Finnish company, Helsinki
data centres), **Hetzner** (Helsinki data centre, very low cost), **AWS
eu-north-1** (Stockholm, richest managed services). Public-sector and
consultant customers may prefer a European-owned provider (no US CLOUD Act
exposure). Recommendation: design for S3-compatible + plain Postgres so we can
start on Hetzner or UpCloud and move if needed.

### 11.2 GDPR

- **Audio can contain people.** Speech near a station is personal data. The
  pipeline detects human speech and, by default, **mutes those segments in all
  derived clips and exports** and limits access to the raw chunk to project
  admins, with every access logged (REQ-P1, REQ-P2). Redacted clips are derived
  files that reference the original's hash, so chain of custody holds.
- **Roles:** the customer is the controller of their recordings; we are a
  processor. We provide a standard **Data Processing Agreement**, a sub-processor
  list and a record of processing.
- **Signage:** the kit includes site signs ("automatic sound recording for bird
  monitoring") with a link/QR to a privacy notice, which customers are advised
  to put up.
- **User accounts:** minimal personal data (name, email, organization), EU-only
  email/SMS providers where possible.
- **Retention & deletion:** configurable per project (e.g. 1 year default,
  up to 10 years for legal cases, moved to cold storage), with deletion that
  respects object-lock commitments.
- **Security:** encryption in transit and at rest, MFA for accounts, role-based
  access, audit log, regular backups to a second EU location.

## 12. Cost per station *(est.)*

Assumptions: continuous 48 kHz recording, 4-week deployment, Reference upload
mode, all channels uploaded after retrieval, 1-year retention.

| Item | Per station-month | Notes |
|---|---|---|
| Hot object storage, 0.6 TB | €3–15 | Hetzner/UpCloud ≈ €5–10 per TB-month; AWS S3 ≈ €21 |
| Cold archive after 3 months | €1–2 | Glacier-class storage |
| Species ID compute | < €1 | ~700 h mono audio is a few CPU-hours |
| Localization compute | < €1 | Detection windows only |
| Telemetry, DB, bandwidth | ~€1 | |
| **Marginal cloud cost** | **≈ €5–20** | Mostly storage; halved with schedules or mono-only retention |
| 4G SIM (not cloud) | €15–30 | Finnish unlimited data plans, IoT plans are cheaper but capped |
| Fixed platform cost | €150–400 / month total | Servers, monitoring, backups; spread over all stations |

Implication for the business document: a **per-station subscription** in the
range that covers storage + SIM + support is realistic, and long-retention or
"evidence grade" tiers should be priced separately because storage dominates.

## 13. Delivery phases

| Phase | Cloud & app scope |
|---|---|
| **Prototype (step 3)** | Ingest with hashes and manifests, BirdNET + Perch batch runs with run versioning, Finnish species list, simple review UI, CSV + Raven export, desktop CLI for SD import with manifest verification, multi-station TDOA tested on recordings of sounds played from known positions |
| **Field pilot (step 4)** | Dashboard with device status and alerts, remote config, maps, phone setup flow, on-demand clip requests, localization and individual counting with review on the map, stratified review with precision estimates, Laji.fi export, PDF report, speech muting, desktop app |
| **Product v1** | Multi-tenant orgs and roles, station layout planner, territory maps, DPA/legal package, billing |
| **v2** | Custom Finnish classifier, occupancy outputs, mail-in SD service |

## 14. Interfaces to sibling documents

| Needs from | What |
|---|---|
| Hardware | Synchronous multi-channel ADC; GPS with PPS; secure element for device key; mic geometry spec; power budget for 4G uplink in winter |
| Edge software | Chunk + signed manifest format; resumable uploader; MQTT topics for telemetry/config/commands; on-demand clip upload; OTA |
| Requirements & data quality | Target precision/recall per species group; which outputs must be "evidence grade"; retention requirements |
| Product & business | Model licensing outcome; cloud subscription pricing for a sold kit; first report template for consultants and researchers |

## 15. Decisions and open questions

Decided by walto on 2026-11-02:
- V1 counts and locates individual birds with multiple stations (§5.3).
- Consultants and researchers are the first customers.
- The kit is sold, not rented. Cloud use is still an ongoing service (§12).
- Contacting the BirdNET team and the Finnish research group about licensing
  is approved; drafts are prepared for walto to review before sending.
- Stations use solar plus battery, and have Bluetooth/Wi-Fi for phone setup.
- A possible pilot partner: Luontopalvelut Flava (luontopalvelutflava.fi).

Still open:
1. **Hosting:** Finnish provider (UpCloud), lowest cost (Hetzner) or AWS?
2. **Retention:** how long do customers need raw audio kept (legal cases may
   need years)?
3. **Desktop OS:** is Windows the main platform for customers?
4. **Pricing of the cloud service** for a sold kit: included for a first
   period, then a yearly subscription? (business doc)
