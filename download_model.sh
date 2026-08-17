#!/usr/bin/env bash
# Download Theoria's primary model weight for ADTC 2026 submission.
# Wrapper around scripts/download_weights.sh (visible progress + aria2/curl).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$HERE/scripts/download_weights.sh" primary
