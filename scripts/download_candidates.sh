#!/usr/bin/env bash
# Download bake-off candidates into model/candidates/.
# Uses huggingface-cli (more reliable than raw curl on HF CDN).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DIR="$ROOT/model/candidates"

mkdir -p "$DIR"
cd "$DIR"

# Activate venv if present so huggingface-cli is on PATH
if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

if ! command -v huggingface-cli > /dev/null 2>&1 && ! command -v hf > /dev/null 2>&1; then
  echo "error: huggingface-cli not found. Run: pip install huggingface-hub" >&2
  exit 1
fi

HF_CMD="huggingface-cli"
command -v hf > /dev/null 2>&1 && HF_CMD="hf"

# Clean incomplete curl leftovers so hf can start clean
rm -f "$DIR"/*.partial 2>/dev/null || true

# Bake-off is Qwen2.5-Math-1.5B Q8_0 (copied from model/, no re-download)
# vs Qwen3-1.7B Q8_0. Quantization comparisons come later, after the winner
# is chosen — don't burn bandwidth on variants that can't win the gate.

echo "=== [1/2] Qwen2.5-Math-1.5B-Instruct Q8_0 (reuse local copy) ==="
if [[ -f "$DIR/qwen2.5-math-1.5b-q8_0.gguf" ]]; then
  echo "[skip] already present"
elif [[ -f "$ROOT/model/Qwen2.5-Math-1.5B-Instruct-Q8_0.gguf" ]]; then
  cp "$ROOT/model/Qwen2.5-Math-1.5B-Instruct-Q8_0.gguf" "$DIR/qwen2.5-math-1.5b-q8_0.gguf"
  echo "[copied] from model/"
else
  $HF_CMD download QuantFactory/Qwen2.5-Math-1.5B-Instruct-GGUF \
    Qwen2.5-Math-1.5B-Instruct.Q8_0.gguf \
    --local-dir "$DIR"
  mv -f "$DIR/Qwen2.5-Math-1.5B-Instruct.Q8_0.gguf" "$DIR/qwen2.5-math-1.5b-q8_0.gguf"
  echo "[done] $(du -h "$DIR/qwen2.5-math-1.5b-q8_0.gguf" | cut -f1)"
fi

echo "=== [2/2] Qwen3-1.7B Q8_0 (~1.8 GB) ==="
if [[ -f "$DIR/qwen3-1.7b-q8_0.gguf" ]]; then
  echo "[skip] already present"
else
  $HF_CMD download Qwen/Qwen3-1.7B-GGUF \
    Qwen3-1.7B-Q8_0.gguf \
    --local-dir "$DIR"
  mv -f "$DIR/Qwen3-1.7B-Q8_0.gguf" "$DIR/qwen3-1.7b-q8_0.gguf"
  echo "[done] $(du -h "$DIR/qwen3-1.7b-q8_0.gguf" | cut -f1)"
fi

echo ""
echo "Candidates ready:"
ls -lh "$DIR"/*.gguf
