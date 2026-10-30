# 01 — Thematic 1 Analysis: "Road accidents: improving emergency response"

Source: the SolveX 3.0 problem sheet (HIS University / No Limit Club). Only Thematic 1 is analysed here; Thematic 2 (hypertension) is out of scope.

## 1. What the thematic actually says (faithful English rendering)

**Problem.** Road accidents are emergencies where every minute affects patient care. The first steps of a response can be held back by missing information at the moment of intervention. Those steps are:

1. locating the accident;
2. assessing its severity;
3. transmitting the information;
4. directing the victims to an appropriate health facility.

**Stake.** Information must reach responders faster and more reliably, so that coordination improves between:

- the accident scene,
- the intervention teams,
- the health facilities.

**Analysis.** The goal is a faster and more reliable emergency response, using data such as:

- **geolocation**,
- **information about the accident**,
- **available vital signs**.

**Suggested solution shape.** A technology that:

- **automatically transmits** essential information to intervention services;
- gives a **first assessment** of the situation and **decision support**;
- works as a **decision-support layer that complements existing systems**;
- can adapt to **connectivity constraints**, using **low-bandwidth or SMS** communication.

**Why the organisers chose it (their scoring criteria):**

- **Highest global score: 85.4 / 100.**
- **High impact.** A shorter response time directly improves victim care.
- **Automatable data.** Geolocation, accident information and some medical data can be collected without adding manual steps.
- **Technological feasibility.** A prototype can be built on **smartphones and equipment that already exist**, without depending on complex digital hospital infrastructure.
- **Fit with the Algerian context.** It works even where medical digitalisation is limited.
- **Strong hackathon relevance.** The journey **accident → alert → assessment → orientation** makes a concrete demo that is easy to understand.

## 2. What the jury will likely evaluate

These are inferred from the sheet's own criteria:

| Criterion (from the sheet) | What it means for us |
|---|---|
| Accident → alert → assessment → orientation journey | The demo must show **all four steps end-to-end**, not only detection. |
| Faster, more reliable information transmission | Measure and display time-to-alert and time-to-acknowledge. Make delivery reliable (retries, multi-channel). |
| Geolocation, accident info, vital signs | Every incident record has exact coordinates, road and kilometre point, type, severity, evidence and, once responders arrive, victim triage and vital signs. |
| First assessment and decision support | Severity and priority scoring, a recommended responding unit and hospital, a mass-casualty flag. |
| Complements existing systems | Do **not** replace the emergency numbers 14, 17 and 1055 or the control rooms. Plug into them using a standard alert format (CAP 1.2). |
| Low connectivity, SMS | SMS fallback for alerts **and** for responder acknowledgements and triage reports. |
| Uses smartphones and existing equipment | Use existing CCTV cameras and the responders' smartphones. No new hardware. |
| Algerian context | Arabic and French, the real agencies (Civil Protection, national police, Gendarmerie, SAMU), Algerian roads on the map, data-protection law. |

## 3. Challenging our initial idea

Our initial vision is a camera-AI platform that detects accidents and notifies authorities. It is a strong **differentiator**, but on its own it **only covers step 1 and part of step 2** of the thematic. The gaps:

1. **Coverage gap.** Most of the network has no cameras. Only city centres and planned highway sections do (see `02-algeria-research.md`). A camera-only system misses most rural and national-road crashes. Those are exactly where response is slowest.
2. **The thematic is about the response chain, not detection.** It explicitly asks for:
   - **severity assessment**,
   - **transmission to intervention teams**,
   - **orientation to an adapted health facility**,
   - **vital signs**.

   Cameras cannot measure vital signs. Responders on the scene can.
3. **Connectivity and SMS** are explicit requirements. A video dashboard alone does not address them.
4. **"Complementary to existing systems"** means the jury wants interoperability, not a parallel silo.

### Recommendation: reframe the product

> **An incident coordination platform for road emergencies, with AI video detection as its fastest sensor.**

- **Sensor layer (multi-source).** The flagship is CCTV accident detection. A second source is a **lightweight citizen/bystander report** (web and SMS) for roads without cameras. A third is a manual entry by the operator, for example from a 14/1055 call.
- **Assessment layer.** Merge reports about the same event into one incident. Compute severity and priority. A human operator verifies.
- **Coordination layer.**
  - Recommend and dispatch the nearest capable unit (by real road ETA).
  - Pre-alert the most appropriate hospital.
  - Track the response through each status.
  - Collect on-scene triage and vital signs from responders, including over SMS.
- **Interoperability layer.** CAP 1.2 alerts and SMS-compact payloads.

This keeps the camera-AI idea at the centre, which is the impressive and technically hard part. It also answers **every bullet of the thematic**, which a camera-only solution cannot. The citizen-report and responder-triage pieces are cheap to build (forms plus an SMS parser), so the extra scope is small relative to the coverage it adds.

### What we deliberately do NOT do

- No wearable or medical sensors. Vital signs are entered by responders using a structured triage form, which is realistic for Algerian field conditions.
- No replacement of 14, 17 or 1055 and no new emergency number.
- No claim to integrate with real government systems during the hackathon. We demonstrate **integration-ready interfaces** (RTSP/ONVIF ingest, CAP 1.2 output, SMS gateway).
- No automated enforcement such as speeding fines or plate reading. It is out of scope, legally sensitive, and unrelated to the emergency response.
