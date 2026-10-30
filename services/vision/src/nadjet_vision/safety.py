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


def sanitize(text: str, lang: str) -> tuple[str, bool]:
    """Return (safe_text, changed). Unknown languages are checked against all patterns."""
    patterns = [_PATTERNS[lang]] if lang in _PATTERNS else list(_PATTERNS.values())
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
