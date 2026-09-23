import io
import time
from typing import Tuple, Optional
from dataclasses import dataclass
import numpy as np
import cv2
from PIL import Image
import pymupdf

from app.settings import settings


@dataclass
class PreprocessResult:
    numero_pagina: int
    preprocesado: bool
    angulo_corregido: float
    otsu_aplicado: bool
    duracion_ms: float
    image_bytes: bytes  # WebP 1024px q75


def render_page_to_numpy(page: pymupdf.Page, max_dim: int = 1024) -> Tuple[np.ndarray, float]:
    """
    Renderiza una página PDF directamente en C con PyMuPDF (fitz.Matrix)
    escalando la dimensión máxima a max_dim (ADR-004 Sección 3).
    
    Retorna:
        Tuple[np.ndarray, float]: (imagen_rgb_numpy, factor_de_escala)
    """
    rect = page.rect
    width = rect.width
    height = rect.height
    scale = max_dim / max(width, height)

    matrix = pymupdf.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, alpha=False)

    # PyMuPDF samples son RGB
    img_rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
    return img_rgb, scale


def detect_skew_angle(image_rgb: np.ndarray, max_angle: float = 15.0) -> float:
    """
    Detecta el ángulo de inclinación dominante de la página mediante OpenCV (US-06 Escenario 1).
    Acelerado sobre miniatura de 500 px de ancho (< 30 ms de CPU).
    Acotado estrictamente al rango [-max_angle, +max_angle] (típicamente [-15°, +15°]).
    """
    h, w = image_rgb.shape[:2]
    if w == 0 or h == 0:
        return 0.0

    # 1. Reducción a miniatura de ancho 500 px para cálculo acelerado
    thumb_w = 500
    thumb_h = max(int(h * (thumb_w / w)), 1)
    thumb = cv2.resize(image_rgb, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)

    # 2. Conversión a escala de grises y detección de bordes
    gray = cv2.cvtColor(thumb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # 3. Transformada de Hough probabilística para líneas horizontales dominantes
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=60,
        minLineLength=40,
        maxLineGap=8,
    )

    detected_angles = []
    if lines is not None:
        for line in lines:
            coords = line.ravel()
            if len(coords) < 4:
                continue
            x1, y1, x2, y2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0:
                continue
            angle_rad = np.arctan2(dy, dx)
            angle_deg = float(np.degrees(angle_rad))

            # Normalizar para líneas cercanas a la horizontal
            if -max_angle <= angle_deg <= max_angle:
                detected_angles.append(angle_deg)
            elif 180 - max_angle <= abs(angle_deg) <= 180:
                adjusted = angle_deg - 180 if angle_deg > 0 else angle_deg + 180
                if -max_angle <= adjusted <= max_angle:
                    detected_angles.append(adjusted)

    # 4. Fallback con momentos/minAreaRect de componentes conexos si Hough no encontró líneas
    if not detected_angles:
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) > 100:
            rect = cv2.minAreaRect(coords)
            angle = rect[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            if -max_angle <= angle <= max_angle:
                detected_angles.append(angle)

    if not detected_angles:
        return 0.0

    # Mediana robusta ante outliers
    median_angle = float(np.median(detected_angles))

    # Limitar estrictamente al rango [-max_angle, +max_angle]
    bounded_angle = max(-max_angle, min(max_angle, median_angle))
    return round(bounded_angle, 2)


def deskew_image(image_rgb: np.ndarray, angle: float) -> np.ndarray:
    """
    Aplica rotación inversa en alta resolución para enderezar el documento.
    """
    # Si la inclinación es insignificante (< 0.4°), no rotar para evitar artefactos de interpolación
    if abs(angle) < 0.4:
        return image_rgb

    # Acotación estricta de seguridad
    angle_clamped = max(-15.0, min(15.0, angle))

    h, w = image_rgb.shape[:2]
    center = (w / 2, h / 2)

    # Matriz de rotación 2D (rotación inversa = -angle_clamped)
    rot_matrix = cv2.getRotationMatrix2D(center, angle_clamped, 1.0)
    deskewed = cv2.warpAffine(
        image_rgb,
        rot_matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),  # Fondo blanco limpio
    )
    return deskewed


def evaluate_contrast_and_otsu(image_rgb: np.ndarray) -> Tuple[np.ndarray, bool]:
    """
    Evalúa la varianza del histograma y aplica selectivamente binarización de Otsu
    si la imagen presenta bajo contraste, sombras o fondos degradados (US-06 Escenario 2).
    """
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    std_dev = float(np.std(gray))

    # Si la desviación estándar es muy baja (< 40) o hay bajo contraste evidente
    if std_dev < 42.0:
        _, binarized = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binarized_rgb = cv2.cvtColor(binarized, cv2.COLOR_GRAY2RGB)
        return binarized_rgb, True

    return image_rgb, False


def encode_image_to_webp(image_rgb: np.ndarray, quality: int = 75) -> bytes:
    """
    Codifica un array numpy RGB en formato WebP con calidad configurable (por defecto q75).
    """
    pil_img = Image.fromarray(image_rgb)
    buf = io.BytesIO()
    pil_img.save(buf, format="WEBP", quality=quality, method=4)
    return buf.getvalue()


def preprocess_page(page: pymupdf.Page, max_dim: int = 1024, quality: int = 75) -> PreprocessResult:
    """
    Ejecuta el pipeline completo de preprocesamiento de visión en C/OpenCV (US-06):
    1. Renderizado directo en C con fitz.Matrix a 1024px.
    2. Detección de ángulo de inclinación acotado a [-15°, +15°] en miniatura de 500px.
    3. Rotación afín inversa en alta resolución.
    4. Binarización adaptativa de Otsu selectiva ante bajo contraste.
    5. Codificación en memoria a WebP q75.
    """
    start_time = time.perf_counter()
    page_num = page.number + 1

    # 1. Renderizado inicial a max_dim (1024px)
    img_rgb, _ = render_page_to_numpy(page, max_dim=max_dim)

    # 2. Detección de inclinación acotada
    detected_angle = detect_skew_angle(img_rgb, max_angle=15.0)

    # 3. Deskew si la inclinación es apreciable
    was_deskewed = False
    if abs(detected_angle) >= 0.5:
        img_rgb = deskew_image(img_rgb, angle=detected_angle)
        was_deskewed = True

    # 4. Evaluación de contraste y binarización selectiva de Otsu
    img_rgb, otsu_applied = evaluate_contrast_and_otsu(img_rgb)

    # 5. Codificación en memoria a WebP q75
    webp_bytes = encode_image_to_webp(img_rgb, quality=quality)

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    preprocesado = was_deskewed or otsu_applied

    return PreprocessResult(
        numero_pagina=page_num,
        preprocesado=preprocesado,
        angulo_corregido=detected_angle if was_deskewed else 0.0,
        otsu_aplicado=otsu_applied,
        duracion_ms=elapsed_ms,
        image_bytes=webp_bytes,
    )
