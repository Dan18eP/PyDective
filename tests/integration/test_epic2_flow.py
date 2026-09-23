from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_flow_digital_factura_classified_as_local_zero_preprocess():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, fecha, nit", "catalogar_imagenes": "true"}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    assert res["paginas_totales"] == 1
    assert len(res["resultados_por_pagina"]) == 1
    p1 = res["resultados_por_pagina"][0]
    assert p1["tipo"] == "local"
    assert p1["preprocesado"] is False
    assert res["telemetria"]["classification_ms"] > 0.0


def test_flow_skewed_scan_classified_as_needs_ai_and_preprocessed():
    pdf_path = FIXTURES_DIR / "escaneo_inclinado_skew.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("skewed.pdf", f, "application/pdf")}
        data = {"parametros": "total, vigencia"}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    assert res["paginas_totales"] == 1
    p1 = res["resultados_por_pagina"][0]
    assert p1["tipo"] == "needs_ai"
    assert p1["preprocesado"] is True


def test_flow_ocr_corrupto_diverted_to_needs_ai():
    pdf_path = FIXTURES_DIR / "ocr_corrupto.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("corrupt.pdf", f, "application/pdf")}
        data = {"parametros": "total"}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    p1 = res["resultados_por_pagina"][0]
    assert p1["tipo"] == "needs_ai"


def test_stream_flow_reports_accurate_lanes():
    pdf_path = FIXTURES_DIR / "escaneo_inclinado_skew.pdf"
    with open(pdf_path, "rb") as f:
        files = {"file": ("skewed.pdf", f, "application/pdf")}
        data = {"parametros": "total"}
        response = client.post("/procesar/stream", files=files, data=data)

    assert response.status_code == 200
    lines = [line.strip() for line in response.text.split("\n") if line.startswith("data:")]
    assert len(lines) >= 3

    init_event = json.loads(lines[0].replace("data:", "").strip())
    assert init_event["tipo"] == "inicio"

    page_event = json.loads(lines[1].replace("data:", "").strip())
    assert page_event["tipo"] == "pagina"
    assert page_event["carril"] == "needs_ai"

    complete_event = json.loads(lines[-1].replace("data:", "").strip())
    assert complete_event["tipo"] == "completado"
