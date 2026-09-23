import hashlib
from pathlib import Path
import pytest
import pymupdf

from app.domain.errors import (
    DocumentoInvalidoError,
    TamanoArchivoExcedidoError,
    DocumentoCorruptoOEncriptadoError,
    ExcesoPaginasError,
)
from app.services.ingestion_service import validate_and_read_pdf

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_valid_pdf_ingestion_in_memory():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists(), "Fixture digital_factura.pdf must exist"

    raw_bytes = pdf_path.read_bytes()
    expected_hash = hashlib.sha256(raw_bytes).hexdigest()

    pdf_hash, doc, pages = validate_and_read_pdf(raw_bytes, filename="factura.pdf")
    try:
        assert pdf_hash == expected_hash
        assert pages == 1
        assert isinstance(doc, pymupdf.Document)
        assert not doc.is_closed
    finally:
        doc.close()


def test_rejects_empty_file():
    with pytest.raises(DocumentoInvalidoError) as exc_info:
        validate_and_read_pdf(b"", filename="vacio.pdf")
    assert exc_info.value.code == "INVALID_PDF"


def test_rejects_non_pdf_extension():
    with pytest.raises(DocumentoInvalidoError) as exc_info:
        validate_and_read_pdf(b"%PDF-1.4\n...", filename="documento.docx")
    assert exc_info.value.code == "INVALID_PDF"


def test_rejects_file_missing_pdf_magic_header():
    fake_content = b"This is plain text with no PDF magic header"
    with pytest.raises(DocumentoInvalidoError) as exc_info:
        validate_and_read_pdf(fake_content, filename="falso.pdf")
    assert exc_info.value.code == "INVALID_PDF"


def test_rejects_file_exceeding_max_size():
    # Simulate a file larger than max_file_size limit
    small_limit = 100
    oversized_bytes = b"%PDF-1.4 " + (b"A" * 200)

    with pytest.raises(TamanoArchivoExcedidoError) as exc_info:
        validate_and_read_pdf(oversized_bytes, filename="pesado.pdf", max_file_size=small_limit)

    assert exc_info.value.code == "FILE_SIZE_EXCEEDED"
    assert exc_info.value.max_bytes == small_limit
    assert exc_info.value.received_bytes == len(oversized_bytes)


def test_rejects_corrupted_pdf():
    # Header starts with %PDF but rest of stream is completely broken
    corrupted_bytes = b"%PDF-1.4\ncorrupted content that pymupdf cannot parse"
    with pytest.raises(DocumentoCorruptoOEncriptadoError) as exc_info:
        validate_and_read_pdf(corrupted_bytes, filename="corrupto.pdf")
    assert exc_info.value.code == "CORRUPTED_OR_ENCRYPTED_PDF"


def test_rejects_encrypted_pdf():
    # Create an encrypted PDF in memory
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Confidencial")
    
    # Save with user and owner passwords
    encrypted_bytes = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="secret123",
        owner_pw="master123",
    )
    doc.close()

    with pytest.raises(DocumentoCorruptoOEncriptadoError) as exc_info:
        validate_and_read_pdf(encrypted_bytes, filename="protegido.pdf")
    assert exc_info.value.code == "CORRUPTED_OR_ENCRYPTED_PDF"


def test_accepts_exactly_20_pages():
    stress_pdf = FIXTURES_DIR / "multipage_stress_20p.pdf"
    assert stress_pdf.exists()

    raw_bytes = stress_pdf.read_bytes()
    pdf_hash, doc, pages = validate_and_read_pdf(raw_bytes, filename="stress.pdf", max_pages=20)
    try:
        assert pages == 20
    finally:
        doc.close()


def test_rejects_exceeding_20_pages():
    # Create a 21-page PDF in memory
    doc = pymupdf.open()
    for i in range(21):
        p = doc.new_page()
        p.insert_text((50, 50), f"Página {i+1}")
    pdf_21p_bytes = doc.tobytes()
    doc.close()

    with pytest.raises(ExcesoPaginasError) as exc_info:
        validate_and_read_pdf(pdf_21p_bytes, filename="21_paginas.pdf", max_pages=20)

    assert exc_info.value.code == "PAGE_LIMIT_EXCEEDED"
    assert exc_info.value.max_pages == 20
    assert exc_info.value.total_pages == 21
