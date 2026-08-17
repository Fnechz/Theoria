"""SymPy symbolic math tool — load-bearing cross-disciplinary integration."""

from __future__ import annotations

import re
from dataclasses import dataclass

import sympy as sp


@dataclass
class SymPyResult:
    handled: bool
    expression: str | None = None
    result: str | None = None
    error: str | None = None


_MATH_KEYWORDS = re.compile(
    r"\b(solve|integrate|integral|antiderivative|differentiate|derivative|"
    r"simplify|factor|expand|limit|equation|polynomial|quadratic|calculus|algebra)\b",
    re.I,
)
_EQUATION = re.compile(r"([^=]+=[^=]+)")
_DERIVATIVE = re.compile(
    r"(?:find the\s+)?(?:derivative|differentiate)\s+(?:of\s+)?(.+?)(?:\s+with respect to\s+(\w+)|\s+w\.?r\.?t\.?\s+(\w+)|$)",
    re.I,
)
_INTEGRAL = re.compile(
    r"(?:integrate|integral of)\s+(.+?)(?:\s+with respect to\s+(\w+)|\s+w\.?r\.?t\.?\s+(\w+)|$)",
    re.I,
)
_SOLVE = re.compile(r"solve\s+(.+?)(?:\s+for\s+(\w+))?(?:\.|$)", re.I)


def should_use_sympy(query: str) -> bool:
    q = query.strip()
    if not q:
        return False
    if _MATH_KEYWORDS.search(q):
        return True
    if _EQUATION.search(q) and any(ch.isalpha() for ch in q):
        return True
    return False


def run_sympy(query: str) -> SymPyResult:
    if not should_use_sympy(query):
        return SymPyResult(handled=False)

    try:
        solve_match = _SOLVE.search(query)
        if solve_match:
            expr_text = solve_match.group(1).strip().rstrip(".")
            var_name = solve_match.group(2) or "x"
            return _solve_expression(expr_text, var_name)

        deriv_match = _DERIVATIVE.search(query)
        if deriv_match:
            expr_text = deriv_match.group(1).strip().rstrip(".")
            var_name = deriv_match.group(2) or deriv_match.group(3) or "x"
            return _differentiate(expr_text, var_name)

        integral_match = _INTEGRAL.search(query)
        if integral_match:
            expr_text = integral_match.group(1).strip().rstrip(".")
            var_name = integral_match.group(2) or integral_match.group(3) or "x"
            return _integrate_expr(expr_text, var_name)

        eq_match = _EQUATION.search(query)
        if eq_match:
            return _solve_expression(eq_match.group(1).strip(), "x")

        expr = _parse_expr(query)
        simplified = sp.simplify(expr)
        return SymPyResult(
            handled=True,
            expression=query,
            result=f"simplified = {simplified}",
        )
    except Exception as exc:  # noqa: BLE001
        return SymPyResult(handled=True, expression=query, error=str(exc))


def _solve_expression(expr_text: str, var_name: str) -> SymPyResult:
    var = sp.Symbol(var_name)
    local_dict: dict = {var_name: var}
    if "=" in expr_text:
        lhs_text, rhs_text = expr_text.split("=", 1)
        # Queries carry prose around the math ("the quadratic equation X = 0
        # and explain each step") — trim words from the outside inward.
        lhs = _tolerant_parse(lhs_text, local_dict, trim="leading")
        rhs = _tolerant_parse(rhs_text, local_dict, trim="trailing")
        eq = sp.Eq(lhs, rhs)
        sols = sp.solve(eq, var)
    else:
        sols = sp.solve(_tolerant_parse(expr_text, local_dict), var)
    return SymPyResult(
        handled=True,
        expression=expr_text,
        result=f"solutions for {var_name}: {sols}",
    )


def _differentiate(expr_text: str, var_name: str) -> SymPyResult:
    var = sp.Symbol(var_name)
    expr = _tolerant_parse(expr_text, {var_name: var})
    deriv = sp.diff(expr, var)
    return SymPyResult(
        handled=True,
        expression=expr_text,
        result=f"d/d{var_name}({expr}) = {deriv}",
    )


def _integrate_expr(expr_text: str, var_name: str) -> SymPyResult:
    var = sp.Symbol(var_name)
    # "integral of 3x^2 dx" — the differential is notation, not a factor.
    expr_text = re.sub(rf"\bd{var_name}\b", "", expr_text).strip()
    expr = _tolerant_parse(expr_text, {var_name: var})
    integral = sp.integrate(expr, var)
    return SymPyResult(
        handled=True,
        expression=expr_text,
        result=f"∫ {expr} d{var_name} = {integral} + C",
    )


def _tolerant_parse(
    text: str, local_dict: dict | None = None, trim: str = "both"
) -> sp.Expr:
    """Parse a math expression embedded in prose by trimming word tokens.

    trim='trailing' drops words from the end ("3x^2 dx" -> "3x^2"),
    'leading' from the start ("the equation x^2 - 5x + 6" -> "x^2 - 5x + 6"),
    'both' tries trailing first, then leading.
    """
    tokens = text.strip().split()
    orders = {
        "trailing": ["trailing"],
        "leading": ["leading"],
        "both": ["trailing", "leading"],
    }[trim]

    last_error: Exception | None = None
    for order in orders:
        for i in range(len(tokens)):
            kept = tokens[: len(tokens) - i] if order == "trailing" else tokens[i:]
            candidate = " ".join(kept)
            if not _looks_mathy(candidate):
                continue
            try:
                return _parse_expr(candidate, local_dict)
            except Exception as exc:  # noqa: BLE001 — keep trimming
                last_error = exc
    raise ValueError(f"could not parse a math expression from {text!r}") from last_error


def _looks_mathy(candidate: str) -> bool:
    """Reject bare English words that sympify would treat as symbols."""
    stripped = candidate.strip()
    if len(stripped) == 1 and stripped.isalpha():
        return True
    return bool(re.search(r"[\d^+\-*/=()]", stripped))


def _parse_expr(text: str, local_dict: dict | None = None) -> sp.Expr:
    cleaned = text.strip()
    cleaned = cleaned.replace("^", "**")
    cleaned = re.sub(r"\bpi\b", "pi", cleaned, flags=re.I)
    cleaned = _insert_implicit_multiplication(cleaned)
    return sp.sympify(cleaned, locals=local_dict or {})


def _insert_implicit_multiplication(text: str) -> str:
    """Convert math shorthand like 5x into valid Python (avoid breaking sin(...))."""
    text = re.sub(r"(\d)\s*([a-zA-Z])", r"\1*\2", text)
    text = re.sub(r"(\d)\s*\(", r"\1*(", text)
    text = re.sub(r"\)\s*([a-zA-Z(])", r")*\1", text)
    return text
