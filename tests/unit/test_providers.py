from unittest.mock import patch, MagicMock
import pytest
import httpx

from app.services.providers import (
    BaseLLMProvider,
    GeminiProvider,
    LocalLLMProvider,
    get_llm_provider,
)
from app.settings import settings


def test_gemini_provider_availability():
    with patch.object(settings, "GEMINI_API_KEYS", ""):
        with patch.object(settings, "GEMINI_API_KEY", None):
            prov = GeminiProvider()
            assert not prov.is_available()

    with patch.object(settings, "GEMINI_API_KEYS", "fake_key_123"):
        prov = GeminiProvider()
        assert prov.is_available()
        assert prov.name == "gemini"


def test_gemini_provider_generate_chat_mocked():
    with patch.object(settings, "GEMINI_API_KEYS", "fake_key_123"):
        prov = GeminiProvider(model_name="test-model")
        with patch("app.services.providers.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.text = "Respuesta simulada [Página 1]"
            mock_client.models.generate_content.return_value = mock_resp

            result = prov.generate_chat_response(
                prompt="¿Quién es el arrendador?",
                system_instruction="Instrucciones forenses",
            )
            assert result == "Respuesta simulada [Página 1]"


def test_local_provider_availability_mocked():
    prov = LocalLLMProvider(base_url="http://localhost:11434/v1", model_name="qwen2.5:3b")
    assert prov.name == "local:qwen2.5:3b"

    # Caso 1: Servidor responde 200 en /models
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        assert prov.is_available()

    # Caso 2: Error de conexión
    with patch("httpx.Client.get", side_effect=httpx.ConnectError("Connection refused")):
        assert not prov.is_available()


def test_local_provider_generate_chat_mocked():
    prov = LocalLLMProvider(base_url="http://localhost:11434/v1", model_name="qwen2.5:3b")

    mock_json = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "El arrendador es ROBERTO ANTONIO JARAMILLO OSPINA [Página 1].",
                }
            }
        ]
    }

    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json
        mock_post.return_value = mock_resp

        ans = prov.generate_chat_response(
            prompt="¿Quién es el arrendador?",
            system_instruction="Eres el asistente",
        )
        assert "ROBERTO ANTONIO JARAMILLO OSPINA" in ans
        assert "[Página 1]" in ans


def test_provider_factory_resolution():
    # Explicit 'gemini'
    with patch.object(settings, "LLM_PROVIDER", "gemini"):
        prov = get_llm_provider()
        assert isinstance(prov, GeminiProvider)

    # Explicit 'local'
    with patch.object(settings, "LLM_PROVIDER", "local"):
        prov = get_llm_provider()
        assert isinstance(prov, LocalLLMProvider)

    # 'auto' with local available
    with patch.object(settings, "LLM_PROVIDER", "auto"):
        with patch.object(LocalLLMProvider, "is_available", return_value=True):
            prov = get_llm_provider()
            assert isinstance(prov, LocalLLMProvider)

    # 'auto' with local unavailable and gemini available
    with patch.object(settings, "LLM_PROVIDER", "auto"):
        with patch.object(LocalLLMProvider, "is_available", return_value=False):
            with patch.object(GeminiProvider, "is_available", return_value=True):
                prov = get_llm_provider()
                assert isinstance(prov, GeminiProvider)
