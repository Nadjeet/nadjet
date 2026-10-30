"""OASIS CAP 1.2 export of an incident (FR-INC-009, NFR-COMP-001, TD-15). Pure."""

from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from nadjet_api.incidents.models import Incident

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
SENDER = "nadjet"

# CAP urgency / severity per Nadjet priority (P1 most urgent).
URGENCY = {1: "Immediate", 2: "Immediate", 3: "Expected", 4: "Future"}
SEVERITY = {1: "Extreme", 2: "Severe", 3: "Moderate", 4: "Minor"}

# (event, description) per language and incident type; unknown types use "crash".
EVENTS: dict[str, dict[str, tuple[str, str]]] = {
    "ar": {
        "crash": ("حادث مرور", "حادث مرور على الطريق"),
        "stalled_vehicle": ("مركبة متوقفة", "مركبة متوقفة على الطريق"),
        "pedestrian_on_road": ("شخص على الطريق", "شخص على الطريق السريع"),
    },
    "fr": {
        "crash": ("Accident de la route", "Accident de la circulation sur la chaussée"),
        "stalled_vehicle": ("Véhicule à l'arrêt", "Véhicule immobilisé sur la chaussée"),
        "pedestrian_on_road": ("Piéton sur la route", "Piéton sur la chaussée"),
    },
}
INSTRUCTION = {
    "ar": "يرجى إرسال فرق الإسعاف والحماية المدنية",
    "fr": "Envoyer les secours et la protection civile",
}


def _certainty(incident: Incident) -> str:
    if incident.status not in ("candidate", "rejected", "merged"):
        return "Observed"  # a human verified it (or created it from a call)
    return "Likely" if incident.ai_status in ("confirmed", "probable") else "Possible"


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, f"{{{CAP_NS}}}{tag}")
    if text is not None:
        element.text = text
    return element


def _iso(moment: datetime) -> str:
    """CAP dateTime: seconds precision with a numeric offset."""
    return moment.astimezone(UTC).replace(microsecond=0).isoformat()


def _area(info: ET.Element, incident: Incident) -> None:
    area = _sub(info, "area")
    if incident.lat is not None and incident.lon is not None:
        where = incident.road or incident.wilaya or "incident location"
        _sub(area, "areaDesc", where)
        _sub(area, "circle", f"{incident.lat:.5f},{incident.lon:.5f} 0")  # radius 0 km: a point
    else:
        _sub(area, "areaDesc", incident.location_text or "location pending call-back")


def build_cap(incident: Incident) -> bytes:
    """CAP 1.2 ``alert`` with one ``info`` block per language (``ar`` and ``fr``)."""
    ET.register_namespace("", CAP_NS)
    alert = ET.Element(f"{{{CAP_NS}}}alert")
    _sub(alert, "identifier", str(incident.id))
    _sub(alert, "sender", SENDER)
    _sub(alert, "sent", _iso(incident.created_at))
    _sub(alert, "status", "Actual")
    _sub(alert, "msgType", "Alert")
    _sub(alert, "source", incident.source)
    _sub(alert, "scope", "Restricted")
    _sub(alert, "restriction", "Authorised emergency services only")
    _sub(alert, "code", f"nadjet:{incident.short_code}")
    for language, events in EVENTS.items():
        event, description = events.get(incident.type, events["crash"])
        info = _sub(alert, "info")
        _sub(info, "language", language)
        _sub(info, "category", "Transport")
        _sub(info, "category", "Rescue")
        _sub(info, "event", event)
        _sub(info, "responseType", "Execute")
        _sub(info, "urgency", URGENCY[incident.priority])
        _sub(info, "severity", SEVERITY[incident.priority])
        _sub(info, "certainty", _certainty(incident))
        _sub(info, "effective", _iso(incident.event_time))
        _sub(info, "senderName", "Nadjet")
        _sub(info, "headline", f"{event} - {incident.short_code}")
        _sub(info, "description", description)
        _sub(info, "instruction", INSTRUCTION[language])
        for name, value in (
            ("nadjet:priority", f"P{incident.priority}"),
            ("nadjet:ai_status", incident.ai_status or "none"),
            ("nadjet:ai_source", incident.verifier_result.get("model") or "rules"),
        ):
            parameter = _sub(info, "parameter")
            _sub(parameter, "valueName", name)
            _sub(parameter, "value", str(value))
        _area(info, incident)
    return bytes(ET.tostring(alert, encoding="utf-8", xml_declaration=True))
