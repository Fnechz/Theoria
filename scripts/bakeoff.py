#!/usr/bin/env python3
"""Score candidate GGUF models with the official ADTC formula.

Runs llama-bench on each candidate in model/candidates/, measures peak RSS,
and reports the resulting S_perf / S_eff contribution so the model choice is
made on measurements rather than intuition.

Usage:
    python scripts/bakeoff.py
"""

from __future__ import annotations

import argparse
import re
import resource
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_DIR = ROOT / "model" / "candidates"
BIN_DIR = ROOT / "inference" / "llama.cpp" / "build" / "bin"

TPS_REFERENCE = 15.0
RAM_LIMIT_GB = 7.0

# llama-bench prints a markdown table; the tg row carries generation speed.
_ROW = re.compile(r"\|\s*([\d.]+)\s*±\s*[\d.]+\s*\|\s*$")


@dataclass
class Result:
    name: str
    size_gb: float
    tps: float
    peak_rss_gb: float

    @property
    def s_perf(self) -> float:
        return min(self.tps / TPS_REFERENCE, 1.0) * 100

    @property
    def s_eff(self) -> float:
        return max(0.0, (RAM_LIMIT_GB - self.peak_rss_gb) / RAM_LIMIT_GB) * 100

    @property
    def mechanical_points(self) -> float:
        """The 50 points available from speed and efficiency combined."""
        return 0.30 * self.s_perf + 0.20 * self.s_eff


def peak_child_rss_gb() -> float:
    raw = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # macOS reports bytes, Linux reports kilobytes.
    divisor = 1024**3 if sys.platform == "darwin" else 1024**2
    return raw / divisor


def bench(model: Path, threads: int, ctx: int) -> tuple[float, float]:
    binary = BIN_DIR / "llama-bench"
    if not binary.is_file():
        raise FileNotFoundError(f"llama-bench not found at {binary}")

    before = peak_child_rss_gb()
    proc = subprocess.run(
        [
            str(binary),
            "-m", str(model),
            "-p", "512",
            "-n", "128",
            "-t", str(threads),
            "-r", "2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "llama-bench failed")

    after = peak_child_rss_gb()

    speeds = [float(m.group(1)) for m in (_ROW.search(l) for l in proc.stdout.splitlines()) if m]
    if not speeds:
        raise RuntimeError(f"could not parse llama-bench output:\n{proc.stdout}")

    # Prompt processing is the faster figure; generation is what ADTC scores.
    tps = min(speeds)
    return tps, max(after - before, after)


def main() -> int:
    parser = argparse.ArgumentParser(description="ADTC model bake-off")
    parser.add_argument("--threads", type=int, default=4, help="target laptop has 4 vCPU")
    parser.add_argument("--ctx", type=int, default=1024)
    args = parser.parse_args()

    models = sorted(CANDIDATE_DIR.glob("*.gguf"))
    if not models:
        print(f"No candidates in {CANDIDATE_DIR}. Run: bash scripts/download_candidates.sh")
        return 1

    results: list[Result] = []
    for model in models:
        print(f"Benchmarking {model.name} ...", flush=True)
        try:
            tps, rss = bench(model, args.threads, args.ctx)
        except Exception as exc:  # noqa: BLE001 — report and continue the sweep
            print(f"  failed: {exc}")
            continue
        results.append(
            Result(
                name=model.name,
                size_gb=model.stat().st_size / 1024**3,
                tps=tps,
                peak_rss_gb=rss,
            )
        )

    if not results:
        return 1

    results.sort(key=lambda r: r.mechanical_points, reverse=True)

    print()
    print(f"{'model':<38} {'size':>7} {'t/s':>7} {'RAM':>7} {'S_perf':>7} {'S_eff':>7} {'pts/50':>7}")
    print("-" * 84)
    for r in results:
        print(
            f"{r.name:<38} {r.size_gb:>6.2f}G {r.tps:>7.1f} {r.peak_rss_gb:>6.2f}G "
            f"{r.s_perf:>7.1f} {r.s_eff:>7.1f} {r.mechanical_points:>7.1f}"
        )

    best = results[0]
    print()
    print(f"Winner on speed+efficiency: {best.name} ({best.mechanical_points:.1f}/50)")
    print("Accuracy is 50% of the total score — verify answer quality before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
