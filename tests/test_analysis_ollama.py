import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.ollama import OllamaConfig, discover_models, select_model


def test_ollama_cloud_requires_api_key_by_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.com")

    result = discover_models(OllamaConfig.from_env())

    assert result.models == []
    assert result.selected_model is None
    assert result.error == "missing_api_key"


def test_ollama_selects_seed_profile_when_discovered():
    selected = select_model(["llama3", "gpt-oss:120b-cloud", "gemma"])

    assert selected == "gpt-oss:120b-cloud"


def test_ollama_local_override_does_not_require_api_key(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    config = OllamaConfig.from_env()

    assert not config.is_cloud
    assert config.headers() == {}
    assert config.tags_url == "http://localhost:11434/api/tags"
