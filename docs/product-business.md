# Product & business: lintu-bongari

Status: draft for step 1 (requirements and design). Owner: walto. Last updated 2026-11-02.

This document covers the market, competitors, the gap this kit fills, EU certification, pricing,
support and warranty, and what "easy to use" has to mean in practice. Numbers marked **(est.)** are
working assumptions to be replaced once the hardware BOM and cloud costs are known.

---

## 0. Decisions from walto (2026-11-02)

| Topic | Decision | Effect on this doc |
|---|---|---|
| Counting | Version 1 **counts and locates individual birds** using multiple time-synced stations | Localization is the headline feature; the smallest professional kit is 4 stations |
| First customers | **Consultants and researchers first**; hobbyists later | Hobbyist tier stays phase 2 |
| Sales model | **Sell** (no rental at launch) | Rental tier removed; hardware + active-month subscription |
| Licensing | OK to contact BirdNET team and University of Helsinki | Classifier licence added as a cost line; outreach drafted for walto to approve before sending |
| Power | **Solar + battery** | Higher BOM and price; solar panel and mount part of the kit |
| Phone setup | Stations **may include Bluetooth/Wi-Fi** | Setup flow uses phone pairing; adds radio tests to CE |
| Pilot | **Luontopalvelut Flava Oy** (luontopalvelutflava.fi) as candidate pilot partner | See section 9 |
| Company | walto has a **toiminimi** | Recommend forming an Oy before the first sale (section 5a) |
| Legal uses | **All**: wind-power YVA, Natura assessments and permit monitoring | Report templates for all three; YVA first in practice because of volume (section 9) |
| Recording | **Continuous** | Drives storage, power and data cost |
| Data ownership | **The customer owns the data** | We act only as processor; full export and delete; desktop-only option (section 4) |
| Polar night (Lapland) | Not in v1; a later version | v1 is specified for southern and central Finland; in midwinter it still runs mostly on battery |
| Battery weight | 17 kg per station accepted, smaller preferred | Kit weight and shipping by road, not air |
| Kit price | €6-8k is "somewhere there" | **Conflicts with parts cost; see section 6 and the open decision** |

---

## 1. One-line positioning

> A complete, remotely accessible, winter-proof bird-sound monitoring kit for Finland that
> delivers **trustworthy, auditable species detections and counts**, without the buyer having to
> collect SD cards, run their own AI, or be an acoustics expert.

The product is a **kit plus a service**, not a recorder: stations, mounts, power, 4G connectivity,
a cloud/desktop analysis pipeline, and reports that hold up in a permitting process.

---

## 2. Buyers and what they need

| Segment | Typical use | What they pay for | What they will not tolerate |
|---|---|---|---|
| **Environmental consultants** (e.g. firms doing YVA/EIA, wind-power and Natura assessments) | 2-4 week surveys at several sites per season, results go into reports to authorities | Reliable data, defensible methods, less fieldwork (fewer site visits), fast reports | Lost data, a dead station found only at pickup, results they cannot defend to an authority |
| **Researchers** (universities, SYKE, Luke, museums, bird societies) | Long series, many sites, comparisons with other studies | Raw audio access, open formats, known microphone calibration, metadata, exports | Black boxes, lock-in, no raw audio |
| **Hobbyists** (birders, landowners, cottage owners) | One station at home or the cottage, curiosity, contributing to citizen science | Fun app, species lists, notifications, low price | Complexity, high subscription |

**Recommendation:** launch for **consultants and researchers first** (they value trust and pay for
it; volumes are small enough for walto to build and support). Offer hobbyists a simpler
"single station" product in a second phase, because consumer sales bring extra obligations (GPSR,
14-day return right, consumer warranty expectations) and a much lower price point.

### "Different scales" maps to three kit sizes
- **Single station:** one point, presence and activity.
- **Localization kit (4+ stations):** a consultant's typical site; counts and locates individuals.
- **Network (10+ stations):** research projects, wind-farm areas, long-term monitoring.

