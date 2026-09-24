import os
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
import pymupdf


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR.parent / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def save_uploaded_pdf(pdf_hash: str, pdf_bytes: bytes) -> Path:
    """
    Persiste el archivo PDF binario en disco para ser servido por el visor.
    Ruta: data/uploads/{pdf_hash}.pdf
    """
    file_path = UPLOADS_DIR / f"{pdf_hash}.pdf"
    if not file_path.exists():
        file_path.write_bytes(pdf_bytes)
    return file_path


def get_pdf_bytes_by_hash(pdf_hash: str) -> Optional[bytes]:
    """
    Recupera los bytes del PDF dado su hash SHA-256.
    Busca en data/uploads/, en el documento sintético de 20 páginas y en tests/fixtures/.
    """
    # 1. Almacenamiento directo en data/uploads/
    target_file = UPLOADS_DIR / f"{pdf_hash}.pdf"
    if target_file.exists():
        return target_file.read_bytes()

    # 2. Búsqueda en archivos conocidos del workspace
    candidate_paths = [
        BASE_DIR.parent / "documento_completo_20_paginas.pdf",
    ]
    fixtures_dir = BASE_DIR.parent / "tests" / "fixtures"
    if fixtures_dir.exists():
        candidate_paths.extend(fixtures_dir.glob("*.pdf"))

    for cand in candidate_paths:
        if cand.exists():
            data = cand.read_bytes()
            if hashlib.sha256(data).hexdigest() == pdf_hash:
                # Cachear en uploads para futuros accesos directos
                target_file.write_bytes(data)
                return data

    return None


def search_exact_pdf_occurrences(pdf_hash: str, query: str) -> Dict[str, Any]:
    """
    Ejecuta búsqueda de coincidencias exactas con PyMuPDF en el binario del PDF.
    Retorna coordenadas rectangulares exactas [x0, y0, x1, y1] por página,
    dimensiones de la página y fragmento de texto circundante.
    """
    pdf_bytes = get_pdf_bytes_by_hash(pdf_hash)
    if not pdf_bytes:
        return {
            "query": query,
            "total_coincidencias": 0,
            "coincidencias": [],
            "error": f"Documento con hash '{pdf_hash}' no encontrado.",
        }

    clean_query = query.strip()
    if not clean_query:
        return {
            "query": query,
            "total_coincidencias": 0,
            "coincidencias": [],
        }

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    all_matches: List[Dict[str, Any]] = []

    try:
        global_idx = 1
        for p_idx in range(len(doc)):
            page = doc[p_idx]
            page_num = p_idx + 1
            width = float(page.rect.width)
            height = float(page.rect.height)

            # PyMuPDF búsqueda insensible a mayúsculas
            rects = page.search_for(clean_query, quads=False)
            for r in rects:
                bbox = [round(float(r.x0), 2), round(float(r.y0), 2), round(float(r.x1), 2), round(float(r.y1), 2)]

                # Extraer línea circundante como contexto
                clip_rect = pymupdf.Rect(0, max(0.0, float(r.y0) - 8.0), width, min(height, float(r.y1) + 8.0))
                line_snippet = page.get_text("text", clip=clip_rect).strip().replace("\n", " ")

                all_matches.append({
                    "indice_global": global_idx,
                    "pagina": page_num,
                    "bbox": bbox,
                    "ancho_pagina": width,
                    "alto_pagina": height,
                    "texto_linea": line_snippet,
                    "contexto": line_snippet,
                })
                global_idx += 1

    finally:
        doc.close()

    return {
        "query": clean_query,
        "total_coincidencias": len(all_matches),
        "coincidencias": all_matches,
    }
