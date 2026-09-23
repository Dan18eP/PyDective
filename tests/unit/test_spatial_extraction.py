from pathlib import Path
import pytest
import pymupdf

from app.domain.enums import MetodoExtraccion
from app.domain.models import Evidence, HallazgoEnriquecido
from app.services.spatial_extraction_service import (
    normalize_currency_amount,
    normalize_date_string,
    normalize_tax_id,
    extract_kwic_context,
    extract_spatial_key_values,
    consolidate_findings,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_normalize_currency_amounts():
    # US-09 Escenario 1: Monedas hispanas y anglosajonas
    val, curr = normalize_currency_amount("$ 12.500.000,50 COP")
    assert val == "12500000.50"
    assert curr == "COP"

    val_usd, curr_usd = normalize_currency_amount("USD 4,500.00")
    assert val_usd == "4500.00"
    assert curr_usd == "USD"

    val_dot, curr_cop = normalize_currency_amount("$ 8.050.000 COP")
    assert val_dot == "8050000.00"
    assert curr_cop == "COP"

    val_simple, _ = normalize_currency_amount("$3.200.000")
    assert val_simple == "3200000.00"


def test_normalize_date_formats():
    # US-09 Escenario 2: Fechas en diversos formatos a ISO-8601
    assert normalize_date_string("15/04/2026") == "2026-04-15"
    assert normalize_date_string("2026-04-15") == "2026-04-15"
    assert normalize_date_string("22 de mayo de 2026") == "2026-05-22"
    assert normalize_date_string("5 de enero de 2025") == "2025-01-05"


def test_normalize_tax_id():
    assert normalize_tax_id("900.543.210-8") == "900543210-8"
    assert normalize_tax_id("NIT: 830.123.987-1") == "830123987-1"


def test_extract_kwic_context():
    # US-10 Escenario 1: Ventana de contexto forense
    text = (
        "El presente contrato se firma en Bogotá. "
        "En caso de incumplimiento de las partes se causará una penalidad pecuniaria de $ 37.500.000 COP. "
        "Las partes renuncian a requerimientos previos."
    )
    kwic = extract_kwic_context(text, "penalidad")
    assert "En caso de incumplimiento" in kwic
    assert "$ 37.500.000 COP" in kwic


def test_spatial_extraction_horizontal_right_on_digital_factura():
    # US-07 Escenario 1: Extracción en vector horizontal derecho
    factura_pdf = FIXTURES_DIR / "digital_factura.pdf"
    assert factura_pdf.exists()

    doc = pymupdf.open(factura_pdf)
    try:
        page = doc[0]
        params = ["subtotal", "fecha de emision", "nit"]
        hallazgos = extract_spatial_key_values(page, params)

        assert len(hallazgos) >= 2
        params_found = {h.parametro: h for h in hallazgos}

        # Check subtotal extracted
        if "subtotal" in params_found:
            sub = params_found["subtotal"]
            assert "8.050.000" in sub.valor or "8050000" in sub.valor
            assert sub.valor_normalizado == "8050000.00"
            assert sub.confianza >= 0.70

        # Check fecha de emision extracted
        if "fecha de emision" in params_found:
            f_em = params_found["fecha de emision"]
            assert "2026-04-15" in f_em.valor
            assert f_em.valor_normalizado == "2026-04-15"

        # Check Evidence structure (US-08)
        for h in hallazgos:
            assert len(h.evidencias) >= 1
            ev = h.evidencias[0]
            assert ev.evidence_id.startswith("ev_p1_")
            assert ev.page == 1
            assert len(ev.bbox) == 4
            assert ev.source == MetodoExtraccion.SPATIAL_VECTOR
            assert 0.50 <= ev.evidence_score <= 1.00
    finally:
        doc.close()


def test_spatial_extraction_vertical_down_vector():
    # US-07 Escenario 2: Extracción en vector vertical descendente
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    # Label
    page.insert_text((100, 100), "DIRECCION DEL INMUEBLE", fontsize=10)
    # Value directly below (y distance ~ 18 pt, high X overlap)
    page.insert_text((100, 120), "Carrera 7 # 71-21 Torre B Piso 12", fontsize=10)

    hallazgos = extract_spatial_key_values(page, ["direccion del inmueble"])
    doc.close()

    assert len(hallazgos) == 1
    h = hallazgos[0]
    assert "Carrera 7" in h.valor
    assert h.metodo == MetodoExtraccion.SPATIAL_VECTOR
    assert h.confianza >= 0.70


def test_spatial_extraction_tight_kerning_fallback():
    # US-07 Escenario 3: Kerning apretado sin espacios (ej. Total:1200)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "Total:1200000", fontsize=10)

    hallazgos = extract_spatial_key_values(page, ["total"])
    doc.close()

    assert len(hallazgos) == 1
    h = hallazgos[0]
    assert h.valor == "1200000"
    assert h.valor_normalizado == "1200000.00"


def test_conflict_resolution_absolute_precedence_of_native_text():
    # US-10 Escenario 2: Precedencia del dato espacial determinista sobre IA
    ev_native = Evidence(
        evidence_id="ev_p1_001",
        page=1,
        text="TOTAL: $ 4.850.000",
        bbox=[100, 200, 300, 220],
        source=MetodoExtraccion.SPATIAL_VECTOR,
        evidence_score=0.95,
    )
    native_finding = HallazgoEnriquecido(
        parametro="total",
        valor="$ 4.850.000",
        confianza=0.95,
        metodo=MetodoExtraccion.SPATIAL_VECTOR,
        evidencias=[ev_native],
        valor_normalizado="4850000.00",
        formato_detectado="COP",
    )

    ev_ai = Evidence(
        evidence_id="ev_p1_002",
        page=1,
        text="TOTAL: $ 4.850.00",
        bbox=[100, 200, 300, 220],
        source=MetodoExtraccion.VISUAL_AI,
        evidence_score=0.88,
    )
    ai_finding = HallazgoEnriquecido(
        parametro="total",
        valor="$ 4.850.00",  # Hallucinated last zero missing
        confianza=0.88,
        metodo=MetodoExtraccion.VISUAL_AI,
        evidencias=[ev_ai],
        valor_normalizado="4850.00",
        formato_detectado="COP",
    )

    consolidated = consolidate_findings([native_finding], [ai_finding])
    assert len(consolidated) == 1
    # Native finding must prevail
    assert consolidated[0].valor == "$ 4.850.000"
    assert consolidated[0].valor_normalizado == "4850000.00"
    assert consolidated[0].metodo == MetodoExtraccion.SPATIAL_VECTOR
