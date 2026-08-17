"""Persistent llama-server lifecycle management.

Keeping the model resident removes the multi-second load penalty that a fresh
llama-cli process pays on every query.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from theoria.config import llama_server_path, model_path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081
STARTUP_TIMEOUT_S = 180


@dataclass
class ServerConfig:
    context_size: int = 4096
    threads: int | None = None
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    cache_type_k: str = "q8_0"
    cache_type_v: str = "q8_0"


class LlamaServer:
    """Starts llama-server on demand and reuses it for later queries."""

    _instance: LlamaServer | None = None

    def __init__(self, config: ServerConfig | None = None) -> None:
        self.config = config or ServerConfig()
        self._proc: subprocess.Popen | None = None

    @classmethod
    def shared(cls, config: ServerConfig | None = None) -> LlamaServer:
        if cls._instance is None:
            cls._instance = cls(config)
            atexit.register(cls._instance.stop)
        return cls._instance

    @property
    def base_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    def is_healthy(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/health", timeout=2) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    def ensure_running(self) -> None:
        if self.is_healthy():
            return

        model = model_path()
        if not model.is_file():
            raise FileNotFoundError(
                f"Model not found at {model}. Run: bash download_model.sh"
            )

        cmd = [
            str(llama_server_path()),
            "-m",
            str(model),
            "-c",
            str(self.config.context_size),
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
            "--cache-type-k",
            self.config.cache_type_k,
            "--cache-type-v",
            self.config.cache_type_v,
            # Apply the GGUF's own chat template server-side. Without it the
            # model never sees its stop tokens and generates until -n runs out
            # (or forever with raw llama-cli prompts).
            "--jinja",
        ]
        threads = self.config.threads or _physical_cores()
        cmd.extend(["-t", str(threads)])

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.is_healthy():
                return
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"llama-server exited early (code {self._proc.returncode})"
                )
            time.sleep(0.5)

        self.stop()
        raise TimeoutError(f"llama-server did not become healthy in {STARTUP_TIMEOUT_S}s")

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: int = 180,
        enable_thinking: bool = False,
    ) -> dict:
        """Chat completion using the model's own template (emits EOS, so the
        model stops on its own instead of running to the token cap)."""
        self.ensure_running()
        payload = json.dumps(
            self._chat_payload(messages, max_tokens, temperature, enable_thinking)
        ).encode("utf-8")
        return self._post("/v1/chat/completions", payload, timeout)

    def stream_chat(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: int = 180,
        enable_thinking: bool = False,
    ):
        """Yield events: {'type': 'delta', 'text': ...} per token chunk, then
        {'type': 'done', 'timings': {...}} when generation finishes."""
        self.ensure_running()
        body = self._chat_payload(messages, max_tokens, temperature, enable_thinking)
        body["stream"] = True
        payload = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timings: dict = {}
        # Keep the response handle so a cancelled generator can close the
        # upstream llama-server stream and stop GPU/CPU decoding immediately.
        resp = urllib.request.urlopen(req, timeout=timeout)
        try:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if "timings" in chunk:
                    timings = chunk["timings"]
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                # With --jinja + reasoning models, llama-server splits hidden
                # reasoning into its own field; surface it as 'think' events.
                reasoning = delta.get("reasoning_content")
                if reasoning:
                    yield {"type": "think", "text": reasoning}
                text = delta.get("content")
                if text:
                    yield {"type": "delta", "text": text}
            yield {"type": "done", "timings": timings}
        finally:
            with contextlib.suppress(Exception):
                resp.close()

    @staticmethod
    def _chat_payload(
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        enable_thinking: bool,
    ) -> dict:
        return {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "cache_prompt": True,
            "stream": False,
            # Qwen3 templates read this; other templates ignore it. Hidden
            # reasoning tokens would stall the UI for tens of seconds.
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
        }

    def complete(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.2,
        timeout: int = 120,
    ) -> dict:
        self.ensure_running()
        payload = json.dumps(
            {
                "prompt": prompt,
                "n_predict": max_tokens,
                "temperature": temperature,
                "cache_prompt": True,
                "stream": False,
            }
        ).encode("utf-8")
        return self._post("/completion", payload, timeout)

    def _post(self, path: str, payload: bytes, timeout: int) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def stop(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None


def _physical_cores() -> int:
    count = os.cpu_count() or 4
    # Hyperthreaded logical cores add contention rather than throughput for
    # bandwidth-bound decoding, so target roughly the physical core count.
    return max(1, count // 2) if count > 4 else count
