# Requirements and data quality

Status: draft for review (step 1 of the plan). Owner: walto. Last updated 2026-11-02.

Decisions from walto (2026-11-02): version 1 counts and locates individual birds using several stations together; consultants and researchers are the first customers, hobbyists come later; kits are sold, not rented; stations are solar plus battery powered; phone setup over Bluetooth or Wi-Fi is allowed; Luontopalvelut Flava (luontopalvelutflava.fi) is a candidate pilot partner.

This document defines what the bird call kit must do for its buyers, which Finnish survey practices it has to fit, what makes its data trustworthy enough for legal and regulatory reports, and how it handles privacy. Hardware, edge software, cloud and business documents should trace their design choices back to the requirement IDs here (`REQ-…`).

Priority words: **MUST** is required for the first sellable kit, **SHOULD** is expected unless there is a documented reason, **MAY** is optional or later.

Items marked *(verify)* are legal or standards details that need checking against the primary source or an expert before the design is frozen.

---

## 1. Product scope in one paragraph

A kit of one or more outdoor recording stations, each with several microphones, that is placed at a remote Finnish site for 2 to 4 weeks at a time in any season including winter. Stations record audio, check their own health, and upload over 4G. They do not identify species. Species identification and counting run in the cloud or on the customer's own computer. The kit must be easy enough for a hobbyist to deploy, and the data must be good enough for a consultant to put in a report that an authority or a court may scrutinise.

## 2. Buyers and what each needs

| | Consultants | Researchers | Hobbyists |
|---|---|---|---|
| Typical job | Bird surveys for environmental impact assessment (YVA), wind farm and land use planning, Natura assessments, follow-up monitoring required by permits | Population trends, phenology, migration, habitat studies, method development | Know what birds are around the cottage or local patch, contribute to citizen science |
| Main output | A defensible report: species list, counts or activity indices, survey effort, methods, uncertainty | Raw audio plus rich metadata, detections with scores, exports to analysis tools | A simple species list with examples to listen to |
| What would make them reject the product | A finding that cannot be traced back to original audio, unclear method, gaps in coverage nobody noticed | Lossy audio, unknown timing accuracy, closed formats, unknown model version | Fiddly setup, confusing results, cost |
| Scale | Several stations across a project area, repeated seasons | One to many stations, long series | One station |
| Human review | Expert verifies every species that matters for the conclusions | Validates samples to estimate error rates | Optional, casual |

Consultants and researchers are the first customers. Hobbyist needs stay in the design but come after version 1.

Requirements that follow from this:

- **REQ-B1 (MUST)** One product, three experience levels: a simple default view (species list, top recordings) and an expert view (all detections, scores, raw audio, metadata, audit trail). The data underneath is the same.
- **REQ-B2 (MUST)** Report export for consultants: species, detection counts per station and day, survey effort (hours actually recorded per station), method description, model versions, and verification status, as PDF plus machine readable tables (CSV).
- **REQ-B3 (MUST)** Raw audio export in an open lossless format (FLAC or WAV) with sidecar metadata (JSON), for researchers.
- **REQ-B4 (SHOULD)** Export observations in Darwin Core form so they can go to FinBIF (Laji.fi) and GBIF. *(verify FinBIF import format and required fields)*
- **REQ-B5 (MUST)** A first-time deployment by a field worker without electronics knowledge takes under 30 minutes per station on site, guided by a phone app over Bluetooth or Wi-Fi (printed card as backup), and the station confirms by itself that it is recording, located and connected.
- **REQ-B6 (MUST)** Human verification workflow: an expert can mark each detection as confirmed, rejected or uncertain. The reviewer's name and time are stored, and reports state which results were verified.

## 3. Fitting Finnish survey practice

Acoustic recorders are an accepted complement to field surveys, but they do not produce the same numbers as a person walking a route. The kit must be honest about this and support the methods buyers already report against.

### 3.1 Methods the kit should support or complement

