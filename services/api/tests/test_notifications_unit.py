"""Unit: SMS grammar, retry policy, webhook signature, gateway channel, CAP 1.2 (FR-NTF, FR-INC-009).

No network or infrastructure.
"""

import hashlib
import hmac
import json
import random
import string
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from lxml import etree

from nadjet_api.incidents.lifecycle import IncidentStatus
from nadjet_api.incidents.models import Incident
from nadjet_api.notifications.cap import build_cap
from nadjet_api.notifications.channels import (
    DeliveryError,
    DeliveryRequest,
    SmsGatewayChannel,
)
from nadjet_api.notifications.grammar import (
    MAX_CASUALTIES_PER_SMS,
    SMS_MAX_CHARS,
    AccidentReport,
    FacilityState,
    GrammarError,
    HospitalResponse,
    MessageTooLongError,
    StatusUpdate,
    Triage,
    ensure_sms,
    fits_sms,
    format_alert,
    gsm7_length,
    help_message,
    normalize_phone,
    parse_inbound,
)
from nadjet_api.notifications.routes import signature_valid
from nadjet_api.notifications.service import out_of_attempts, retry_delay_s

XSD = Path(__file__).parent / "data" / "cap-v1.2.xsd"


# ---------------------------------------------------------------- outbound grammar


def test_alert_matches_the_documented_example() -> None:
    """FR-NTF-002: the example from the PRD, byte for byte."""
    text = format_alert(
        kind="ACC",
        priority=1,
        lat=36.648,
        lon=3.329,
        road="A1",
        pk_km=42,
        vehicles=2,
        short_code="7F3",
    )
    assert text == "ACC|P1|36.64800,3.32900|A1 PK42|2V|7F3"


def test_alert_omits_unknown_optional_parts() -> None:
    text = format_alert(
        kind="ACC",
        priority=3,
        lat=36.1,
        lon=3.2,
        road=None,
        pk_km=None,
        vehicles=None,
        short_code="ABC",
    )
    assert text == "ACC|P3|36.10000,3.20000|ABC"


def test_ascii_outside_gsm7_in_a_road_name_is_dropped() -> None:
    alert = format_alert(
        kind="ACC",
        priority=1,
        lat=36.6,
        lon=3.3,
        road="A1`\t",
        pk_km=None,
        vehicles=None,
        short_code="7F3",
    )
    assert alert == "ACC|P1|36.60000,3.30000|A1|7F3"


def test_every_generated_alert_is_one_gsm7_sms() -> None:
    """FR-NTF-002 / issue: <= 160 GSM-7 characters over generated incidents (incl. hostile roads)."""
    rng = random.Random(11)
    alphabet = string.ascii_letters + string.digits + " |é€ñ中文العربية\n" * 2
    for _ in range(2000):
        road = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 200))) or None
        text = format_alert(
            kind="ACC",
            priority=rng.randint(1, 4),
            lat=rng.uniform(-90, 90),
            lon=rng.uniform(-180, 180),
            road=road[:24]
            if road
            else None,  # the incident column is 64 chars; real roads are short
            pk_km=rng.choice([None, rng.uniform(0, 999)]),
            vehicles=rng.choice([None, 0, rng.randint(1, 30)]),
            short_code="".join(rng.choices("0123456789ABCDEFGHJKMNPQRSTVWXYZ", k=3)),
        )
        assert fits_sms(text), text
        assert text.count("|") <= 5


def test_a_message_over_160_septets_or_outside_gsm7_is_refused() -> None:
    with pytest.raises(MessageTooLongError):
        ensure_sms("A" * (SMS_MAX_CHARS + 1))
    with pytest.raises(MessageTooLongError):
        ensure_sms("حادث")
    assert ensure_sms("A" * SMS_MAX_CHARS)


def test_gsm7_counts_extension_characters_twice() -> None:
    assert gsm7_length("a|b") == 4
    assert gsm7_length("€") == 2
    assert gsm7_length("é") == 1
    assert gsm7_length("ç") is None


def test_help_and_confirmations_fit_one_sms() -> None:
    assert fits_sms(help_message())
    assert fits_sms("Nadjet: unknown code ZZZ. " + help_message())


# ---------------------------------------------------------------- inbound grammar


@pytest.mark.parametrize(
    ("body", "target"),
    [
        ("OK 7F3", IncidentStatus.ACKNOWLEDGED),
        ("ER 7F3", IncidentStatus.EN_ROUTE),
        ("OS 7F3", IncidentStatus.ON_SCENE),
        ("TR 7F3", IncidentStatus.TRANSPORTING),
        ("AH 7F3", IncidentStatus.AT_HOSPITAL),
        ("CL 7F3", IncidentStatus.CLOSED),
        ("  ok   7f3 \n", IncidentStatus.ACKNOWLEDGED),
    ],
)
def test_status_codes_parse(body: str, target: IncidentStatus) -> None:
    assert parse_inbound(body) == StatusUpdate("7F3", target)


