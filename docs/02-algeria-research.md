# 02 — Algeria: Infrastructure, Emergency Chain and Legal Context (research as of 2026-10-29)

Every claim carries a status label and a reference:

- **VERIFIED**: deployed or in force, with a source.
- **ANNOUNCED**: a plan or contract exists, but no source confirms it is in operation.
- **UNKNOWN**: no reliable public source was found.

References are listed at the end. Where sources disagree, the conflict is stated. Nothing here claims a partnership with, or access to, any government system.

> Research caveat: most legal references were checked through APS, Radio Algérie and reputable press, not on joradp.dz directly. Before quoting a legal article in the pitch, confirm the exact text on https://www.joradp.dz.

---

## 1. Key finding for our product

1. **Cameras exist and are growing, but they are watched by people, not by AI.**
   - Algeria has a legal national video-surveillance system run by the national police (DGSN) and the wilaya (province) authorities (VERIFIED).
   - It has large city deployments: 1,837 cameras operational in Algiers in 2024, and 387 in Boumerdès in 2026 (VERIFIED).
   - The East-West Highway central section was contracted in 2014 with CCTV and automatic incident detection (ANNOUNCED; current operation UNKNOWN).
   - No public source shows AI-based incident detection running on Algerian roads today.
2. **The emergency chain is fragmented.**
   - There are three separate numbers and services: 14 and 1021 for Civil Protection (Protection Civile), 17 and 1548 for the DGSN, and 1055 for the Gendarmerie (VERIFIED).
   - No public information exists on computer-aided dispatch, caller geolocation, response-time statistics or hospital-capacity visibility (UNKNOWN).
   - Our solution sits exactly in that gap.
3. **Connectivity is good but not universal.**
   - There are about 55.6 M mobile connections, and 4G carries 88.8% of usage. 5G launched on 3 December 2025 (VERIFIED).
   - Rural and road coverage gaps are officially acknowledged. Emergency roaming on the East-West Highway since May 2025 exists because of them (VERIFIED).
   - SMS and low-bandwidth fallback, as the thematic requires, is therefore justified.
4. **The legal framework is strict on video and data.**
   - Law 18-07, amended by Law 25-11 (July 2025), adds a data protection officer, impact assessments and breach notification.
   - The data protection authority's (ANPDP) video-surveillance rules (March 2026) say surveillance systems must not be connected to the internet.
   - The national government data centre was inaugurated in July 2026.
   - So the platform must be **deployable on-premises or in the national data centre, with no dependency on a foreign cloud**.

---

## 2. Road surveillance and traffic infrastructure

| # | Item | Status | Details | Ref |
|---|---|---|---|---|
| 1 | National video-surveillance system (Presidential Decree 15-228, Aug 2015) | VERIFIED | National centre under the Prime Minister, run by the DGSN. A wilaya centre under each wali. Stated purposes include **road traffic regulation** and crisis management. Covers "major roads" and public places. | R1, R2 |
| 2 | Algiers city surveillance | VERIFIED (partly) | **1,837 operational cameras** at the DGSN centre in Sidi M'Hamed (April 2024). A 5,592-camera extension is planned; its progress is UNKNOWN. An older figure of ~3,000 cameras (2015) conflicts with this. | R3, R4 |
| 3 | Boumerdès surveillance centre | VERIFIED | Opened July 2026. **387 cameras**, traffic management named as an explicit purpose. | R5 |
| 4 | Other wilaya centres or a national camera count | UNKNOWN | No consolidated public list. | — |
| 5 | East-West Highway ITS, central section (Chlef to Bordj Bou Arréridj, ~420 km) | ANNOUNCED (2014 contract) | Cosider–Indra–Ericsson, DA 45.68 bn. Includes **500 CCTV cameras**, **12–20 automatic incident-detection cameras** (sources differ), 500 SOS call posts, 446 km of fibre, 30 variable-message signs, 23 weather stations and 6 operations centres. **Current operation is unconfirmed.** | R6, R7, R8, R9 |
| 6 | Highway tolls | VERIFIED as not in service | ADA (the highway operator) said in January 2026 that tolling is "not on the agenda". | R10, R11 |
| 7 | Gendarmerie highway units | VERIFIED (older sources) | Units every ~40–60 km and mobile radars. No fixed automated speed-camera network found. | R12–R15 |
| 8 | Algiers smart traffic lights | ANNOUNCED / stalled | Plan for 500 intersections controlled from a centre in Kouba. Halted in 2020; a 22-intersection pilot ran in 2024. | R16, R17, R3 |
| 9 | Huawei "Safe City" | UNKNOWN (allegations only) | Media allegations only; Huawei Algeria denies them. **Do not present this as a fact.** | R18, R19 |

