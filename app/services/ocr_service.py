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
_CPU_FALLBACK_ENGINE = None
_OCR_INITIALIZED = False
_OCR_PROVIDER_NAME = "CPU"


def is_directml_available() -> bool:
    """Retorna True si el proveedor DirectML (GPU DirectX 12) está disponible en el entorno."""
    try:
        import onnxruntime as ort
        return "DmlExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def get_ocr_engine(force_cpu: bool = False):
    """
    Retorna la instancia singleton del motor RapidOCR o None si no está disponible.
    Prioriza aceleración DirectML por hardware (GPU AMD/Intel/NVIDIA vía DirectX 12)
    con fallback transparente y automático a CPU si no hay GPU disponible o si DirectML falla.
    """
    global _OCR_ENGINE, _CPU_FALLBACK_ENGINE, _OCR_INITIALIZED, _OCR_PROVIDER_NAME

    if force_cpu:
        if _CPU_FALLBACK_ENGINE is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                _CPU_FALLBACK_ENGINE = RapidOCR(
                    intra_op_num_threads=6,
                    use_cls=False,
                    det_limit_side_len=720,
                    det_limit_type="max",
                    rec_batch_num=16,
                )
                logger.info("Motor RapidOCR (modo CPU) inicializado como respaldo.")
            except Exception as exc:
                logger.warning("Fallo al inicializar motor CPU de respaldo: %s", exc)
                _CPU_FALLBACK_ENGINE = None
        return _CPU_FALLBACK_ENGINE

    if not _OCR_INITIALIZED:
        try:
            from rapidocr_onnxruntime import RapidOCR
            ocr_params = dict(
                intra_op_num_threads=6,
                use_cls=False,
                det_limit_side_len=720,
                det_limit_type="max",
                rec_batch_num=16,
            )

            # Detectar si DirectML (GPU DirectX 12) está disponible en el entorno
            if is_directml_available():
                try:
                    _OCR_ENGINE = RapidOCR(
                        det_use_dml=True,
                        rec_use_dml=True,
                        **ocr_params,
                    )
                    _OCR_PROVIDER_NAME = "DirectML (GPU DirectX 12)"
                    logger.info("Motor RapidOCR acelerado con DirectML (GPU DirectX 12) inicializado exitosamente.")
                except Exception as dml_exc:
                    logger.warning(
                        "Fallo al inicializar RapidOCR con DirectML (%s). Recurriendo automáticamente a CPU.",
                        dml_exc,
                    )
                    _OCR_ENGINE = RapidOCR(**ocr_params)
                    _OCR_PROVIDER_NAME = "CPUExecutionProvider (AVX2)"
                    logger.info("Motor RapidOCR en CPU inicializado como fallback.")
            else:
                _OCR_ENGINE = RapidOCR(**ocr_params)
                _OCR_PROVIDER_NAME = "CPUExecutionProvider (AVX2)"
                logger.info("Motor RapidOCR en CPU inicializado (DirectML no disponible en el sistema).")
        except Exception as exc:
            logger.warning("RapidOCR no disponible en el entorno local: %s", exc)
            _OCR_ENGINE = None
            _OCR_PROVIDER_NAME = "None"
        _OCR_INITIALIZED = True
    return _OCR_ENGINE


def get_ocr_provider_name() -> str:
    """Retorna el nombre descriptivo del proveedor de ejecución activo (DirectML o CPU)."""
    get_ocr_engine()
    return _OCR_PROVIDER_NAME


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
    cleaned = re.sub(r'(?i)\bgedula\b', 'cedula', cleaned)
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
    img_arr: Optional[np.ndarray] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Ejecuta el pipeline de OCR local optimizado:
    1. Descarte instantáneo de páginas en blanco (<2 ms).
    2. Binarización adaptativa Otsu para aceleración de decodificación CRNN.
    3. Inferencia de cajas de texto con RapidOCR a 150 DPI.
    """
    engine = get_ocr_engine()
    if engine is None:
        return "", []

    page_rect = page.rect
    if page_rect.width <= 0 or page_rect.height <= 0:
        return "", []

    try:
        if img_arr is None:
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            img_arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))

        # 1. Descarte ultrarrápido de páginas en blanco (dorsos vacíos como páginas 2 y 4)
        import cv2
        gray = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY)
        if float(np.std(gray)) < 10.0 and float(np.mean(gray)) > 245.0:
            return "", []

        # 2. Binarización adaptativa Otsu para acelerar decodificación CRNN sin alterar geometría
        from app.services.preprocess_service import evaluate_contrast_and_otsu
        img_prep, _ = evaluate_contrast_and_otsu(img_arr)

        scale_x = img_prep.shape[1] / page_rect.width
        scale_y = img_prep.shape[0] / page_rect.height
        try:
            ocr_results, _ = engine(img_prep)
        except Exception as exc:
            if "DirectML" in _OCR_PROVIDER_NAME:
                logger.warning(
                    "Fallo en inferencia DirectML en página %s (%s). Reintentando con CPUExecutionProvider...",
                    page.number + 1,
                    exc,
                )
                cpu_eng = get_ocr_engine(force_cpu=True)
                if cpu_eng:
                    ocr_results, _ = cpu_eng(img_prep)
                else:
                    logger.error("Error ejecutando inferencia OCR en página %s: %s", page.number + 1, exc)
                    return "", []
            else:
                logger.error("Error ejecutando inferencia OCR en página %s: %s", page.number + 1, exc)
                return "", []
    except Exception as exc:
        logger.error("Error general en pipeline OCR de página %s: %s", page.number + 1, exc)
        return "", []

    if not ocr_results:
        return "", []

    lines: List[str] = []
    boxes: List[Dict[str, Any]] = []

    for item in ocr_results:
        poly_pts = item[0]
        raw_text = str(item[1]).strip()
        score = float(item[2])

        from app.services.text_healing_service import heal_scanned_text
        cleaned_text = heal_scanned_text(clean_ocr_line(raw_text))
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

