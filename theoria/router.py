"""Lightweight intent routing — no extra model, just heuristics.

Fixes the "hello -> candle problem" failure: chitchat must never receive the
boxed-answer math prompt or irrelevant RAG chunks.
"""

from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    CHITCHAT = "chitchat"
    MATH = "math"
    SCIENCE = "science"
    GENERAL = "general"
    REFUTE = "refute"  # universal claims -> counterexample search
    PROVE = "prove"    # proof requests -> proof sketch + Lean check


_GREETING_PATTERNS = [
    r"^(hi|hello|hey|hie|yo|howdy|good (morning|afternoon|evening)|mhoro|mhoroi|makadii|hesi)\b",
    r"^(thanks|thank you|thx|ok|okay|cool|nice|great|bye|goodbye)\b",
    r"^(how are you|what'?s up|wassup)\b",
]

_IDENTITY_PATTERNS = [
    r"\b(your name|who are you|what are you|who made you|who created you|"
    r"who built you|about yourself|introduce yourself|zita rako|ndiwe ani)\b",
    r"\bwhat can you do\b",
    r"\bhelp me\b\s*$",
]

_MATH_KEYWORDS = {
    "solve", "equation", "derivative", "differentiate", "integral", "integrate",
    "simplify", "factor", "factorise", "factorize", "expand", "evaluate",
    "calculate", "compute", "prove", "proof", "theorem", "lemma", "limit",
    "matrix", "determinant", "eigenvalue", "polynomial", "quadratic", "algebra",
    "geometry", "trigonometry", "logarithm", "probability", "fraction",
    "gradient", "slope", "vertex", "root", "sum of", "product of",
}

_SCIENCE_KEYWORDS = {
    "physics", "chemistry", "biology", "force", "energy", "velocity",
    "acceleration", "momentum", "gravity", "mass", "atom", "molecule",
    "electron", "proton", "neutron", "reaction", "acid", "base", "cell",
    "photosynthesis", "dna", "evolution", "circuit", "voltage", "current",
    "resistance", "wave", "frequency", "thermodynamics", "entropy", "newton",
    "chemical", "element", "compound", "osmosis", "enzyme", "planet", "orbit",
}

# Digits next to operators or variables, e.g. "2+2", "x^2", "5x = 10"
_MATH_EXPR = re.compile(r"(\d\s*[-+*/^=]\s*\d)|([a-z]\s*\^)|(\d[a-z]\b)|(=\s*0)")

# Claim-refutation cues (checked before PROVE: "prove or disprove" refutes).
_REFUTE_RE = re.compile(
    r"\b(prove or disprove|disprove|counterexample|is it true|true or false|"
    r"always true|does it hold)\b",
    re.I,
)
# Universal quantifiers refute-route only when not an explicit proof request.
_UNIVERSAL_RE = re.compile(r"\b(for all|for every|for any|always)\b", re.I)
_PROVE_RE = re.compile(r"\b(prove|proof|show that|demonstrate that)\b", re.I)


def classify(query: str) -> Intent:
    text = query.strip().lower()

    for pattern in _GREETING_PATTERNS + _IDENTITY_PATTERNS:
        if re.search(pattern, text):
            return Intent.CHITCHAT

    # Fill-the-sorry requests carry Lean code; route them to the proof flow.
    if "sorry" in text and ("theorem" in text or "lean" in text or "```" in text):
        return Intent.PROVE
    if _REFUTE_RE.search(text):
        return Intent.REFUTE
    if _PROVE_RE.search(text):
        return Intent.PROVE
    if _UNIVERSAL_RE.search(text):
        return Intent.REFUTE

    # Very short queries with no math signal are almost always conversational.
    words = text.split()
    has_math_expr = bool(_MATH_EXPR.search(text))
    has_math_kw = any(kw in text for kw in _MATH_KEYWORDS)
    has_sci_kw = any(kw in text for kw in _SCIENCE_KEYWORDS)

    if len(words) <= 3 and not (has_math_expr or has_math_kw or has_sci_kw):
        return Intent.CHITCHAT

    if has_math_expr or has_math_kw:
        return Intent.MATH
    if has_sci_kw:
        return Intent.SCIENCE
    return Intent.GENERAL
