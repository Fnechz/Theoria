#!/usr/bin/env python3
"""Gather Lean / formalization training pairs for a *careful* future QLoRA.

This does NOT retrain anything. It writes curated JSONL buckets you can mix
into a future low-LR fine-tune (identity + Lean bridge only — never the
full 9k GSM8K soup that collapsed the last tune).

Sources (all public, offline after download):
  - hoskinson-center/proofnet  (NL statement + Lean formal statement)
  - HuggingFaceH4/minif2f or cat-searcher/minif2f-lean4
  - Hand-written TheoriaKit fill-sorry examples (core tactics)

Outputs:
  data/finetune/lean_bridge.jsonl
  data/finetune/sorry_fill.jsonl
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "finetune"

SYSTEM_LEAN = (
    "You are Theoria, an offline mathematics assistant. When asked to "
    "formalize a statement, produce a Lean 4 theorem statement inside a "
    "```lean code block. Use Lean 4 syntax only (no begin/end)."
)
SYSTEM_SORRY = (
    "You are Theoria, an offline mathematics assistant. Replace every sorry "
    "with a working Lean 4 proof using only core tactics (rfl, simp, decide, "
    "omega, induction, exact). Prefer `by omega` for Nat arithmetic. Reply "
    "with a short explanation and one ```lean block."
)


def row(system: str, user: str, assistant: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


def _load_proofnet() -> list[dict]:
    from datasets import load_dataset
    from huggingface_hub import HfApi

    files = HfApi().list_repo_files(
        "hoskinson-center/proofnet",
        repo_type="dataset",
        revision="refs/convert/parquet",
    )
    parquets = [
        f"hf://datasets/hoskinson-center/proofnet@refs%2Fconvert%2Fparquet/{f}"
        for f in files
        if f.endswith(".parquet")
    ]
    ds = load_dataset("parquet", data_files=parquets, split="train")
    rows = []
    for ex in ds:
        informal = (ex.get("nl_statement") or "").strip()
        formal = (ex.get("formal_statement") or "").strip()
        if informal and formal:
            rows.append(
                row(
                    SYSTEM_LEAN,
                    f"Formalize this statement in Lean 4:\n{informal}",
                    f"```lean\n{formal}\n```",
                )
            )
    return rows


def _load_minif2f(limit: int = 800) -> list[dict]:
    from datasets import load_dataset

    pairs: list[tuple[str, str]] = []
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
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {dataset_id}: {exc}")
    rows = []
    for informal, formal in pairs[:limit]:
        rows.append(
            row(
                SYSTEM_LEAN,
                f"Formalize this statement in Lean 4:\n{informal}",
                f"```lean\n{formal}\n```",
            )
        )
    return rows


# Hand-written fill-sorry curriculum matching TheoriaKit's core-tactic scope.
_SORRY_EXAMPLES: list[tuple[str, str, str]] = [
    (
        "theorem two_mul (n : Nat) : 2 * n = n + n := by sorry",
        "Nat multiplication by 2 unfolds to addition; `omega` closes linear Nat goals.",
        "theorem two_mul (n : Nat) : 2 * n = n + n := by omega",
    ),
    (
        "theorem add_zero' (n : Nat) : n + 0 = n := by sorry",
        "`n + 0` is definitionally `n`, so `rfl` works.",
        "theorem add_zero' (n : Nat) : n + 0 = n := rfl",
    ),
    (
        "theorem succ_pos' (n : Nat) : 0 < n + 1 := by sorry",
        "Successor is always positive; `omega` proves the inequality.",
        "theorem succ_pos' (n : Nat) : 0 < n + 1 := by omega",
    ),
    (
        "theorem even_add (a b : Nat) (ha : a % 2 = 0) (hb : b % 2 = 0) : (a + b) % 2 = 0 := by sorry",
        "Parity of a sum of even numbers is even; `omega` handles modular Nat arithmetic.",
        "theorem even_add (a b : Nat) (ha : a % 2 = 0) (hb : b % 2 = 0) : (a + b) % 2 = 0 := by omega",
    ),
    (
        "theorem mul_one' (n : Nat) : n * 1 = n := by sorry",
        "`n * 1` simplifies to `n` by the Nat simp lemmas.",
        "theorem mul_one' (n : Nat) : n * 1 = n := by simp",
    ),
    (
        "theorem le_add_right' (a b : Nat) : a ≤ a + b := by sorry",
        "Adding a natural cannot decrease a value; `omega` proves it.",
        "theorem le_add_right' (a b : Nat) : a ≤ a + b := by omega",
    ),
    (
        "theorem add_comm' (a b : Nat) : a + b = b + a := by sorry",
        "Use the library lemma for Nat commutativity.",
        "theorem add_comm' (a b : Nat) : a + b = b + a := Nat.add_comm a b",
    ),
    (
        "theorem zero_add' (n : Nat) : 0 + n = n := by sorry",
        "`0 + n` simplifies by simp.",
        "theorem zero_add' (n : Nat) : 0 + n = n := by simp",
    ),
]


def sorry_rows(upsample: int = 8) -> list[dict]:
    rows = []
    for stub, idea, filled in _SORRY_EXAMPLES:
        user = f"Fill the sorry in this Lean 4 theorem:\n```lean\n{stub}\n```"
        assistant = f"{idea}\n\n```lean\n{filled}\n```"
        rows.append(row(SYSTEM_SORRY, user, assistant))
    return rows * upsample


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} -> {path}")


def main() -> int:
    bridge: list[dict] = []
    try:
        bridge.extend(_load_proofnet())
        print(f"proofnet: {len(bridge)}")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] proofnet failed: {exc}")
    try:
        mf = _load_minif2f()
        print(f"minif2f: {len(mf)}")
        bridge.extend(mf)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] minif2f failed: {exc}")

    random.Random(42).shuffle(bridge)
    write_jsonl(OUT_DIR / "lean_bridge.jsonl", bridge)

    sorry = sorry_rows()
    random.Random(42).shuffle(sorry)
    write_jsonl(OUT_DIR / "sorry_fill.jsonl", sorry)

    print(
        "\nNext (careful retrain only): mix these with identity seeds, "
        "lr≈5e-5, max 1 epoch, abort if GSM8K/identity probes regress."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
