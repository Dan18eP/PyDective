import json
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_procesar_with_default_rapidocr():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, fecha, nit"}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    assert res["motor_seleccionado"] == "rapidocr"
    assert res["comparativa_motores"] is None
    assert len(res["hallazgos"]) == 3
    # Verificar presencia de evidencias y coordenadas BBox
    for h in res["hallazgos"]:
        if h["evidencias"]:
            bbox = h["evidencias"][0]["bbox"]
            assert len(bbox) == 4
            assert all(isinstance(coord, (int, float)) for coord in bbox)


def test_procesar_dual_benchmark_generates_comparison():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists()

    # Mock Florence-2 para ejecutar test de integración determinista y ultra rápido
    mock_florence_findings = [
        {
            "parametro": "total",
            "valor": "$ 250,000 COP",
            "confianza": 0.94,
            "metodo": "florence2_vlm",
            "bbox": [180.0, 540.0, 320.0, 560.0],
            "valor_normalizado": "250000.00",
            "formato_detectado": "COP",
            "tipo_entidad": "moneda",
        },
        {
            "parametro": "fecha",
            "valor": "2026-01-15",
            "confianza": 0.95,
            "metodo": "florence2_vlm",
            "bbox": [100.0, 150.0, 220.0, 170.0],
            "valor_normalizado": "2026-01-15",
            "formato_detectado": "ISO-8601",
            "tipo_entidad": "fecha",
        },
        {
            "parametro": "nit",
            "valor": "900.123.456-7",
            "confianza": 0.96,
            "metodo": "florence2_vlm",
            "bbox": [80.0, 200.0, 210.0, 220.0],
            "valor_normalizado": "900123456-7",
            "formato_detectado": "NIT",
            "tipo_entidad": "nit",
        },
    ]

    with patch("app.main.extract_page_florence") as mock_florence:
        mock_florence.return_value = (mock_florence_findings, 8500.0, [])

        with open(pdf_path, "rb") as f:
            files = {"file": ("factura.pdf", f, "application/pdf")}
            data = {"parametros": "total, fecha, nit", "motor_vision": "dual"}
            response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    assert res["motor_seleccionado"] == "dual"
    assert res["comparativa_motores"] is not None

    bench = res["comparativa_motores"]
    assert bench["habilitado"] is True
    assert "factor_aceleracion" in bench
    assert bench["factor_aceleracion"] > 0
    assert "rapidocr" in bench
    assert "florence2" in bench
    assert len(bench["filas_comparativas"]) == 3

    # Verificar coordenadas exactas en las filas comparativas
    for fila in bench["filas_comparativas"]:
        assert len(fila["rapid_bbox"]) == 4
        assert len(fila["florence_bbox"]) == 4
        assert fila["concordancia"] in ("Exacta", "Cercana", "Discrepante", "Solo RapidOCR", "Solo Florence-2", "No detectado")


def test_ssr_resultados_renders_benchmark_card_and_bbox_coords():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists()

    mock_florence_findings = [
        {
            "parametro": "total",
            "valor": "$ 250,000 COP",
            "confianza": 0.94,
            "metodo": "florence2_vlm",
            "bbox": [180.0, 540.0, 320.0, 560.0],
            "valor_normalizado": "250000.00",
            "formato_detectado": "COP",
            "tipo_entidad": "moneda",
        }
    ]

    with patch("app.main.extract_page_florence") as mock_florence:
        mock_florence.return_value = (mock_florence_findings, 9200.0, [])

        with open(pdf_path, "rb") as f:
            files = {"file": ("factura.pdf", f, "application/pdf")}
            data = {"parametros": "total", "motor_vision": "dual"}
            response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    pdf_hash = response.json()["pdf_hash"]

    # Consultar vista SSR
    view_resp = client.get(f"/resultados/{pdf_hash}")
    assert view_resp.status_code == 200
    html = view_resp.text

    # Verificar que el benchmark A/B se renderiza
    assert "Benchmark A/B en Paralelo" in html
    assert "Factor de Aceleración" in html
    assert "RapidOCR ONNX" in html
    assert "Microsoft Florence-2" in html
    assert "Coordenadas BBox" in html
    assert "btn-copy-bbox" in html
