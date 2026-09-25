"""
PyDective — Extractor OCR Local y Visión a Través de Imágenes (Air-Gap)
Permite 'ver a través de las imágenes' en documentos 100% escaneados (ej. factura-medica.pdf)
sin depender de APIs en la nube. Extrae texto, calcula coordenadas espaciales precisas,
inyecta la capa invisible de texto con PyMuPDF y aísla firmas, sellos y códigos de barras/QR.
"""

import os
import sys
import json
import subprocess
import tempfile
import logging
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path

import pymupdf
import cv2
import numpy as np

from app.domain.models import MetadatoImagen
from app.services.ocr_service import clean_ocr_line, inject_ocr_text_layer
from app.services.image_service import (
    detect_morphological_visual_elements,
    detect_qr_with_opencv,
    inventory_physical_images,
    classify_image_semantics,
)

logger = logging.getLogger("pydective.image_ocr")
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
WIN_OCR_SCRIPT = ROOT_DIR / "app" / "services" / "ocr_helpers" / "win_ocr.ps1"


def is_page_scanned_image(page: pymupdf.Page) -> bool:
    """Retorna True si la página carece de texto nativo y contiene imágenes incrustadas o es un escaneo."""
    text = page.get_text().strip()
    if len(text) > 20:
        return False
    # Si no tiene texto, verificar si tiene imágenes o dibujos
    images = page.get_images()
    return len(text) <= 5 or len(images) > 0


