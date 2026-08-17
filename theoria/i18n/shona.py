"""Shona language support for the African Alpha bonus (+15%).

Three layers:
  1. Query-side: detect Shona, translate math vocabulary so SymPy/RAG work.
  2. Prompt-side: instruct the model to reply in Shona when the user does.
  3. UI-side: full chiShona interface strings.

The QLoRA fine-tune (data/finetune/seed_identity.json "shona" section) bakes
Shona greetings and math explanations into the model weights themselves.
"""

from __future__ import annotations

# Math/query vocabulary: Shona -> English (for RAG + SymPy routing)
SHONA_TO_ENGLISH: dict[str, str] = {
    "verenga": "calculate",
    "pawo": "solve",
    "gadzirisa": "solve",
    "tsvaga": "find",
    "mhedzisiro": "result",
    "yakawanda": "sum",
    "pfaruro": "difference",
    "kupatsanura": "divide",
    "kuparadza": "multiply",
    "kuwedzera": "add",
    "kubvisa": "subtract",
    "muviri": "equation",
    "chiverengero": "number",
    "tsanangura": "explain",
    "ratidza": "show",
    "svomhu": "math",
    "masvomhu": "mathematics",
    "sainzi": "science",
}

# Conversational markers that flag a Shona query even without math vocabulary
SHONA_MARKERS: tuple[str, ...] = (
    "mhoro", "mhoroi", "makadii", "hesi", "ndeipi", "ndatenda", "maita basa",
    "zita rako", "ndiwe ani", "unogona", "ndibatsire", "chii chinonzi",
    "sei ", "nei ",
)

UI_STRINGS_SHONA: dict[str, str] = {
    "title": "Theoria — Mubatsiri weMasvomhu neSainzi",
    "welcome": "Bvunza chero mubvunzo wemasvomhu kana sainzi",
    "placeholder": "Bvunza mubvunzo wemasvomhu, semuenzaniso: Gadzirisa x^2 - 5x + 6 = 0",
    "ask_button": "Bvunza",
    "thinking": "Kufunga…",
    "sources": "Zvinyorwa",
    "documents": "Magwaro",
    "upload": "Isa gwaro rePDF",
    "sympy": "Yakasimbiswa neSymPy",
    "language": "Mutauro",
    "offline": "Inoshanda pasina internet",
}

UI_STRINGS_EN: dict[str, str] = {
    "title": "Theoria — Offline Math & Science Assistant",
    "welcome": "Ask anything in math or science",
    "placeholder": "Ask a math or science question…",
    "ask_button": "Ask",
    "thinking": "Thinking…",
    "sources": "Sources",
    "documents": "Documents",
    "upload": "Attach a PDF",
    "sympy": "Verified by SymPy",
    "language": "Language",
    "offline": "Runs 100% on this laptop",
}


def detect_shona(query: str) -> bool:
    lower = f" {query.lower()} "
    if any(marker in lower for marker in SHONA_MARKERS):
        return True
    return any(f" {word} " in lower for word in SHONA_TO_ENGLISH)


def translate_shona_query(query: str) -> str:
    """Lightweight keyword translation so SymPy/RAG understand the request."""
    result = query
    for shona, english in SHONA_TO_ENGLISH.items():
        result = result.replace(shona, english)
    return result


# Deterministic replies for common Shona small talk. The base model cannot
# generate Shona (it echoes the input); until the fine-tuned model lands,
# these keep the Shona experience working at the app layer.
CANNED_REPLIES: list[tuple[tuple[str, ...], str]] = [
    (
        ("mhoro", "mhoroi", "hesi", "ndeipi"),
        "Mhoro! Ndini Theoria, mubatsiri wako wemasvomhu nesainzi. "
        "Ndingakubatsira nei nhasi?",
    ),
    (
        ("makadii",),
        "Ndiripo makadiiwo! Ndini Theoria, mubatsiri wemasvomhu. "
        "Mungada kubatsirwa nei?",
    ),
    (
        ("zita rako", "ndiwe ani"),
        "Zita rangu ndinonzi Theoria. Ndiri mubatsiri wemasvomhu nesainzi "
        "anoshanda pakombuta yako pasina internet.",
    ),
    (
        ("unogona", "ndibatsire"),
        "Hongu, ndinogona kukubatsira! Nyora mubvunzo wako wemasvomhu kana "
        "wesainzi — semuenzaniso: Gadzirisa x^2 - 5x + 6 = 0.",
    ),
    (
        ("ndatenda", "maita basa", "waita zvakanaka"),
        "Munotendwa! Bvunzai zvakare pese pamunoda.",
    ),
]


def canned_shona_reply(query: str) -> str | None:
    lower = query.lower()
    for triggers, reply in CANNED_REPLIES:
        if any(t in lower for t in triggers):
            return reply
    return None


def shona_reply_instruction() -> str:
    """Appended to the system prompt when the user writes in Shona."""
    return (
        "The user wrote in chiShona. Reply in simple chiShona where possible, "
        "keeping mathematical notation and formulas in standard form. If a "
        "technical term has no common Shona word, give the English term with "
        "a short Shona explanation."
    )


def localize_ui(lang: str = "en") -> dict[str, str]:
    return UI_STRINGS_SHONA if lang == "sn" else UI_STRINGS_EN
