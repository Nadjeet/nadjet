"""Unit: lifecycle, merge rules, short codes, signing, event chain, store, SSE scope."""

import itertools
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nadjet_api.audit.service import GENESIS_HASH, chain_hash
from nadjet_api.auth.roles import Agency, Scope
from nadjet_api.incidents import lifecycle as lc
from nadjet_api.incidents.events import frame, visible_to
from nadjet_api.incidents.merge import (
    best_ai_status,
    best_verifier,
    merge_signals,
    should_merge,
)
from nadjet_api.incidents.models import IncidentEvent
from nadjet_api.incidents.service import canonical_event, check_event_chain
from nadjet_api.incidents.shortcodes import ALPHABET, LENGTH, pick_short_code, short_code
from nadjet_api.incidents.signing import ChainSigner, generate_seed_hex
from nadjet_api.incidents.store import (
    EvidenceNotFoundError,
    EvidenceTooLargeError,
    LocalEvidenceStore,
    sha256_of,
)
from nadjet_shared.events import AiStatus, VerifierResult

S = lc.IncidentStatus
T0 = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

HAPPY_PATH = [
    S.CANDIDATE, S.VERIFIED, S.DISPATCHED, S.ACKNOWLEDGED, S.EN_ROUTE,
    S.ON_SCENE, S.TRANSPORTING, S.AT_HOSPITAL, S.CLOSED,
]  # fmt: skip


def test_FR_INC_005_full_lifecycle_is_legal() -> None:
    for current, target in itertools.pairwise(HAPPY_PATH):
        lc.check_transition(current, target)


def test_on_scene_can_close_directly() -> None:
    lc.check_transition(S.ON_SCENE, S.CLOSED)


@pytest.mark.parametrize("target", [S.REJECTED, S.MERGED, S.VERIFIED])
def test_candidate_can_be_verified_rejected_or_merged(target: S) -> None:
    lc.check_transition(S.CANDIDATE, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.CANDIDATE, S.DISPATCHED),
        (S.VERIFIED, S.ON_SCENE),
        (S.VERIFIED, S.REJECTED),
        (S.DISPATCHED, S.EN_ROUTE),
        (S.ON_SCENE, S.AT_HOSPITAL),
        (S.AT_HOSPITAL, S.TRANSPORTING),
        (S.CLOSED, S.VERIFIED),
        (S.REJECTED, S.VERIFIED),
        (S.MERGED, S.CLOSED),
    ],
)
def test_illegal_transitions_raise(current: S, target: S) -> None:
    with pytest.raises(lc.IllegalTransitionError):
        lc.check_transition(current, target)


def test_every_status_has_a_transition_entry_and_terminals_are_final() -> None:
    assert set(lc.TRANSITIONS) == set(S)
    for terminal in lc.CLOSED_STATUSES:
        assert lc.TRANSITIONS[terminal] == frozenset()


@pytest.mark.parametrize(
    ("seconds", "metres", "expected"),
    [
        (30, 20, True),  # AC-INC-002.1
        (60, 50, True),
        (61, 20, False),
        (30, 51, False),
        (-45, 10, True),  # candidate older than the last event
        (0, 0, True),
    ],
)
def test_FR_INC_002_merge_window_and_radius(seconds: int, metres: float, expected: bool) -> None:
    assert should_merge(T0, T0 + timedelta(seconds=seconds), metres) is expected


def test_merge_keeps_strongest_signals_and_best_ai_status() -> None:
    assert merge_signals({"a": 1, "b": 5}, {"a": 3, "c": 2}) == {"a": 3, "b": 5, "c": 2}
    assert best_ai_status(AiStatus.POSSIBLE, AiStatus.CONFIRMED) is AiStatus.CONFIRMED
    assert best_ai_status(AiStatus.PROBABLE, AiStatus.POSSIBLE) is AiStatus.PROBABLE


def test_best_verifier_prefers_available_then_higher_probability() -> None:
    down = VerifierResult(available=False)
    low = VerifierResult(available=True, model="m", yes_probability=0.4)
    high = VerifierResult(available=True, model="m", yes_probability=0.9)
    assert best_verifier(down, low) == low
    assert best_verifier(low, high) == high
    assert best_verifier(high, low) == high


def test_short_codes_are_three_base32_chars_and_deterministic() -> None:
    incident_id = uuid.uuid4()
    code = short_code(incident_id)
    assert len(code) == LENGTH and set(code) <= set(ALPHABET)
    assert code == short_code(incident_id)
    assert len(ALPHABET) == 32


