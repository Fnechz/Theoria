"""Lean 4 verification via the TheoriaKit mini-kit — verification layer 3.

Runs `lake env lean` on a candidate proof in `lean/TheoriaKit/` as a
subprocess AFTER generation finishes (never concurrent with decoding), with
a hard timeout. Degrades gracefully to "unavailable" when the toolchain is
not installed (see scripts/setup_lean.sh).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from shutil import which

KIT_DIR = Path(__file__).resolve().parent.parent.parent / "lean" / "TheoriaKit"
ELAN_BIN = Path.home() / ".elan" / "bin"
LEAN_TIMEOUT_S = 60

_LEAN_BLOCK = re.compile(r"```lean\s*\n(.*?)```", re.DOTALL)

# Match "theorem name ... : stmt := <anything>" so we can swap the proof body.
_THEOREM_HEAD = re.compile(
    r"(?P<head>(?:theorem|lemma|example)\s+[\s\S]*?:=\s*)(?P<body>.*)",
    re.DOTALL,
)

_AUTO_TACTICS = ("by omega", "by simp", "by decide", "by rfl", "rfl")


@dataclass
class LeanResult:
    available: bool
    success: bool
    output: str
    attempts: int = 1
    source: str | None = None  # filled source when auto_fill succeeds


def _lake() -> str | None:
    lake = which("lake")
    if lake:
        return lake
    candidate = ELAN_BIN / "lake"
    return str(candidate) if candidate.exists() else None


def is_available() -> bool:
    return _lake() is not None and KIT_DIR.exists()


def extract_lean_block(text: str) -> str | None:
    """Pull the first ```lean fenced block out of a model answer."""
    match = _LEAN_BLOCK.search(text)
    return match.group(1).strip() if match else None


def auto_fill(source: str, timeout: int = 30) -> LeanResult | None:
    """Deterministic fill-the-sorry: keep the theorem statement, try a short
    list of core tactics. Returns the first that verifies, else None.

    This beats asking a 1.7B model to invent Lean 4 syntax — omega alone
    closes most Nat arithmetic goals in TheoriaKit's scope.
    """
    # Strip a leading import so we re-wrap cleanly in verify().
    body = re.sub(r"^\s*import\s+\S+\s*", "", source).strip()
    match = _THEOREM_HEAD.match(body)
    if not match:
        return None
    head = match.group("head")
    for tactic in _AUTO_TACTICS:
        candidate = f"{head}{tactic}"
        result = verify(candidate, timeout=timeout)
        if result.success:
            result.output = f"auto-filled with `{tactic}`"
            result.attempts = 1
            # Stash the working source on the result for callers.
            result.source = candidate  # type: ignore[attr-defined]
            return result
    return None


def verify(source: str, timeout: int = LEAN_TIMEOUT_S) -> LeanResult:
    lake = _lake()
    if lake is None or not KIT_DIR.exists():
        return LeanResult(
            available=False,
            success=False,
            output="Lean 4 toolchain not installed (run scripts/setup_lean.sh).",
        )

    if "sorry" in source or "admit" in source:
        return LeanResult(
            available=True, success=False, output="proof contains sorry/admit"
        )

    # `lake env lean` resolves `import TheoriaKit` against the built kit.
    body = source if source.lstrip().startswith("import") else f"import TheoriaKit\n\n{source}"
    env = dict(os.environ, PATH=f"{ELAN_BIN}:{os.environ.get('PATH', '')}")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".lean", delete=False, dir=KIT_DIR
    ) as tmp:
        tmp.write(body)
        scratch = Path(tmp.name)
    try:
        proc = subprocess.run(
            [lake, "env", "lean", str(scratch)],
            cwd=KIT_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        output = (proc.stdout + proc.stderr).strip()
        return LeanResult(
            available=True,
            success=proc.returncode == 0,
            output=output or "verified",
        )
    except subprocess.TimeoutExpired:
        return LeanResult(
            available=True, success=False, output=f"Lean timed out after {timeout}s"
        )
    finally:
        scratch.unlink(missing_ok=True)


def verify_with_repair(source: str, repair_fn=None, timeout: int = LEAN_TIMEOUT_S) -> LeanResult:
    """Verify; on failure try deterministic auto-fill, then one LLM repair.

    repair_fn(bad_source, lean_errors) -> new_source | None
    """
    result = verify(source, timeout=timeout)
    if result.success or not result.available:
        return result

    # Prefer a deterministic tactic over asking the LLM — faster and reliable
    # on TheoriaKit's Nat-arithmetic domain.
    filled = auto_fill(source, timeout=min(timeout, 30))
    if filled and filled.success:
        filled.attempts = 2
        return filled

    if repair_fn is None:
        return result

    repaired = repair_fn(source, result.output)
    if not repaired or repaired.strip() == source.strip():
        return result
    second = verify(repaired, timeout=timeout)
    if second.success:
        second.source = repaired
        second.attempts = 3
        return second
    # Last chance: auto-fill the LLM's repaired statement.
    filled = auto_fill(repaired, timeout=min(timeout, 30))
    if filled and filled.success:
        filled.attempts = 3
        return filled
    second.attempts = 3
    return second
