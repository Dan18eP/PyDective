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


def test_rapidocr_extracts_name_on_scanned_pdf_fixture_051():
    # Valida que el motor RapidOCR reconoce el nombre completo en doc_051_escaneo.pdf
    fixtures_100_dir = Path(__file__).resolve().parent.parent / "fixtures_100"
    pdf_path = fixtures_100_dir / "doc_051_escaneo.pdf"
    if not pdf_path.exists():
        pytest.skip("Fixture doc_051_escaneo.pdf no encontrado")

    with open(pdf_path, "rb") as f:
        files = {"file": ("doc_051_escaneo.pdf", f, "application/pdf")}
        data = {"parametros": "nombre, notario, fecha, valor", "motor_vision": "rapidocr"}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    assert res["motor_seleccionado"] == "rapidocr"

    h_map = {h["parametro"]: h for h in res["hallazgos"]}

    # Validar deteccion exacta del nombre completo
    assert "nombre" in h_map
    assert h_map["nombre"]["valor"] == "ROBERTO ANTONIO JARAMILLO OSPINA"
    assert h_map["nombre"]["confianza"] == 1.0
    assert len(h_map["nombre"]["evidencias"]) >= 1

    bbox = h_map["nombre"]["evidencias"][0]["bbox"]
    assert len(bbox) == 4
    assert bbox[2] > bbox[0]
    assert bbox[3] > bbox[1]

    # Validar fecha y valor
    assert "fecha" in h_map
    assert h_map["fecha"]["valor"] == "2026-01-15"
    assert "valor" in h_map
    assert "1.250.000" in h_map["valor"]["valor"]

