import hashlib
from typing import Optional, Tuple
import pymupdf

from app.settings import settings
from app.domain.errors import (
    DocumentoInvalidoError,
    TamanoArchivoExcedidoError,
    DocumentoCorruptoOEncriptadoError,
    ExcesoPaginasError,
)

PDF_MAGIC_BYTES = b"%PDF"


def validate_and_read_pdf(
    pdf_bytes: bytes,
    filename: Optional[str] = None,
    max_file_size: Optional[int] = None,
    max_pages: Optional[int] = None,
) -> Tuple[str, pymupdf.Document, int]:
    """
    Valida e ingesta un documento PDF directamente en memoria sin persistencia en disco.

    Aplica las reglas:
    - RNF-022: Procesamiento 100% en memoria (RAM), 0 escrituras a disco.
    - RV-001 / RF-001: Validación de extensión y bytes mágicos (%PDF en los primeros 1024 bytes).
    - RV-002: Límite de tamaño de archivo (por defecto 25 MB).
    - RV-003 / US-01: Detección y rechazo de PDFs corruptos o protegidos con contraseña.
    - RV-006 / US-03: Límite de páginas (por defecto <= 20 páginas).
    - RF-003: Cálculo del hash criptográfico SHA-256 sobre los bytes crudos.

    Retorna:
        Tuple[str, pymupdf.Document, int]: (pdf_hash, fitz_doc, total_paginas)
    """
    limit_bytes = max_file_size or settings.MAX_FILE_SIZE_BYTES
    limit_pages = max_pages or settings.MAX_PAGES_PER_DOCUMENT

    # 1. Validación de nombre de archivo si fue proporcionado
    if filename:
        clean_name = filename.strip().lower()
        if not clean_name.endswith(".pdf"):
            raise DocumentoInvalidoError("Solo se permiten archivos en formato PDF (.pdf).")

    # 2. Validación de archivo no vacío
    if not pdf_bytes or len(pdf_bytes) == 0:
        raise DocumentoInvalidoError("El archivo provisto está vacío.")

    # 3. Validación de tamaño máximo de archivo
    received_bytes = len(pdf_bytes)
    if received_bytes > limit_bytes:
        raise TamanoArchivoExcedidoError(max_bytes=limit_bytes, received_bytes=received_bytes)

    # 4. Validación de firma binaria mágica (%PDF en la cabecera)
    header = pdf_bytes[:1024]
    if PDF_MAGIC_BYTES not in header:
        raise DocumentoInvalidoError("El archivo provisto no es un PDF válido o no cuenta con la cabecera %PDF.")

    # 5. Cálculo determinista de hash SHA-256
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # 6. Apertura e inspección en memoria con PyMuPDF
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise DocumentoCorruptoOEncriptadoError(
            f"El documento PDF está corrupto o mal formado y no pudo ser abierto: {str(exc)}"
        ) from exc

    # 7. Verificación de cifrado / contraseña
    if doc.is_encrypted or doc.needs_pass:
        doc.close()
        raise DocumentoCorruptoOEncriptadoError(
            "El documento PDF está protegido con contraseña y no puede ser procesado sin credenciales."
        )

    # 8. Verificación de conteo de páginas
    page_count = doc.page_count
    if page_count == 0:
        doc.close()
        raise DocumentoInvalidoError("El documento PDF no contiene páginas válidas.")

    if page_count > limit_pages:
        doc.close()
        raise ExcesoPaginasError(max_pages=limit_pages, total_pages=page_count)

    return pdf_hash, doc, page_count
