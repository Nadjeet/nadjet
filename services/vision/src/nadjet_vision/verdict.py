"""Verifier answer schema and validation layer (PRD FR-VIS-016, FR-VIS-017, doc 11 TD-24).

The model's JSON is checked against ``VerifierAnswer``; findings must cite frames that exist in
the video it was shown (others are dropped and logged); every free text goes through
``safety.sanitize``; a priority raise needs a surviving finding. When the answer stays invalid,
``template_result`` builds the FR/AR description from the rule trigger alone.
"""

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from nadjet_shared import Finding, TriggerType, VerifierResult
from nadjet_vision.safety import mentions_health, sanitize

log = logging.getLogger("nadjet_vision.verdict")


class FindingAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    basis: Literal["observed", "inferred"]
    frame_ids: list[int]


class VerifierAnswer(BaseModel):
    """Fixed answer format of the verifier (doc 11 §6). ``collision_visible`` comes first so
    that its token is the first decision the model writes (yes-token probability)."""

    model_config = ConfigDict(extra="forbid")

    collision_visible: Literal["yes", "no", "cannot_judge"]
    t_contact: float | None
    type: Literal["collision", "rollover", "fire", "stalled", "pedestrian", "none"]
    vehicles_involved: int = Field(ge=0)
    lanes_blocked: int = Field(ge=0)
    findings: list[FindingAnswer]
    not_assessable: list[str]
    priority_raise: Literal[0, 1]
    description_fr: str
    description_ar: str


def answer_schema() -> dict[str, Any]:
    return VerifierAnswer.model_json_schema()


def _safe(text: str, lang: str) -> str:
    return sanitize(text, lang, any_language=True)[0]


def _keep(text: str, field: str) -> bool:
    """Findings and not-assessable items that mention health are dropped, never rewritten:
    the neutral "person lying on the ground" sentence would be an observation nobody made."""
    if mentions_health(text):
        log.warning("%s dropped (health wording, FR-VIS-017): %r", field, text)
        return False
    return True


def finalize(
    answer: VerifierAnswer, frame_count: int, model: str, yes_probability: float | None
) -> VerifierResult:
    """Apply the TD-24 rules to a schema-valid answer."""
    findings: list[Finding] = []
    for item in answer.findings:
        valid = sorted({i for i in item.frame_ids if 0 <= i < frame_count})
        if len(valid) != len(set(item.frame_ids)):
            log.warning(
                "finding cites missing frames %s (video has %d): %r",
                sorted(set(item.frame_ids) - set(valid)),
                frame_count,
                item.statement,
            )
        if not valid:
            log.warning("finding dropped, no valid frame cited: %r", item.statement)
            continue
        if not _keep(item.statement, "finding"):
            continue
        findings.append(Finding(statement=item.statement, basis=item.basis, frame_ids=valid))
    return VerifierResult(
        available=True,
        model=model,
        collision_visible=answer.collision_visible,
        yes_probability=yes_probability,
        t_contact=answer.t_contact,
        type=answer.type,
        vehicles_involved=answer.vehicles_involved,
        lanes_blocked=answer.lanes_blocked,
        description_fr=_safe(answer.description_fr, "fr"),
        description_ar=_safe(answer.description_ar, "ar"),
        priority_raise=answer.priority_raise if findings else 0,
        findings=findings,
        not_assessable=[t for t in answer.not_assessable if _keep(t, "not_assessable")],
    )


_TEMPLATE_FR = {
    TriggerType.COLLISION_CANDIDATE: "contact puis arrêt de deux véhicules",
    TriggerType.HARD_STOP: "arrêt brutal d'un véhicule",
    TriggerType.STALLED_VEHICLE: "véhicule immobilisé sur une voie",
    TriggerType.PEDESTRIAN_ON_ROAD: "personne sur la chaussée",
    TriggerType.AI_SWEEP: "détection par balayage IA",
}
_TEMPLATE_AR = {
    TriggerType.COLLISION_CANDIDATE: "احتكاك ثم توقف مركبتين",
    TriggerType.HARD_STOP: "توقف مفاجئ لمركبة",
    TriggerType.STALLED_VEHICLE: "مركبة متوقفة في مسار",
    TriggerType.PEDESTRIAN_ON_ROAD: "شخص على الطريق",
    TriggerType.AI_SWEEP: "رصد بمسح الذكاء الاصطناعي",
}


def template_result(trigger: TriggerType, model: str) -> VerifierResult:
    """Description from the rule trigger alone, after the model answered invalidly twice."""
    return VerifierResult(
        available=False,
        invalid=True,
        model=model,
        description_fr=(
            f"Signal automatique : {_TEMPLATE_FR.get(trigger, trigger.value)}. "
            "Analyse visuelle IA invalide : évaluation humaine nécessaire."
        ),
        description_ar=(
            f"إشارة آلية: {_TEMPLATE_AR.get(trigger, trigger.value)}. "
            "تحليل الذكاء الاصطناعي غير صالح: يلزم تقييم بشري."
        ),
    )
