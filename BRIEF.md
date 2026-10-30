# Nadjet (نجاة) — Creative Brief for Design and Film

This brief is for the **designer** and the **filmmaker**. It contains no technical knowledge requirements. The full requirements are in [`PRD.md`](PRD.md), but you don't need to read it to do your part.

---

## 1. Nadjet in one sentence

**Nadjet spots road crashes automatically on Algeria's existing cameras, collects reports from citizens everywhere else, and coordinates the whole rescue: the right team, the right hospital, alerts by app and by SMS, even without internet.**

## 2. The name

- **Nadjet**, in Arabic **نجاة**: *survival, being saved*.
- It is the outcome the product exists for. The tone is **hope and calm competence**, not fear.
- The Latin and Arabic forms must both work, in logo and in UI.

---

## 3. The story: problem → solution

### The problem

These are verified facts, safe to use in film and slides:

- Road crashes killed **3,838 people in Algeria in 2025**. That is more than 10 per day (national road-safety delegation, DNSR).
- After a crash, minutes are lost:
  - nobody knows exactly **where** it happened or **how bad** it is;
  - information passes slowly between **three separate emergency services**: Civil Protection (14), Police (17) and Gendarmerie (1055);
  - hospitals often learn about the victims **only when the ambulance arrives**.
- Algeria already has thousands of road cameras: **1,837 in Algiers** and **387 in Boumerdès**. **People** watch them, and no one can watch every screen.
- Mass-casualty crashes happen, for example a bus crash in Boumerdès on 31 July 2026 (25 dead, 44 injured).

### The solution, as 6 simple beats

1. **Detect.** A camera's AI notices a crash. Or a witness taps one button on their phone, or sends one SMS.
2. **Verify.** A human operator sees the short video clip and confirms. **The AI never sends help on its own.**
3. **Decide.** Nadjet suggests the nearest rescue team and the best-suited hospital, ranked by real driving time.
4. **Alert.** Responders get a notification **and an SMS**. SMS works even with no mobile internet.
5. **Respond.** The responder texts back "OK". On the scene, they send the victims' condition from their phone.
6. **Prepare.** The hospital sees who is coming and when, before the ambulance arrives. It answers "Ready" or "Full".

**What about roads without cameras** (most of Algeria)? A citizen taps "Report a crash". If they have no internet, their phone writes an SMS with the **exact GPS position** in it, ready to send. After that, the rescue chain is exactly the same.

---

## 4. Who uses Nadjet

| Person | Where they are | What they feel | What they need from the screen |
|---|---|---|---|
| **Control-room operator** | Dark room, wall of screens, phone ringing | Overloaded, afraid of missing something | Calm, clear priorities; one obvious next action |
| **Responder** (Civil Protection, Gendarmerie, SAMU) | In a moving vehicle or at the crash scene, gloves, sun, bad signal | Urgency, physical stress | Huge buttons, one tap per action, readable in sunlight, works with SMS |
| **Hospital emergency staff** | Busy emergency room | Interrupted all the time | A glanceable "who's coming, how bad, when" card |
| **Citizen / witness** | Roadside, shocked | Panic | One giant button, no sign-up, no reading |
| **Analyst / supervisor** | Office | Needs evidence to act | Clear charts: response times, dangerous road sections |
| **Jury / audience** | Hackathon hall | Sceptical | Proof it's real; something they can try themselves |

---

## 5. For the designer

### Screens to design (4 surfaces)

1. **Operator console** (large desktop screen, dark theme):
   - map of Algeria with cameras, incidents (by priority), rescue units, hospitals and routes;
   - incident queue sorted by urgency;
   - **incident detail**: video clip, *why* the AI flagged it (simple reasons), priority P1–P4, the suggested team and hospital, one **Confirm** button and one **Reject** button;
   - camera wall: 4+ live cameras with AI boxes drawn on the vehicles;
   - KPI page (response times) and a page showing the AI's measured accuracy.
2. **Responder phone app**:
   - my incidents;
   - incident: map/route, photo/clip, status buttons (*On my way* → *On scene* → *Transporting* → *At hospital* → *Closed*);
   - triage form per victim: colour tag red / yellow / green / black, conscious?, breathing, pulse;
   - offline state: a clear "Send by SMS instead" path.
3. **Hospital view** (tablet): incoming patients, severity, ETA countdown, **Ready / Full** buttons.
4. **Public pages** (phone):
   - **"Report a crash"**: a single giant button, then a confirmation;
   - **"Try it"**: upload a video or turn your phone into a camera, then watch the AI result;
   - privacy notice.

