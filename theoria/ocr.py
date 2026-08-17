"""Photo-homework OCR — RAM-safe subprocess worker.

Design: the OCR engine (RapidOCR / ONNX, ~100-300 MB peak) runs in a
throwaway child process launched per photo. It prints extracted text as JSON
on stdout and exits, so its memory never coexists with the resident LLM for
more than a few seconds and never accumulates. The parent enforces a timeout.

Worker entry point:  python -m theoria.ocr <image_path>
Parent-side helper:  extract_text(image_path) -> {"text", "confidence", "lines"}
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

OCR_TIMEOUT_S = 90  # first run loads ONNX models from the package cache


def extract_text(image_path: str | Path) -> dict:
    """Run the OCR worker subprocess and return its parsed JSON result."""
    proc = subprocess.run(
        [sys.executable, "-m", "theoria.ocr", str(image_path)],
        capture_output=True,
        text=True,
        timeout=OCR_TIMEOUT_S,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "OCR worker failed")
    # The JSON payload is the last stdout line (engine may log above it).
    payload = proc.stdout.strip().splitlines()[-1]
    return json.loads(payload)


def _worker(image_path: str) -> dict:
    """Runs inside the throwaway subprocess only."""
    import logging

    logging.disable(logging.INFO)  # keep stdout clean for the JSON payload
    from rapidocr import RapidOCR

    engine = RapidOCR()
    output = engine(image_path)

    if output is None or output.txts is None or len(output.txts) == 0:
        return {"text": "", "confidence": 0.0, "lines": []}

    lines = []
    for box, text, score in zip(output.boxes, output.txts, output.scores):
        top = min(p[1] for p in box)
        left = min(p[0] for p in box)
        lines.append({"text": text, "confidence": float(score), "top": top, "left": left})

    # Reading order: top-to-bottom, then left-to-right.
    lines.sort(key=lambda l: (l["top"], l["left"]))
    text = "\n".join(l["text"] for l in lines)
    confidence = sum(l["confidence"] for l in lines) / len(lines)
    return {
        "text": text,
        "confidence": round(confidence, 3),
        "lines": [{"text": l["text"], "confidence": round(l["confidence"], 3)} for l in lines],
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m theoria.ocr <image_path>", file=sys.stderr)
        return 2
    try:
        print(json.dumps(_worker(sys.argv[1]), ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 — surface to parent via stderr
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
