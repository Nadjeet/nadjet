import pytest

from nadjet_vision.safety import NEUTRAL, sanitize


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "Two cars collided. The driver is dead."),
        ("en", "One person appears injured near the barrier."),
        ("fr", "Deux voitures se sont percutées. Un passager est blessé."),
        ("fr", "Le conducteur semble mort."),
        ("ar", "اصطدمت سيارتان. يوجد مصاب على الطريق."),
    ],
)
def test_medical_claims_are_replaced_by_neutral_wording(lang: str, text: str) -> None:
    safe, changed = sanitize(text, lang)
    assert changed is True
    assert NEUTRAL[lang] in safe


def test_factual_sentences_are_kept() -> None:
    safe, changed = sanitize("Two cars collided. One car blocks the right lane.", "en")
    assert changed is False
    assert safe == "Two cars collided. One car blocks the right lane."


def test_only_offending_sentence_is_replaced_once() -> None:
    safe, changed = sanitize("Two cars collided. Driver dead. Passenger injured.", "en")
    assert changed is True
    assert safe == f"Two cars collided. {NEUTRAL['en']}"


def test_unknown_language_checks_every_pattern() -> None:
    _, changed = sanitize("Le conducteur est blessé.", "es")
    assert changed is True


def test_words_containing_forbidden_substrings_are_not_flagged() -> None:
    _, changed = sanitize("The deadline for the report is today.", "en")
    assert changed is False
