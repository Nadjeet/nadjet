"""Safety wording for AI-generated text (PRD FR-VIS-017).

AI text must never state death, injury or a medical condition. Sentences containing such
words are replaced by a neutral sentence in the same language.
"""

import re

NEUTRAL = {
    "en": "Person lying on the ground — needs human assessment.",
    "fr": "Personne au sol — évaluation humaine nécessaire.",
    "ar": "شخص ملقى على الأرض — يحتاج إلى تقييم بشري.",
}

_FORBIDDEN = {
    "en": (
        r"\b(dead|deaths?|died|killed|fatal(ity|ities)?|injur(y|ies|ed)"
        r"|wounded|unconscious|bleeding)\b"
    ),
    "fr": r"\b(morts?|mortes?|décédée?s?|tuée?s?|blessée?s?|blessures?|inconsciente?s?|saigne)\b",
    "ar": r"(ميت|موتى|متوفى|قتيل|قتلى|مصاب|مصابون|إصابة|جريح|جرحى|فاقد للوعي|ينزف)",
}

_PATTERNS = {lang: re.compile(p, re.IGNORECASE) for lang, p in _FORBIDDEN.items()}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟])\s+")


def mentions_health(text: str) -> bool:
    """True if ``text`` states death, injury or a medical condition in any supported language."""
    return any(p.search(text) for p in _PATTERNS.values())


def sanitize(text: str, lang: str, *, any_language: bool = False) -> tuple[str, bool]:
    """Return (safe_text, changed). Unknown languages are checked against all patterns.

    ``any_language``: check every language (a model can mix them) but answer in ``lang``.
    """
    if any_language or lang not in _PATTERNS:
        patterns = list(_PATTERNS.values())
    else:
        patterns = [_PATTERNS[lang]]
    neutral = NEUTRAL.get(lang, NEUTRAL["en"])
    out: list[str] = []
    changed = False
    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        if any(p.search(sentence) for p in patterns):
            changed = True
            if neutral not in out:
                out.append(neutral)
        elif sentence:
            out.append(sentence)
    return " ".join(out), changed