| Finnish method | What it measures | How the kit helps | Limits to state in reports |
|---|---|---|---|
| Point count (pistelaskenta) | Species and pairs heard and seen at a fixed point in a fixed time window, usually early morning in breeding season | A station is a permanent point count running every morning for weeks, which reduces chance and observer bias | Only vocal birds, no visual detections, detection radius depends on species, wind and terrain |
| Line transect (linjalaskenta) | Density along a walked route | Several stations along a line can sample the same habitat | Not a transect; densities need a detection distance model |
| Territory mapping (kartoituslaskenta) | Number of territories from repeated visits | Repeated daily coverage; with array localisation, positions of singing birds | Territory counts need localisation or expert interpretation |
| Night singer and owl surveys (yölaulaja- ja pöllölaskennat) | Nocturnal species, often in spring | Strong fit: nights are long, people are expensive at night | Owls call rarely; detection depends on survey length |
| Nocturnal migration monitoring | Flight calls overhead | Strong fit for continuous recording | Calls give passage activity, not number of birds |
| Winter bird count (talvilintulaskenta) | Wintering species along routes | Stations can run through winter | Few vocalisations in winter; acoustic coverage is weaker |
| Wind farm pre-construction and monitoring surveys | Use of the area by sensitive species (raptors, cranes, grouse, owls) | Long unattended deployments in remote terrain | Some target species call rarely; acoustic data complements, not replaces, visual watch |

### 3.2 Counting at different scales

"How many birds" can mean different things. The kit must label which one a number is.

- **Level 1, presence:** species detected at station X on day Y. Always available.
- **Level 2, activity index:** number of detections or number of minutes with detections per hour, per station. Comparable between stations and years if the hardware and settings are the same. Always available.
- **Level 3, minimum number of individuals with positions:** the number of birds of one species calling at the same time, estimated by locating each caller from arrival time differences across microphones in several stations. Needs tight time synchronisation (REQ-T2), accurately surveyed station positions (REQ-L3) and localisation software. **Required for version 1.**
- **Level 4, density or abundance:** needs a detection distance model per species. Research topic; MAY come later.

- **REQ-C1 (MUST)** Every count in the app and in reports states its level (presence, activity index, minimum individuals) and the effort it is based on.
- **REQ-C2 (MUST)** Survey effort is recorded exactly: when each microphone was actually recording, including gaps from power, storage, faults or noise. Without this a "not detected" result means nothing.
- **REQ-C3 (SHOULD)** Recording schedules matching standard methods are available as presets, for example "breeding season dawn" (from 1 hour before sunrise for 4 hours), "night singers", "continuous", alongside custom schedules. Continuous recording is the default when power allows, because missing data cannot be recovered.

### 3.3 Data standards and sensitive species

- **REQ-S1 (SHOULD)** Use FinBIF/Laji.fi taxonomy (scientific name plus the Finnish name and FinBIF taxon ID) as the species list, so results line up with Finnish databases. *(verify taxon ID source and licence)*
- **REQ-S2 (MUST)** Sensitive species locations (for example breeding raptors, owls, some grouse) are not shown publicly or in shared exports at full precision. Follow FinBIF's coarsening rules for sensitive species. *(verify current FinBIF sensitive species list and coarsening levels)*
- **REQ-S3 (MAY)** One-click submission of verified observations to Laji.fi or to BirdLife Finland's Tiira, with the user's own account.

## 4. Data trustworthiness for legal and regulatory use

The goal: for any species claim in a report, anyone can follow it back to the exact original audio, recorded at a known time and place by a known working device, analysed by a known model version, and see that nothing was changed in between.

### 4.1 Time

- **REQ-T1 (MUST)** Each station timestamps audio from a GNSS-disciplined clock (GPS PPS or equivalent). Absolute error to UTC under 10 ms during recording. Station logs the GNSS lock state, and any period without lock is flagged with the estimated drift.
- **REQ-T2 (MUST)** All microphones in one station are sampled by the same clock, so inter-channel timing error is under 0.1 ms. Between stations of the same kit, timing error is also under 0.1 ms (about 3 cm of sound travel), using GNSS PPS recorded in the audio stream so each sample has an exact UTC time. Localisation of individual birds across stations depends on this.
- **REQ-T3 (MUST)** All stored times are UTC (ISO 8601); local time (Europe/Helsinki) is only for display. Sunrise and sunset are computed from the station position.

### 4.2 Location and setup

- **REQ-L1 (MUST)** Station position from GNSS, stored with accuracy estimate, at deployment and periodically. A position change of more than a set threshold (moved or stolen) raises an alert.
- **REQ-L3 (MUST)** For cross-station localisation, station and microphone positions are known to within 0.5 m relative to each other. Standard GNSS is not enough; the method (long GNSS averaging, RTK, or measuring distances on site) is for the hardware and edge documents to choose. Positions and their accuracy are stored with the deployment.
- **REQ-L2 (MUST)** Deployment record: who deployed, when, photo of the setup, habitat note, microphone height, microphone geometry (as built), and mounting. Same at retrieval.

