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
    try:
        import rapidocr_onnxruntime
    except ImportError:
        pytest.skip("rapidocr_onnxruntime no instalado o sin wheel compatible en este entorno Python")
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


def test_inject_ocr_text_layer_and_name_extraction():
    # Valida inyeccion de capa OCR y extraccion de nombre y notario en doc_051_escaneo.pdf
    pdf_path = FIXTURES_DIR / "doc_051_escaneo.pdf"
    if not pdf_path.exists():
        pytest.skip("Fixture doc_051_escaneo.pdf no encontrado")

    from app.services.ocr_service import inject_ocr_text_layer
    from app.services.spatial_extraction_service import extract_spatial_key_values

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    full_text, boxes = extract_page_ocr(page)
    inject_ocr_text_layer(page, boxes)

    # Validar que tras la inyeccion, las palabras estan disponibles en la pagina
    words = page.get_text("words")
    assert len(words) >= 10

    # Comprobar extraccion espacial directa
    findings = extract_spatial_key_values(page, ["nombre", "notario", "fecha", "valor"])
    f_map = {f.parametro: f for f in findings}

    assert "nombre" in f_map
    assert f_map["nombre"].valor == "ROBERTO ANTONIO JARAMILLO OSPINA"
    assert f_map["nombre"].confianza >= 0.90
    assert len(f_map["nombre"].evidencias) == 1

    assert "fecha" in f_map
    assert f_map["fecha"].valor == "2026-01-15"

    assert "valor" in f_map
    assert "1.250.000" in f_map["valor"].valor

    doc.close()


def test_ocr_directml_and_graceful_cpu_fallback(monkeypatch):
    """
    Verifica que el motor opera con aceleración DirectML (GPU) si está presente,
    y que ante la ausencia de GPU o DirectML conmuta transparentemente a CPUExecutionProvider
    sin generar excepciones ni fallas de extracción.
    """
    from app.services import ocr_service

    # 1. Verificar proveedor activo
    provider_name = ocr_service.get_ocr_provider_name()
    assert provider_name in ("DirectML (GPU DirectX 12)", "CPUExecutionProvider (AVX2)")

    # 2. Forzar motor CPU de respaldo explícito
    cpu_engine = ocr_service.get_ocr_engine(force_cpu=True)
    assert cpu_engine is not None
    assert "CPUExecutionProvider" in cpu_engine.text_det.infer.session.get_providers()

    # 3. Simular entorno sin GPU (DirectML no disponible)
    monkeypatch.setattr(ocr_service, "is_directml_available", lambda: False)
    monkeypatch.setattr(ocr_service, "_OCR_INITIALIZED", False)
    monkeypatch.setattr(ocr_service, "_OCR_ENGINE", None)

    fallback_engine = ocr_service.get_ocr_engine()
    assert fallback_engine is not None
    assert ocr_service.get_ocr_provider_name() == "CPUExecutionProvider (AVX2)"
    assert "CPUExecutionProvider" in fallback_engine.text_det.infer.session.get_providers()


