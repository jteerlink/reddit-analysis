"""Ollama provider configuration and model discovery."""

from __future__ import annotations

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