def test_triage_parses_counts_per_tag() -> None:
    """AC-NTF-005.2: ``T 7F3 R1 Y2 G0``."""
    assert parse_inbound("T 7F3 R1 Y2 G0") == Triage("7F3", {"red": 1, "yellow": 2, "green": 0})
    assert parse_inbound("t 7f3 b1") == Triage("7F3", {"black": 1})


def test_hospital_reply_parses() -> None:
    assert parse_inbound("H 7F3 READY") == HospitalResponse("7F3", FacilityState.READY)
    assert parse_inbound("h 7f3 divert") == HospitalResponse("7F3", FacilityState.DIVERT)


def test_accident_with_coordinates_people_and_trapped() -> None:
    """Issue: ``ACCIDENT 36.64800,3.32900 P3 C1``."""
    assert parse_inbound("ACCIDENT 36.64800,3.32900 P3 C1") == AccidentReport(
        36.648, 3.329, 3, True, ""
    )


def test_accident_optional_parts_and_free_text() -> None:
    assert parse_inbound("ACCIDENT 36.5,3.1") == AccidentReport(36.5, 3.1, None, False, "")
    assert parse_inbound("accident 36.5,3.1 C0 two cars on the bridge") == AccidentReport(
        36.5, 3.1, None, False, "two cars on the bridge"
    )
    assert parse_inbound("ACCIDENT -36.5, 3.1 P2") == AccidentReport(-36.5, 3.1, 2, False, "")


def test_accident_without_coordinates_keeps_the_text_for_call_back() -> None:
    """Issue: ``ACCIDENT RN24 Dellys`` is flagged for call-back."""
    assert parse_inbound("ACCIDENT RN24 Dellys") == AccidentReport(
        None, None, None, False, "RN24 Dellys"
    )


def test_a_comma_decimal_distance_is_a_location_not_coordinates() -> None:
    """``12,5 km`` must not place the incident at 12 N 5 E; it goes to call-back."""
    assert parse_inbound("ACCIDENT 12,5 km avant Dellys") == AccidentReport(
        None, None, None, False, "12,5 km avant Dellys"
    )


@pytest.mark.parametrize(
    "body",
    [
        "",
        "hello",
        "OK",  # no code
        "OK 7F",  # code too short
        "OK 7F3 extra",
        "XX 7F3",
        "T 7F3",  # no counts
        "T 7F3 R1 R2",  # duplicate letter
        "T 7F3 R100",  # more than two digits
        "T 7F3 X1",
        "H 7F3",
        "H 7F3 MAYBE",
        "ACCIDENT",  # nothing at all
        "ACCIDENT   ",
        "ACCIDENT 95.0,3.0",  # latitude out of range
        "ACCIDENT 36.0,200.0",  # longitude out of range
    ],
)
def test_malformed_messages_raise_grammar_error(body: str) -> None:
    """E-08: bad syntax is rejected (the caller replies with help, no state change)."""
    with pytest.raises(GrammarError):
        parse_inbound(body)


