"""
PyDective — Servicio Autónomo de OCR Local (OCR-01)
Provee reconocimiento óptico de caracteres local de alta velocidad sin dependencias externas
del sistema (ej. sin requerir instalación de Tesseract binario en PATH).
Utiliza RapidOCR basado en ONNX Runtime sobre CPU con AVX2 para PDFs escaneados e imágenes forenses.
"""

import re
import logging
from typing import List, Tuple, Dict, Any, Optional
import pymupdf
import numpy as np

logger = logging.getLogger(__name__)

_OCR_ENGINE = None
_OCR_INITIALIZED = False


def get_ocr_engine():
    """Retorna la instancia singleton del motor RapidOCR o None si no está disponible."""
    global _OCR_ENGINE, _OCR_INITIALIZED
    if not _OCR_INITIALIZED:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR_ENGINE = RapidOCR()
            logger.info("Motor RapidOCR inicializado exitosamente en modo CPU/ONNX Runtime.")
        except Exception as exc:
            logger.warning("RapidOCR no disponible en el entorno local: %s", exc)
            _OCR_ENGINE = None
        _OCR_INITIALIZED = True
    return _OCR_ENGINE


def is_ocr_available() -> bool:
    """Retorna True si el motor de OCR local está disponible para inferencia."""
    return get_ocr_engine() is not None


def clean_ocr_line(line: str) -> str:
    """
    Sanea confusiones fonéticas y morfológicas frecuentes de motores OCR en documentos
    administrativos, notariales y financieros hispanos.
    """
    if not line:
        return ""
    cleaned = line.strip()
    # Correcciones de valor económico
    cleaned = re.sub(r'(?i)\bvalqr\b', 'valor', cleaned)
    cleaned = re.sub(r'(?i)valqrdeclarado', 'valor declarado', cleaned)
    # Correcciones de fecha
    cleaned = re.sub(r'(?i)fechadeactuac[^\s:]*', 'fecha de actuacion', cleaned)
    cleaned = re.sub(r'(?i)cbrculo', 'circulo', cleaned)
    # Correcciones de terminaciones Q por O en nombres propios (ej. ANTONIQ -> ANTONIO, antoniq -> antonio)
    cleaned = re.sub(r'([A-Z]{3,})Q\b', r'\g<1>O', cleaned)
    cleaned = re.sub(r'([a-z]{3,})q\b', r'\g<1>o', cleaned)
    # Correcciones de términos frecuentes en documentos de identidad y médicos
    cleaned = re.sub(r'(?i)\bteiefooo\b|\btelefooo\b', 'telefono', cleaned)
    cleaned = re.sub(r'(?i)\bidentificaceen\b', 'identificacion', cleaned)
    cleaned = re.sub(r'(?i)\bc[ií]lidaoania\b|\bciudaania\b|\bciuoadania\b', 'ciudadania', cleaned)
    cleaned = re.sub(r'(?i)\bpfevisalod\b', 'Previsalud', cleaned)
    # Separación de apellidos fusionados por artefactos de escaneo
    cleaned = re.sub(
        r'([A-Z]{3,})(OSPINA|MEJIA|ALVAREZ|HENAO|BOTERO|RIVERA|CASTILLO|LONDONO|TORRES|DUQUE)',
        r'\1 \2',
        cleaned,
    )
    return cleaned


def extract_page_ocr(
    page: pymupdf.Page,
    dpi: int = 150,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Ejecuta el pipeline de OCR local sobre una página PDF renderizada como pixmap RGB.
    Retorna el texto unificado y la lista de cajas de texto con coordenadas en puntos PDF.
    """
    engine = get_ocr_engine()
    if engine is None:
        return "", []

    page_rect = page.rect
    if page_rect.width <= 0 or page_rect.height <= 0:
        return "", []

    try:
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        img_arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
        ocr_results, _ = engine(img_arr)
    except Exception as exc:
        logger.error("Error ejecutando inferencia OCR en página %s: %s", page.number + 1, exc)
        return "", []

    if not ocr_results:
        return "", []

    scale_x = pix.width / page_rect.width
    scale_y = pix.height / page_rect.height

    lines: List[str] = []
    boxes: List[Dict[str, Any]] = []

    for item in ocr_results:
        poly_pts = item[0]
        raw_text = str(item[1]).strip()
        score = float(item[2])

        cleaned_text = clean_ocr_line(raw_text)
        if not cleaned_text:
            continue

        lines.append(cleaned_text)

        # Convertir polígono de 4 esquinas a bounding box ortogonal [x0, y0, x1, y1] en puntos PDF
        xs = [pt[0] for pt in poly_pts]
        ys = [pt[1] for pt in poly_pts]
        bbox_pt = [
            round(min(xs) / scale_x, 2),
            round(min(ys) / scale_y, 2),
            round(max(xs) / scale_x, 2),
            round(max(ys) / scale_y, 2),
        ]

        boxes.append({
            "text": cleaned_text,
            "raw_text": raw_text,
            "score": round(score, 3),
            "bbox": bbox_pt,
        })

    full_text = "\n".join(lines)
    return full_text, boxes


def inject_ocr_text_layer(page: pymupdf.Page, ocr_boxes: List[Dict[str, Any]]) -> None:
    """
    Inyecta una capa de texto invisible (render_mode=3) con escala tipografica adaptable.
    Asegura que todo el texto detectado por el OCR encaje en su bounding box sin ser descartado.
    """
    for b in ocr_boxes:
        bbox = b.get("bbox")
        text = b.get("text", "")
        if not bbox or not text:
            continue
        try:
            rect = pymupdf.Rect(bbox)
            inserted = False
            # Cascada decreciente de tamano de fuente para evitar rechazo por desbordamiento en PyMuPDF
            for fs in (10.0, 8.5, 7.0, 6.0, 5.0, 4.0, 3.0):
                if page.insert_textbox(rect, text, fontsize=fs, render_mode=3) >= 0:
                    inserted = True
                    break
            if not inserted:
                # Fallback de posicionamiento puntual si la caja es excesivamente angosta
                point = pymupdf.Point(rect.x0, min(rect.y1, rect.y0 + 8.0))
                page.insert_text(point, text, fontsize=6.0, render_mode=3)
        except Exception as exc:
            logger.debug("Error inyectando texto OCR '%s': %s", text, exc)

