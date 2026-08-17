#!/usr/bin/env bash
# Run ADTC profiler locally against this submission.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BIN_DIR="$ROOT/inference/llama.cpp/build/bin"

export PATH="$BIN_DIR:$PATH"

if ! command -v llama-bench > /dev/null 2>&1; then
  echo "llama-bench not found. Run: bash scripts/build_llama.sh" >&2
  exit 1
fi

MODEL_PATH="$(python3 -c "import json; print(json.load(open('$ROOT/metadata.json'))['_runtime']['model_path'])")"
if [[ ! -f "$ROOT/$MODEL_PATH" ]]; then
  echo "Model not found at $MODEL_PATH. Run: bash download_model.sh" >&2
  exit 1
fi

if ! command -v adtc-profiler > /dev/null 2>&1; then
  echo "Installing adtc-profiler..."
  python3 -m pip install "git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git"
fi

SKIP_ACC="${1:-}"
ARGS=(run --submission "$ROOT" --mode participant --output "$ROOT/submission.json")
if [[ "$SKIP_ACC" == "--skip-accuracy" ]]; then
  ARGS+=(--skip-accuracy)
fi

adtc-profiler "${ARGS[@]}"
echo "Report written to $ROOT/submission.json"