**Integration implication.** Our platform is an **analytics and coordination layer**. It reads existing camera streams (RTSP/ONVIF) inside wilaya or DGSN control rooms and on the East-West Highway fibre network. It replaces no camera and no control room.

---

## 3. Emergency response chain

| Number | Service | Status | Ref |
|---|---|---|---|
| 14, 1021 | Civil Protection (DGPC) | VERIFIED | R20, R21 |
| 17, 1548 | DGSN, national police (urban) | VERIFIED | R20, R22 |
| 1055 | Gendarmerie (roads outside cities) | VERIFIED | R20, R22 |
| 115 "SAMU" | Not confirmed by any Algerian official source | UNKNOWN | — |
| 112 | No Algerian announcement found | UNKNOWN | — |

- **Emergency roaming on the East-West Highway (VERIFIED, May 2025).** Emergency calls go through any available operator when the caller's own network has no coverage. Extension to other roads is ANNOUNCED. (R20)
- **Civil Protection is the main pre-hospital responder at road accidents.**
  - It has a directorate in each of the 58 wilayas, plus motorcycle rapid-response, heavy-extraction and air units (R21).
  - Summer 2025: 47,631 road-accident interventions, 700 deaths and 34,175 injured (R23).
  - A typical 2025 week: ~40 deaths and ~1,700 injured (R24).
  - **No published response-time statistics.**
- **Citizen first-aid training (VERIFIED).** The "One rescuer in every family" programme ("Un secouriste dans chaque famille") has trained more than 170,000 citizens (R25). This is a ready-made pool of bystander first responders.
- **Digital tools in use:**
  - Gendarmerie **Tariki** road-information portal and app (VERIFIED, in use January 2026) (R26, R27).
  - DGSN **Allo Chorta** reporting app (VERIFIED in 2020; current status UNKNOWN) (R28).
  - **No Civil Protection citizen-alert app found.**
- **SAMU (emergency medical service).**
  - It exists operationally: it evacuates victims alongside Civil Protection (R29).
  - The national SAMU body and its call-regulation process are UNKNOWN (R30).
- **Hospitals.**
  - The inter-hospital transfer digitalisation platform was ANNOUNCED in December 2025 (R31).
  - Electronic medical record (DME) rollout: "final phase" meeting held in September 2026 (VERIFIED, R32).
  - Emergency departments were digitised first, keyed by national ID number (R33).
  - **No bed-availability or emergency-capacity system found.**

**Unknowns that become our value proposition:** computer-aided dispatch, caller geolocation, one shared incident picture across Civil Protection, DGSN, Gendarmerie and SAMU, hospital capacity visibility, and response-time measurement.

---

## 4. Road accident statistics (always cite the source; agencies count differently)

| Source | Scope | 2025 | Ref |
|---|---|---|---|
| DNSR | National | 26,976 accidents · **3,838 deaths** · 37,020 injured (+2.68% / +2.62% / +4.9% vs 2024) | R34, R35 |
| DGSN | Urban areas only | 19,241 accidents · 842 deaths · 23,516 injured | R36 |
| Civil Protection | Own interventions, summer 2025 | 700 deaths · 34,175 injured | R23 |
| Civil Protection | Own interventions, 2023 | 63,697 accidents · 1,893 deaths · 79,771 injured | R37 |

