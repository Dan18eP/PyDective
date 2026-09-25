import io
import re
import logging
from typing import Optional, Dict, List
import pymupdf

try:
    from markitdown import MarkItDown
    _markitdown_instance = MarkItDown()
except Exception as e:
    _markitdown_instance = None

from app.domain.models import MetadatoImagen
from app.services.cache_service import get_l1_cache, set_l1_cache, L1DocumentEntry
from app.services.pdf_viewer_service import get_pdf_bytes_by_hash

logger = logging.getLogger("pydective.markdown")


def generate_page_indexed_markdown(
    pdf_bytes: bytes,
    metadatos_visuales_por_pagina: Optional[Dict[int, List[MetadatoImagen]]] = None,
    pdf_hash: Optional[str] = None,
) -> str:
    """
    Pipeline de procesamiento 100% en memoria (RAM) optimizado para LLMs.
    1. Abre el PDF con PyMuPDF.
    2. Segmenta virtualmente cada página en memoria.
    3. Convierte cada página a Markdown con MarkItDown (convert_stream).
    4. Si la página es escaneada, ejecuta OCR local multiplataforma de alta resolución (DPI 200)
       e inyecta la capa invisible de texto (render_mode=3).
    5. Aplica saneamiento pericial (Text Healing) para eliminar mojibake y ruido OCR.
    6. Inyecta anclas semánticas de imágenes y comentarios HTML estándar:
       <!-- INICIO_PAGINA_X -->
       ...
       <!-- FIN_PAGINA_X -->
    7. Consolida todas las páginas en un String unificado.
    """
    if not pdf_bytes:
        return ""

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    pages_output: List[str] = []
    any_injected_ocr = False

    for idx in range(total_pages):
        page_num = idx + 1
        page_text = ""

        # Intentar conversión en memoria con MarkItDown
        if _markitdown_instance is not None:
            try:
                single_doc = pymupdf.open()
                single_doc.insert_pdf(doc, from_page=idx, to_page=idx)
                single_bytes = single_doc.tobytes()
                single_doc.close()

                stream = io.BytesIO(single_bytes)
                res = _markitdown_instance.convert_stream(stream, ext=".pdf")
                if res and res.text_content:
                    page_text = res.text_content.strip()
            except Exception as exc:
                logger.debug(f"MarkItDown falló en página {page_num}, usando PyMuPDF directo: {exc}")

        # Fallback o complemento con PyMuPDF directo si MarkItDown no obtuvo texto
        if not page_text:
            page_text = doc[idx].get_text("text").strip()

        # Si aún no hay texto sustantivo (<20 caracteres) y la página es un escaneo o imagen,
        # ejecutar OCR local multiplataforma (Windows Native OCR / RapidOCR) con DPI 200
        if len(page_text) < 20:
            try:
                from app.services.image_ocr_extractor import is_page_scanned_image, extract_page_ocr_cross_platform
                if is_page_scanned_image(doc[idx]):
                    ocr_text, ocr_boxes = extract_page_ocr_cross_platform(doc[idx], dpi=200)
                    if ocr_text and ocr_text.strip():
                        page_text = ocr_text.strip()
                        from app.services.ocr_service import inject_ocr_text_layer
                        inject_ocr_text_layer(doc[idx], ocr_boxes)
                        any_injected_ocr = True
            except Exception as exc:
                logger.debug(f"Error ejecutando OCR en página {page_num}: {exc}")

        # Saneamiento fonético-ortográfico y des-corrupción de glifos en español (Text Healing)
        from app.services.text_healing_service import heal_scanned_text
        page_text = heal_scanned_text(page_text)

        # Normalizar espacios horizontales redundantes preservando saltos de línea
        page_text = re.sub(r"[ \t]{2,}", " ", page_text)

        # Inyectar descripciones de elementos visuales (diagramas, fotos, firmas, sellos)
        visual_notes = []
        if metadatos_visuales_por_pagina and page_num in metadatos_visuales_por_pagina:
            for v in metadatos_visuales_por_pagina[page_num]:
                desc = v.descripcion_visual or v.clasificacion_semantica or "elemento visual"
                if v.contenido_decodificado:
                    desc += f" (datos: {v.contenido_decodificado})"
                visual_notes.append(f"[Elemento Visual: {desc} | Coordenadas: {v.bbox}]")

        if visual_notes:
            visual_block = "\n".join(visual_notes)
            page_text = f"{page_text}\n\n{visual_block}" if page_text else visual_block

        # Estándar de marcación de páginas invisible para frontend
        marked_page = f"<!-- INICIO_PAGINA_{page_num} -->\n{page_text}\n<!-- FIN_PAGINA_{page_num} -->"
        pages_output.append(marked_page)

    if pdf_hash and any_injected_ocr:
        try:
            from app.services.pdf_viewer_service import save_uploaded_pdf
            save_uploaded_pdf(pdf_hash, doc.tobytes(), overwrite=True)
        except Exception as exc:
            logger.debug(f"No se pudo persistir PDF enriquecido con texto OCR: {exc}")

    doc.close()
    return "\n\n".join(pages_output)


def get_or_create_page_indexed_markdown(
    pdf_hash: str,
    pdf_bytes: Optional[bytes] = None,
) -> str:
    """
    Obtiene el Markdown indexado por páginas desde la caché L1 o lo genera en RAM
    y lo almacena para consultas subsecuentes ultrarrápidas (<1s).
    """
    l1_entry: Optional[L1DocumentEntry] = get_l1_cache(pdf_hash)
    if l1_entry and getattr(l1_entry, "documento_markdown_indexado", None):
        return l1_entry.documento_markdown_indexado

    if not pdf_bytes:
        pdf_bytes = get_pdf_bytes_by_hash(pdf_hash)

    if not pdf_bytes:
        return ""

    # Extraer metadatos visuales si existen en L1
    visuals_by_page: Dict[int, List[MetadatoImagen]] = {}
    if l1_entry and l1_entry.resultados_por_pagina:
        for res in l1_entry.resultados_por_pagina:
            if getattr(res, "metadatos_visuales", None):
                visuals_by_page[res.numero_pagina] = res.metadatos_visuales

    markdown_doc = generate_page_indexed_markdown(pdf_bytes, visuals_by_page, pdf_hash=pdf_hash)

    if l1_entry:
        l1_entry.documento_markdown_indexado = markdown_doc
        set_l1_cache(pdf_hash, l1_entry)

    return markdown_doc
