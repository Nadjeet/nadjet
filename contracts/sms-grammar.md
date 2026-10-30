# SMS message grammar (FR-NTF-002, FR-NTF-005)

Single source of truth for every SMS Nadjet sends or accepts. Implemented in
`services/api/src/nadjet_api/notifications/grammar.py`; keep both in sync.
Every outbound message is **one SMS: ≤ 160 GSM-7 septets, Latin text only** (extension
characters `^{}\[~]|€` cost two). Codes are the 3-character incident short code (Crockford base32,
e.g. `7F3`), case-insensitive on input.

## Outbound

| Message | Meaning |
|---|---|
| `ACC\|P<n>\|<lat>,<lon>\|<road> PK<km>\|<k>V\|<code>` | Alert to a responder or hospital. Example: `ACC\|P1\|36.64800,3.32900\|A1 PK42\|2V\|7F3`. The road/PK part and the vehicle count are omitted when unknown. |
| `Nadjet: <code> <status> recorded` | Confirmation of a status, triage or hospital reply. |
| `Nadjet: report received, code <code>` | Confirmation of a citizen `ACCIDENT` report. |
| `Nadjet: OK\|ER\|OS\|TR\|AH\|CL <code> ; T <code> R# Y# G# B# ; H <code> READY\|DIVERT` | Help, sent for a message outside the grammar (E-08). |
| `Nadjet: not authorised for this incident. The operator was notified.` | Sender is not assigned to the incident (E-09). |

## Inbound

| Message | Sender | Effect |
|---|---|---|
| `OK <code>` | assigned responder / hospital, operator roles | status `acknowledged` |
| `ER <code>` | idem | `en_route` |
| `OS <code>` | idem | `on_scene` |
| `TR <code>` | idem | `transporting` |
| `AH <code>` | idem | `at_hospital` |
| `CL <code>` | idem | `closed` |
| `T <code> R# Y# G# B#` | assigned responder, operator roles | `#` casualties per triage tag (red, yellow, green, black); 1 to 4 letters, each at most once, at most 99 in total; priority recomputed |
| `H <code> READY` / `H <code> DIVERT` | assigned hospital | facility Ready / Divert |
| `ACCIDENT <lat>,<lon> [P<n>] [C<0\|1>] [text]` | anyone | unverified citizen incident at the coordinates (decimal degrees with a `.`, e.g. `36.648,3.329`; `12,5 km` is text); `P` = people, `C1` = trapped; merged with a nearby open incident (FR-INC-002) |
| `ACCIDENT <text>` | anyone | unverified incident without position, flagged `callback_needed` |

Illegal status moves, unknown codes and bad syntax never change state and get a short reply.
Senders are matched by `users.phone` (Algerian `05…` and `+2135…` are the same number).
