#!/usr/bin/env bash
# Install the Lean 4 toolchain for TheoriaKit (one-time, needs network).
# After this completes, proof verification is fully offline.
#
# Disk budget: elan + one pinned toolchain ~1.5 GB. No Mathlib.
set -euo pipefail

cd "$(dirname "$0")/.."
KIT_DIR="lean/TheoriaKit"

if ! command -v elan >/dev/null 2>&1 && [ ! -x "$HOME/.elan/bin/elan" ]; then
  echo "[1/3] Installing elan (Lean toolchain manager)..."
  curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --default-toolchain none
else
  echo "[1/3] elan already installed"
fi

export PATH="$HOME/.elan/bin:$PATH"

echo "[2/3] Installing the pinned toolchain ($(cat "$KIT_DIR/lean-toolchain"))..."
elan toolchain install "$(cat "$KIT_DIR/lean-toolchain")" || true

echo "[3/3] Building TheoriaKit (compiles the lemma kit once)..."
cd "$KIT_DIR"
lake build

echo
echo "Done. Verify with:  cd $KIT_DIR && echo 'theorem t (n : Nat) : n + 0 = n := rfl' > /tmp/s.lean && lake env lean /tmp/s.lean"
echo "Theoria will now show 'Formally verified (Lean 4)' badges on proof answers."
