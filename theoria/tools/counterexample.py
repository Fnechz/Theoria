"""Counterexample search engine — verification layer 2.

For universal claims ("is it true that for all n, ..."), search small
domains for a violating assignment using SymPy. Pure Python, no extra RAM.
The finding is injected into the LLM prompt as a verified constraint and
surfaced in the UI as a badge.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

import sympy as sp

from theoria.tools.sympy_solver import _tolerant_parse

# Ordered so two-char operators match before their one-char prefixes.
_RELATION_SPAN = re.compile(
    r"([0-9a-zA-Z^*/+\-\s().|]+?)\s*(>=|<=|!=|>|<|=)\s*([0-9a-zA-Z^*/+\-\s().|]+)"
)

_REL_BUILDERS = {
    ">=": sp.Ge,
    "<=": sp.Le,
    "!=": sp.Ne,
    ">": sp.Gt,
    "<": sp.Lt,
    "=": sp.Eq,
}

# Integers catch most refutations; the fractions catch 0<x<1 traps and the
# negatives catch sign traps (sqrt(x^2)=x, |x| claims, ...).
_SCAN_VALUES = [sp.Integer(v) for v in range(-10, 11)] + [
    sp.Rational(1, 2),
    sp.Rational(-1, 2),
    sp.Rational(3, 2),
    sp.Rational(-3, 2),
]


@dataclass
class CounterexampleResult:
    handled: bool
    claim: str | None = None
    counterexample: dict | None = None
    verdict: str | None = None  # "refuted" | "no_counterexample"
    detail: str | None = None
    error: str | None = None


def search_counterexample(query: str) -> CounterexampleResult:
    try:
        relation, claim_text = _extract_relation(query)
    except Exception as exc:  # noqa: BLE001 — claim not machine-checkable
        return CounterexampleResult(handled=False, error=str(exc))
    if relation is None:
        return CounterexampleResult(handled=False)

    variables = sorted(relation.free_symbols, key=lambda s: s.name)
    if not variables:
        holds = bool(sp.simplify(relation))
        return CounterexampleResult(
            handled=True,
            claim=claim_text,
            verdict="no_counterexample" if holds else "refuted",
            counterexample=None if holds else {},
            detail="constant claim evaluated directly",
        )
    if len(variables) > 3:
        return CounterexampleResult(handled=False)

    values = _SCAN_VALUES if len(variables) <= 2 else [sp.Integer(v) for v in range(-3, 4)]

    for assignment in itertools.product(values, repeat=len(variables)):
        subs = dict(zip(variables, assignment))
        try:
            outcome = relation.subs(subs)
            if outcome not in (sp.true, sp.false):
                outcome = sp.simplify(outcome)
            if outcome == sp.false:
                return CounterexampleResult(
                    handled=True,
                    claim=claim_text,
                    verdict="refuted",
                    counterexample={str(k): str(v) for k, v in subs.items()},
                    detail=_violation_detail(relation, subs),
                )
        except Exception:  # noqa: BLE001 — undefined point (e.g. 1/0); skip
            continue

    var_names = ", ".join(v.name for v in variables)
    return CounterexampleResult(
        handled=True,
        claim=claim_text,
        verdict="no_counterexample",
        detail=(
            f"no counterexample found scanning {var_names} over integers "
            f"-10..10 and simple fractions (not a proof, but strong evidence)"
        ),
    )


def _extract_relation(query: str) -> tuple[sp.Basic | None, str | None]:
    """Find the mathematical relation embedded in the claim text."""
    text = query.replace("^", "**")

    best: tuple[sp.Basic, str] | None = None
    for match in _RELATION_SPAN.finditer(text):
        lhs_text, op, rhs_text = match.groups()
        # "==" written as "=" is fine; skip relations with empty math content.
        try:
            lhs = _tolerant_parse(lhs_text, trim="leading")
            rhs = _tolerant_parse(rhs_text, trim="trailing")
        except Exception:  # noqa: BLE001 — this span wasn't the claim
            continue
        relation = _REL_BUILDERS[op](lhs, rhs)
        claim = f"{sp.sstr(lhs)} {op} {sp.sstr(rhs)}"
        # Prefer the span with the most free symbols (the real claim).
        if best is None or len(relation.free_symbols) > len(best[0].free_symbols):
            best = (relation, claim)

    if best is None:
        return None, None
    return best


def _violation_detail(relation: sp.Basic, subs: dict) -> str:
    parts = [f"{k} = {v}" for k, v in subs.items()]
    lhs_v = relation.lhs.subs(subs)
    rhs_v = relation.rhs.subs(subs)
    return (
        f"at {', '.join(parts)}: left side = {sp.sstr(sp.nsimplify(lhs_v))}, "
        f"right side = {sp.sstr(sp.nsimplify(rhs_v))}, so the claim fails"
    )


def format_for_prompt(result: CounterexampleResult) -> str | None:
    """Verified constraint text injected into the system prompt."""
    if not result.handled:
        return None
    if result.verdict == "refuted":
        cex = ", ".join(f"{k} = {v}" for k, v in (result.counterexample or {}).items())
        return (
            f"A verified counterexample search REFUTED the claim "
            f"({result.claim}): it fails {result.detail}. "
            f"Your answer must conclude the claim is FALSE and present the "
            f"counterexample ({cex})."
        )
    return (
        f"A counterexample search over {result.detail} found NO counterexample "
        f"to the claim ({result.claim}). If you can, give a proof; otherwise "
        f"state the evidence carefully."
    )
