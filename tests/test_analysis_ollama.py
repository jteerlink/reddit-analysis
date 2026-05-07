import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.ollama import (
    OllamaAuthError,
    OllamaConfig,
    OllamaTimeoutError,
    OllamaUnavailableError,
    chat,
    discover_models,
    probe_model,
    select_model,
)


def _local_config() -> OllamaConfig:
    return OllamaConfig(host="http://localhost:11434", api_key=None)


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


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------


def test_chat_returns_content():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "model": "llama3",
        "message": {"role": "assistant", "content": "Hello, world!"},
        "done": True,
    }

    with patch("requests.post", return_value=mock_response):
        result = chat(_local_config(), "llama3", [{"role": "user", "content": "hi"}])

    assert result == "Hello, world!"


def test_chat_raises_on_401():
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("requests.post", return_value=mock_response):
        with pytest.raises(OllamaAuthError):
            chat(_local_config(), "llama3", [{"role": "user", "content": "hi"}])


def test_chat_raises_on_403():
    mock_response = MagicMock()
    mock_response.status_code = 403

    with patch("requests.post", return_value=mock_response):
        with pytest.raises(OllamaAuthError):
            chat(_local_config(), "llama3", [{"role": "user", "content": "hi"}])


def test_chat_raises_on_timeout():
    with patch("requests.post", side_effect=requests.Timeout()):
        with pytest.raises(OllamaTimeoutError):
            chat(_local_config(), "llama3", [{"role": "user", "content": "hi"}])


def test_chat_raises_on_connection_error():
    with patch("requests.post", side_effect=requests.ConnectionError("refused")):
        with pytest.raises(OllamaUnavailableError):
            chat(_local_config(), "llama3", [{"role": "user", "content": "hi"}])


def test_chat_raises_on_http_500():
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("requests.post", return_value=mock_response):
        with pytest.raises(OllamaUnavailableError):
            chat(_local_config(), "llama3", [{"role": "user", "content": "hi"}])


def test_chat_raises_on_empty_content():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": {"role": "assistant", "content": ""}, "done": True}

    with patch("requests.post", return_value=mock_response):
        with pytest.raises(OllamaUnavailableError):
            chat(_local_config(), "llama3", [{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# probe_model()
# ---------------------------------------------------------------------------


def test_probe_model_returns_true_on_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": {"role": "assistant", "content": "pong"}, "done": True}

    with patch("requests.post", return_value=mock_response):
        assert probe_model(_local_config(), "llama3") is True


def test_probe_model_returns_false_on_timeout():
    with patch("requests.post", side_effect=requests.Timeout()):
        assert probe_model(_local_config(), "llama3") is False


def test_probe_model_returns_false_on_auth_error():
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("requests.post", return_value=mock_response):
        assert probe_model(_local_config(), "llama3") is False
