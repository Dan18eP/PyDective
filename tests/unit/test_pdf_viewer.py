import hashlib
from pathlib import Path
import pytest

from app.services.pdf_viewer_service import (
    save_uploaded_pdf,
    get_pdf_bytes_by_hash,
    search_exact_pdf_occurrences,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PDF_20P_PATH = BASE_DIR / "documento_completo_20_paginas.pdf"


def test_save_and_retrieve_pdf_bytes(tmp_path):
    sample_data = b"%PDF-1.4 dummy binary content for test"
    sample_hash = hashlib.sha256(sample_data).hexdigest()

    saved_path = save_uploaded_pdf(sample_hash, sample_data)
    assert saved_path.exists()
    assert saved_path.name == f"{sample_hash}.pdf"

    retrieved = get_pdf_bytes_by_hash(sample_hash)
    assert retrieved == sample_data


def test_get_pdf_bytes_missing_hash():
    non_existent_hash = "0" * 64
    assert get_pdf_bytes_by_hash(non_existent_hash) is None


def test_search_exact_pdf_occurrences_on_real_20p_document():
    assert PDF_20P_PATH.exists(), "El documento real de 20 páginas debe existir"
    pdf_bytes = PDF_20P_PATH.read_bytes()
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # Persistir para el servicio
    save_uploaded_pdf(pdf_hash, pdf_bytes)

    # 1. Búsqueda de palabra clave presente en el contrato
    res = search_exact_pdf_occurrences(pdf_hash, "ARRENDAMIENTO")
    assert res["query"] == "ARRENDAMIENTO"
    assert res["total_coincidencias"] > 0
    assert len(res["coincidencias"]) == res["total_coincidencias"]

    first_match = res["coincidencias"][0]
    assert first_match["pagina"] >= 1
    assert len(first_match["bbox"]) == 4
    x0, y0, x1, y1 = first_match["bbox"]
    assert x0 < x1
    assert y0 < y1
    assert first_match["ancho_pagina"] > 0
    assert first_match["alto_pagina"] > 0
    assert "ARRENDAMIENTO".lower() in first_match["contexto"].lower()

    # 2. Búsqueda de números / valores
    res_num = search_exact_pdf_occurrences(pdf_hash, "NIT")
    assert res_num["total_coincidencias"] > 0
    for match in res_num["coincidencias"]:
        assert match["pagina"] >= 1
        assert len(match["bbox"]) == 4

    # 3. Búsqueda de término inexistente
    res_empty = search_exact_pdf_occurrences(pdf_hash, "TERMINO_INEXISTENTE_XYZ_999")
    assert res_empty["total_coincidencias"] == 0
    assert len(res_empty["coincidencias"]) == 0

    # 4. Búsqueda vacía
    res_blank = search_exact_pdf_occurrences(pdf_hash, "   ")
    assert res_blank["total_coincidencias"] == 0
    assert len(res_blank["coincidencias"]) == 0
