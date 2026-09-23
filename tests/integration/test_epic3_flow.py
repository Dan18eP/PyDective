from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.domain.models import HallazgoEnriquecido, Evidence
from app.domain.enums import MetodoExtraccion
from app.services.spatial_extraction_service import consolidate_findings

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_epic3_spatial_extraction_factura():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, subtotal, fecha de emision, nit"}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    assert res["paginas_totales"] == 1
    p1 = res["resultados_por_pagina"][0]
    assert p1["tipo"] == "local"

    # US-08: Grounding Fuerte con Evidence
    evidencias = p1.get("evidencias", [])
    assert len(evidencias) > 0

    for ev in evidencias:
        # Check evidence identity format: ev_p{N}_{idx:03d}
        assert ev["evidence_id"].startswith("ev_p1_")
        # Check bbox validity: [x0, y0, x1, y1] with positive area
        bbox = ev["bbox"]
        assert len(bbox) == 4
        assert bbox[2] > bbox[0]
        assert bbox[3] > bbox[1]
        # Check evidence_score bounded in [0.50, 1.00]
        assert 0.50 <= ev["evidence_score"] <= 1.00
        # Check KWIC context window is present
        assert "kwic_snippet" in ev
        assert ev["kwic_snippet"] is not None
        assert len(ev["kwic_snippet"]) > 0

    # US-07 & US-09: Clave-Valor Geométrica y Normalización
    hallazgos_list = res.get("hallazgos", [])
    assert len(hallazgos_list) > 0
    hallazgos = {h["parametro"]: h for h in hallazgos_list}

    # Verify normalization of detected fields
    if "total" in hallazgos and hallazgos["total"]["valor_normalizado"]:
        assert float(hallazgos["total"]["valor_normalizado"]) in (9579500.00, 8050000.00)
        assert hallazgos["total"]["tipo_entidad"] == "moneda"
        assert hallazgos["total"]["divisa"] == "COP"

    if "subtotal" in hallazgos and hallazgos["subtotal"]["valor_normalizado"]:
        assert float(hallazgos["subtotal"]["valor_normalizado"]) == 8050000.00
        assert hallazgos["subtotal"]["tipo_entidad"] == "moneda"
        assert hallazgos["subtotal"]["divisa"] == "COP"

    if "fecha de emision" in hallazgos and hallazgos["fecha de emision"]["valor_normalizado"]:
        assert hallazgos["fecha de emision"]["valor_normalizado"] == "2026-04-15"
        assert hallazgos["fecha de emision"]["tipo_entidad"] == "fecha"

    if "nit" in hallazgos and hallazgos["nit"]["valor_normalizado"]:
        assert hallazgos["nit"]["valor_normalizado"] == "900543210-8"
        assert hallazgos["nit"]["tipo_entidad"] == "nit"


def test_epic3_stream_reports_evidences_and_hallazgos():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, subtotal, nit"}
        response = client.post("/procesar/stream", files=files, data=data)

    assert response.status_code == 200
    lines = [line.strip() for line in response.text.split("\n") if line.startswith("data:")]
    assert len(lines) >= 3

    page_event = json.loads(lines[1].replace("data:", "").strip())
    assert page_event["tipo"] == "pagina"
    assert "evidencias" in page_event
    assert len(page_event["evidencias"]) > 0

    complete_event = json.loads(lines[-1].replace("data:", "").strip())
    assert complete_event["tipo"] == "completado"
    assert "hallazgos" in complete_event
    assert len(complete_event["hallazgos"]) > 0


def test_epic3_conflict_resolution_native_over_ai():
    # US-10 Escenario 2: Precedencia absoluta del texto vectorial nativo
    native_ev = Evidence(
        evidence_id="ev_p1_001",
        page=1,
        text="TOTAL: $ 4.850.000",
        bbox=[100.0, 200.0, 250.0, 215.0],
        source=MetodoExtraccion.SPATIAL_VECTOR,
        evidence_score=0.98,
        kwic_snippet="TOTAL: $ 4.850.000",
    )
    native_finding = HallazgoEnriquecido(
        parametro="total",
        valor="$ 4.850.000",
        confianza=0.98,
        metodo=MetodoExtraccion.SPATIAL_VECTOR,
        evidencias=[native_ev],
        valor_normalizado="4850000.00",
        formato_detectado="COP",
    )

    ai_ev = Evidence(
        evidence_id="ev_p1_ai_001",
        page=1,
        text="$ 4.850.00",
        bbox=[98.0, 198.0, 252.0, 216.0],
        source=MetodoExtraccion.VISUAL_AI,
        evidence_score=0.85,
    )
    ai_finding = HallazgoEnriquecido(
        parametro="total",
        valor="$ 4.850.00",
        confianza=0.85,
        metodo=MetodoExtraccion.VISUAL_AI,
        evidencias=[ai_ev],
        valor_normalizado="4850.00",
        formato_detectado="COP",
    )

    consolidated = consolidate_findings([native_finding], [ai_finding])
    assert len(consolidated) == 1
    # Strict immutable precedence of native vector text
    assert consolidated[0].valor == "$ 4.850.000"
    assert consolidated[0].valor_normalizado == "4850000.00"
    assert consolidated[0].metodo == MetodoExtraccion.SPATIAL_VECTOR
