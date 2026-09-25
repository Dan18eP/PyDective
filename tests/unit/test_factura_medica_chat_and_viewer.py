import hashlib
from pathlib import Path
import pytest
from app.services.chat_service import process_chat_query
from app.services.markdown_service import get_or_create_page_indexed_markdown
from app.services.pdf_viewer_service import search_exact_pdf_occurrences


@pytest.fixture(scope="module")
def factura_medica_hash():
    pdf_path = Path(__file__).resolve().parent.parent.parent / "factura-medica.pdf"
    assert pdf_path.exists(), "El archivo factura-medica.pdf debe existir en la raíz"
    pdf_bytes = pdf_path.read_bytes()
    h = hashlib.sha256(pdf_bytes).hexdigest()
    # Asegurar indexación
    get_or_create_page_indexed_markdown(h)
    return h


def test_chat_patient_identity(factura_medica_hash):
    """Verifica resolución pericial y cruzada del paciente titular."""
    res = process_chat_query(factura_medica_hash, "cual es el nombre del paciente")
    assert res is not None
    assert "[Página 1]" in res.citas or "[Página 3]" in res.citas
    assert "MEDINA" in res.respuesta.upper()
    assert "32848952" in res.respuesta or "32.848.952" in res.respuesta
    assert "COOSALUD" in res.respuesta.upper()


def test_chat_cedula_identity(factura_medica_hash):
    """Verifica detección de ambas cédulas en el expediente."""
    res = process_chat_query(factura_medica_hash, "quien es la persona de la cedula")
    assert res is not None
    assert "[Página 5]" in res.citas
    assert "[Página 7]" in res.citas
    assert "32.848.952" in res.respuesta
    assert "1.043.589.150" in res.respuesta
    assert "MEDINA" in res.respuesta.upper()


def test_chat_resume_products(factura_medica_hash):
    """Verifica síntesis limpia de medicamentos formulados y entregados."""
    res = process_chat_query(factura_medica_hash, "resume los productos")
    assert res is not None
    assert "[Página 3]" in res.citas
    assert "LOSARTAN" in res.respuesta.upper()
    assert "HDROCLOROTIAZDA" in res.respuesta.upper() or "HIDROCLOROTIAZIDA" in res.respuesta.upper()
    assert "ALUMINIO" in res.respuesta.upper()


def test_chat_doctor_name(factura_medica_hash):
    """Verifica identificación de la médica tratante y medicina general."""
    res = process_chat_query(factura_medica_hash, "como se llama la medicina general")
    assert res is not None
    assert "[Página 3]" in res.citas
    assert "LINA" in res.respuesta.upper()
    assert "GOMEZ" in res.respuesta.upper()


def test_chat_contact_and_address(factura_medica_hash):
    """Verifica domicilios y sedes de atención."""
    res = process_chat_query(factura_medica_hash, "telefono")
    assert res is not None
    assert "[Página 1]" in res.citas
    assert "3013188556" in res.respuesta
    assert "VILLACARMEN" in res.respuesta.upper() or "CALLE 28" in res.respuesta.upper()


def test_chat_cliente_institutional_and_patient(factura_medica_hash):
    """Verifica diferenciación entre cliente institucional (Coosalud EPS) y paciente titular."""
    res = process_chat_query(factura_medica_hash, "cliente")
    assert res is not None
    assert "[Página 1]" in res.citas
    assert "COOSALUD" in res.respuesta.upper()
    assert "MEDINA" in res.respuesta.upper()


def test_chat_quien_recibe(factura_medica_hash):
    """Verifica quién recibe y reclama los medicamentos en el acta de entrega."""
    res = process_chat_query(factura_medica_hash, "quien recibe")
    assert res is not None
    assert "[Página 1]" in res.citas
    assert "32848952" in res.respuesta
    assert "MEDINA" in res.respuesta.upper()
    assert "QUIEN RECLAMA" in res.respuesta.upper()


def test_chat_sucursal_y_punto(factura_medica_hash):
    """Verifica detección de sucursal 1012 y sedes asistenciales."""
    res_suc = process_chat_query(factura_medica_hash, "sucursal")
    assert res_suc is not None
    assert "[Página 1]" in res_suc.citas
    assert "1012" in res_suc.respuesta
    assert "SABANALARGA" in res_suc.respuesta.upper()

    res_punto = process_chat_query(factura_medica_hash, "cual es el punto")
    assert res_punto is not None
    assert "1012" in res_punto.respuesta


