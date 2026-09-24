from pathlib import Path
import pymupdf
import pytest

from app.services.ocr_service import (
    is_ocr_available,
    clean_ocr_line,
    extract_page_ocr,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures_100"


def test_ocr_availability():
    # Verifica que el motor RapidOCR basado en ONNX Runtime esté disponible localmente
    assert is_ocr_available() is True


def test_clean_ocr_line_fixes_common_glitches():
    # 1. Corrección de palabras clave económicas
    assert clean_ocr_line("VALQRDECLARADO: $ 1.250.000 COP") == "valor declarado: $ 1.250.000 COP"
    assert clean_ocr_line("VALQR") == "valor"

    # 2. Corrección de fecha y actuación
    assert clean_ocr_line("FECHADEACTUAC1@N: 2026-01-15") == "fecha de actuacion: 2026-01-15"

    # 3. Corrección de terminaciones Q por O en nombres propios
    assert clean_ocr_line("ROBERTO ANTONIQ") == "ROBERTO ANTONIO"
    assert clean_ocr_line("CARLOS EDUARDQ") == "CARLOS EDUARDO"

    # 4. Separación de apellidos hispanos fusionados por OCR
    assert clean_ocr_line("JARAMILLOOSPINA") == "JARAMILLO OSPINA"
    assert clean_ocr_line("RESTREPOMEJIA") == "RESTREPO MEJIA"


def test_extract_page_ocr_on_scanned_pdf():
    pdf_path = FIXTURES_DIR / "doc_051_escaneo.pdf"
    if not pdf_path.exists():
        pytest.skip("Fixture doc_051_escaneo.pdf no encontrado")

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]

    full_text, boxes = extract_page_ocr(page)
    doc.close()

    assert len(full_text) > 0
    assert len(boxes) >= 3

    # Verificar que contiene datos esenciales
    upper_text = full_text.upper()
    assert "2026-01-15" in upper_text
    assert any(k in upper_text for k in ("ROBERTO", "ANTONIO", "JARAMILLO", "OSPINA"))
    assert any(k in upper_text for k in ("1.250.000", "1250000", "COP"))

    # Validar estructura geométrica de las cajas
    for b in boxes:
        assert "text" in b
        assert "bbox" in b
        bbox = b["bbox"]
        assert len(bbox) == 4
        assert bbox[2] > bbox[0]
        assert bbox[3] > bbox[1]


def test_extract_page_ocr_handles_empty_or_invalid():
    # Página en blanco no debe generar errores ni excepciones
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=700)
    full_text, boxes = extract_page_ocr(page)
    doc.close()

    assert full_text == ""
    assert boxes == []
