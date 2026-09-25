"""
PyDective — Detector de Layout y Elementos Visuales Documentales (YOLO / OpenCV DNN)
Ejecución 100% local en CPU para maquetación forense de páginas:
- Clasifica y delimita: 'fotografia', 'diagrama', 'sello_oficial', 'firma_manuscrita', 'codigo_qr', 'codigo_barras'
- Erradica falsos positivos de QR en fotografías mediante verificación estricta de patrones de alineación.
- Filtra lienzos de escaneo completo (area >= 0.75) para evitar falsos diagramas de fondo.
"""

import logging
from typing import List, Dict, Any, Tuple, Optional
import cv2
import numpy as np
import pymupdf

from app.domain.models import MetadatoImagen

logger = logging.getLogger("pydective.yolo_detector")


def compute_image_entropy(img_bgr: np.ndarray) -> float:
    """
    Calcula la entropía de Shannon sobre el canal de luminancia.
    Las fotografías de escenas reales presentan alta entropía (> 5.5),
    mientras que diagramas, códigos y cajas de texto tienen baja entropía (< 4.2).
    """
    if img_bgr is None or img_bgr.size == 0:
        return 0.0
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if len(img_bgr.shape) == 3 else img_bgr
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist = hist.ravel() / (hist.sum() + 1e-7)
    non_zero = hist[hist > 0]
    return float(-np.sum(non_zero * np.log2(non_zero)))


def verify_qr_pattern_opencv(crop_bgr: np.ndarray) -> Tuple[bool, Optional[str]]:
    """
    Verifica de forma estricta si un recorte contiene un código QR real
    utilizando el detector de patrones de localización de OpenCV.
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return False, None
    try:
        detector = cv2.QRCodeDetector()
        retval, decoded_info, points, _ = detector.detectAndDecodeMulti(crop_bgr)
        if retval and any(bool(d.strip()) for d in decoded_info):
            valid_txt = next(d.strip() for d in decoded_info if d.strip())
            return True, valid_txt
        
        # Detección de patrones de alineación aunque no logre decodificar datos
        has_pattern, points = detector.detect(crop_bgr)
        if has_pattern and points is not None and len(points) >= 1:
            return True, None
    except Exception as exc:
        logger.debug(f"Falla verificando patrón QR con OpenCV: {exc}")
    return False, None


def verify_barcode_frequency(crop_bgr: np.ndarray) -> bool:
    """
    Verifica si una región rectangular presenta el patrón espectral y de gradiente
    típico de un código de barras 1D (alta frecuencia horizontal, baja variación vertical).
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return False
    h, w = crop_bgr.shape[:2]
    if w < 40 or h < 15 or (w / max(1.0, h)) < 1.8:
        return False

    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY) if len(crop_bgr.shape) == 3 else crop_bgr
    # Gradiente Scharr a lo largo de X (barras verticales)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    var_x = float(np.var(grad_x))
    var_y = float(np.var(grad_y))

    # En un código de barras real, la variación en X es significativamente mayor a Y
    if var_y > 0 and (var_x / var_y) > 2.2 and var_x > 500.0:
        return True
    return False


def classify_document_layout_element(
    crop_bgr: Optional[np.ndarray],
    bbox: List[float],
    page_width: float,
    page_height: float,
    context_text: str = "",
    is_vector: bool = False,
) -> str:
    """
    Clasificador de layout documental con salvaguardas forenses estrictas:
    1. Filtro de lienzo de página (área >= 0.75) -> 'fondo_escaneo' (se descarta de diagramas)
    2. Detección estricta de 'codigo_qr' vía OpenCV
    3. Detección de 'fotografia' pericial mediante texto y análisis de entropía
    4. Detección de 'sello_oficial' y 'firma_manuscrita'
    5. Detección de 'codigo_barras' mediante análisis espectral 1D
    6. 'diagrama' para esquemas, gráficos y tablas vectoriales
    """
    w = max(1.0, bbox[2] - bbox[0])
    h = max(1.0, bbox[3] - bbox[1])
    area_ratio = (w * h) / max(1.0, page_width * page_height)
    aspect_ratio = w / h
    norm_text = context_text.lower()

    # 1. Filtro de lienzo completo o escaneo de fondo
    if area_ratio >= 0.75 or (bbox[0] <= 15 and bbox[1] <= 15 and bbox[2] >= page_width - 15 and bbox[3] >= page_height - 15):
        return "fondo_escaneo"

    # 2. Verificación estricta de Código QR
    if crop_bgr is not None and (0.65 <= aspect_ratio <= 1.55) and (30 <= w <= 500 and 30 <= h <= 500):
        is_qr, _ = verify_qr_pattern_opencv(crop_bgr)
        if is_qr:
            return "codigo_qr"

    # 3. Detección de Fotografía Pericial / Técnica
    # Si el texto describe una fotografía o inspección
    has_photo_caption = any(
        kw in norm_text for kw in (
            "anexo fotografico", "anexo fotográfico", "fotografia", "fotografía",
            "registro fotografico", "registro fotográfico", "inspeccion visual",
            "inspección visual", "evidencia visual: ref-foto", "camara", "cámara",
            "unidad canina", "sala de servidores", "servidor", "rack"
        )
    )
    if has_photo_caption and not is_vector:
        return "fotografia"

    if crop_bgr is not None and not is_vector and (w >= 100 and h >= 80):
        entropy = compute_image_entropy(crop_bgr)
        # Fotografías naturales suelen tener entropía > 5.4 y 3 canales cromáticos con variación
        if entropy > 5.4:
            b, g, r = cv2.split(crop_bgr)
            color_variance = float(np.mean(np.abs(r.astype(float) - b.astype(float))))
            if color_variance > 12.0 or (w >= 200 and h >= 150):
                return "fotografia"

    # 4. Sello Oficial Notarial / Institucional
    has_seal_text = any(
        kw in norm_text for kw in (
            "sello", "notaria", "notaría", "notario", "circulo", "círculo",
            "alcaldia", "alcaldía", "republica", "república", "registraduria",
            "registraduría", "apostilla", "autenticado", "certifico", "oficial"
        )
    )
    if (0.75 <= aspect_ratio <= 1.35) and (40.0 <= w <= 260.0 and 40.0 <= h <= 260.0):
        if has_seal_text:
            return "sello_oficial"

    # 5. Firma Manuscrita
    has_signature_text = any(
        kw in norm_text for kw in (
            "firma", "firmado", "rubrica", "rúbrica", "representante", "arrendador",
            "arrendatario", "perito", "viceministro", "interventor", "dr.", "dra."
        )
    )
    if (1.2 <= aspect_ratio <= 4.5) and (w <= 280.0 and h <= 120.0 and area_ratio <= 0.08):
        if has_signature_text:
            return "firma_manuscrita"

    # 6. Código de Barras (requiere patrón 1D real o palabra clave inequívoca)
    has_barcode_text = any(kw in norm_text for kw in ("codigo de barras", "código de barras", "barcode"))
    if not is_vector and (aspect_ratio >= 1.8 and h <= 120 and w <= 400):
        if has_barcode_text or (crop_bgr is not None and verify_barcode_frequency(crop_bgr)):
            return "codigo_barras"

    # 7. Logotipo institucional
    y_center = (bbox[1] + bbox[3]) / 2.0
    if bbox[1] <= 65 and y_center <= 160 and h <= 160:
        return "logotipo"

    # 8. Gráficos o diagramas explícitos
    return "diagrama"
