"""Inference against a resident llama.cpp model.

Primary path: llama-server /v1/chat/completions with the model's own chat
template, so the model emits its stop token and generation ends naturally.
Every call carries a hard timeout — nothing here can hang the app.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from theoria.llama_server import LlamaServer, ServerConfig


@dataclass
class InferenceConfig:
    # 4096 ctx with q8_0 KV cache costs ~0.5 GB for a 1.5-2B model — combined
    # peak stays ~2.6 GB, far under the 7 GB ADTC ceiling. 1024 generated
    # tokens is enough for a full proof (the 384 cap truncated Fermat).
    context_size: int = 4096
    max_tokens: int = 1024
    temperature: float = 0.2
    threads: int | None = None
    timeout_s: int = 180
    enable_thinking: bool = False


@dataclass
class InferenceResult:
    text: str
    tokens_per_second: float | None = None
    first_token_ms: float | None = None
    elapsed_s: float | None = None
    backend: str = "server"


def warm_up(config: InferenceConfig | None = None) -> None:
    """Load the model before the first user query so it does not pay the cost."""
    _server(config or InferenceConfig()).ensure_running()


def run_chat(messages: list[dict], config: InferenceConfig | None = None) -> InferenceResult:
    cfg = config or InferenceConfig()
    server = _server(cfg)

    started = time.monotonic()
    data = server.chat(
        messages,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        timeout=cfg.timeout_s,
        enable_thinking=cfg.enable_thinking,
    )
    elapsed = time.monotonic() - started

    choice = (data.get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content") or "").strip()

    timings = data.get("timings", {})
    return InferenceResult(
        text=text,
        tokens_per_second=timings.get("predicted_per_second"),
        first_token_ms=timings.get("prompt_ms"),
        elapsed_s=round(elapsed, 2),
        backend="server",
    )


def stream_chat(messages: list[dict], config: InferenceConfig | None = None):
    """Yield {'type': 'delta'|'done', ...} events from the resident server."""
    cfg = config or InferenceConfig()
    server = _server(cfg)
    yield from server.stream_chat(
        messages,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        timeout=cfg.timeout_s,
        enable_thinking=cfg.enable_thinking,
    )


def run_inference(prompt: str, config: InferenceConfig | None = None) -> InferenceResult:
    """Raw-completion path, kept for compatibility. Prefer run_chat."""
    cfg = config or InferenceConfig()
    server = _server(cfg)

    started = time.monotonic()
    data = server.complete(
        prompt,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        timeout=cfg.timeout_s,
    )
    elapsed = time.monotonic() - started

    timings = data.get("timings", {})
    return InferenceResult(
        text=(data.get("content") or "").strip(),
        tokens_per_second=timings.get("predicted_per_second"),
        first_token_ms=timings.get("prompt_ms"),
        elapsed_s=round(elapsed, 2),
        backend="server",
    )


def _server(cfg: InferenceConfig) -> LlamaServer:
    return LlamaServer.shared(
        ServerConfig(context_size=cfg.context_size, threads=cfg.threads)
    )
