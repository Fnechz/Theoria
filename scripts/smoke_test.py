"""Bounded end-to-end smoke test: warm server, then timed queries.

Run: .venv/bin/python scripts/smoke_test.py
"""

from __future__ import annotations

import time

from theoria.inference import InferenceConfig, warm_up
from theoria.pipeline import ask

QUERIES = [
    "What is 2 + 2?",
    "Solve the quadratic equation x^2 - 5x + 6 = 0 and explain each step.",
    "Find the derivative of sin(x^2) with respect to x and show the chain rule steps.",
]


def main() -> None:
    cfg = InferenceConfig(max_tokens=384, timeout_s=90)

    t0 = time.monotonic()
    warm_up(cfg)
    print(f"[warm-up] model loaded in {time.monotonic() - t0:.1f}s\n")

    for query in QUERIES:
        t0 = time.monotonic()
        result = ask(query, config=cfg)
        wall = time.monotonic() - t0

        print(f"Q: {query}")
        print(
            f"   backend={result.backend}  wall={wall:.1f}s  "
            f"tps={result.tokens_per_second}  sympy={result.sympy_result!r}"
        )
        answer = result.answer
        if len(answer) > 600:
            answer = answer[:600] + f" ...[{len(result.answer)} chars total]"
        print(f"A: {answer}\n{'-' * 70}")


if __name__ == "__main__":
    main()
