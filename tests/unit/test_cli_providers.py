import subprocess
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.providers.cli_provider import AgyCLIProvider, OpenCodeCLIProvider

client = TestClient(app)


def test_v1_models_endpoint():
    """Verifica que /v1/models retorne 200 OK con estructura estándar OpenAI."""
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    ids = [m["id"] for m in data["data"]]
    assert "agy" in ids
    assert "opencode" in ids
    assert "chain" in ids


def test_v1_chat_completions_endpoint():
    """Verifica endpoint básico /v1/chat/completions."""
    with patch("app.services.providers.get_llm_provider") as mock_get_provider:
        mock_provider = MagicMock()
        mock_provider.generate_chat_response.return_value = "Respuesta simulada forense"
        mock_get_provider.return_value = mock_provider

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "chain",
                "messages": [
                    {"role": "user", "content": "Hola"}
                ]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "chat.completion"
        assert data["choices"][0]["message"]["content"] == "Respuesta simulada forense"


def test_opencode_provider_invokes_run_subcommand():
    """Verifica que OpenCodeCLIProvider invoque 'opencode run <prompt>' con stdin=subprocess.DEVNULL."""
    provider = OpenCodeCLIProvider(bin_path="/usr/bin/opencode")
    with patch("app.services.providers.cli_provider._find_executable", return_value="/usr/bin/opencode"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["/usr/bin/opencode", "run", "Hola"],
                returncode=0,
                stdout="> build · model\nRespuesta desde OpenCode",
                stderr="",
            )

            result = provider.generate_chat_response("Hola")
            assert result == "Respuesta desde OpenCode"
            mock_run.assert_called_once()
            called_args, called_kwargs = mock_run.call_args
            assert called_args[0] == ["/usr/bin/opencode", "run", "Hola"]
            assert called_kwargs.get("stdin") == subprocess.DEVNULL


def test_agy_provider_handles_auth_gracefully():
    """Verifica que AgyCLIProvider detecte solicitud de autenticación y retorne None para activar fallback."""
    provider = AgyCLIProvider(bin_path="/snap/bin/agy")
    with patch("app.services.providers.cli_provider._find_executable", return_value="/snap/bin/agy"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["/snap/bin/agy", "-p", "Hola"],
                returncode=0,
                stdout="Authentication required. Please visit URL...",
                stderr="",
            )

            result = provider.generate_chat_response("Hola")
            assert result is None
            called_kwargs = mock_run.call_args[1]
            assert called_kwargs.get("stdin") == subprocess.DEVNULL