- Human factor: **more than 96%** of accidents (DNSR) (R34).
- Summer is the deadliest season (R38).
- Mass-casualty bus crashes in 2025–2026 include El Harrach (18 dead) and Boumerdès, 31 July 2026 (25 dead, 44 injured) (R24, R39).
- A Civil Protection spokesperson describes multi-fatality crashes as a "new phenomenon" (R40). **This justifies multi-victim triage support.**
- Per-road-type breakdown (highway vs national road): UNKNOWN at national level.

> **Do NOT use** "155 emergency departments", "141" or "6 million ER visits". Those figures are **Moroccan**, not Algerian.

---

## 5. Connectivity

| Item | Status | Ref |
|---|---|---|
| ~55.6 M mobile connections (~117% of population); 94.5% are 3G, 4G or 5G | VERIFIED | R41 |
| 4G carries 88.8% of usage. Operator shares: Mobilis 42.4%, Djezzy 31.6%, Ooredoo 25.9% | VERIFIED | R42 |
| 5G commercial launch on 3 December 2025, 6-year rollout | VERIFIED | R43, R44 |
| Rural and road coverage gaps; 4,500 extra zones targeted by 2027; ARPCE (telecom regulator) tender, September 2026 | VERIFIED | R45, R46 |
| Business SMS (A2P) through operators and aggregators, ~5–8 DZD per SMS; two-way SMS limited on standard bulk routes | VERIFIED (commercial sources) | R47, R48 |
| eCall regulation | UNKNOWN | — |

---

## 6. Governance, digitalisation, legal

| Item | Status | Ref |
|---|---|---|
| DNSR (national road-safety delegation), Executive Decree 19-303 (Nov 2019), under the Interior Ministry | VERIFIED | R49 |
| New road code: Law 26-09 of 2 May 2026 (Official Journal no. 36, 20 May 2026). Camera-based enforcement provisions: UNKNOWN | VERIFIED | R50, R51 |
| High Commission for Digitalization; National Digital Transformation Strategy (May 2025) | VERIFIED | R52, R53 |
| National data centre (Mohammadia and Blida, active-active), inaugurated July 2026 | VERIFIED | R54, R55 |
| Law 18-07 on personal data (applicable since Aug 2023), amended by **Law 25-11 (24 July 2025)**: DPO, records of processing, impact assessments, breach notification | VERIFIED | R56–R59 |
| ANPDP Deliberation no. 02 (4 Mar 2026), workplace video surveillance: wali authorisation; **systems not connected to the internet**; restricted access; retention ≤ 1 year (reported) | VERIFIED | R60, R61 |
| Security and public-order exemptions in Law 18-07 | UNKNOWN (check the text) | — |
| Cybersecurity: Presidential Decree 20-05; National Cybersecurity Strategy 2025–2029 (Mar 2026); Presidential Decree 26-07 (Jan 2026) requires a cybersecurity unit in every public entity | VERIFIED | R62–R65 |

**Design consequences**

- On-premises or national-data-centre deployment. No foreign cloud for video or personal data.
- Video stays on a closed network. Only alert metadata crosses networks, through controlled gateways.
- Data minimisation:
  - Keep evidence clips, not continuous recordings.
  - Retention policy configurable, ≤ 1 year by default.
  - Option to blur faces and licence plates in exported evidence.
- Role-based access control, an append-only audit log, a records-of-processing export for the DPO, and evidence integrity hashes.

---

## References