def test_chat_tipo_doc(factura_medica_hash):
    """Verifica catalogación de los tipos documentales presentes en el expediente."""
    res = process_chat_query(factura_medica_hash, "tipo doc")
    assert res is not None
    assert "[Página 3]" in res.citas
    assert "ORDENES MEDICAS" in res.respuesta.upper()


def test_chat_diagnostico_principal(factura_medica_hash):
    """Verifica extracción exacta del diagnóstico principal CIE-10."""
    res = process_chat_query(factura_medica_hash, "diagnostico principal")
    assert res is not None
    assert "[Página 3]" in res.citas
    assert "I10X" in res.respuesta
    assert "HIPERTENSI" in res.respuesta.upper()


def test_chat_aseguradora(factura_medica_hash):
    """Verifica extracción de la EPS / aseguradora."""
    res = process_chat_query(factura_medica_hash, "aseguradora cual es")
    assert res is not None
    assert "[Página 1]" in res.citas or "[Página 3]" in res.citas
    assert "COOSALUD" in res.respuesta.upper()


def test_chat_completely_different_document_no_contamination():
    """Verifica generalización 100% libre de contaminación sobre una factura completamente distinta."""
    import pymupdf
    from app.services.cache_service import invalidate_l1_cache
    from app.services.pdf_viewer_service import save_uploaded_pdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    txt = '''
    FERRETERIA LA TUERCA Y EL TORNILLO S.A.S.
    FACTURA ELECTRONICA DE VENTA
    Sucursal: Sede Industrial 502 - Medellin
    Cliente: Pedro Pablo Perez Gomez
    Telefono: 3105559988
    QUIEN RECIBE: Pedro Pablo Perez Gomez - Firma para constancia
    '''
    page.insert_text(pymupdf.Point(50, 100), txt, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()

    h = hashlib.sha256(pdf_bytes).hexdigest()
    save_uploaded_pdf(h, pdf_bytes)
    invalidate_l1_cache(h)

    res_cli = process_chat_query(h, "cliente")
    assert res_cli is not None
    assert "Pedro Pablo Perez Gomez" in res_cli.respuesta
    assert "Medina" not in res_cli.respuesta
    assert "Coosalud" not in res_cli.respuesta

    res_tel = process_chat_query(h, "telefono")
    assert res_tel is not None
    assert "3105559988" in res_tel.respuesta
    assert "3013188556" not in res_tel.respuesta

    res_suc = process_chat_query(h, "sucursal")
    assert res_suc is not None
    assert "502" in res_suc.respuesta
    assert "Medellin" in res_suc.respuesta
    assert "1012" not in res_suc.respuesta


def test_chat_visual_diagrama_barras_disambiguation():
    """Verifica que 'diagrama de barras' en documento de 20 páginas aísle exclusivamente la Página 2."""
    doc_path = Path(__file__).resolve().parent.parent.parent / "documento_completo_20_paginas.pdf"
    if not doc_path.exists():
        pytest.skip("documento_completo_20_paginas.pdf no encontrado en la raíz")
    h = hashlib.sha256(doc_path.read_bytes()).hexdigest()
    res = process_chat_query(h, "de que trata el diagrama de barras")
    assert res is not None
    assert res.citas == ["[Página 2]"]
    assert "COMPORTAMIENTO FINANCIERO TRIMESTRAL" in res.respuesta


def test_ctrl_f_search_in_scanned_images(factura_medica_hash):
    """Verifica que Ctrl+F localice texto en imágenes escaneadas y retorne bboxes exactos."""
    terms = ["Previsalud", "32848952", "Coosalud", "Losartan", "formula", "Sabanalarga"]
    for term in terms:
        search_res = search_exact_pdf_occurrences(factura_medica_hash, term)
        total = search_res.get("total_coincidencias", 0)
        assert total > 0, f"Debe encontrar coincidencias para '{term}' en factura-medica.pdf"
        first = search_res["coincidencias"][0]
        assert "bbox" in first
        assert len(first["bbox"]) == 4
        assert first["pagina"] >= 1
