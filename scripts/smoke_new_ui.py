#!/usr/bin/env python3
"""Smoke tests for the new chat / TeX / Lean / photo flows."""
from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8080"


def stream_ask(payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}/api/ask/stream",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    text, think, lean, meta = "", "", None, None
    with urllib.request.urlopen(req, timeout=360) as resp:
        buf = ""
        for raw in resp:
            buf += raw.decode()
            while "\n\n" in buf:
                chunk, buf = buf.split("\n\n", 1)
                if not chunk.startswith("data: "):
                    continue
                ev = json.loads(chunk[6:])
                if ev["type"] == "meta":
                    meta = ev
                elif ev["type"] == "delta":
                    text += ev["text"]
                elif ev["type"] == "think":
                    think += ev["text"]
                elif ev["type"] == "lean":
                    lean = ev
    return {"text": text, "think": think, "lean": lean, "meta": meta}


def main() -> None:
    print("=== LaTeX document ===")
    r = stream_ask(
        {
            "query": (
                "Generate a short LaTeX document titled Quadratic Formula that "
                "derives the quadratic formula by completing the square. Put the "
                "whole file in a single ```latex code block."
            )
        }
    )
    has_doc = "\\documentclass" in r["text"]
    has_fence = "```latex" in r["text"] or "```tex" in r["text"]
    print(f"  intent={r['meta'] and r['meta'].get('intent')} fence={has_fence} documentclass={has_doc}")
    print(f"  ok={has_doc}")

    print("=== Fill sorry ===")
    r = stream_ask(
        {
            "query": (
                "Fill the sorry in this Lean 4 theorem:\n"
                "```lean\n"
                "theorem two_mul (n : Nat) : 2 * n = n + n := by sorry\n"
                "```"
            )
        }
    )
    lean = r["lean"] or {}
    print(f"  intent={r['meta'] and r['meta'].get('intent')}")
    print(f"  lean_status={lean.get('status')} attempts={lean.get('attempts')}")
    print(f"  has_lean_fence={'```lean' in r['text']}")
    print(f"  snippet={r['text'][:180].replace(chr(10), ' ')}")

    print("=== Chat list ===")
    with urllib.request.urlopen(f"{BASE}/api/chats") as resp:
        chats = json.loads(resp.read())["chats"]
    print(f"  {len(chats)} chats")
    for c in chats[:4]:
        print(f"  - {c['title'][:50]}")

    print("=== Photo attachment ===")
    r = stream_ask(
        {
            "query": "",
            "attachment_text": "Solve x^2 - 5x + 6 = 0",
            "attachment_name": "hw.png",
        }
    )
    print(f"  intent={r['meta'] and r['meta'].get('intent')}")
    print(f"  sympy={r['meta'] and r['meta'].get('sympy_result')}")
    print(f"  starts_ok={('x' in r['text'].lower() or 'quadratic' in r['text'].lower())}")


if __name__ == "__main__":
    main()