- R1 https://www.algerie360.com/lorganisation-et-le-fonctionnement-du-systeme-national-de-videosurveillance-reglementes-par-un-decret-presidentiel/
- R2 https://www.algerie360.com/a-compter-du-22-aout-la-videosurveillance-entre-les-mains-de-la-police/
- R3 https://algerie-eco.com/2024/04/06/alger-un-projet-dextension-du-systeme-de-videosurveillance-avec-5-592-cameras/
- R4 https://www.algerie360.com/la-dgsn-deploiera-5-000-cameras-a-alger/
- R5 https://www.dzair-tube.dz/en/algeria-opens-video-surveillance-centre-in-boumerdes-to-strengthen-public-security/
- R6 https://www.algerie360.com/autoroute-est-ouest-realisation-des-equipements-du-lot-centre-le-suivi-des-travaux-confie-a-un-groupement-sud-coreen/
- R7 https://www.indracompany.com/en/node/47958
- R8 https://www.idom.com/en/?p=14979
- R9 https://www.indracompany.com/en/node/74265
- R10 https://news.radioalgerie.dz/fr/node/55507
- R11 https://news.radioalgerie.dz/fr/node/77422
- R12 https://www.echoroukonline.com/850-gendarmes-pour-securiser-lautoroute-est-ouest
- R13 https://www.algerie360.com/autoroute-est-ouest-sept-unites-de-la-gendarmerie-bientot-deployees-dans-louest-du-pays/
- R14 https://www.algerie360.com/la-gendarmerie-met-en-service-des-radars-high-tech-les-chauffards-recidivistes-dans-une-black-list/
- R15 https://www.algerie360.com/plus-de-3000-morts-en-huit-mois-sur-nos-routes-la-dgsn-compte-acquerir-100-nouveaux-radars/
- R16 https://www.algerie360.com/lancement-projet-de-systeme-de-regulation-trafic-routier-feux-tricolores-intelligents-a-alger/
- R17 https://algerie-eco.com/2020/01/30/systeme-regulation-trafic-routier-dalger-projet-larret/
- R18 https://www.tsa-algerie.com/accuse-daider-le-pouvoir-a-espionner-lopposition-huawei-algerie-reagit/
- R19 https://www.tsa-algerie.com/lalgerie-utilise-des-outils-de-surveillance-russe-et-chinois/
- R20 https://news.radioalgerie.dz/fr/node/65354
- R21 https://en.wikipedia.org/wiki/Algerian_Civil_Defence
- R22 https://www.algerie360.com/ils-sont-mis-a-la-disposition-des-citoyens-par-la-gn-et-la-dgsn-10-55-et-15-48-ces-numeros-qui-sauvent/
- R23 https://www.horizons.dz/2025/10/horizons-dz-societe-saison-estivale-2025-700-morts-dans-des-accidents-de-la-route/
- R24 https://lavoiedalgerie.dz/accidents-de-la-circulation-chiffres-alarmants-drames-humains-et-reponse-de-letat/2025/28/00/
- R25 https://fr.allafrica.com/stories/202508020038.html
- R26 https://www.algerie360.com/gendarmerie-nationale-un-nouveau-site-pour-sinformer-de-letat-des-routes/
- R27 https://news.radioalgerie.dz/fr/node/77953
- R28 https://algerie-eco.com/?p=104093
- R29 https://www.lesoirdalgerie.com/actualites/un-mort-et-52-blesses-lors-d-un-accident-d-un-bus-transportant-des-supporteurs-de-l-usm-annaba-112760
- R30 https://www.algerie360.com/hasbellaoui-creation-dun-etablissement-national-de-samu/
- R31 https://www.wearetech.africa/fr/fils/actualites/tech/algerie-le-ministere-de-la-sante-lance-la-numerisation-du-processus-de-transfert-des-patients
- R32 https://www.aps.dz/fr/algerie/sante-et-environnement/mtsp0upk-ait-messaoudene-preside-une-rencontre-sur-la-generalisation-de-la-numerisation-et-du-dossier-medical-electronique-dans-les-etablissements-de-sante
- R33 https://www.algerie360.com/fini-la-paperasse-dans-les-hopitaux-algeriens-le-dossier-medical-passe-au-tout-numerique-des-cet-ete/
- R34 https://news.radioalgerie.dz/fr/node/80144
- R35 https://atlas-mag.net/fr/articles/hausse-des-accidents-sur-les-routes-algeriennes-en-2025
- R36 https://www.aps.dz/fr/algerie/societe/mnovpe8k-842-deces-et-plus-de-23-000-blesses-en-zones-urbaines-en-2025
- R37 https://atlas-mag.net/fr/articles/plus-de-1-800-deces-sur-les-routes-algeriennes-en-2023
- R38 https://fr.allafrica.com/stories/202410090138.html
- R39 https://www.blick.ch/fr/monde/accident-en-algerie-un-autocar-tombe-dans-un-ravin-25-morts-et-44-blesses-id22148965.html
- R40 https://www.tsa-algerie.com/accidents-de-la-route-il-y-a-un-phenomene-nouveau-en-algerie/
- R41 https://datareportal.com/reports/digital-2026-algeria
- R42 https://telecomlead.com/5g/algeria-5g-performance-mobilis-djezzy-ooredoo-compete-on-speed-reliability-and-market-share-125569
- R43 https://www.tsa-algerie.com/lancement-officiel-de-la-5g-six-ans-pour-couvrir-toute-lalgerie/
- R44 https://www.ecofinagency.com/news-digital/2711-50886-algeria-awards-5g-licenses-to-three-operators-for-nearly-492-million
- R45 https://osiris.sn/couverture-reseau-l-algerie-cible-4500-zones-supplementaires-d-ici-2027.html
- R46 https://www.telecomreviewafrica.com/?p=29185
- R47 https://www.sent.dm/resources/dz-sms-guidance
- R48 https://www.budgetsms.net/sms-gateway-pricing/dz/algeria/
- R49 https://algerie-eco.com/2019/11/30/ministere-de-linterieur-creation-de-la-delegation-nationale-de-la-securite-routiere
- R50 https://news.radioalgerie.dz/fr/node/86685
- R51 https://www.tsa-algerie.com/algerie-le-nouveau-code-de-la-route-adopte-de-lourdes-peines-prevues/
- R52 https://www.aps.dz/fr/tags/haut-commissariat-numerisation
- R53 https://news.radioalgerie.dz/fr/node/64550
- R54 https://techafricanews.com/2026/07/07/algeria-launches-national-digital-services-center-to-strengthen-digital-sovereignty/
- R55 https://algerie-eco.com/2024/04/21/realisation-dun-data-center-signature-dun-accord-avec-huawei-consortium/
- R56 https://www.upgrowth.dz/journal-officiel/loi-18-07-protection-donnees-personnelles
- R57 https://www.gide.com/en/news-insights/protection-of-personal-data-focus-on-algerian-regulations/
- R58 https://natlex.ilo.org/dyn/natlex2/r/natlex/fe/details?p3_isn=107253
- R59 https://cms.law/en/int/expert-guides/cms-expert-guide-to-data-protection-and-cyber-security-laws/algeria2
- R60 https://www.tsa-algerie.com/cameras-de-surveillance-lalgerie-impose-de-nouvelles-regles/
- R61 https://www.algerie360.com/anpdp-de-nouvelles-regles-pour-lutilisation-des-systemes-de-videosurveillance-sur-les-lieux-de-travail/
- R62 https://digitalpolicyalert.org/change/12309-presidential-decree-no-20-05-on-establishing-a-national-framework-for-the-security-of-information-systems
- R63 https://www.dzair-tube.dz/en/algeria-charts-its-digital-sovereignty-ministry-of-national-defence-unveils-2025-2029-national-cybersecurity-strategy/
- R64 https://www.digitalbusiness.africa/algerie-une-strategie-nationale-2025-2029-pour-renforcer-la-cybersecurite-et-proteger-la-souverainete-numerique/
- R65 https://fr.apanews.net/security/algerie-un-cadre-reglementaire-renforce-pour-la-cybersecurite-du-secteur-public/
