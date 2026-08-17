"""Resolve paths and configuration for Theoria."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_metadata() -> dict:
    path = ROOT / "metadata.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def model_path() -> Path:
    meta = load_metadata()
    return ROOT / meta["_runtime"]["model_path"]


def llama_cli_path() -> Path:
    return _llama_binary("llama-cli", "THEORIA_LLAMA_CLI")


def llama_server_path() -> Path:
    return _llama_binary("llama-server", "THEORIA_LLAMA_SERVER")


def _llama_binary(name: str, env_var: str) -> Path:
    env = os.environ.get(env_var)
    if env:
        return Path(env)
    candidates = [
        ROOT / f"inference/llama.cpp/build/bin/{name}",
        ROOT / f"inference/llama.cpp/build/{name}",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = _which(name)
    if found:
        return Path(found)
    raise FileNotFoundError(
        f"{name} not found. Run: bash scripts/build_llama.sh or set {env_var}"
    )


def rag_db_path() -> Path:
    return ROOT / "rag" / "theoria.db"


def static_dir() -> Path:
    return ROOT / "static"


def data_dir() -> Path:
    return ROOT / "data"


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)
