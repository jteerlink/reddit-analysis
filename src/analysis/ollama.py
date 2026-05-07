"""Ollama provider configuration, model discovery, and LLM chat."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional

import requests

SEED_MODEL_PREFERENCES = [
    "gemma4:31b-cloud",
    "gpt-oss:20b-cloud",
    "gpt-oss:120b-cloud",
    "deepseek-v4-flash:cloud",
    "qwen3.5:cloud",
    "qwen3.5:397b-cloud",
]


class OllamaAuthError(Exception):
    pass


class OllamaTimeoutError(Exception):
    pass


class OllamaUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class OllamaConfig:
    host: str
    api_key: Optional[str]
    timeout_seconds: float = 5.0
    allow_local_fallback: bool = False

    @classmethod
    def from_env(cls) -> "OllamaConfig":
        host = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com").rstrip("/")
        api_key = os.environ.get("OLLAMA_API_KEY") or None
        allow_local = os.environ.get("OLLAMA_ALLOW_LOCAL_FALLBACK", "").lower() in {"1", "true", "yes"}
        timeout = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "5"))
        return cls(host=host, api_key=api_key, timeout_seconds=timeout, allow_local_fallback=allow_local)

    @property
    def is_cloud(self) -> bool:
        return self.host == "https://ollama.com" or self.host.endswith(".ollama.com")

    @property
    def chat_url(self) -> str:
        return f"{self.host}/api/chat"

    @property
    def tags_url(self) -> str:
        return f"{self.host}/api/tags"

    def headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}


@dataclass
class DiscoveryResult:
    models: List[dict]
    selected_model: Optional[str]
    error: Optional[str] = None
    used_fallback: bool = False


def select_model(model_names: list[str]) -> Optional[str]:
    available = set(model_names)
    for preferred in SEED_MODEL_PREFERENCES:
        if preferred in available:
            return preferred
        no_cloud = preferred.replace("-cloud", "")
        if no_cloud in available:
            return no_cloud
    return model_names[0] if model_names else None


def discover_models(config: Optional[OllamaConfig] = None) -> DiscoveryResult:
    config = config or OllamaConfig.from_env()
    if config.is_cloud and not config.api_key:
        return DiscoveryResult(models=[], selected_model=None, error="missing_api_key")

    try:
        response = requests.get(config.tags_url, headers=config.headers(), timeout=config.timeout_seconds)
    except requests.Timeout:
        return DiscoveryResult(models=[], selected_model=None, error="timeout")
    except requests.RequestException as exc:
        return DiscoveryResult(models=[], selected_model=None, error=f"request_error:{exc.__class__.__name__}")

    if response.status_code in {401, 403}:
        return DiscoveryResult(models=[], selected_model=None, error="auth_failed")
    if response.status_code >= 400:
        return DiscoveryResult(models=[], selected_model=None, error=f"http_{response.status_code}")

    data = response.json()
    models = data.get("models", []) if isinstance(data, dict) else []
    names = [str(item.get("name") or item.get("model")) for item in models if item.get("name") or item.get("model")]
    if not names:
        return DiscoveryResult(models=[], selected_model=None, error="empty_model_list")
    return DiscoveryResult(models=models, selected_model=select_model(names))


def chat(
    config: OllamaConfig,
    model: str,
    messages: List[dict],
    temperature: float = 0.3,
    timeout: Optional[float] = None,
) -> str:
    """
    Send a chat request to Ollama and return the assistant's reply text.

    Uses non-streaming mode for simplicity. Raises typed exceptions on
    auth failure, timeout, or any other HTTP/connection error.
    """
    if timeout is None:
        timeout = config.timeout_seconds

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }

    try:
        response = requests.post(
            config.chat_url,
            headers={**config.headers(), "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=timeout,
        )
    except requests.Timeout:
        raise OllamaTimeoutError(f"Ollama chat timed out after {timeout}s")
    except requests.RequestException as exc:
        raise OllamaUnavailableError(f"Ollama request failed: {exc.__class__.__name__}: {exc}")

    if response.status_code in {401, 403}:
        raise OllamaAuthError(f"Ollama auth failed: HTTP {response.status_code}")
    if response.status_code >= 400:
        raise OllamaUnavailableError(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")

    try:
        data = response.json()
    except ValueError as exc:
        raise OllamaUnavailableError(f"Ollama returned non-JSON response: {exc}")

    content = (data.get("message") or {}).get("content") or ""
    if not content:
        raise OllamaUnavailableError("Ollama returned empty content")
    return content.strip()


def probe_model(config: OllamaConfig, model: str, timeout: float = 10.0) -> bool:
    """Return True if the model responds to a minimal ping message."""
    try:
        chat(config, model, [{"role": "user", "content": "ping"}], timeout=timeout)
        return True
    except (OllamaAuthError, OllamaTimeoutError, OllamaUnavailableError):
        return False
