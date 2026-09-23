from pathlib import Path
import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.domain.enums import EstadoCobertura, TipoPagina, MetodoExtraccion
from app.services.gemini_service import GeminiInvocationResult

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_epic4_scanned_pdf_triggers_gemini_multimodal():
    pdf_path = FIXTURES_DIR / "escaneo_inclinado_skew.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("skewed.pdf", f, "application/pdf")}
        data = {"parametros": "total, vigencia", "catalogar_imagenes": "true"}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    assert res["status"] == EstadoCobertura.COMPLETE.value
    assert res["paginas_totales"] == 1
    p1 = res["resultados_por_pagina"][0]
    assert p1["tipo"] == TipoPagina.NEEDS_AI.value
    assert p1["preprocesado"] is True

    # Telemetría de Fase B (US-11 y US-12)
    telemetria = res["telemetria"]
    assert telemetria["render_ms"] > 0.0
    assert telemetria["gemini_ms"] > 0.0

    # Hallazgos multimodales
    hallazgos = res.get("hallazgos", [])
    assert len(hallazgos) > 0
    ai_findings = [h for h in hallazgos if h["metodo"] == MetodoExtraccion.VISUAL_AI.value]
    assert len(ai_findings) > 0


def test_epic4_image_cataloging_in_pipeline():
    # US-13: Catalogación Física y Forense en pipeline
    pdf_path = FIXTURES_DIR / "mixto_sello_firma.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("mixto.pdf", f, "application/pdf")}
        data = {"parametros": "total", "catalogar_imagenes": "true"}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    p1 = res["resultados_por_pagina"][0]
    visuals = p1.get("metadatos_visuales", [])
    assert len(visuals) > 0

    for v in visuals:
        assert v["pagina"] == 1
        assert len(v["bbox"]) == 4
        assert v["clasificacion_semantica"] in (
            "firma_manuscrita",
            "sello_oficial",
            "logotipo",
            "diagrama",
        )


def test_epic4_strict_per_page_failure_isolation():
    # US-12 Escenario 2: Aislamiento estricto de fallo por página -> PARTIAL
    pdf_path = FIXTURES_DIR / "digital_contrato.pdf"
    assert pdf_path.exists()

    def mock_failing_page(image_bytes, page_number, parameters, **kwargs):
        if page_number == 2:
            return GeminiInvocationResult(
                numero_pagina=2,
                exito=False,
                error="Error 400: Imagen no decodificable en página 2",
                hallazgos=[],
                duracion_ms=15.0,
            )
        return GeminiInvocationResult(
            numero_pagina=page_number,
            exito=True,
            error=None,
            hallazgos=[],
            duracion_ms=10.0,
        )

    # Forzar que la página sea tratada como needs_ai para probar el aislamiento
    with patch("app.main.classify_page") as mock_classify, \
         patch("app.main.invoke_gemini_multimodal_page", side_effect=mock_failing_page):

        from app.services.classifier_service import PageClassification

        def side_effect_classify(page, bypass_threshold=80):
            return PageClassification(
                numero_pagina=page.number + 1,
                tipo=TipoPagina.NEEDS_AI,
                readability_score=0.40,
                word_count=10,
                bypass_opencv=False,
            )

        mock_classify.side_effect = side_effect_classify

        with open(pdf_path, "rb") as f:
            files = {"file": ("contrato.pdf", f, "application/pdf")}
            data = {"parametros": "canon, plazo"}
            response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    # US-12: Aislamiento estricto genera EstadoCobertura.PARTIAL
    assert res["status"] == EstadoCobertura.PARTIAL.value
    assert 2 in res["paginas_pendientes"]

    pages = res["resultados_por_pagina"]
    p1 = pages[0]
    p2 = pages[1]
    assert p1["exito"] is True
    assert p2["exito"] is False
    assert "Error 400" in p2["error"]


def test_epic4_streaming_reports_gemini_and_visuals():
    pdf_path = FIXTURES_DIR / "escaneo_inclinado_skew.pdf"
    with open(pdf_path, "rb") as f:
        files = {"file": ("skewed.pdf", f, "application/pdf")}
        data = {"parametros": "total"}
        response = client.post("/procesar/stream", files=files, data=data)

    assert response.status_code == 200
    lines = [line.strip() for line in response.text.split("\n") if line.startswith("data:")]
    assert len(lines) >= 3

    page_event = json.loads(lines[1].replace("data:", "").strip())
    assert page_event["tipo"] == "pagina"
    assert page_event["carril"] == "needs_ai"
    assert "gemini_ms" in page_event

    complete_event = json.loads(lines[-1].replace("data:", "").strip())
    assert complete_event["tipo"] == "completado"
    assert complete_event["status"] == EstadoCobertura.COMPLETE.value
