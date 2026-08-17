#!/usr/bin/env python3
"""Build the Theoria QLoRA training set (v2 — proof-aware, Shona parked).

Buckets:
  A. Handwritten seeds (identity, chitchat, boundaries) x5 repeats
  B. GSM8K train subset — step-by-step word problems, boxed answers
  C. MATH (hendrycks) algebra + prealgebra + counting_and_probability
  D. ProofNet informal statement+proof pairs (proof-assistance language), x3
  E. NL -> Lean 4 bridge (miniF2F statements; ProofNet fallback)
  F. SciQ — quantitative science QA
  G. Counterexample generator (SymPy-verified refutations and validations)
  H. Tool-use traces (SymPy-verified constraint format used by the app)

Output: data/finetune/train.jsonl — one {"messages": [...]} per line, ready
for the Colab QLoRA notebook (training/theoria_qlora.ipynb).

Needs internet once (HF datasets). Run: python scripts/build_finetune_dataset.py
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = ROOT / "data" / "finetune" / "seed_identity.json"
OUT_FILE = ROOT / "data" / "finetune" / "train.jsonl"

SYSTEM_MATH = "Please reason step by step, and put your final answer within \\boxed{}."
SYSTEM_PERSONA = (
    "You are Theoria, an offline mathematics and science assistant built for "
    "the Africa Deep Tech 2026 Laptop LLM Challenge. You run entirely on the "
    "user's laptop with no internet."
)
SYSTEM_PROOF = (
    "You are Theoria, an offline mathematics assistant. Write clear, rigorous "
    "proofs step by step. State what is given, what must be shown, and justify "
    "each step."
)
SYSTEM_LEAN = (
    "You are Theoria, an offline mathematics assistant. When asked to "
    "formalize a statement, produce a Lean 4 theorem statement inside a "
    "```lean code block."
)

# Persona examples repeat so identity rows survive shuffling into the
# few-thousand-row math/science corpus without being drowned out.
SEED_REPEATS = 5

MAX_SOURCE_FRACTION = 0.35


def row(system: str, user: str, assistant: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


# ---------------------------------------------------------------- bucket A
def seed_rows() -> list[dict]:
    seeds = json.loads(SEED_FILE.read_text())
    rows: list[dict] = []
    # Shona parked for now — reintroduce once model-level Shona is viable.
    for section in ("identity_qa", "chitchat", "boundaries"):
        for pair in seeds[section]:
            rows.append(row(SYSTEM_PERSONA, pair["q"], pair["a"]))
    return rows * SEED_REPEATS


# ---------------------------------------------------------------- bucket B
def gsm8k_rows(limit: int) -> list[dict]:
    from datasets import load_dataset

    ds = load_dataset("openai/gsm8k", "main", split="train")
    rows = []
    for ex in ds.select(range(min(limit, len(ds)))):
        answer = ex["answer"]
        if "####" in answer:
            steps, final = answer.rsplit("####", 1)
            answer = f"{steps.strip()}\nThe final answer is \\boxed{{{final.strip()}}}."
        rows.append(row(SYSTEM_MATH, ex["question"], answer))
    return rows


# ---------------------------------------------------------------- bucket C
def math_rows(limit: int) -> list[dict]:
    from datasets import load_dataset

    configs = ["algebra", "prealgebra", "counting_and_probability"]
    per_config = max(1, limit // len(configs))
    rows: list[dict] = []
    for config in configs:
        ds = load_dataset("EleutherAI/hendrycks_math", config, split="train")
        for ex in ds.select(range(min(per_config, len(ds)))):
            rows.append(row(SYSTEM_MATH, ex["problem"], ex["solution"]))
    return rows


# ---------------------------------------------------------------- bucket D
def _load_hf_parquet(repo_id: str):
    """Load a script-based HF dataset via its auto-converted parquet branch
    (datasets>=3 removed loader-script support)."""
    from datasets import load_dataset
    from huggingface_hub import HfApi

    files = HfApi().list_repo_files(
        repo_id, repo_type="dataset", revision="refs/convert/parquet"
    )
    parquets = [
        f"hf://datasets/{repo_id}@refs%2Fconvert%2Fparquet/{f}"
        for f in files
        if f.endswith(".parquet")
    ]
    if not parquets:
        raise RuntimeError(f"no parquet files on {repo_id}")
    return load_dataset("parquet", data_files=parquets, split="train")


def proofnet_rows(upsample: int = 3) -> list[dict]:
    ds = _load_hf_parquet("hoskinson-center/proofnet")
    rows: list[dict] = []
    for ex in ds:
        statement = (ex.get("nl_statement") or "").strip()
        proof = (ex.get("nl_proof") or "").strip()
        if not statement or not proof:
            continue
        rows.append(row(SYSTEM_PROOF, f"Prove the following: {statement}", proof))
    return rows * upsample


# ---------------------------------------------------------------- bucket E
def lean_bridge_rows(limit: int) -> list[dict]:
    """NL problem -> Lean theorem statement pairs (the NL-to-Lean bridge)."""
    from datasets import load_dataset

    pairs: list[tuple[str, str]] = []

    # Preferred: miniF2F in Lean 4.
    for dataset_id in ("cat-searcher/minif2f-lean4", "HuggingFaceH4/minif2f"):
        try:
            for split in ("validation", "test"):
                ds = load_dataset(dataset_id, split=split)
                for ex in ds:
                    informal = (
                        ex.get("informal_stmt")
                        or ex.get("informal_statement")
                        or ex.get("nl_statement")
                        or ""
                    ).strip()
                    formal = (ex.get("formal_statement") or "").strip()
                    if informal and formal:
                        pairs.append((informal, formal))
            if pairs:
                break
        except Exception:  # noqa: BLE001 — try next mirror
            continue

    # Fallback: ProofNet ships Lean formal statements too.
    if not pairs:
        for split in ("validation", "test"):
            ds = load_dataset("hoskinson-center/proofnet", split=split)
            for ex in ds:
                informal = (ex.get("nl_statement") or "").strip()
                formal = (ex.get("formal_statement") or "").strip()
                if informal and formal:
                    pairs.append((informal, formal))

    rows = []
    for informal, formal in pairs[:limit]:
        user = f"Formalize this statement in Lean 4:\n{informal}"
        assistant = f"```lean\n{formal}\n```"
        rows.append(row(SYSTEM_LEAN, user, assistant))
    return rows


# ---------------------------------------------------------------- bucket F
def sciq_rows(limit: int) -> list[dict]:
    from datasets import load_dataset

    ds = load_dataset("allenai/sciq", split="train")
    rows = []
    for ex in ds.select(range(min(limit, len(ds)))):
        support = (ex.get("support") or "").strip()
        answer = ex["correct_answer"]
        if support:
            text = f"{support}\n\nSo the answer is: {answer}."
        else:
            text = f"The answer is: {answer}."
        rows.append(row(SYSTEM_PERSONA, ex["question"], text))
    return rows


# ---------------------------------------------------------------- bucket G
_CLASSIC_CLAIMS: list[tuple[str, str]] = [
    (
        "Is it true that (a + b)^2 = a^2 + b^2 for all real numbers a and b?",
        "Let's test the claim. Try a = 1, b = 1: (1 + 1)^2 = 4, but "
        "1^2 + 1^2 = 2, and 4 \u2260 2.\n\nThe claim is false. The correct "
        "expansion is (a + b)^2 = a^2 + 2ab + b^2; the identity only holds "
        "when 2ab = 0.\n\nCounterexample: \\boxed{a = 1,\\ b = 1}.",
    ),
    (
        "Is every prime number odd?",
        "Check the smallest primes: 2, 3, 5, 7. The number 2 is prime "
        "(its only divisors are 1 and 2) and it is even.\n\nThe claim is "
        "false: \\boxed{2} is an even prime — the only one.",
    ),
    (
        "Is it true that sqrt(x^2) = x for all real x?",
        "Test x = -3: sqrt((-3)^2) = sqrt(9) = 3, but x = -3, and 3 \u2260 -3."
        "\n\nThe claim is false. In general sqrt(x^2) = |x|.\n\n"
        "Counterexample: \\boxed{x = -3}.",
    ),
    (
        "Does dividing a number always make it smaller?",
        "Test dividing by a number between 0 and 1: 10 / 0.5 = 20, which is "
        "larger than 10. Dividing by a negative also flips the sign.\n\n"
        "The claim is false; division only shrinks a positive number when the "
        "divisor is greater than 1.\n\nCounterexample: \\boxed{10 \\div 0.5 = 20}.",
    ),
    (
        "Is it true that if n^2 is even then n is even?",
        "Suppose n is odd, so n = 2k + 1. Then n^2 = 4k^2 + 4k + 1 = "
        "2(2k^2 + 2k) + 1, which is odd. So an odd n gives an odd n^2 — "
        "contrapositively, if n^2 is even, n must be even.\n\nThe claim is "
        "true: \\boxed{\\text{if } n^2 \\text{ is even, then } n \\text{ is even}}.",
    ),
    (
        "Is it true that for all real x, x <= x^2?",
        "Test a value strictly between 0 and 1. Try x = 1/2: x^2 = 1/4, and "
        "1/2 > 1/4, so x <= x^2 fails.\n\nThe claim is false; for 0 < x < 1 "
        "we have x^2 < x.\n\nCounterexample: \\boxed{x = \\tfrac{1}{2}}.",
    ),
]


def counterexample_rows(limit: int, seed: int) -> list[dict]:
    """SymPy-verified claims: mostly refutable inequalities with a concrete
    counterexample, plus provably-true quadratic inequalities (discriminant
    argument) so the model learns both outcomes."""
    import sympy as sp

    rng = random.Random(seed)
    n = sp.Symbol("n")
    rows: list[dict] = []

    # Classic hand-written claims, lightly upsampled.
    for claim, answer in _CLASSIC_CLAIMS * 8:
        rows.append(row(SYSTEM_MATH, claim, answer))

    while len(rows) < limit:
        a = rng.choice([-3, -2, -1, 1, 2, 3])
        b, c, d, e = (rng.randint(-6, 6) for _ in range(4))
        lhs = a * n**2 + b * n + c
        rhs = d * n + e
        diff = sp.expand(lhs - rhs)
        claim = (
            f"Is it true that for all integers n, "
            f"{sp.sstr(lhs)} > {sp.sstr(rhs)}?"
        )

        cex = next(
            (v for v in range(-10, 11) if not bool(sp.Gt(lhs, rhs).subs(n, v))),
            None,
        )
        if cex is not None:
            lv, rv = lhs.subs(n, cex), rhs.subs(n, cex)
            answer = (
                f"Test candidate values of n.\n\nTry n = {cex}: the left side is "
                f"{sp.sstr(lhs)} = {lv} and the right side is {sp.sstr(rhs)} = {rv}. "
                f"Since {lv} > {rv} is false, the inequality fails at n = {cex}.\n\n"
                f"The claim is false. Counterexample: \\boxed{{n = {cex}}}."
            )
            rows.append(row(SYSTEM_MATH, claim, answer))
            continue

        # No counterexample in the scan — only keep it if we can PROVE truth.
        poly = sp.Poly(diff, n)
        if poly.degree() == 2:
            A, B, C = poly.all_coeffs()
            disc = B**2 - 4 * A * C
            if A > 0 and disc < 0:
                answer = (
                    f"Consider the difference D(n) = {sp.sstr(diff)}.\n\n"
                    f"This is a quadratic with positive leading coefficient "
                    f"{A} and discriminant ({B})^2 - 4({A})({C}) = {disc} < 0, "
                    f"so D(n) has no real roots and is always positive.\n\n"
                    f"Therefore {sp.sstr(lhs)} > {sp.sstr(rhs)} for every real "
                    f"n, in particular every integer.\n\nThe claim is true: "
                    f"\\boxed{{\\text{{the inequality holds for all integers }} n}}."
                )
                rows.append(row(SYSTEM_MATH, claim, answer))
    return rows[:limit]


# ---------------------------------------------------------------- bucket H
def tool_trace_rows(limit: int, seed: int) -> list[dict]:
    """Conversations in the app's exact verified-constraint prompt format so
    the tuned model cooperates with the SymPy badge."""
    import sympy as sp

    rng = random.Random(seed)
    x = sp.Symbol("x")
    rows: list[dict] = []

    # Quadratics with integer roots — the app's flagship flow.
    while len(rows) < int(limit * 0.6):
        r1, r2 = rng.randint(-9, 9), rng.randint(-9, 9)
        if r1 == r2:
            continue
        r1, r2 = sorted((r1, r2))
        poly = sp.expand((x - r1) * (x - r2))
        b_coef = -(r1 + r2)
        c_coef = r1 * r2
        system = (
            f"{SYSTEM_MATH}\n"
            f"A computer algebra system verified: solutions for x: [{r1}, {r2}]. "
            f"Your final answer must agree with this."
        )
        user = f"Solve {sp.sstr(poly)} = 0 and explain each step."
        assistant = (
            f"We need two numbers that multiply to {c_coef} and add to "
            f"{-b_coef}... those are {-r1} and {-r2} with signs flipped, i.e. "
            f"the factorization is (x - ({r1}))(x - ({r2})).\n\n"
            f"1. Factor: {sp.sstr(poly)} = (x - ({r1}))(x - ({r2})).\n"
            f"2. Set each factor to zero: x = {r1} or x = {r2}.\n"
            f"3. Check: both values satisfy the original equation, and they "
            f"match the verified result.\n\n"
            f"\\boxed{{x = {r1} \\text{{ or }} x = {r2}}}"
        )
        rows.append(row(system, user, assistant))

    # Derivatives with a verified result to agree with.
    inner_choices = [x**2, x**3, 2 * x, x**2 + 1, 3 * x]
    outer_choices = [sp.sin, sp.cos, sp.exp]
    while len(rows) < limit:
        inner = rng.choice(inner_choices)
        outer = rng.choice(outer_choices)
        f = outer(inner)
        df = sp.diff(f, x)
        system = (
            f"{SYSTEM_MATH}\n"
            f"A computer algebra system verified: d/dx({sp.sstr(f)}) = "
            f"{sp.sstr(df)}. Your final answer must agree with this."
        )
        user = f"Find the derivative of {sp.sstr(f)} with respect to x."
        assistant = (
            f"This is a composite function, so apply the chain rule.\n\n"
            f"1. Outer function: {outer.__name__}(u); inner function: "
            f"u = {sp.sstr(inner)}.\n"
            f"2. Derivative of the outer function evaluated at u, times "
            f"du/dx = {sp.sstr(sp.diff(inner, x))}.\n"
            f"3. Multiply: d/dx({sp.sstr(f)}) = {sp.sstr(df)}, matching the "
            f"verified result.\n\n\\boxed{{{sp.latex(df)}}}"
        )
        rows.append(row(system, user, assistant))
    return rows[:limit]


# ---------------------------------------------------------------- assembly
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gsm8k", type=int, default=3000)
    parser.add_argument("--math", type=int, default=1500)
    parser.add_argument("--sciq", type=int, default=1500)
    parser.add_argument("--lean-bridge", type=int, default=500)
    parser.add_argument("--counterexamples", type=int, default=800)
    parser.add_argument("--tool-traces", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--seeds-only",
        action="store_true",
        help="Skip HF downloads; emit only locally generated buckets.",
    )
    args = parser.parse_args()

    buckets: dict[str, list[dict]] = {
        "seeds": seed_rows(),
        "counterexamples": counterexample_rows(args.counterexamples, args.seed),
        "tool_traces": tool_trace_rows(args.tool_traces, args.seed),
    }

    if not args.seeds_only:
        remote = (
            ("gsm8k", lambda: gsm8k_rows(args.gsm8k)),
            ("math", lambda: math_rows(args.math)),
            ("proofnet", lambda: proofnet_rows(upsample=3)),
            ("lean_bridge", lambda: lean_bridge_rows(args.lean_bridge)),
            ("sciq", lambda: sciq_rows(args.sciq)),
        )
        for name, fn in remote:
            try:
                buckets[name] = fn()
            except Exception as exc:  # noqa: BLE001 — partial corpus still trains
                print(f"[warn] {name} failed ({exc}); continuing without it")
                buckets[name] = []

    # Auto-rebalance: truncate any bucket that dominates the mix (e.g. when a
    # remote source failed and GSM8K's share inflates past the cap).
    changed = True
    while changed:
        changed = False
        total = sum(len(b) for b in buckets.values())
        for name, bucket in buckets.items():
            cap = int(MAX_SOURCE_FRACTION * total)
            if len(bucket) > cap:
                print(f"[rebalance] trimming {name}: {len(bucket)} -> {cap}")
                buckets[name] = bucket[:cap]
                changed = True

    rows = [r for bucket in buckets.values() for r in bucket]
    total = len(rows)

    print(f"\n{'bucket':<18} {'rows':>6} {'share':>7}")
    print("-" * 34)
    for name, bucket in buckets.items():
        share = len(bucket) / total if total else 0
        print(f"{name:<18} {len(bucket):>6} {share:>6.1%}")

    assert total >= 2000, f"corpus too small to train on ({total} rows)"
    for name, bucket in buckets.items():
        assert len(bucket) / total <= MAX_SOURCE_FRACTION + 0.02, (
            f"{name} dominates the mix ({len(bucket)}/{total}); rebalance limits"
        )

    random.Random(args.seed).shuffle(rows)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nwrote {total} rows -> {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
