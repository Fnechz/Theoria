#!/usr/bin/env bash
# Install Theoria ship weights (theoria-v3 Q4_K_M) with visible progress.
#
# Primary path for local/dev: copy/symlink from model/candidates/ after Colab.
# Gate 1 still needs a public URL — set THEORIA_GGUF_URL when the GGUF is hosted.
#
# Prefers aria2c (16 connections) > curl (HTTP/1.1 + resume).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
MODEL_DIR="$ROOT/model"
CAND_DIR="$MODEL_DIR/candidates"
mkdir -p "$MODEL_DIR" "$CAND_DIR"

# Ship model (ADTC VM 2026-08-13): theoria-v3 Q4_K_M — ~18 t/s, ~1880 MB peak,
# S_perf=100. Beats Q8 (~12.6 t/s) and matches mikromini speed without its
# quality failures (thinking leak, false n^2>n proof).
PRIMARY_NAME="theoria-v3-q4_k_m.gguf"
PRIMARY_OUT="$MODEL_DIR/$PRIMARY_NAME"
CANDIDATE_SRC="$CAND_DIR/$PRIMARY_NAME"
# Public ship weights (uploaded 2026-08-17). Env override still wins.
PRIMARY_URL="${THEORIA_GGUF_URL:-https://huggingface.co/fnechz/theoria-v3-q4_k_m/resolve/main/theoria-v3-q4_k_m.gguf}"

download_file() {
  local url="$1"
  local out="$2"
  local label="$3"

  if [[ -f "$out" ]]; then
    echo "[skip] $label already at $out ($(du -h "$out" | cut -f1))"
    return 0
  fi

  echo ""
  echo "============================================================"
  echo " Downloading: $label"
  echo " Target:      $out"
  echo "============================================================"

  local partial="$out.partial"

  if command -v aria2c > /dev/null 2>&1; then
    aria2c \
      --max-connection-per-server=16 \
      --split=16 \
      --min-split-size=1M \
      --continue=true \
      --allow-overwrite=true \
      --auto-file-renaming=false \
      --console-log-level=notice \
      --summary-interval=3 \
      --dir="$(dirname "$out")" \
      --out="$(basename "$partial")" \
      "$url"
    mv -f "$partial" "$out"
  elif command -v curl > /dev/null 2>&1; then
    curl -L --fail --http1.1 --retry 8 --retry-all-errors --retry-delay 3 \
      --continue-at - \
      --progress-bar \
      -o "$partial" \
      "$url"
    mv -f "$partial" "$out"
  else
    echo "error: need aria2c or curl" >&2
    exit 1
  fi

  if [[ ! -f "$out" ]]; then
    echo "error: expected file missing: $out" >&2
    ls -la "$(dirname "$out")" >&2
    exit 1
  fi

  echo "[done] $label — $(du -h "$out" | cut -f1)"
}

install_primary() {
  if [[ -f "$PRIMARY_OUT" ]] || [[ -L "$PRIMARY_OUT" ]]; then
    echo "[skip] PRIMARY already at $PRIMARY_OUT ($(du -h "$PRIMARY_OUT" | cut -f1))"
    return 0
  fi

  if [[ -f "$CANDIDATE_SRC" ]]; then
    echo "[link] $CANDIDATE_SRC -> $PRIMARY_OUT"
    ln -sfn "candidates/$PRIMARY_NAME" "$PRIMARY_OUT"
    return 0
  fi

  if [[ -n "$PRIMARY_URL" ]]; then
    download_file "$PRIMARY_URL" "$PRIMARY_OUT" "PRIMARY theoria-v3 Q4_K_M (~1.03 GiB)"
    return 0
  fi

  cat >&2 <<EOF
error: ship GGUF not found.

Place it at either:
  $CANDIDATE_SRC
  $PRIMARY_OUT

Or publish it and re-run:
  THEORIA_GGUF_URL='https://...' bash download_model.sh

EOF
  exit 1
}

MODE="${1:-primary}"

install_primary

# Keep candidates/ in sync for bake-off scripts
if [[ -f "$PRIMARY_OUT" && ! -f "$CANDIDATE_SRC" ]]; then
  ln -sfn "../$PRIMARY_NAME" "$CANDIDATE_SRC" 2>/dev/null \
    || cp -n "$PRIMARY_OUT" "$CANDIDATE_SRC" 2>/dev/null \
    || true
fi

if [[ "$MODE" == "--all" ]]; then
  download_file \
    "https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf" \
    "$CAND_DIR/qwen3-1.7b-q4_k_m.gguf" \
    "CANDIDATE official Qwen3-1.7B Q4_K_M (~1.0 GB)"
  download_file \
    "https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q8_0.gguf" \
    "$CAND_DIR/qwen3-1.7b-q8_0.gguf" \
    "CANDIDATE official Qwen3-1.7B Q8_0 (~1.8 GB)"
fi

echo ""
echo "Ready. Model path for metadata.json:"
echo "  $PRIMARY_OUT"
ls -lh "$PRIMARY_OUT"
