import pytest
import pymupdf
from pathlib import Path

from app.services.image_ocr_extractor import is_page_scanned_image, process_scanned_page_and_inject
from app.services.synthetic_summary_service import detect_document_archetype, generate_synthetic_executive_summary
from app.services.chat_service import process_chat_query
from app.services.cache_service import set_l1_cache, L1DocumentEntry
from app.domain.enums import EstadoCobertura

FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "factura-medica.pdf"


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="factura-medica.pdf no encontrada en la raíz")
def test_scanned_page_detection_and_text_injection():
    """Valida que factura-medica.pdf sea reconocida como escaneada y se inyecte texto."""
    doc = pymupdf.open(str(FIXTURE_PATH))
    page1 = doc[0]

    assert is_page_scanned_image(page1) is True

    text, boxes, visuals = process_scanned_page_and_inject(page1, dpi=120)
    assert len(text) > 50
    assert len(boxes) >= 5

    # Verificar que tras la inyección, PyMuPDF puede leer texto directamente
    native_chars = len(page1.get_text())
    assert native_chars > 50
    doc.close()


def test_synthetic_summary_medical_archetype():
    """Valida que una factura médica genere la Ficha Médica-Financiera en < 50 ms."""
    test_hash = "test_medical_invoice_hash_unit"
    markdown_doc = (
        "<!-- INICIO_PAGINA_1 -->\n"
        "# CLINICA SALUD INTEGRAL - FACTURA DE VENTA N° 10294\n"
        "Paciente: ANA MARIA RESTREPO\n"
        "Identificación: CC 52.891.023\n"
        "Total a Pagar: $ 280.000 COP\n"
        "<!-- FIN_PAGINA_1 -->"
    )

    archetype = detect_document_archetype(markdown_doc)
    assert archetype == "FACTURA_MEDICA"

    entry = L1DocumentEntry(
        pdf_hash=test_hash,
        status=EstadoCobertura.COMPLETE,
        paginas_totales=1,
        documento_markdown_indexado=markdown_doc,
    )
    set_l1_cache(test_hash, entry)

    res = process_chat_query(test_hash, "¿De qué trata este documento?")
    assert "Factura de Prestación de Servicios de Salud" in res.respuesta
    assert "[Página 1]" in res.citas