### 4.3 Audio quality

- **REQ-A1 (MUST)** Archive copy is lossless: FLAC, at least 48 kHz, at least 16 bit (24 bit preferred). Lossy compression MAY be used only for quick listening copies, never as the archive.
- **REQ-A2 (MUST)** Fixed and recorded gain. No automatic gain control on the archive copy, so levels stay comparable.
- **REQ-A3 (MUST)** Microphone sensitivity known per unit (dBFS per Pa at 1 kHz), checked with an acoustic calibrator before and after each deployment, and stored with the deployment. Hobbyist kits MAY use a simpler built-in self-test.
- **REQ-A4 (MUST)** Continuous health monitoring per microphone: dead channel, clipping, abnormal noise floor, likely ice, water or wind noise. Faults are logged with time and reduce the counted effort (REQ-C2).
- **REQ-A5 (SHOULD)** Weather context logged at the station (temperature, and if feasible wind and rain indicator), because detection probability depends on it.
- **REQ-A6 (MUST)** Frequency response covers at least 100 Hz to 12 kHz flat enough for species ID in all conditions down to -30 °C; the hardware document sets the exact spec. *(note: some species call up to 16 kHz; hardware to decide)*

### 4.4 Integrity and chain of custody

- **REQ-I1 (MUST)** Every audio file and its metadata get a SHA-256 hash on the station at the moment the file is closed.
- **REQ-I2 (MUST)** The station signs a manifest of file hashes with a device private key kept in a secure element. Manifests are chained (each includes the hash of the previous one), so a missing or altered file is detectable.
- **REQ-I3 (MUST)** Signed manifests (REQ-I2) and status go to the cloud continuously, within an hour of each file closing when 4G is available. This fixes each file's hash in the cloud long before the audio itself arrives, so audio collected later can still be proven unchanged.
- **REQ-I7 (MUST)** Audio reaches the cloud in tiers, because uploading every channel over 4G is not affordable in power or data (about 35 GB per station per day for 4 channels at 48 kHz/24 bit). Tier 1: one reference channel uploads by default for species ID. Tier 2: the full multichannel archive uploads only when power and coverage allow, or on request for selected time windows. Tier 3: the station's SD cards are the archive of record and are collected at service visits.
- **REQ-I8 (MUST)** Every file that reaches the cloud, by 4G or from an SD card, is accepted only after its recomputed hash matches the signed manifest already in the cloud. Mismatches and files missing from the manifest are flagged, not silently accepted. The station never deletes audio it has not had confirmed this way.
- **REQ-I4 (MUST)** Original audio in the cloud is stored write-once (object lock or equivalent) for the agreed retention period. Any derived file (filtered, redacted, clipped) records the hash of its source.
- **REQ-I5 (MUST)** Append-only audit log of everything that happens to the data: uploads, analyses, human reviews, edits, exports, deletions, access to raw audio. Each entry has who, what, when.
- **REQ-I6 (SHOULD)** A report export includes a verification package: manifest, hashes, model versions, and audit log extract, so a third party can check it.

### 4.5 Reproducible species identification

