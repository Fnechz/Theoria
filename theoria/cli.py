"""CLI entry point for Theoria."""

from __future__ import annotations

import argparse
import json
import sys

from theoria.pipeline import ask
from theoria.tools.sympy_solver import run_sympy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Theoria — offline math & science assistant (ADTC 2026)"
    )
    parser.add_argument("query", nargs="?", help="Question to ask")
    parser.add_argument("--no-rag", action="store_true", help="Disable retrieval")
    parser.add_argument(
        "--sympy-only",
        action="store_true",
        help="Run SymPy only (skip LLM, fast for math checks)",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--lang", default="en", choices=["en", "sn"], help="Language")
    parser.add_argument(
        "--warm",
        action="store_true",
        help="Load the model into a resident server and exit",
    )
    args = parser.parse_args(argv)

    if args.warm:
        from theoria.inference import warm_up

        warm_up()
        print("Model loaded and resident. Later queries will skip the load cost.")
        return 0

    if not args.query:
        parser.print_help()
        return 1

    if args.sympy_only:
        from theoria.i18n.shona import detect_shona, translate_shona_query

        q = args.query
        if args.lang == "sn" or detect_shona(q):
            q = translate_shona_query(q)
        sympy = run_sympy(q)
        payload = {
            "sympy_result": sympy.result,
            "sympy_error": sympy.error,
            "handled": sympy.handled,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            if sympy.result:
                print(f"SymPy: {sympy.result}")
            if sympy.error:
                print(f"SymPy note: {sympy.error}")
            if not sympy.handled:
                print("No symbolic math detected in query.")
        return 0

    result = ask(args.query, use_rag=not args.no_rag, lang=args.lang)

    if args.json:
        payload = {
            "answer": result.answer,
            "sympy_result": result.sympy_result,
            "sympy_error": result.sympy_error,
            "sources": result.sources,
            "tokens_per_second": result.tokens_per_second,
            "backend": result.backend,
        }
        print(json.dumps(payload, indent=2))
        return 0

    if result.sympy_result:
        print(f"SymPy: {result.sympy_result}")
    if result.sympy_error:
        print(f"SymPy note: {result.sympy_error}")
    if result.sources:
        print("\nSources:")
        for i, src in enumerate(result.sources, 1):
            print(f"  [{i}] ({src['source']}) {src['content'][:120]}...")
    print(f"\nAnswer:\n{result.answer}")
    if result.tokens_per_second:
        print(f"\n[{result.backend}: {result.tokens_per_second:.1f} tok/s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
