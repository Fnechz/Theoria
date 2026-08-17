"""Prompt templates: Theoria persona + intent-specific instructions."""

from __future__ import annotations

from dataclasses import dataclass

from theoria.router import Intent

# Every intent shares this identity so the assistant always knows who it is.
PERSONA = (
    "You are Theoria, an offline mathematics and science assistant built for "
    "the Africa Deep Tech 2026 Laptop LLM Challenge. You run entirely on the "
    "user's laptop with no internet. You explain math and science clearly, "
    "step by step, for students and engineers."
)

MATH_INSTRUCTIONS = (
    "Reason step by step and put the final answer within \\boxed{}."
)

SCIENCE_INSTRUCTIONS = (
    "Explain clearly and accurately. Use short paragraphs or numbered steps. "
    "State formulas in LaTeX where helpful."
)

CHITCHAT_INSTRUCTIONS = (
    "Reply naturally and briefly (1-3 sentences). Do not solve math unless "
    "asked. If greeted, greet back and offer to help with math or science."
)

PROOF_INSTRUCTIONS = (
    "Write a clear, rigorous step-by-step proof: state what is given, what "
    "must be shown, and justify every step. If the statement is simple "
    "arithmetic or logic, also include a Lean 4 formalization in a ```lean "
    "code block using only core tactics (rfl, simp, decide, omega, induction)."
)

# The base model drifts into Lean 3 syntax (begin/end, nat.*); a few canonical
# Lean 4 examples anchor the correct dialect far more reliably than prose.
LEAN4_FEWSHOT = (
    "Lean 4 syntax examples (core tactics only, no Mathlib, no begin/end):\n"
    "```lean\n"
    "theorem two_mul (n : Nat) : 2 * n = n + n := by omega\n\n"
    "theorem add_zero' (n : Nat) : n + 0 = n := rfl\n\n"
    "theorem even_add_even (a b : Nat) (ha : a % 2 = 0) (hb : b % 2 = 0) :\n"
    "    (a + b) % 2 = 0 := by omega\n\n"
    "theorem succ_pos' (n : Nat) : 0 < n + 1 := by omega\n"
    "```"
)

SORRY_INSTRUCTIONS = (
    "The user has a Lean 4 theorem containing `sorry`. Replace every sorry "
    "with a working proof using ONLY core Lean 4 tactics (rfl, simp, decide, "
    "omega, induction, exact). Prefer `by omega` for Nat arithmetic equalities "
    "and inequalities (e.g. 2 * n = n + n). Use `rfl` ONLY when both sides "
    "are definitionally identical (e.g. n + 0 = n). Briefly explain the proof "
    "idea in one or two sentences, then output the COMPLETE corrected theorem "
    "in a single ```lean code block. Do not change the theorem statement."
)

LATEX_DOC_INSTRUCTIONS = (
    "The user wants a LaTeX document. Output ONE complete, compilable file in "
    "a single ```latex code block: start with \\documentclass{article}, use "
    "\\usepackage{amsmath, amssymb}, include \\begin{document}...\\end{document}, "
    "and typeset all math properly."
)

REFUTE_INSTRUCTIONS = (
    "The user is asking whether a claim holds. Decide true or false. If "
    "false, present a concrete counterexample and verify it numerically. If "
    "true, give a proof or the strongest argument you can. Put the final "
    "verdict within \\boxed{}."
)


@dataclass
class ToolContext:
    sympy_result: str | None = None
    sympy_error: str | None = None
    counterexample_note: str | None = None


def wants_latex_doc(query: str) -> bool:
    q = query.lower()
    return any(
        cue in q
        for cue in (
            "latex document", "latex file", "tex document", "tex file",
            "in latex", "generate latex", "write latex", ".tex",
        )
    )


def is_sorry_request(query: str) -> bool:
    q = query.lower()
    return "sorry" in q and ("theorem" in q or "lean" in q or "```" in q)


def build_messages(
    query: str,
    intent: Intent = Intent.MATH,
    rag_chunks: list[str] | None = None,
    tool_ctx: ToolContext | None = None,
    reply_in_shona: bool = False,
    history: list[dict] | None = None,
) -> list[dict]:
    system_parts = [PERSONA]

    if reply_in_shona:
        from theoria.i18n.shona import shona_reply_instruction

        system_parts.append(shona_reply_instruction())

    if intent == Intent.CHITCHAT:
        system_parts.append(CHITCHAT_INSTRUCTIONS)
    elif intent == Intent.MATH:
        system_parts.append(MATH_INSTRUCTIONS)
    elif intent == Intent.PROVE:
        if is_sorry_request(query):
            system_parts.append(SORRY_INSTRUCTIONS)
        else:
            system_parts.append(PROOF_INSTRUCTIONS)
        system_parts.append(LEAN4_FEWSHOT)
    elif intent == Intent.REFUTE:
        system_parts.append(REFUTE_INSTRUCTIONS)
    else:
        system_parts.append(SCIENCE_INSTRUCTIONS)

    if wants_latex_doc(query):
        system_parts.append(LATEX_DOC_INSTRUCTIONS)

    if rag_chunks and intent != Intent.CHITCHAT:
        system_parts.append("Reference material (use only if relevant):")
        for i, chunk in enumerate(rag_chunks, 1):
            system_parts.append(f"[{i}] {chunk.strip()}")

    if tool_ctx and tool_ctx.sympy_result and intent == Intent.MATH:
        system_parts.append(
            f"A computer algebra system verified: {tool_ctx.sympy_result}. "
            "Your final answer must agree with this."
        )

    if tool_ctx and tool_ctx.counterexample_note and intent == Intent.REFUTE:
        system_parts.append(tool_ctx.counterexample_note)

    messages: list[dict] = [{"role": "system", "content": "\n".join(system_parts)}]
    for turn in history or []:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": query.strip()})
    return messages


def build_prompt(
    query: str,
    rag_chunks: list[str] | None = None,
    tool_ctx: ToolContext | None = None,
) -> str:
    """Flat prompt for the raw-completion fallback path."""
    parts: list[str] = [PERSONA]

    if rag_chunks:
        parts.append("\nReference material:")
        for i, chunk in enumerate(rag_chunks, 1):
            parts.append(f"[{i}] {chunk.strip()}")

    if tool_ctx and tool_ctx.sympy_result:
        parts.append(f"\nSymPy computed result: {tool_ctx.sympy_result}")

    parts.append(f"\nUser: {query.strip()}")
    parts.append("Assistant:")
    return "\n".join(parts)