Multi-microphone stations give **direction of arrival**, and several GNSS-time-synced stations
together give **localization of individual birds**. Version 1 must do this (walto, 2026-11-02):
it is what lets the kit *count individuals and territories* rather than only list species, and it
is the strongest technical differentiator. Practical consequence for sales: localization needs at
least 3, preferably 4, stations hearing the same bird, so the **4-station kit is the base
professional product**, and single stations are sold as add-ons or for presence/activity only.

---

## 3. Competitor landscape

Prices are list prices seen in Nov 2026 from European resellers, VAT excluded unless noted.

| Product | Price | Strengths | Weaknesses vs our goal |
|---|---|---|---|
| **Wildlife Acoustics Song Meter Mini 2 (AA)** | ~£408 recorder, ~£445 bundle ([NHBS](https://nhbs.com/song-meter-mini-2-acoustic-recorder)); Li-ion version ~£491 | Industry standard, Kaleidoscope software, trusted by consultants, Bluetooth setup app, 2-year warranty | No cellular: data only at pickup. Mono (stereo with extra mic). Analysis software is a separate paid licence. AA life ~530 h. |
| **Wildlife Acoustics SM4 / Song Meter 2-series** | ~€900-1,200 (est.) | Rugged, stereo, long deployments, wide acceptance | Same: SD cards, no remote status, expensive per site |
| **AudioMoth v1.2 (Open Acoustic Devices)** | ~$100 ([GroupGets](https://groupgets.com/products/audiomoth-v1-2-0)) | Very cheap, open source, huge research user base | Bare board, needs case, DIY setup, no connectivity, availability through group buys, no support for regulatory use |
| **BirdWeather PUC** | ~£227 ([NHBS](https://www.nhbs.com/birdweather-puc)) | On-device BirdNET, dual mics, GPS, environmental sensors, free app and dashboard | Wi-Fi only (no 4G), AA batteries, hobbyist grade, detections not built for auditable reporting, cold performance unproven |
| **BirdNET-Pi / Haikubox / DIY Raspberry Pi stations** | €100-400 | Cheap, live results | Mains + Wi-Fi, not field deployable, no support |
| **Frontier Labs BAR-LT and similar long-term recorders** | ~€1,000+ (est., verify) | Long deployments, GPS time sync | SD-card workflow, limited presence in Finland |
| **Finnish ecosystem: Muuttolintujen kevät app, LIFEPLAN, laji.fi** | Free | Strong Finnish classifier work (University of Helsinki, Lauha 2026 thesis showed fine-tuned local models improve accuracy, [source](https://www.helsinki.fi/en/news/artificial-intelligence/artificial-intelligence-can-identify-bird-sounds-more-reliably)) | Phone apps and research projects, not a deployable kit. These are **partners and data destinations, not competitors.** |

### The gap we fill
Nobody sells a **Finnish-ready, 4G-connected, winter-capable, multi-microphone kit with a
defensible analysis and reporting pipeline**. Today a consultant buys Song Meters, drives out to
swap batteries and cards, runs BirdNET or Kaleidoscope themselves, and manually checks results.
Our value proposition, in the buyer's words:

1. **"I know it's working."** Daily health check over 4G (battery, storage, mic, temperature,
   last detection). Alerts when something breaks, instead of finding out at pickup.
2. **"I get results while it's still out there."** Detections and summaries uploaded daily.
3. **"It survives January."** Designed and tested for -30 °C, snow, ice and short days.
4. **"I can count, not just list."** Multi-mic direction finding and station sync enable
   individual/territory estimates.
5. **"I can defend it."** Signed audio, GPS time, versioned models, validation workflow,
   standard export to report templates and to laji.fi/FinBIF.
6. **"Finnish species, Finnish language."** Classifier fine-tuned for Finnish species and
   dialects; UI in Finnish, Swedish and English.

---

## 4. Requirements this places on the other workstreams

Product decisions that the Hardware, Edge software, Cloud & app and Requirements threads need.
These line up with `docs/requirements.md`: data integrity REQ-I1–I5, model versioning REQ-R1–R6,
privacy/speech redaction and EU hosting REQ-P1–P5, 28-day operation at -30 °C REQ-O1–O5.

- **Data integrity for legal use:** every recording has GPS time, station ID, location, firmware
  and model version, and a cryptographic hash/signature created on the device. Raw audio kept
  (or at least retained for the detections used in a report) so a human can verify.
- **Localization (v1):** station clocks synced to GNSS time well enough for time-difference-of-
  arrival between stations, station positions surveyed at deployment, and reports that show
  individuals/territories with an uncertainty estimate, not just a point.
- **Human verification workflow:** reports must separate "AI detection" from "expert-verified".
  Authorities will not accept unverified AI counts as the sole evidence for a while.
- **Remote health telemetry** at least daily, even if audio upload is limited.
- **Configurable recording schedules** (dawn chorus, nocturnal migration, continuous).
- **Open exports:** WAV/FLAC, CSV/JSON detections, Raven selection tables, and the FinBIF/laji.fi
  format.
- **Customer owns the data (walto, 2026-11-02):** contracts state the customer owns all audio,
  detections and reports. We process data only on their instructions (GDPR processor, DPA
  included), never reuse it for model training without opt-in, offer full export at any time in
  open formats, and delete on request or at contract end. The desktop licence lets a customer keep
  everything on their own machines, with the station uploading only health data to us.
- **Privacy:** outdoor recording can capture human speech, which is personal data under GDPR.
  Needed: a speech-detection filter that drops or masks speech before upload, a privacy notice
  sticker on each station, and a data processing agreement (DPA) for business customers.

---

## 5. EU certification and compliance

Target: CE marking for sale in Finland/EU. walto signs the EU Declaration of Conformity as the
manufacturer, so the technical file must exist before the first sale (including the first paid
pilot).

| Area | Legislation | What it means for us | Effort |
|---|---|---|---|
| **Radio, EMC, electrical safety** | Radio Equipment Directive **2014/53/EU (RED)** | The station contains 4G, GNSS (and maybe Bluetooth/Wi-Fi), so RED covers it. RED also absorbs EMC and safety (LVD) requirements. Use a **pre-certified 4G module** (e.g. Quectel/u-blox/Telit) and follow its integration guide; still test the whole product: EN 301 908-1/-13 (LTE), EN 303 413 (GNSS), EN 301 489-1/-19/-52 (EMC), EN 62368-1 (safety), EN 62311 or EN 50665 (RF exposure). | High. Budget **€8-20k (est.)** at a test lab (e.g. in Finland or Estonia) for the first product, less if module certificates are reused. |
| **Bluetooth / Wi-Fi for phone setup** | RED, EN 300 328 (2.4 GHz), EN 301 489-17 (EMC) | Adds two test standards. Using a pre-certified BLE/Wi-Fi module keeps it cheap. Pairing must not use a default password (EN 18031). | Low-medium |
| **Cybersecurity** | RED Delegated Regulation (EU) **2022/30**, harmonised standard **EN 18031-1/-2/-3**, mandatory since 1 Aug 2025 | An internet-connected device: no default passwords, secure updates, protection of network and personal data. Some EN 18031 options carry restrictions; if we hit one, a notified body is needed. | Medium. Design it in from day one (Edge software thread). |
| **Cyber Resilience Act** | Regulation **(EU) 2024/2847** | Vulnerability reporting obligations apply from **11 Sep 2026**, full requirements from **11 Dec 2027**. Our launch is likely around then, so plan for: SBOM, vulnerability handling process, security updates for the support period. | Medium, mostly process. |
| **Hazardous substances** | **RoHS 2011/65/EU**, **REACH** | Buy RoHS-compliant parts, collect supplier declarations, keep in technical file. | Low. |
| **Waste electronics** | **WEEE 2012/19/EU** | Register as producer in Finland's producer register (Pirkanmaa ELY / producer responsibility) or join a producer organization (e.g. SER-Tuottajayhteisö), crossed-out bin symbol on the product. | Low, yearly fee. |
| **Batteries** | **Battery Regulation (EU) 2023/1542** | Register as battery producer, join a battery producer organization, labelling (capacity, collection symbol, chemistry), removability/replaceability rules for portable batteries (from Feb 2027). Packs above 2 kWh are "industrial" with more obligations, so keep station packs below that. | Low-medium. |
| **Battery transport** | **UN 38.3**, ADR (road), IATA DGR (air, PI 965-967) | Lithium packs must have a UN 38.3 test summary. Buy cells/packs that already have one; a custom pack needs its own test (€3-8k est.). Shipping to customers by road is easier than air. | Medium if custom pack. |
| **General product safety** | **GPSR (EU) 2023/988** | Applies if sold to consumers (hobbyists): traceability, contact info on product, safety info in Finnish and Swedish. | Low, but another reason to launch B2B first. |
| **Ingress/environment** | Not a law, but a selling point | Claim IP66/IP67 (EN 60529) and operating temperature only after testing. Consultants will ask. | Medium. |
| **Data protection** | **GDPR**, Finnish Data Protection Act | We process audio that may contain speech. Privacy by design (section 4), DPA template, data hosted in the EU. | Medium. |
| **SIM / connectivity** | Operator terms | Use an EU IoT/M2M SIM with roaming across Finnish operators (Elisa, Telia, DNA) for coverage in remote areas. | Low. |

### 5a. Company form and liability

walto runs a **toiminimi** (sole trader). That is fine for development and pilots, but as the
manufacturer selling CE-marked electronics, a sole trader is **personally liable without limit**
under the Product Liability Act (tuotevastuulaki) and for warranty claims. A battery fire or a
failed regulatory survey could reach personal assets. Recommendation: **form an Oy (osakeyhtiö,
minimum share capital €0) before the first sale**, take **product liability and professional
liability insurance**, and register the Oy (not the toiminimi) as manufacturer for CE, WEEE and
batteries so registrations do not have to be moved later.

**Practical path:** design with pre-certified modules, do an EMC/radio **pre-compliance scan** on
the prototype (step 3), then full testing on the pilot hardware (step 4). Paid pilots before CE
are risky; free loans to research partners as "prototypes not for sale" are the usual route.

---

## 6. Business model and pricing

Principle (from walto): price follows quality; customers must be able to trust the product.
Recurring revenue is needed because every station uses 4G data and cloud compute every day.

### Model: sell hardware + subscription
Decision: **sell, no rental at launch.** Customers own the stations and pay a subscription for
4G data, cloud analysis, localization and reports. Billing is per *active month*, so seasonal
users (2-4 week surveys in spring and autumn) only pay while stations are deployed. Rental could be
revisited later if pilots show consultants want it.

| Tier | Who | Hardware | Subscription (incl. 4G data, cloud ID, storage) | Notes |
|---|---|---|---|---|
| **Kotipiha / Home** (phase 2) | Hobbyists | 1 station **€390-490** (est.) | **€6-10 / month** | Simplified station (maybe Wi-Fi or 4G), app, species lists, laji.fi sharing |
| **Pro station** (add-on) | Researchers, extending a kit | **€3,500-5,000** per station incl. solar (est., see below) | **€25-40 / station / month** while deployed | Full multi-mic, raw audio, exports, API |
| **Localization kit** (base product) | Consultants, researchers | 4 stations + solar panels + batteries + mounts + case: **see price problem below** | **€100-160 / month** for the kit while active | Individual counts/territory maps, report templates, verification tools, priority support |
| **Desktop licence** | Researchers who will not use the cloud | Any | **€300-600 / year** (est.) | Analysis runs on their computer; no audio leaves their control |

Subscription is billed only while stations are deployed ("active months"), which fits seasonal use.

### The price problem: €6-8k does not cover the parts

The hardware design (`docs/hardware.md`, PR #5) estimates **€1,450-2,650 per station** at
prototype quantities, plus **€750-1,500 per kit** for shared items (survey GNSS, calibrator).
A 4-station kit is therefore **€6,600-12,100 in parts alone**. The largest items are the LTO
winter battery and the storage.

Selling at €6-8k would lose money on every kit before labour, certification, warranty and support.
Small-volume professional electronics usually sell at **2.5-4x parts cost**. Options:

| Option | Kit price (4 stations) | What it means |
|---|---|---|
| **A. Price by real cost** | **€16,000-22,000** (est.) | Keeps the full design (4 mics, LTO, solar, 2 TB). Still competitive for consultants: one avoided field day costs a consultancy roughly €600-1,000 (est.), and a kit covering 2-3 surveys a season replaces many visits. Comparable professional array setups (4 high-end recorders + GPS sync + software) are in the €8-15k range without any 4G or service. |
| **B. Design to cost** | **€9,000-12,000** (est.) | Target parts **€700-900 per station**: cheaper battery (LiFePO4 for summer, LTO as winter add-on), 1 TB storage, fewer shared items, volume pricing. Requires changes in the hardware design during step 2. |
| **C. Both** | Launch at A, move to B | Pilots and first customers on the full design at price A; a cost-reduced v2 brings the price down. |

**Recommendation: C.** Quality and trust come first (walto's rule), the first customers are
professionals who value data over price, and a lower price can follow once real BOM and volume
are known. The €6-8k target is reachable only after cost reduction and at higher volume.

### Other running costs (est.)
- 4G data: with continuous recording, the hardware/edge plan uploads one reference channel in FLAC
  (about 8 GB/day, ~240 GB/month per station) plus manifests and clips; the full multichannel
  archive stays on the SD cards. 240 GB/month costs roughly €15-40/month per station on Finnish
  unlimited/IoT plans (est., verify with Elisa/Telia/DNA business pricing). A lossy codec (e.g.
  Opus at high bitrate, ~30 GB/month) would cut this a lot; whether that is acceptable for ID and
  legal use is being checked in the Edge/Cloud threads. Subscription prices above assume the
  cheaper case and must rise if lossless upload is the default.
- Cloud ID compute and storage: €2-8 per station per month (est.).
- **Classifier licence:** BirdNET's models are licensed CC BY-NC-SA, so commercial use needs a
  licence from the BirdNET team (Cornell / TU Chemnitz), or a model trained by us or licensed from
  the University of Helsinki group. Unknown cost; could be a per-station fee or a flat fee. Must be
  settled before pricing is final.
- Margin on subscription needs to fund support and model updates.

### Further revenue
- **Verification service:** a Finnish birder verifies detections for a consultant's report
  (per-hour or per-site fee). High value for regulatory reports.
- **Annual recalibration and service** of microphones.
- **Data partnerships** with research institutes (with customer consent only).

---

## 7. Support and warranty

- **Warranty:** 2 years on hardware (matches Wildlife Acoustics and EU consumer expectations);
  microphones and batteries as wear parts, 1 year. Clear exclusions for physical damage, but **not**
  for water ingress, since we claim an outdoor rating.
- **Advance replacement** for Pro/Survey customers: a failed station is replaced within 2 working
  days in Finland, so a survey season is not lost.
- **Support channels:** email and phone in Finnish, Swedish and English; in-app status with
  "send diagnostics" button; remote diagnosis via 4G is the main support tool.
- **Software support period:** security updates for at least 5 years after purchase (needed for
  the Cyber Resilience Act and for trust).
- **Documentation:** quick-start card in the case, short videos, deployment best-practice guide
  (height, orientation, avoid roads/streams), method description for consultants to cite in reports.
- **Field calibration:** a microphone self-test at boot and a yearly lab calibration option.
- **Spare parts** (mic modules, windscreens, battery packs) sold separately.

---

## 8. What "easy to use" must look like

The test: **a consultant who has never seen the kit deploys a station in under 10 minutes,
with gloves on, in snow, without a laptop.**

**Out of the box**
1. Hard case, pre-charged batteries, stations already registered to the customer's account and
   SIM already active. Nothing to configure at the desk.
2. One printed quick-start card with pictures, QR code to the app.

**At the site**
3. Strap or screw the station to a tree/pole (included strap and bracket).
4. Connect the battery and press one button. The LED shows: searching GPS/4G → OK (green).
5. Open the phone app; it pairs with the station over Bluetooth (QR code on the lid identifies it) and records location, a photo of the site and
   a note (or does it automatically from the station's GPS).
6. The app confirms "Recording, connected, battery estimate 26 days". Done.

**During the deployment**
7. Daily status visible in the web/app: map of stations, battery, storage, temperature, latest
   detections. Push/email alerts on problems.
8. Recording schedule and settings changeable remotely, no site visit needed.

**After**
9. Press "End deployment" in the app; pick up the station; put it back in the case.
10. Report ready: species list, counts/activity per station and per time, verification status,
    method text and data export. One click to PDF and to laji.fi.

Also: no SD card handling for the normal workflow (card is a backup only), no firmware updates by
hand, sensible defaults for Finnish seasons (spring migration, breeding, autumn, winter).

---

## 9. Go-to-market (outline)

1. **Pilot partners (step 4):** 1-2 consultancies and 1 research group, free or heavily discounted
   use in spring 2027 migration/breeding season in exchange for feedback and a reference.
   **Candidate: Luontopalvelut Flava Oy** (Helsinki, founded 2023). They do bird surveys from
   early-spring owl and grouse counts to autumn migration, for zoning, construction and permits
   across Finland, list wind and solar projects as references, and do golden eagle tracking and
   collision modelling. Localization of individual birds fits their work directly. walto makes
   the first contact; a one-page pilot proposal can be drafted for walto to review.
2. **Validation study:** compare kit results with point counts by experienced birders at the
   pilot sites. Publish the result; this is the main sales asset for regulatory buyers.
3. **Legal uses:** all three are in scope (wind-power YVA, Natura assessments, permit
   monitoring). Report templates for each; wind-power YVA has the most survey volume in Finland,
   so it gets the first template and pilot focus.
4. **Channels:** direct sales to consultancies, BirdLife Suomi and regional bird societies,
   Luke/SYKE/universities, trade fairs, later Nordic resellers (Sweden, Norway, Estonia).
5. **Expansion:** Sweden and Norway share most species and similar winter conditions; models and
   UI languages carry over.

---

## 10. Open questions for walto

Answered on 2026-11-02: see section 0. Still open:

1. **Kit price vs parts cost** (section 6): price by real cost (~€16-22k), redesign for cost
   (~€9-12k), or launch at the first and move to the second (recommended)?
2. Will you form an **Oy** before the first sale (section 5a)?

---

## Sources
- Song Meter Mini 2 prices and specs: https://nhbs.com/song-meter-mini-2-acoustic-recorder
- BirdWeather PUC price and specs: https://www.nhbs.com/birdweather-puc
- AudioMoth v1.2 price: https://groupgets.com/products/audiomoth-v1-2-0
- Finnish bird-sound classifier research (Lauha 2026, University of Helsinki):
  https://www.helsinki.fi/en/news/artificial-intelligence/artificial-intelligence-can-identify-bird-sounds-more-reliably
- Legislation referenced: Directive 2014/53/EU (RED), Delegated Regulation (EU) 2022/30,
  Regulation (EU) 2024/2847 (CRA), Directive 2011/65/EU (RoHS), Directive 2012/19/EU (WEEE),
  Regulation (EU) 2023/1542 (Batteries), Regulation (EU) 2023/988 (GPSR), GDPR (EU) 2016/679.
  Dates and standard numbers should be re-checked against EUR-Lex and the Official Journal lists
  of harmonised standards before the certification step.
