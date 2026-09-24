import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.settings import settings

client = TestClient(app)


def test_index_page_returns_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PyDective" in response.text
    assert "dropzone-area" in response.text


def test_health_check_returns_valid_json():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "PyDective"
    assert data["version"] == "2.2.0"
    assert data["model"] == settings.GEMINI_MODEL
    assert data["max_pages"] == 20


def test_resultados_page_renders_html():
    sample_hash = "a" * 64
    response = client.get(f"/resultados/{sample_hash}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Dictamen Documental" in response.text
    assert sample_hash in response.text


def test_procesar_rejects_non_pdf():
    files = {"file": ("test.txt", b"not a pdf content", "text/plain")}
    data = {"parametros": '["total"]'}
    response = client.post("/procesar", files=files, data=data)
    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_PDF"


def test_chat_nonexistent_short_hash_returns_404():
    response = client.post("/chat/invalid_hash", json={"pregunta": "¿Cuál es el total?"})
    assert response.status_code == 404
    assert response.json()["error"] == "DOCUMENT_NOT_FOUND_OR_EXPIRED"