- **REQ-R1 (MUST)** Every detection stores: model name, model version, hash of the model weights, analysis settings (thresholds, window, filters, species list), software version, and when it ran.
- **REQ-R2 (MUST)** Rerunning the same model version with the same settings on the same audio gives the same result. Old model versions stay available for as long as reports based on them are retained.
- **REQ-R3 (MUST)** Each detection keeps its confidence score. Reports state the threshold used.
- **REQ-R4 (MUST)** Published per-species performance (precision and recall) of each model version on a Finnish validation set, so users know which species are reliable and which need human checks. Species with poor or unknown performance are flagged in the app.
- **REQ-R5 (SHOULD)** Running a new model version on old data creates a new analysis run alongside the old one, never overwriting it.
- **REQ-R6 (MUST)** Cloud and local (user's computer) analysis give identical results for the same model version and settings.

### 4.6 Retention

- **REQ-D1 (MUST)** Configurable retention per project. Defaults: original audio kept for the project term plus a set number of years for consultant projects; detection results and audit log kept at least as long as the audio. *(walto to decide default, see questions)*
- **REQ-D2 (MUST)** Customers can export everything (audio, metadata, results, audit log) in open formats and delete their data at the end.

## 5. Privacy and law

The stations record everything they hear, including people. In Finland this touches the GDPR, the Data Protection Act (1050/2018) and the eavesdropping provision of the Criminal Code (salakuuntelu, RL 24:5). *(verify with a lawyer before sale)*

### 5.1 Roles

- The customer who deploys the station decides where and why to record, so the customer is normally the **controller** of any personal data captured.
- When we host data in our cloud, we are a **processor** and need a data processing agreement (DPA) with each business customer.
- Hobbyists recording on their own property for a personal purpose may fall under the household exemption, but recordings that reach neighbours or public paths still need care.

### 5.2 Requirements

- **REQ-P1 (MUST)** Human speech detection runs on all audio as it reaches the cloud or the user's computer (tier 1 first, the full archive when it arrives). Segments with speech are hidden from normal listening and from shared exports by default. Only users with a raw audio role can open them, and every such access is logged (REQ-I5).
- **REQ-P2 (MUST)** Redaction never breaks the chain of custody: the original keeps its hash and write-once status, the redacted copy is a derived file that refers to it (REQ-I4). Policy option: delete the original speech segments after a set period while keeping a record that they were deleted, when and why.
- **REQ-P3 (MUST)** Guidance and a ready-made sign for the site ("Lintujen äänitallennin / Bird sound recorder", controller contact, purpose), since people in the area must be informed (GDPR Art. 13/14). Hobbyist guidance warns against placing stations aimed at yards, homes or other private spaces.
- **REQ-P4 (MUST)** Landowner permission is part of the deployment record (REQ-L2). Everyman's rights do not cover leaving equipment in place for weeks.
- **REQ-P5 (MUST)** All customer data is stored and processed in the EU/EEA. Encryption in transit and at rest. Role-based access per project.
- **REQ-P6 (SHOULD)** We provide a data protection impact assessment (DPIA) template for consultant customers.
- **REQ-P7 (MUST)** Sensitive species locations are protected as in REQ-S2. This is a nature protection matter, not GDPR, but it uses the same access control.

## 6. Operating requirements that affect data quality

These are summarised here because they decide whether data exists at all. The hardware and edge software documents set the detailed specs.

- **REQ-O1 (MUST)** Unattended operation for 28 days with continuous recording on all channels, in temperatures from -30 °C to +35 °C, through snow, rain and icing, powered by solar panel plus battery. The power budget must hold through the darkest Finnish winter weeks, where solar input is close to zero in the north. Data loss from a full battery or storage must not happen silently.
- **REQ-O2 (MUST)** Station keeps recording when 4G is down and catches up manifest, status and tier 1 uploads when the connection returns. Local storage holds the whole deployment's full multichannel audio, since the SD cards are the archive of record (REQ-I7).
- **REQ-O3 (MUST)** Remote status at least every hour when connected: recording state, battery, storage, temperature, GNSS lock, microphone health, last upload.
- **REQ-O4 (MUST)** Remote configuration changes (schedule, gain) are logged in the audit log and take effect at a recorded time, so effort stays traceable.
- **REQ-O5 (MUST)** One project can include from 1 to at least 20 stations, managed together, with results shown per station and combined.

## 7. Acceptance criteria for the first field pilot

1. Three stations run 28 days at a real site with a pilot partner (candidate: Luontopalvelut Flava), at least one deployment period below 0 °C.
2. A test sound played at known positions inside the station layout is located by the system within an agreed error (target 5 m), and simultaneous callers are counted correctly.
3. Recorded effort is 95% or more of scheduled time, and every gap is explained in the log.
4. Every file in a sample of 100 traces from report to original audio with matching hashes, including files recovered from SD cards at the service visit and checked against manifests uploaded during the deployment.
5. GNSS timing check: a test sound recorded by all microphones shows inter-channel error within REQ-T2.
6. Model results for the pilot agree with an expert's review on a random sample, and precision per common species is reported.
7. A field worker without electronics knowledge deploys a station from the guide alone in under 30 minutes.

## 8. Open questions for walto

Answered on 2026-11-02: individual counting (yes, across stations), first customers (consultants and researchers), sales model (sell), power (solar plus battery), phone setup (yes), pilot partner (Luontopalvelut Flava).

Still open:

1. Which legal use comes first: wind farm YVA surveys, Natura assessments, or permit monitoring? This sets the report template and which species need validated performance first.
2. How long should raw audio be kept by default (for example 5 years for consultant projects)? This drives cloud storage cost.
3. Continuous recording around the clock, or scheduled windows by default? Continuous gives the best data but costs winter power.
4. Should our cloud host customer data (we become a processor with a DPA), or should consultants also be able to keep everything on their own machines only?
