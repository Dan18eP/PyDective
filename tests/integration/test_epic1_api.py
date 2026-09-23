import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import pymupdf

from app.main import app

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_api_procesar_valid_pdf_returns_success():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "  TOTAL, Facturación, número de radicado  "}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res_json = response.json()
    assert res_json["paginas_totales"] == 1
    assert len(res_json["hallazgos"]) == 3
    # Check that parameters were canonically normalized
    detected_params = [h["parametro"] for h in res_json["hallazgos"]]
    assert detected_params == ["facturacion", "numero de radicado", "total"]


def test_api_procesar_rejects_empty_parameters():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "   , ,  "}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 400
    res_json = response.json()
    assert res_json["error"] == "EMPTY_SEARCH_PARAMETERS"

    # Also test empty string explicitly
    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": ""}
        response_empty = client.post("/procesar", files=files, data=data)

    assert response_empty.status_code == 400
    assert response_empty.json()["error"] == "EMPTY_SEARCH_PARAMETERS"


def test_api_procesar_rejects_non_pdf():
    files = {"file": ("datos.csv", b"col1,col2\nval1,val2", "text/csv")}
    data = {"parametros": "total"}
    response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 400
    res_json = response.json()
    assert res_json["error"] == "INVALID_PDF"


def test_api_procesar_rejects_fake_header_pdf():
    files = {"file": ("falso.pdf", b"No soy un PDF real", "application/pdf")}
    data = {"parametros": "total"}
    response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 400
    res_json = response.json()
    assert res_json["error"] == "INVALID_PDF"


def test_api_procesar_rejects_corrupted_pdf():
    files = {"file": ("corrupto.pdf", b"%PDF-1.4\n[bad stream content]", "application/pdf")}
    data = {"parametros": "total"}
    response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 400
    res_json = response.json()
    assert res_json["error"] == "CORRUPTED_OR_ENCRYPTED_PDF"


def test_api_procesar_rejects_more_than_20_pages():
    # Build 21-page PDF in memory
    doc = pymupdf.open()
    for i in range(21):
        p = doc.new_page()
        p.insert_text((50, 50), f"Página {i+1}")
    pdf_bytes = doc.tobytes()
    doc.close()

    files = {"file": ("large.pdf", pdf_bytes, "application/pdf")}
    data = {"parametros": "total"}
    response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 400
    res_json = response.json()
    assert res_json["error"] == "PAGE_LIMIT_EXCEEDED"
    assert res_json["max_pages"] == 20
    assert res_json["received_pages"] == 21


def test_api_procesar_stream_valid():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, fecha"}
        response = client.post("/procesar/stream", files=files, data=data)

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    text = response.text
    assert '"tipo": "inicio"' in text
    assert '"tipo": "pagina"' in text
    assert '"tipo": "completado"' in text


def test_api_procesar_stream_rejects_empty_parameters():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": ""}
        response = client.post("/procesar/stream", files=files, data=data)

    assert response.status_code == 400
    res_json = response.json()
    assert res_json["error"] == "EMPTY_SEARCH_PARAMETERS"
