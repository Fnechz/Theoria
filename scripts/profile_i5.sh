#!/usr/bin/env bash
# Profile Theoria under an 8 GB RAM / 4-CPU ceiling (ADTC Standard Laptop).
# Safe over SSH — prefers sudo systemd-run (works without a desktop session).
#
# Usage (from repo root on the i5):
#   bash scripts/profile_i5.sh
#   bash scripts/profile_i5.sh --full
#   bash scripts/profile_i5.sh --skip-install
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FULL=0
SKIP_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    --skip-install) SKIP_INSTALL=1 ;;
  esac
done

echo "== Theoria ADTC profile (8 GB ceiling, 4 threads) =="
echo "host: $(uname -a)"
echo "mem:  $(free -h 2>/dev/null | awk '/Mem:/{print $2}' || echo unknown)"
echo "user: $(whoami)  ssh=${SSH_CONNECTION:-local}"
echo

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "[1/5] Python venv + deps"
  python3 -m venv .venv 2>/dev/null || true
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -U pip
  pip install -q -r requirements.txt
  pip install -q "git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git" || {
    echo "[warn] adtc-profiler pip install failed — continuing with local bakeoff"
  }
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[2/5] llama.cpp binaries"
if [[ ! -x inference/llama.cpp/build/bin/llama-bench ]]; then
  bash scripts/build_llama.sh
fi
export PATH="$ROOT/inference/llama.cpp/build/bin:$PATH"

echo "[3/5] Model weights"
bash download_model.sh

echo "[4/5] Local bake-off (4 threads)"
python scripts/bakeoff.py --threads 4 | tee bakeoff_i5.txt

echo "[5/5] Official ADTC profiler (memory-capped)"
OUT="submission.json"
PROFILER_CMD=(adtc-profiler run --submission . --mode participant --output "$OUT")
if [[ "$FULL" -eq 0 ]]; then
  PROFILER_CMD+=(--skip-accuracy)
  echo "(accuracy skipped; re-run with --full before Gate 1 submit)"
fi

# Cap strategies, in order. SSH note: --user scopes often fail without linger;
# system-scope (sudo) and Docker work reliably over SSH.
run_capped() {
  local mem="7500M"
  local cpu="400%"

  if command -v adtc-profiler >/dev/null 2>&1; then
    :
  else
    echo "[warn] adtc-profiler not on PATH; bakeoff_i5.txt is your report"
    return 0
  fi

  # 1) sudo systemd-run — best over SSH
  if command -v systemd-run >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    echo "Using: sudo systemd-run MemoryMax=$mem CPUQuota=$cpu"
    sudo systemd-run --scope --uid="$(id -u)" --gid="$(id -g)" \
      -p "MemoryMax=$mem" -p MemorySwapMax=0 -p "CPUQuota=$cpu" \
      --working-directory="$ROOT" \
      --setenv=PATH --setenv=HOME --setenv=VIRTUAL_ENV \
      -- "${PROFILER_CMD[@]}"
    return $?
  fi

  if command -v systemd-run >/dev/null 2>&1; then
    echo "Using: sudo systemd-run (will prompt for password)"
    sudo systemd-run --scope --uid="$(id -u)" --gid="$(id -g)" \
      -p "MemoryMax=$mem" -p MemorySwapMax=0 -p "CPUQuota=$cpu" \
      --working-directory="$ROOT" \
      --setenv=PATH --setenv=HOME \
      -- "${PROFILER_CMD[@]}"
    return $?
  fi

  # 2) Docker — also SSH-friendly
  if command -v docker >/dev/null 2>&1; then
    echo "Using: docker --memory=7.5g --cpus=4"
    mkdir -p "$ROOT/artifacts"
    docker run --rm --memory=7.5g --cpus=4 \
      -v "$ROOT:/submission:ro" \
      -v "$ROOT/artifacts:/artifacts" \
      -w /submission \
      python:3.12-slim bash -lc '
        pip install -q "git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git" &&
        adtc-profiler run --submission /submission --mode participant --output /artifacts/submission.json '"$([[ $FULL -eq 0 ]] && echo --skip-accuracy)"'
      '
    cp -f "$ROOT/artifacts/submission.json" "$ROOT/submission.json" 2>/dev/null || true
    return $?
  fi

  # 3) Uncapped fallback
  echo "[warn] No RAM cap available (install systemd or docker). Running UNCAPED."
  "${PROFILER_CMD[@]}"
}

run_capped || echo "[warn] profiler exited non-zero — inspect $OUT / bakeoff_i5.txt"

echo
echo "Done."
echo "  bakeoff:  $ROOT/bakeoff_i5.txt"
echo "  profiler: $ROOT/$OUT"
echo "Check: memory.peak_rss_mb < 7000"
