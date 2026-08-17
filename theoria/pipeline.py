"""Orchestrate routing, RAG, SymPy tools, and LLM inference.

The LLM is the primary answerer — judges evaluate the raw model, so it must
answer well on its own. An intent router keeps chitchat away from the math
prompt and RAG only fires when the retrieved chunk is actually relevant.
SymPy verifies math exactly and doubles as an instant fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from theoria.i18n.shona import canned_shona_reply, detect_shona, translate_shona_query
from theoria.inference import InferenceConfig, run_chat
from theoria.prompts import ToolContext, build_messages
from theoria.rag.retrieve import retrieve
from theoria.router import Intent, classify
from theoria.tools.counterexample import format_for_prompt, search_counterexample
from theoria.tools.lean_kit import extract_lean_block, is_available as lean_available, verify_with_repair
from theoria.tools.sympy_solver import run_sympy

# BGE cosine similarity: related math/science text scores ~0.6+, unrelated
# text ~0.3-0.4. Below this threshold a chunk hurts more than it helps.
RAG_MIN_SCORE = 0.55

CHITCHAT_MAX_TOKENS = 192

_ATTACH_MARKER = "— transcribed text]:"


def _tool_query(query: str) -> str:
    """When a photo was attached, SymPy/routing should see the OCR text, not
    the wrapping 'please solve the attached photo' prose."""
    if _ATTACH_MARKER in query:
        return query.split(_ATTACH_MARKER, 1)[1].strip() or query
    return query


@dataclass
class AskResult:
    answer: str
    intent: str = "math"
    sources: list[dict] = field(default_factory=list)
    sympy_result: str | None = None
    sympy_error: str | None = None
    counterexample: dict | None = None
    lean: dict | None = None
    prompt: str = ""
    tokens_per_second: float | None = None
    elapsed_s: float | None = None
    backend: str = ""


def prepare(
    query: str,
    use_rag: bool = True,
    lang: str = "en",
    history: list[dict] | None = None,
) -> dict:
    """Route the query and gather RAG/SymPy context (no LLM call).

    Shared by the blocking ask() and the streaming endpoint.
    """
    effective_query = query
    is_shona = lang == "sn" or detect_shona(query)
    if is_shona:
        effective_query = translate_shona_query(query)

    # Tools (SymPy, counterexamples, intent) key off the math content; for
    # photo asks that is the OCR transcription, not the wrapper prose.
    tool_q = _tool_query(effective_query)
    intent = classify(tool_q)

    # Base model echoes Shona instead of speaking it; canned greetings keep
    # the Shona UX working until the fine-tuned model takes over.
    canned = canned_shona_reply(query) if is_shona and intent == Intent.CHITCHAT else None

    sources: list[dict] = []
    rag_chunks: list[str] = []
    if use_rag and intent in (Intent.MATH, Intent.SCIENCE, Intent.GENERAL):
        sources = [
            s for s in retrieve(tool_q, top_k=2)
            if s.get("score", 0.0) >= RAG_MIN_SCORE
        ]
        rag_chunks = [s["content"] for s in sources]

    sympy = run_sympy(tool_q) if intent == Intent.MATH else None

    cex_info: dict | None = None
    cex_note: str | None = None
    if intent == Intent.REFUTE:
        cex = search_counterexample(tool_q)
        if cex.handled:
            cex_note = format_for_prompt(cex)
            cex_info = {
                "claim": cex.claim,
                "verdict": cex.verdict,
                "counterexample": cex.counterexample,
                "detail": cex.detail,
            }

    tool_ctx = ToolContext(
        sympy_result=sympy.result if sympy and sympy.handled else None,
        sympy_error=sympy.error if sympy and sympy.handled else None,
        counterexample_note=cex_note,
    )

    messages = build_messages(
        query,
        intent=intent,
        rag_chunks=rag_chunks or None,
        tool_ctx=tool_ctx,
        reply_in_shona=is_shona,
        history=history,
    )
    return {
        "intent": intent,
        "messages": messages,
        "sources": sources,
        "sympy_result": tool_ctx.sympy_result,
        "sympy_error": tool_ctx.sympy_error,
        "counterexample": cex_info,
        "canned_answer": canned,
    }


def check_proof(answer: str) -> dict | None:
    """Verification layer 3: extract the ```lean block from a proof answer
    and check it with the TheoriaKit verifier (one repair round via the LLM).

    Runs strictly AFTER generation so Lean's RAM spike never coexists with
    decoding. Returns None when there is nothing to check.
    """
    source = extract_lean_block(answer)
    if source is None:
        return None
    if not lean_available():
        return {"status": "unavailable", "source": source}

    def repair(bad_source: str, errors: str) -> str | None:
        messages = [
            {
                "role": "system",
                "content": (
                    "You fix Lean 4 proofs. Use only core tactics (rfl, simp, "
                    "decide, omega, induction, exact). Prefer `by omega` for "
                    "Nat arithmetic. Never use begin/end. Reply with ONLY the "
                    "corrected code in a ```lean block."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"This Lean 4 proof fails:\n```lean\n{bad_source}\n```\n\n"
                    f"Compiler errors:\n{errors}\n\nFix it."
                ),
            },
        ]
        try:
            reply = run_chat(messages, config=InferenceConfig(max_tokens=512))
            return extract_lean_block(reply.text)
        except Exception:  # noqa: BLE001 — repair is best-effort
            return None

    result = verify_with_repair(source, repair_fn=repair)
    return {
        "status": "verified" if result.success else "failed",
        "output": result.output,
        "attempts": result.attempts,
        "source": result.source or source,
    }


def ask(
    query: str,
    use_rag: bool = True,
    config: InferenceConfig | None = None,
    lang: str = "en",
) -> AskResult:
    ctx = prepare(query, use_rag=use_rag, lang=lang)
    intent: Intent = ctx["intent"]

    if ctx["canned_answer"]:
        return AskResult(
            answer=ctx["canned_answer"],
            intent=intent.value,
            backend="i18n-canned",
        )

    cfg = config or InferenceConfig()
    if intent == Intent.CHITCHAT:
        cfg = replace(cfg, max_tokens=CHITCHAT_MAX_TOKENS)

    try:
        inference = run_chat(ctx["messages"], config=cfg)
        answer = inference.text
        tps = inference.tokens_per_second
        elapsed = inference.elapsed_s
        backend = inference.backend
    except Exception as exc:  # noqa: BLE001 — never leave the user hanging
        if ctx["sympy_result"]:
            answer = (
                f"Exact result (SymPy): {ctx['sympy_result']}\n"
                f"(Language model unavailable: {exc})"
            )
        else:
            answer = f"Inference failed: {exc}"
        tps = None
        elapsed = None
        backend = "sympy-fallback"

    lean_info = check_proof(answer) if intent == Intent.PROVE else None

    return AskResult(
        answer=answer,
        intent=intent.value,
        sources=ctx["sources"],
        sympy_result=ctx["sympy_result"],
        sympy_error=ctx["sympy_error"],
        counterexample=ctx["counterexample"],
        lean=lean_info,
        prompt=str(ctx["messages"]),
        tokens_per_second=tps,
        elapsed_s=elapsed,
        backend=backend,
    )
