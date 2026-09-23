import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.pdf_viewer_service import save_uploaded_pdf

client = TestClient(app)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PDF_20P_PATH = BASE_DIR / "documento_completo_20_paginas.pdf"


@pytest.fixture(scope="module")
def setup_real_pdf():
    assert PDF_20P_PATH.exists()
    pdf_bytes = PDF_20P_PATH.read_bytes()
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
    save_uploaded_pdf(pdf_hash, pdf_bytes)
    return pdf_hash, pdf_bytes


def test_get_raw_pdf_success(setup_real_pdf):
    pdf_hash, pdf_bytes = setup_real_pdf
    response = client.get(f"/documentos/{pdf_hash}/raw")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == pdf_bytes


def test_get_raw_pdf_not_found():
    response = client.get(f"/documentos/{'e' * 64}/raw")
    assert response.status_code == 404
    assert "no fue encontrado" in response.json()["detail"]


def test_get_search_pdf_success(setup_real_pdf):
    pdf_hash, _ = setup_real_pdf
    response = client.get(f"/documentos/{pdf_hash}/search?q=CONTRATO")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "CONTRATO"
    assert data["total_coincidencias"] > 0
    assert len(data["coincidencias"]) == data["total_coincidencias"]

    # Validar estructura de coincidencia para visor
    match = data["coincidencias"][0]
    assert "pagina" in match
    assert "bbox" in match
    assert len(match["bbox"]) == 4
    assert "ancho_pagina" in match
    assert "alto_pagina" in match


def test_get_search_pdf_empty_query(setup_real_pdf):
    pdf_hash, _ = setup_real_pdf
    response = client.get(f"/documentos/{pdf_hash}/search?q=")
    assert response.status_code == 200
    data = response.json()
    assert data["total_coincidencias"] == 0
    assert data["coincidencias"] == []


def test_resultados_view_contains_pdf_viewer_elements(setup_real_pdf):
    pdf_hash, _ = setup_real_pdf
    response = client.get(f"/resultados/{pdf_hash}")
    assert response.status_code == 200
    html = response.text

    # Verificar inclusión de PDF.js y visor
    assert "pdf.min.js" in html
    assert "pdf_viewer.css" in html
    assert "pdf_viewer.js" in html
    assert 'id="pdf-viewer-pages-container"' in html
    assert 'id="pdf-finder-toolbar"' in html
    assert 'id="pdf-search-input"' in html
    assert "PydectivePdfViewer" in html
    assert "highlightSourceInPdf" in html