def test_triage_total_is_capped() -> None:
    with pytest.raises(GrammarError):
        parse_inbound(f"T 7F3 R{MAX_CASUALTIES_PER_SMS} Y1")
    assert parse_inbound(f"T 7F3 R{MAX_CASUALTIES_PER_SMS}")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0550123456", "+213550123456"),
        ("+213 550 12 34 56", "+213550123456"),
        ("00213550123456", "+213550123456"),
        ("213550123456", "+213550123456"),
        ("+33 6 12 34 56 78", "+33612345678"),
    ],
)
def test_phone_numbers_are_normalised(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


# ---------------------------------------------------------------- retry policy


def test_retry_delay_doubles_from_the_base() -> None:
    """doc 11 section 9: 30 s, then exponential back-off."""
    assert [retry_delay_s(n, 30) for n in (1, 2, 3)] == [30, 60, 120]


def test_attempts_run_out_after_the_first_send_and_three_retries() -> None:
    assert [out_of_attempts(n, 3) for n in range(5)] == [False, False, False, False, True]
    assert out_of_attempts(1, 0)


# ---------------------------------------------------------------- webhook signature


def _sign(secret: str, body: bytes, ts: str) -> str:
    return hmac.new(secret.encode(), body + ts.encode(), hashlib.sha256).hexdigest()


def test_signature_accepts_a_valid_hmac_within_tolerance() -> None:
    body, ts = b'{"event":"sms:received"}', "1000"
    assert signature_valid("s3cret", body, _sign("s3cret", body, ts), ts, now=1100, tolerance=300)


@pytest.mark.parametrize(
    ("signature", "ts", "now"),
    [
        (None, "1000", 1000),  # missing
        ("deadbeef", "1000", 1000),  # wrong
        ("sig", "abc", 1000),  # timestamp not a number
        ("sig", None, 1000),
        ("valid", "1000", 2000),  # replay outside the window
    ],
)
def test_signature_rejects_bad_requests(signature: str | None, ts: str | None, now: int) -> None:
    body = b"{}"
    if signature == "valid":
        signature = _sign("s3cret", body, ts or "")
    assert not signature_valid("s3cret", body, signature, ts, now=now, tolerance=300)


def test_signature_rejects_a_tampered_body() -> None:
    ts = "1000"
    good = _sign("s3cret", b'{"a":1}', ts)
    assert not signature_valid("s3cret", b'{"a":2}', good, ts, now=1000, tolerance=300)


# ---------------------------------------------------------------- SMS gateway channel


def _request(recipient: str = "+213550123456") -> DeliveryRequest:
    return DeliveryRequest(
        uuid.uuid4(), recipient, "ACC|P1|36.64800,3.32900|7F3", str(uuid.uuid4())
    )


async def test_gateway_channel_posts_the_documented_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, json={"id": "x", "state": "Pending"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        channel = SmsGatewayChannel(client, "https://gw.example/", "user", "pass")
        request = _request()
        await channel.send(request)

    [sent] = seen
    assert str(sent.url) == "https://gw.example/api/3rdparty/v1/messages"
    assert sent.headers["authorization"].startswith("Basic ")
    assert json.loads(sent.content) == {
        "id": request.ref,
        "textMessage": {"text": request.text},
        "phoneNumbers": [request.recipient],
        "withDeliveryReport": True,
    }


async def test_gateway_error_status_is_a_retryable_delivery_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        channel = SmsGatewayChannel(client, "https://gw.example", "u", "p")
        with pytest.raises(DeliveryError) as excinfo:
            await channel.send(_request())
    assert not excinfo.value.permanent


async def test_gateway_offline_is_a_retryable_delivery_error() -> None:
    """E-07: SMS gateway offline."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        channel = SmsGatewayChannel(client, "https://gw.example", "u", "p")
        with pytest.raises(DeliveryError) as excinfo:
            await channel.send(_request())
    assert not excinfo.value.permanent


# ---------------------------------------------------------------- CAP 1.2


def _incident(**overrides: object) -> Incident:
    now = datetime(2026, 10, 30, 12, 30, 45, 123456, tzinfo=UTC)
    fields: dict[str, object] = {
        "id": uuid.uuid4(),
        "short_code": "7F3",
        "type": "crash",
        "status": IncidentStatus.VERIFIED.value,
        "priority": 1,
        "lat": 36.648,
        "lon": 3.329,
        "road": "A1",
        "wilaya": "Boumerdes",
        "source": "camera",
        "event_time": now,
        "created_at": now,
        "ai_status": "probable",
        "verifier_result": {"available": True, "model": "Qwen/Qwen3-VL-8B-Instruct-FP8"},
    }
    fields.update(overrides)
    return Incident(**fields)


def _validate(xml: bytes) -> etree._Element:
    schema = etree.XMLSchema(etree.parse(str(XSD)))
    document = etree.fromstring(xml)
    schema.assertValid(document)
    return document


def test_cap_export_is_valid_against_the_oasis_xsd_with_ar_and_fr() -> None:
    """FR-INC-009 / TD-15."""
    document = _validate(build_cap(_incident()))
    ns = {"c": "urn:oasis:names:tc:emergency:cap:1.2"}
    assert sorted(document.xpath("//c:info/c:language/text()", namespaces=ns)) == ["ar", "fr"]
    assert set(document.xpath("//c:info[1]/c:category/text()", namespaces=ns)) == {
        "Transport",
        "Rescue",
    }
    assert document.xpath("//c:info[1]/c:area/c:circle/text()", namespaces=ns) == [
        "36.64800,3.32900 0"
    ]


def test_cap_cites_the_ai_source() -> None:
    """FR-VIS-021: AI values carry their source."""
    document = _validate(build_cap(_incident()))
    ns = {"c": "urn:oasis:names:tc:emergency:cap:1.2"}
    values = document.xpath(
        "//c:info[1]/c:parameter[c:valueName='nadjet:ai_source']/c:value/text()", namespaces=ns
    )
    assert values == ["Qwen/Qwen3-VL-8B-Instruct-FP8"]


@pytest.mark.parametrize("priority", [1, 2, 3, 4])
@pytest.mark.parametrize("kind", ["crash", "stalled_vehicle", "pedestrian_on_road", "other"])
def test_cap_is_valid_for_every_priority_and_type(priority: int, kind: str) -> None:
    _validate(build_cap(_incident(priority=priority, type=kind)))


def test_cap_is_valid_for_a_position_less_call_back_report() -> None:
    xml = build_cap(
        _incident(
            lat=None,
            lon=None,
            location_text="RN24 Dellys",
            road=None,
            status="candidate",
            source="citizen",
            ai_status=None,
            verifier_result={"available": False},
        )
    )
    document = _validate(xml)
    ns = {"c": "urn:oasis:names:tc:emergency:cap:1.2"}
    assert document.xpath("//c:area/c:areaDesc/text()", namespaces=ns)[0] == "RN24 Dellys"
    assert not document.xpath("//c:circle", namespaces=ns)
