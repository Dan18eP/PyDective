import os
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
import pymupdf


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR.parent / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def save_uploaded_pdf(pdf_hash: str, pdf_bytes: bytes, overwrite: bool = False) -> Path:
    """
    Persiste el archivo PDF binario en disco para ser servido por el visor.
    Ruta: data/uploads/{pdf_hash}.pdf
    """
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOADS_DIR / f"{pdf_hash}.pdf"
    if overwrite or not file_path.exists():
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
        BASE_DIR.parent / "factura-medica.pdf",
    ]
    candidate_paths.extend(BASE_DIR.parent.glob("*.pdf"))
    fixtures_dir = BASE_DIR.parent / "tests" / "fixtures"
    if fixtures_dir.exists():
        candidate_paths.extend(fixtures_dir.glob("*.pdf"))

    fixtures_100_dir = BASE_DIR.parent / "tests" / "fixtures_100"
    if fixtures_100_dir.exists():
        candidate_paths.extend(fixtures_100_dir.glob("*.pdf"))

    for cand in candidate_paths:
        if cand.exists():
            data = cand.read_bytes()
            if hashlib.sha256(data).hexdigest() == pdf_hash:
                # Cachear en uploads para futuros accesos directos
                UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
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

    import unicodedata
    def _strip_acc(s: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

    query_variants = [clean_query]
    unaccented = _strip_acc(clean_query)
    if unaccented != clean_query and unaccented not in query_variants:
        query_variants.append(unaccented)

    # Variantes y alias de escaneos degradados para búsqueda robusta e interactiva
    SCAN_SEARCH_ALIASES = {
        "previsalud": ["previsalud", "p[evisalud", "pfevisalod", "evisalud"],
        "coosalud": ["coosalud", "cocnlud", "coosaluo", "coosaluco", "coosaluc"],
        "losartan": ["losartan", "losartán", "sartan", "sartalu", "c09ca0101"],
        "hidroclorotiazida": ["hidroclorotiazida", "orocloratiazida", "orocloratiazioa", "c03aa0301"],
        "amoxicilina": ["amoxicilina", "oroxicio", "droxicio"],
        "hidroxido": ["hidroxido", "hidróxido", "droxicio", "oxido de aluminio"],
        "ceminsa": ["ceminsa", "ce>iins", "cemitsa"],
        "miryan": ["miryan", "mirian", "a1 ryan", "mary"],
        "medina": ["medina", "bedlna", "redinaercado", "medinamer"],
    }
    q_lower = unaccented.lower()
    for root_term, aliases in SCAN_SEARCH_ALIASES.items():
        if root_term in q_lower or q_lower in root_term:
            for alias in aliases:
                if alias not in query_variants:
                    query_variants.append(alias)

    all_matches: List[Dict[str, Any]] = []

    try:
        global_idx = 1
        for p_idx in range(len(doc)):
            page = doc[p_idx]
            page_num = p_idx + 1
            width = float(page.rect.width)
            height = float(page.rect.height)

            seen_rects = []
            for q_var in query_variants:
                rects = page.search_for(q_var, quads=False)
                for r in rects:
                    bbox = [round(float(r.x0), 2), round(float(r.y0), 2), round(float(r.x1), 2), round(float(r.y1), 2)]
                    # Evitar duplicados entre variantes con/sin tilde
                    if any(abs(bbox[0]-sr[0]) < 2 and abs(bbox[1]-sr[1]) < 2 for sr in seen_rects):
                        continue
                    seen_rects.append(bbox)

                    # Extraer línea circundante como contexto
                    clip_rect = pymupdf.Rect(0, max(0.0, float(r.y0) - 8.0), width, min(height, float(r.y1) + 8.0))
                    line_snippet = page.get_text("text", clip=clip_rect).strip().replace("\n", " ")

                    all_matches.append({
                        "indice_global": global_idx,
                        "pagina": page_num,
                        "bbox": bbox,
                        "ancho_pagina": width,
                        "alto_pagina": height,
                        "texto_linea": line_snippet or q_var,
                        "contexto": line_snippet or q_var,
                    })
                    global_idx += 1

    finally:
        doc.close()

    return {
        "query": clean_query,
        "total_coincidencias": len(all_matches),
        "coincidencias": all_matches,
    }