def extract_page_ocr_cross_platform(
    page: pymupdf.Page,
    dpi: int = 150,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Ejecuta el OCR local multiplataforma sobre una página escaneada.
    En Windows utiliza el motor nativo acelerado por hardware de Windows (Windows.Media.Ocr).
    En Linux utiliza RapidOCR o Tesseract según disponibilidad en el sistema.
    """
    page_rect = page.rect
    if page_rect.width <= 0 or page_rect.height <= 0:
        return "", []

    pix = page.get_pixmap(dpi=dpi, alpha=False)
    scale_x = pix.width / page_rect.width
    scale_y = pix.height / page_rect.height

    img_rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))

    # 1. Detección ultrarrápida de página en blanco (dorsos vacíos como páginas 2 y 4)
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    std_dev = float(np.std(gray))
    mean_val = float(np.mean(gray))
    if std_dev < 10.0 and mean_val > 245.0:
        logger.info(f"[OCR] Página {page.number + 1} detectada como dorso en blanco (std={std_dev:.1f}, mean={mean_val:.1f}). Omitiendo OCR en 2 ms.")
        return "", []

    # 2. Preprocesamiento Deskew (Enderezado de rotación con Hough / minAreaRect en C++)
    from app.services.preprocess_service import detect_skew_angle, deskew_image, evaluate_contrast_and_otsu
    skew_angle = detect_skew_angle(img_rgb, max_angle=15.0)
    if abs(skew_angle) >= 0.4:
        img_rgb = deskew_image(img_rgb, angle=skew_angle)

    # 3. Preprocesamiento Otsu (Binarización adaptativa ante bajo contraste o sombras de escaneo)
    img_rgb, otsu_applied = evaluate_contrast_and_otsu(img_rgb)

    # 2. Motor Primario: RapidOCR (ONNX Runtime / DBNet + CRNN) para máxima precisión
    try:
        from app.services.ocr_service import extract_page_ocr, is_ocr_available
        if is_ocr_available():
            text, boxes = extract_page_ocr(page, dpi=max(dpi, 200))
            if text and len(text.strip()) > 10:
                logger.info(f"[OCR] Página {page.number + 1} procesada exitosamente con RapidOCR: {len(boxes)} cajas de texto.")
                return text, boxes
    except Exception as exc:
        logger.warning(f"Error o indisponibilidad en RapidOCR para página {page.number + 1}: {exc}")

    # 3. Fallback: OCR nativo de Windows (Windows.Media.Ocr vía PowerShell)
    if sys.platform == "win32" and WIN_OCR_SCRIPT.exists():
        temp_img = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_img = f.name
            cv2.imwrite(temp_img, cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR))

            cmd = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", str(WIN_OCR_SCRIPT),
                "-ImagePath", temp_img,
            ]
            res = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            if res.returncode == 0 and res.stdout.strip():
                try:
                    data = json.loads(res.stdout.strip(), strict=False)
                except Exception:
                    import re
                    clean_stdout = re.sub(r"[\x00-\x1f]", " ", res.stdout.strip())
                    data = json.loads(clean_stdout, strict=False)
                lines_data = data.get("lines", [])
                boxes = []
                clean_lines = []

                from app.services.text_healing_service import heal_scanned_text
                for item in lines_data:
                    raw_txt = item.get("text", "").strip()
                    c_txt = heal_scanned_text(clean_ocr_line(raw_txt))
                    if not c_txt:
                        continue
                    clean_lines.append(c_txt)
                    raw_bbox = item.get("bbox", [0, 0, 10, 10])
                    if isinstance(raw_bbox, str):
                        coords = [float(x) for x in raw_bbox.split() if x.strip()]
                    elif isinstance(raw_bbox, (list, tuple)):
                        coords = [float(x) for x in raw_bbox]
                    else:
                        coords = [0.0, 0.0, 10.0, 10.0]

                    if len(coords) < 4:
                        continue

                    # Convertir coordenadas de píxeles a puntos PDF
                    bbox_pt = [
                        round(coords[0] / scale_x, 2),
                        round(coords[1] / scale_y, 2),
                        round(coords[2] / scale_x, 2),
                        round(coords[3] / scale_y, 2),
                    ]
                    boxes.append({
                        "text": c_txt,
                        "raw_text": raw_txt,
                        "score": 0.95,
                        "bbox": bbox_pt,
                    })

                full_text = "\n".join(clean_lines)
                if full_text:
                    return full_text, boxes
        except Exception as exc:
            logger.warning(f"Error en OCR nativo de Windows: {exc}")
        finally:
            if temp_img and os.path.exists(temp_img):
                try:
                    os.remove(temp_img)
                except Exception:
                    pass

    return "", []


def process_scanned_page_and_inject(
    page: pymupdf.Page,
    dpi: int = 150,
) -> Tuple[str, List[Dict[str, Any]], List[MetadatoImagen]]:
    """
    Procesa integralmente un folio escaneado:
    1. Extrae el texto mediante OCR local multiplataforma.
    2. Inyecta la capa de texto invisible (render_mode=3) en el PDF en RAM.
    3. Detecta y cataloga elementos visuales (firmas, sellos, códigos QR/barras).
    """
    full_text, boxes = extract_page_ocr_cross_platform(page, dpi=dpi)

    if boxes:
        inject_ocr_text_layer(page, boxes)

    # Catalogación visual mediante OpenCV (firmas manuscritas y sellos cromáticos)
    visuals: List[MetadatoImagen] = []
    page_num = page.number + 1

    try:
        morph_items = detect_morphological_visual_elements(page)
        visuals.extend(morph_items)
    except Exception as exc:
        logger.debug(f"Error segmentando firmas/sellos en página {page_num}: {exc}")

    # Detectar códigos QR mediante OpenCV
    try:
        pix = page.get_pixmap(dpi=120)
        img_arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
        if pix.n == 4:
            img_arr = cv2.cvtColor(img_arr, cv2.COLOR_RGBA2BGR)
        elif pix.n == 1:
            img_arr = cv2.cvtColor(img_arr, cv2.COLOR_GRAY2BGR)
        else:
            img_arr = cv2.cvtColor(img_arr, cv2.COLOR_RGB2BGR)

        qr_detector = cv2.QRCodeDetector()
        data, points, _ = qr_detector.detectAndDecode(img_arr)
        if data and points is not None:
            # Calcular bbox del código QR en puntos PDF
            scale_x = pix.width / page.rect.width
            scale_y = pix.height / page.rect.height
            pts = points[0]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            qr_bbox = [
                round(min(xs) / scale_x, 2),
                round(min(ys) / scale_y, 2),
                round(max(xs) / scale_x, 2),
                round(max(ys) / scale_y, 2),
            ]
            visuals.append(
                MetadatoImagen(
                    id_imagen=f"qr_p{page_num}_{len(visuals)+1:02d}",
                    pagina=page_num,
                    tipo_fisico="raster",
                    bbox=qr_bbox,
                    area_ratio=round(((qr_bbox[2]-qr_bbox[0])*(qr_bbox[3]-qr_bbox[1])) / (page.rect.width * page.rect.height), 4),
                    clasificacion_semantica="codigo_qr",
                )
            )
    except Exception as exc:
        logger.debug(f"Error detectando QR en página {page_num}: {exc}")

    return full_text, boxes, visuals
