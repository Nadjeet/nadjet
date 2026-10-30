"""SMS message grammar (FR-NTF-002, FR-NTF-005; spec in ``contracts/sms-grammar.md``). Pure."""

import re
from dataclasses import dataclass
from enum import StrEnum

from nadjet_api.incidents.lifecycle import IncidentStatus

SMS_MAX_CHARS = 160

# GSM 03.38 basic set. Extension characters ({}[]~^|\€ and form feed) cost two septets.
_GSM7_BASIC = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM7_EXTENSION = frozenset("^{}\\[~]|€\f")


def gsm7_length(text: str) -> int | None:
    """Septets needed for ``text``, or ``None`` if it has a character outside GSM-7."""
    total = 0
    for char in text:
        if char in _GSM7_BASIC:
            total += 1
        elif char in _GSM7_EXTENSION:
            total += 2
        else:
            return None
    return total


def fits_sms(text: str) -> bool:
    length = gsm7_length(text)
    return length is not None and length <= SMS_MAX_CHARS


class MessageTooLongError(ValueError):
    """The message is not GSM-7 or exceeds one SMS segment."""


def ensure_sms(text: str) -> str:
    if not fits_sms(text):
        raise MessageTooLongError(f"not a single GSM-7 SMS: {text!r}")
    return text


# ---------------------------------------------------------------- outbound


def _ascii(value: str) -> str:
    """Latin-only GSM-7 text without the grammar separator."""
    latin = value.replace("|", "/").encode("ascii", "ignore").decode()
    return "".join(c for c in latin if c in _GSM7_BASIC).strip()


def format_alert(
    *,
    kind: str,
    priority: int,
    lat: float,
    lon: float,
    road: str | None,
    pk_km: float | None,
    vehicles: int | None,
    short_code: str,
    eta_min: int | None = None,
) -> str:
    """``ACC|P1|36.64800,3.32900|A1 PK42|2V|7F3`` (FR-NTF-002); optional fields are omitted.

    A hospital pre-alert uses kind ``PRE`` and adds the ambulance ETA: ``...|2V|E12|7F3``.
    """
    parts = [kind, f"P{priority}", f"{lat:.5f},{lon:.5f}"]
    where = _ascii(road or "")
    if where and pk_km is not None:
        where = f"{where} PK{pk_km:g}"
    if where:
        parts.append(where)
    if vehicles:
        parts.append(f"{vehicles}V")
    if eta_min is not None:
        parts.append(f"E{eta_min}")
    parts.append(short_code)
    return ensure_sms("|".join(parts))


def help_message() -> str:
    return "Nadjet: OK|ER|OS|TR|AH|CL <code> ; T <code> R# Y# G# B# ; H <code> READY|DIVERT"


# ---------------------------------------------------------------- inbound

STATUS_CODES: dict[str, IncidentStatus] = {
    "OK": IncidentStatus.ACKNOWLEDGED,
    "ER": IncidentStatus.EN_ROUTE,
    "OS": IncidentStatus.ON_SCENE,
    "TR": IncidentStatus.TRANSPORTING,
    "AH": IncidentStatus.AT_HOSPITAL,
    "CL": IncidentStatus.CLOSED,
}
TRIAGE_LETTERS = {"R": "red", "Y": "yellow", "G": "green", "B": "black"}
MAX_CASUALTIES_PER_SMS = 99  # one SMS must not be able to flood the incident

_CODE = r"[0-9A-Za-z]{3}"
_STATUS_RE = re.compile(rf"^(OK|ER|OS|TR|AH|CL)\s+({_CODE})$", re.IGNORECASE)
_TRIAGE_RE = re.compile(rf"^T\s+({_CODE})((?:\s+[RYGB]\d{{1,2}}){{1,4}})$", re.IGNORECASE)
_HOSPITAL_RE = re.compile(rf"^H\s+({_CODE})\s+(READY|DIVERT)$", re.IGNORECASE)
_ACCIDENT_RE = re.compile(r"^ACCIDENT(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
# Decimal points required: "12,5 km avant Dellys" (comma decimal) is a place, not coordinates.
_COORDS_RE = re.compile(r"^(-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)(?:\s+(.*))?$", re.DOTALL)
_PEOPLE_RE = re.compile(r"^P(\d{1,3})$", re.IGNORECASE)
_TRAPPED_RE = re.compile(r"^C([01])$", re.IGNORECASE)


@dataclass(frozen=True)
class StatusUpdate:
    code: str
    target: IncidentStatus


@dataclass(frozen=True)
class Triage:
    code: str
    counts: dict[str, int]  # triage tag -> number of casualties


class FacilityState(StrEnum):
    READY = "ready"
    DIVERT = "divert"


@dataclass(frozen=True)
class HospitalResponse:
    code: str
    state: FacilityState


@dataclass(frozen=True)
class AccidentReport:
    lat: float | None
    lon: float | None
    people: int | None
    trapped: bool
    text: str  # free text; the location description when there are no coordinates


InboundCommand = StatusUpdate | Triage | HospitalResponse | AccidentReport


class GrammarError(ValueError):
    """The SMS is not part of the grammar; reply with the help message (E-08)."""


def parse_inbound(body: str) -> InboundCommand:
    """Parse one inbound SMS; raises ``GrammarError`` on anything outside the grammar."""
    text = " ".join(body.split()) if not body.lstrip().upper().startswith("ACCIDENT") else body
    text = text.strip()
    if m := _STATUS_RE.match(text):
        return StatusUpdate(m[2].upper(), STATUS_CODES[m[1].upper()])
    if m := _TRIAGE_RE.match(text):
        counts: dict[str, int] = {}
        for item in m[2].split():
            tag = TRIAGE_LETTERS[item[0].upper()]
            if tag in counts:
                raise GrammarError(f"duplicate triage letter {item[0]}")
            counts[tag] = int(item[1:])
        if sum(counts.values()) > MAX_CASUALTIES_PER_SMS:
            raise GrammarError("too many casualties in one message")
        return Triage(m[1].upper(), counts)
    if m := _HOSPITAL_RE.match(text):
        return HospitalResponse(m[1].upper(), FacilityState(m[2].lower()))
    if m := _ACCIDENT_RE.match(text):
        return _parse_accident((m[1] or "").strip())
    raise GrammarError("unknown message")


def _parse_accident(rest: str) -> AccidentReport:
    if not rest:
        raise GrammarError("ACCIDENT needs coordinates or a location")
    coords = _COORDS_RE.match(rest)
    if coords is None:
        return AccidentReport(None, None, None, False, " ".join(rest.split()))
    lat, lon = float(coords[1]), float(coords[2])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise GrammarError("coordinates out of range")
    people: int | None = None
    trapped = False
    words = (coords[3] or "").split()
    while words:
        if p := _PEOPLE_RE.match(words[0]):
            people = int(p[1])
        elif c := _TRAPPED_RE.match(words[0]):
            trapped = c[1] == "1"
        else:
            break
        words.pop(0)
    return AccidentReport(lat, lon, people, trapped, " ".join(words))


# ---------------------------------------------------------------- phone numbers

_ALGERIA_CC = "213"


def normalize_phone(raw: str) -> str:
    """Canonical ``+<digits>``; Algerian national numbers (``0550...``) get ``+213``."""
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("0") and not digits.startswith("00"):
        digits = f"+{_ALGERIA_CC}{digits[1:]}"
    if not digits.startswith("+"):
        digits = f"+{digits}"
    return digits
