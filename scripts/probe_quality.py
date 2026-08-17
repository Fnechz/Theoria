#!/usr/bin/env python3
"""Quality probes for the model bake-off.

For each candidate GGUF, starts llama-server, runs identity/chitchat, math,
and science probes through the chat endpoint (thinking disabled), and prints
answers plus per-probe throughput so accuracy can be judged side by side.

Usage:
    python scripts/probe_quality.py [--model PATH ...]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_DIR = ROOT / "model" / "candidates"
SERVER_BIN = ROOT / "inference" / "llama.cpp" / "build" / "bin" / "llama-server"
PORT = 8099

PROBES = [
    ("chitchat", "hello"),
    ("chitchat", "what is your name?"),
    ("math", "What is 2 + 2?"),
    ("math", "Solve x^2 - 5x + 6 = 0. Show each step briefly."),
    ("math", "Find the derivative of sin(x^2) with respect to x."),
    ("math", "A candle burns 2 cm per hour. How much shorter is it after 4 hours?"),
    ("math", "Compute the integral of 3x^2 dx."),
    ("science", "Why does ice float on water? Answer in 3 sentences."),
    ("science", "State Newton's second law and give one everyday example."),
    ("science", "What is photosynthesis? Answer briefly."),
    ("proof", "Prove that the sum of two even numbers is even."),
    ("proof", "Prove or disprove: for all integers n, n^2 > n."),
    (
        "proof",
        "Prove that n + 0 = n for natural numbers, and include a Lean 4 "
        "theorem statement in a ```lean code block.",
    ),
]

SYSTEM = (
    "You are Theoria, an offline mathematics and science assistant. "
    "Answer accurately and concisely. For math, reason step by step and put "
    "the final answer within \\boxed{}. For greetings, just reply naturally."
)


def start_server(model: Path) -> subprocess.Popen:
    proc = subprocess.Popen(
        [
            str(SERVER_BIN), "-m", str(model), "-c", "4096",
            "--host", "127.0.0.1", "--port", str(PORT),
            "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
            "--jinja", "-t", "4",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200:
                    return proc
        except OSError:
            pass
        if proc.poll() is not None:
            raise RuntimeError(f"server died (code {proc.returncode})")
        time.sleep(0.5)
    proc.kill()
    raise TimeoutError("server did not become healthy")


def chat(prompt: str, max_tokens: int = 512) -> tuple[str, float | None]:
    payload = json.dumps(
        {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
    ).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    text = (data["choices"][0]["message"].get("content") or "").strip()
    tps = data.get("timings", {}).get("predicted_per_second")
    return text, tps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="append", type=Path)
    args = parser.parse_args()

    models = args.model or sorted(CANDIDATE_DIR.glob("*.gguf"))
    for model in models:
        print(f"\n{'=' * 78}\nMODEL: {model.name}\n{'=' * 78}")
        proc = start_server(model)
        try:
            for category, prompt in PROBES:
                text, tps = chat(prompt)
                short = text if len(text) <= 400 else text[:400] + " ...[truncated]"
                tps_s = f"{tps:.1f} t/s" if tps else "n/a"
                print(f"\n[{category}] {prompt}  ({tps_s})\n{short}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
