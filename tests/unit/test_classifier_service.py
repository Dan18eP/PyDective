from pathlib import Path
import pytest
import pymupdf

from app.domain.enums import TipoPagina
from app.services.classifier_service import (
    calculate_readability_score,
    inventory_page_images,
    classify_page,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_readability_score_clean_text():
    clean_text = (
        "Factura electrónica de venta número FE-2026-0842. "
        "Fecha de emisión: 15 de abril de 2026. "
        "Cliente: Logística y Transportes Andinos S.A. "
        "Total a pagar: ocho millones cincuenta mil pesos colombianos."
    )
    words = clean_text.split()
    score = calculate_readability_score(clean_text, words)

    assert score >= 0.80, f"Expected clean text score >= 0.80, got {score}"


def test_readability_score_corrupt_ocr_with_replacement_chars():
    # Simulated corrupt OCR layer with > 5% \ufffd
    corrupt_text = "\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd" + " PalabraTexto " * 5
    words = corrupt_text.split()
    score = calculate_readability_score(corrupt_text, words)

    assert score < 0.60, f"Expected corrupt text score < 0.60, got {score}"


def test_readability_score_corrupt_ocr_with_abnormally_long_words():
    # Long words without spaces (> 30 characters)
    glued_text = "TotalAPagarSinEspaciosNiSeparadoresDeNingunTipo98500000000000000000000000000000000 " * 4
    words = glued_text.split()
    score = calculate_readability_score(glued_text, words)

    assert score < 0.60, f"Expected glued text score < 0.60, got {score}"


def test_readability_score_short_clean_text():
    # 35-40 words clean text (US-05 Escenario 2)
    short_text = (
        "Por medio del presente documento certificamos que la empresa contratista "
        "ha dado estricto cumplimiento a los acuerdos pactados en el acta de inicio. "
        "Se autoriza el pago correspondiente al mes en curso sin penalizaciones adicionales."
    )
    words = short_text.split()
    score = calculate_readability_score(short_text, words)

    assert score >= 0.70, f"Expected short clean text score >= 0.70, got {score}"


def test_inventory_page_images_on_digital_without_images():
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=700)
    page.insert_text((50, 50), "Texto sin imágenes")

    images = inventory_page_images(page)
    doc.close()
    assert images == []


def test_inventory_page_images_on_document_with_stamp():
    stamp_pdf = FIXTURES_DIR / "mixto_sello_firma.pdf"
    assert stamp_pdf.exists()

    doc = pymupdf.open(stamp_pdf)
    try:
        images = inventory_page_images(doc[0])
        assert len(images) >= 1
        assert images[0].tipo_fisico in ("raster", "vector")
        assert images[0].area_ratio > 0.0
        assert len(images[0].bbox) == 4
    finally:
        doc.close()


def test_classify_page_digital_clean_bypasses_opencv_and_ai():
    # US-04 Escenario 1: digital_factura.pdf
    factura_pdf = FIXTURES_DIR / "digital_factura.pdf"
    assert factura_pdf.exists()

    doc = pymupdf.open(factura_pdf)
    try:
        classification = classify_page(doc[0], bypass_threshold=80)
        assert classification.tipo == TipoPagina.LOCAL
        assert classification.bypass_opencv is True
        assert classification.word_count >= 80
        assert classification.readability_score >= 0.60
    finally:
        doc.close()


def test_classify_page_empty_page():
    # US-04 Escenario 2: Blank page
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    classification = classify_page(page)
    doc.close()

    assert classification.tipo == TipoPagina.EMPTY
    assert classification.word_count == 0
    assert classification.bypass_opencv is True


def test_classify_page_pure_raster_scan():
    # Pure scan (escaneo_limpio.pdf)
    scan_pdf = FIXTURES_DIR / "escaneo_limpio.pdf"
    assert scan_pdf.exists()

    doc = pymupdf.open(scan_pdf)
    try:
        classification = classify_page(doc[0])
        assert classification.tipo == TipoPagina.NEEDS_AI
        assert classification.bypass_opencv is False
        assert classification.word_count == 0
    finally:
        doc.close()


def test_classify_page_corrupt_ocr_layer_diverts_to_ai():
    # US-05 Escenario 1: ocr_corrupto.pdf
    corrupt_pdf = FIXTURES_DIR / "ocr_corrupto.pdf"
    assert corrupt_pdf.exists()

    doc = pymupdf.open(corrupt_pdf)
    try:
        classification = classify_page(doc[0])
        assert classification.tipo == TipoPagina.NEEDS_AI
        assert classification.bypass_opencv is False
        assert classification.readability_score < 0.60
    finally:
        doc.close()


def test_classify_page_short_clean_text_remains_local():
    # US-05 Escenario 2: 40 clean words
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    short_clean = (
        "Por medio del presente documento certificamos que la empresa contratista "
        "ha dado estricto cumplimiento a los acuerdos pactados en el acta de inicio. "
        "Se autoriza el pago correspondiente al mes en curso sin penalizaciones adicionales."
    )
    page.insert_textbox(page.rect, short_clean)

    classification = classify_page(page, bypass_threshold=80)
    doc.close()

    assert classification.tipo == TipoPagina.LOCAL
    assert classification.word_count < 80
    assert classification.readability_score >= 0.65