def test_short_code_collision_picks_another_free_code() -> None:
    incident_id = uuid.uuid4()
    first = pick_short_code(incident_id, set())
    second = pick_short_code(incident_id, {first})
    assert second != first and second == short_code(incident_id, 1)


def test_short_code_space_exhaustion_raises() -> None:
    incident_id = uuid.uuid4()
    taken = {short_code(incident_id, n) for n in range(256)}
    with pytest.raises(RuntimeError):
        pick_short_code(incident_id, taken)


def test_signing_round_trip_and_tamper_detection() -> None:
    signer = ChainSigner(generate_seed_hex())
    signature = signer.sign("abc")
    assert signer.verify("abc", signature)
    assert not signer.verify("abd", signature)
    assert not signer.verify("abc", None)
    assert not signer.verify("abc", "zz-not-hex")
    assert not ChainSigner(generate_seed_hex()).verify("abc", signature)


def make_chain(signer: ChainSigner, count: int) -> list[IncidentEvent]:
    incident_id = uuid.uuid4()
    events: list[IncidentEvent] = []
    prev = GENESIS_HASH
    for n in range(count):
        ts = T0 + timedelta(seconds=n)
        payload = {"n": n}
        digest = chain_hash(
            prev,
            canonical_event(
                incident_id=incident_id, kind="k", actor_id=None, payload=payload, ts=ts
            ),
        )
        events.append(
            IncidentEvent(
                id=n + 1, incident_id=incident_id, kind="k", actor_id=None, payload=payload,
                ts=ts, prev_hash=prev, hash=digest, signature=signer.sign(digest),
            )
        )  # fmt: skip
        prev = digest
    return events


def test_FR_SEC_003_valid_chain_passes() -> None:
    signer = ChainSigner(generate_seed_hex())
    assert check_event_chain(make_chain(signer, 4), signer) == []
    assert check_event_chain([], signer) == []


def test_FR_SEC_003_tampered_payload_is_detected() -> None:
    signer = ChainSigner(generate_seed_hex())
    events = make_chain(signer, 4)
    events[1].payload = {"n": 999}
    [failure] = check_event_chain(events, signer)
    assert (failure.kind, failure.ref) == ("event", "2")


def test_FR_SEC_003_removed_event_is_detected() -> None:
    signer = ChainSigner(generate_seed_hex())
    events = make_chain(signer, 4)
    del events[1]
    assert check_event_chain(events, signer)[0].kind == "event"


def test_FR_SEC_003_forged_head_signature_is_detected() -> None:
    signer = ChainSigner(generate_seed_hex())
    events = make_chain(signer, 3)
    events[-1].signature = ChainSigner(generate_seed_hex()).sign(events[-1].hash)
    [failure] = check_event_chain(events, signer)
    assert failure.kind == "signature"


def test_sse_scope_filtering_and_frame() -> None:
    message = {"type": "incident.updated", "incident_id": "i1", "version": 3,
               "agencies": ["samu"], "facilities": ["h1"]}  # fmt: skip
    assert visible_to(Scope(unrestricted=True), message)
    assert visible_to(Scope(agency=Agency.SAMU), message)
    assert not visible_to(Scope(agency=Agency.POLICE), message)
    assert visible_to(Scope(facility_id="h1"), message)
    assert not visible_to(Scope(facility_id="h2"), message)
    assert (
        frame(message) == 'event: incident.updated\ndata: {"incident_id": "i1", "version": 3}\n\n'
    )


async def chunks(*parts: bytes):  # type: ignore[no-untyped-def]
    for part in parts:
        yield part


async def test_local_store_saves_hashes_reads_and_rejects_oversize(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path)
    stored = await store.save("a/b.bin", chunks(b"hello ", b"world"), max_bytes=100)
    assert stored.size_bytes == 11
    assert stored.sha256 == await sha256_of(store, "a/b.bin")
    with pytest.raises(EvidenceTooLargeError):
        await store.save("a/big.bin", chunks(b"x" * 60, b"x" * 60), max_bytes=100)
    assert not (tmp_path / "a" / "big.bin").exists()
    with pytest.raises(EvidenceNotFoundError):
        await sha256_of(store, "a/missing.bin")


async def test_local_store_refuses_path_traversal(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "root")
    with pytest.raises(ValueError, match="escapes"):
        await store.save("../evil.bin", chunks(b"x"), max_bytes=10)