### Design constraints (must)

- **Three languages:** Arabic (right-to-left layout), French and English. Every screen must work mirrored.
- **Priority is never shown by colour alone.** Always pair colour with a label or icon (P1–P4) for colour-blind users and bad screens.
- **Accessible contrast** (WCAG 2.2 AA).
- **Responder app:** every action in at most 2 taps; usable on a 5-inch phone; readable outdoors.
- **Operator console:** dark mode first, low glare, urgent items stand out without flashing chaos.
- **AI honesty in the UI:**
  - every AI result shows *why* (the reasons) and *how sure* it is;
  - uncertain results look uncertain;
  - "simulated" data, such as the demo hospitals, is labelled as simulated.
- **Map attribution** "© OpenStreetMap contributors" stays visible.

### Brand direction (proposal, open for you to change)

- **Mood:** calm, trustworthy, governmental but modern. Think "rescue service", not "startup gadget".
- **Colour ideas:**
  - deep night blue or charcoal for the console;
  - one warm emergency accent, used sparingly;
  - a distinct, separate scale for priorities P1–P4.
- **Logo:** the Latin "Nadjet" and the Arabic "نجاة", together or interchangeable.
- **Iconography:** simple, high-contrast, readable at small sizes.

### Deliverables we'd love

- Logo (Latin + Arabic), colour palette, typography (one Latin and one Arabic font that pair well).
- Mockups for the key screens above, desktop console plus phone screens.
- A one-page visual style sheet the developers can follow.
- A QR-code poster: "Report a crash" and "Try Nadjet".

---

## 6. For the filmmaker

### Pitch film (suggested 60–90 s)

| Beat | Picture | Message |
|---|---|---|
| 1. Hook | Road at night, a crash happens off-screen (sound only), a phone lying on the asphalt | "Every day in Algeria, more than 10 people die on the roads." |
| 2. The gap | Control room, an operator looking at dozens of screens; a phone ringing; three different emergency numbers | "The cameras are already there. But no one can watch them all." |
| 3. Nadjet | Screen: a red box appears around two cars, an alert pops up with the clip | "Nadjet sees it in seconds." |
| 4. Human decides | Operator clicks **Confirm** | "A human always decides." |
| 5. Rescue moves | A responder's phone vibrates with an SMS; they reply "OK" | "The team is alerted, even without internet." |
| 6. Hospital ready | Emergency staff look at a tablet: "3 patients, 1 critical, arriving in 12 min" | "The hospital is ready before the ambulance arrives." |
| 7. Everywhere | A witness on a dark rural road taps one button | "Where there's no camera, every citizen becomes one." |
| 8. Close | Logo **Nadjet — نجاة** | "Because every minute is a life." |

### Live-demo moments to film (backup recording and highlights)

- The live camera wall with AI boxes following cars.
- The crash clip, then the incident appearing on the map with its reasons.
- **A jury member receiving the real SMS on their own phone.**
- **Someone from the audience scanning the QR code and their phone appearing on the camera wall.**
- The hospital tablet updating.
- The "honesty" page: the AI's measured accuracy, including its mistakes.

### Practical notes

- Record a **full clean run of the real demo** before the event. It is our safety net if the network fails.
- Screen content must be **real captures** of the working product. No mocked-up "fake AI" screens presented as real.
- Any re-enacted crash scenes must be clearly staged (no real victims), and should avoid identifiable licence plates and faces.

---

## 7. What we may and may not say

**We can say:**

- "Nadjet detects crashes on video using real AI, and we show its accuracy honestly."
- "It works with Algeria's existing cameras and doesn't need new hardware."
- "It's ready to connect to existing systems, using international emergency-alert standards."
- "It runs on Algerian servers and respects Algeria's data-protection law."

**We must NOT say:**

- That Nadjet is already **connected to** the police, Civil Protection or hospitals. Say "ready to connect", never "connected".
- That the AI is **perfect** or never wrong. It can miss crashes at night, in bad image quality, or when something hides the crash. That is why humans and citizen reports are part of the system.
- That the demo videos were filmed in Algeria. They are public research videos, shown on virtual cameras placed on real Algerian roads.
- Any statistic that is not in the verified list above. Ask the team first.

---

## 8. Open questions for you

1. Logo: Arabic and Latin side by side, or two versions?
2. Light theme for the public pages and the hospital view, or dark everywhere?
3. Film language: Arabic voice-over with French subtitles, or another mix?
4. Do we need a clickable prototype before development starts (PRD Q-08)?
