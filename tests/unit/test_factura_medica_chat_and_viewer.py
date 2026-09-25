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
    assert "[Página 1]" in res.citas
    assert "[Página 3]" in res.citas
    assert "[Página 7]" in res.citas
    assert "Miryan Esther Medina Mercado" in res.respuesta
    assert "32.848.952" in res.respuesta or "32848952" in res.respuesta
    assert "Coosalud EPS" in res.respuesta


def test_chat_cedula_identity(factura_medica_hash):
    """Verifica detección de ambas cédulas en el expediente."""
    res = process_chat_query(factura_medica_hash, "quien es la persona de la cedula")
    assert res is not None
    assert "[Página 5]" in res.citas
    assert "[Página 7]" in res.citas
    assert "Miryan Esther Medina Mercado" in res.respuesta
    assert "Mirian Esther Medina Blanquiceth" in res.respuesta


def test_chat_resume_products(factura_medica_hash):
    """Verifica síntesis limpia de medicamentos formulados y entregados."""
    res = process_chat_query(factura_medica_hash, "resume los productos")
    assert res is not None
    assert "[Página 1]" in res.citas
    assert "[Página 3]" in res.citas
    assert "Losartán" in res.respuesta
    assert "Hidroclorotiazida" in res.respuesta
    assert "Hidróxido de Aluminio" in res.respuesta


def test_chat_doctor_name(factura_medica_hash):
    """Verifica identificación de la médica tratante y medicina general."""
    res = process_chat_query(factura_medica_hash, "como se llama la medicina general")
    assert res is not None
    assert "[Página 1]" in res.citas
    assert "[Página 3]" in res.citas
    assert "Lina Margarita Gómez" in res.respuesta
    assert "CEMINSA" in res.respuesta


def test_chat_contact_and_address(factura_medica_hash):
    """Verifica domicilios y sedes de atención."""
    res = process_chat_query(factura_medica_hash, "telefono")
    assert res is not None
    assert "[Página 1]" in res.citas
    assert "[Página 3]" in res.citas
    assert "Sabanalarga" in res.respuesta
    assert "Calle 28" in res.respuesta


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
