#!/usr/bin/env bash
# Clone and build llama.cpp with llama-cli and llama-bench for ADTC profiling.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
LLAMA_DIR="$ROOT/inference/llama.cpp"
BUILD_DIR="$LLAMA_DIR/build"

if [[ ! -d "$LLAMA_DIR/.git" ]]; then
  echo "Cloning llama.cpp..."
  git clone --depth 1 https://github.com/ggerganov/llama.cpp.git "$LLAMA_DIR"
fi

echo "Building llama.cpp..."
cmake -S "$LLAMA_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD_DIR" -j "$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"

BIN_DIR="$BUILD_DIR/bin"
echo ""
echo "Build complete. Binaries:"
ls -la "$BIN_DIR"/llama-cli "$BIN_DIR"/llama-bench 2>/dev/null || ls -la "$BUILD_DIR"/llama-cli "$BUILD_DIR"/llama-bench 2>/dev/null || true
echo ""
echo "Add to PATH for profiling:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
