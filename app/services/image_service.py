import re
from typing import List, Optional, Tuple
import pymupdf
from app.domain.models import MetadatoImagen


def inventory_physical_images(
    page: pymupdf.Page,
    min_dim_pt: float = 80.0,
    min_area_ratio: float = 0.005,
) -> List[MetadatoImagen]:
    """
    Inventario físico local en Cero-IA con PyMuPDF (US-13 Escenario 1).
    Filtra artefactos o iconos decorativos insignificantes (<15% del área o <80x80 pt).
    """
    page_rect = page.rect
    page_area = max(1.0, page_rect.width * page_rect.height)
    page_num = page.number + 1
    items: List[MetadatoImagen] = []

    # 1. Inspeccionar imágenes ráster incrustadas
    img_list = page.get_images(full=True)
    img_counter = 0

    for img_info in img_list:
        xref = img_info[0]
        # Obtener los rectángulos donde se ubica la imagen en la página
        rects = page.get_image_rects(xref)
        for r in rects:
            w = r.width
            h = r.height
            area = w * h
            area_ratio = area / page_area

            # Filtrar si ambas dimensiones son menores a 80 pt o si es un logo diminuto decorativo
            if (w < min_dim_pt and h < min_dim_pt) or area_ratio < min_area_ratio:
                continue

            img_counter += 1
            bbox = [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]
            items.append(
                MetadatoImagen(
                    id_imagen=f"img_p{page_num}_{img_counter:02d}",
                    pagina=page_num,
                    tipo_fisico="raster",
                    bbox=bbox,
                    area_ratio=round(area_ratio, 4),
                    clasificacion_semantica=None,
                )
            )

    # 2. Inspeccionar dibujos vectoriales significativos (filtrando bordes de página y líneas)
    drawings = page.get_drawings()
    if drawings:
        for d in drawings:
            r = d.get("rect")
            if not r:
                continue
            dw = r.width
            dh = r.height
            d_area_ratio = (dw * dh) / page_area

            # Filtrar líneas o divisores ultra delgados
            if dw <= 5.0 or dh <= 5.0:
                continue

            # Filtrar marcos completos o bordes perimetrales de la página
            if (dw > page_rect.width * 0.70 and dh > page_rect.height * 0.65) or d_area_ratio > 0.35:
                continue

            # Solo dibujos con dimensiones mínimas relevantes y área acotada
            if (dw >= min_dim_pt or dh >= min_dim_pt) and min_area_ratio <= d_area_ratio <= 0.30:
                img_counter += 1
                items.append(
                    MetadatoImagen(
                        id_imagen=f"draw_p{page_num}_{img_counter:02d}",
                        pagina=page_num,
                        tipo_fisico="vector",
                        bbox=[round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)],
                        area_ratio=round(d_area_ratio, 4),
                        clasificacion_semantica=None,
                    )
                )

    return items


def detect_qr_with_opencv(page: pymupdf.Page, bbox: List[float]) -> Tuple[bool, Optional[str]]:
    """
    Detecta y decodifica códigos QR mediante visión por computador (OpenCV QRCodeDetector).
    Retorna (True, decoded_info) si se detecta un patrón de código QR válido.
    """
    try:
        import cv2
        import numpy as np

        rect = pymupdf.Rect(bbox)
        if rect.width < 25.0 or rect.height < 25.0:
            return False, None

        # Renderizar recorte con resolución moderada
        pix = page.get_pixmap(clip=rect, dpi=120)
        img_arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
        if pix.n == 4:
            img_arr = cv2.cvtColor(img_arr, cv2.COLOR_BGRA2BGR)
        elif pix.n == 1:
            img_arr = cv2.cvtColor(img_arr, cv2.COLOR_GRAY2BGR)

        detector = cv2.QRCodeDetector()
        decoded_info, points, _ = detector.detectAndDecode(img_arr)
        if points is not None or (decoded_info and len(decoded_info.strip()) > 0):
            val = decoded_info.strip() if decoded_info else None
            return True, val
    except Exception:
        pass
    return False, None


def classify_image_semantics(
    image_meta: MetadatoImagen,
    page_text: str = "",
    nearby_text: str = "",
    is_qr_detected: bool = False,
    crop_bgr: Optional[np.ndarray] = None,
    page_width: float = 612.0,
    page_height: float = 792.0,
) -> str:
    """
    Clasificación semántica de alta precisión basada en YOLO/OpenCV layout analysis,
    proximidad contextual, geometría y visión OpenCV (US-13).
    Tipologías válidas: 'firma_manuscrita', 'sello_oficial', 'codigo_barras', 'codigo_qr', 'fotografia', 'logotipo', 'diagrama'.
    """
    if is_qr_detected:
        return "codigo_qr"

    from app.services.yolo_detector_service import classify_document_layout_element
    context_str = f"{nearby_text} {page_text}"
    label = classify_document_layout_element(
        crop_bgr=crop_bgr,
        bbox=image_meta.bbox,
        page_width=page_width,
        page_height=page_height,
        context_text=context_str,
        is_vector=(image_meta.tipo_fisico == "vector"),
    )
    return label


def catalog_page_images(
    page: pymupdf.Page,
    catalogar_imagenes: bool = True,
) -> List[MetadatoImagen]:
    """
    Orquesta el inventario físico y extrae contexto espacial de proximidad para clasificación semántica (US-13).
    Aplica detección de layout con YOLO/OpenCV y filtra fondos escaneados.
    """
    images = inventory_physical_images(page)
    if not catalogar_imagenes or not images:
        return images

    page_rect = page.rect
    full_text = page.get_text()

    # Extraer pixmap de baja resolución (72 dpi) para recortes rápidos de análisis
    page_pix = None
    page_bgr = None

    for img in images:
        # Extraer texto de proximidad (borde de 40pt alrededor del elemento)
        clip = pymupdf.Rect(
            max(0.0, img.bbox[0] - 30.0),
            max(0.0, img.bbox[1] - 40.0),
            min(page_rect.width, img.bbox[2] + 30.0),
            min(page_rect.height, img.bbox[3] + 40.0),
        )
        nearby_text = page.get_text("text", clip=clip).strip()

        # Recorte de imagen para análisis visual con OpenCV
        crop_bgr = None
        w = max(1.0, img.bbox[2] - img.bbox[0])
        h = max(1.0, img.bbox[3] - img.bbox[1])
        aspect_ratio = w / h

        try:
            if page_bgr is None:
                page_pix = page.get_pixmap(dpi=72, alpha=False)
                arr = np.frombuffer(page_pix.samples, dtype=np.uint8).reshape((page_pix.height, page_pix.width, 3))
                page_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

            scale_x = page_pix.width / max(1.0, page_rect.width)
            scale_y = page_pix.height / max(1.0, page_rect.height)
            rx0 = max(0, int(img.bbox[0] * scale_x))
            ry0 = max(0, int(img.bbox[1] * scale_y))
            rx1 = min(page_bgr.shape[1], int(img.bbox[2] * scale_x))
            ry1 = min(page_bgr.shape[0], int(img.bbox[3] * scale_y))
            if rx1 > rx0 and ry1 > ry0:
                crop_bgr = page_bgr[ry0:ry1, rx0:rx1]
        except Exception:
            crop_bgr = None

        # Detección y decodificación de código QR mediante visión por computador (OpenCV)
        is_qr = False
        if 0.55 <= aspect_ratio <= 1.80 and (w >= 30.0 and h >= 30.0):
            is_qr, decoded = detect_qr_with_opencv(page, img.bbox)
            if is_qr:
                img.contenido_decodificado = decoded

        # Detección de caption o descripción textual adyacente
        caption = None
        for line in nearby_text.splitlines():
            line_str = line.strip()
            if re.match(r"^(figura|gr[aá]fico|grafico|diagrama|tabla|ilustraci[oó]n|imagen|anexo\s+fotogr[aá]fico)\b", line_str, re.IGNORECASE):
                caption = line_str
                break

        img.clasificacion_semantica = classify_image_semantics(
            img,
            page_text=full_text,
            nearby_text=nearby_text,
            is_qr_detected=is_qr,
            crop_bgr=crop_bgr,
            page_width=page_rect.width,
            page_height=page_rect.height,
        )

        if caption:
            img.descripcion_visual = caption
        elif nearby_text:
            first_sentence = nearby_text.split(".")[0].strip()
            img.descripcion_visual = f"{img.clasificacion_semantica}: {first_sentence[:120]}"
        else:
            img.descripcion_visual = img.clasificacion_semantica

    # Filtrar fondos de escaneo completos que no sean diagramas reales ni códigos verificados
    images = [
        i for i in images
        if i.clasificacion_semantica != "fondo_escaneo"
        and not (i.area_ratio >= 0.75 and i.tipo_fisico == "raster" and i.clasificacion_semantica not in ("codigo_qr", "codigo_barras"))
    ]

    # Salvaguarda VIS-01: Detección de firmas y sellos por segmentación cromática
    has_signature = any(i.clasificacion_semantica == "firma_manuscrita" for i in images)
    has_seal = any(i.clasificacion_semantica == "sello_oficial" for i in images)

    if (not has_signature or not has_seal) and (not full_text.strip() or len(images) <= 2):
        morph_items = detect_morphological_visual_elements(page)
        for item in morph_items:
            if item.clasificacion_semantica == "firma_manuscrita" and not has_signature:
                images.append(item)
                has_signature = True
            elif item.clasificacion_semantica == "sello_oficial" and not has_seal:
                images.append(item)
                has_seal = True

    return images


def detect_morphological_visual_elements(
    page: pymupdf.Page,
    min_sig_area_px: float = 60.0,
    min_seal_area_px: float = 120.0,
) -> List[MetadatoImagen]:
    """
    Segmentacion morfologica y cromatica de firmas y sellos en imagenes puras y escaneos (VIS-01).
    Utiliza OpenCV y conversion HSV para detectar trazos de tinta manuscrita (azul) y sellos notariales (rojo/violeta).
    """
    results: List[MetadatoImagen] = []
    page_rect = page.rect
    page_area = max(1.0, page_rect.width * page_rect.height)
    page_num = page.number + 1

    try:
        import cv2
        import numpy as np

        pix = page.get_pixmap(dpi=120)
        img_arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
        if pix.n == 4:
            img_arr = cv2.cvtColor(img_arr, cv2.COLOR_RGBA2BGR)
        elif pix.n == 1:
            img_arr = cv2.cvtColor(img_arr, cv2.COLOR_GRAY2BGR)
        else:
            img_arr = cv2.cvtColor(img_arr, cv2.COLOR_RGB2BGR)

        hsv = cv2.cvtColor(img_arr, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        scale_x = pix.width / page_rect.width
        scale_y = pix.height / page_rect.height

        # 1. Mascara de tinta azul (firmas manuscritas)
        blue_mask = ((hsv[:, :, 0] >= 90) & (hsv[:, :, 0] <= 135) & (sat > 35)).astype(np.uint8) * 255
        blue_cnts, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in blue_cnts:
            x, y, w, h = cv2.boundingRect(c)
            if w > 40 and h > 12 and (w / h >= 1.3) and cv2.contourArea(c) > min_sig_area_px:
                if (y / scale_y) > 180.0:
                    sig_bbox = [
                        round(x / scale_x, 2),
                        round(y / scale_y, 2),
                        round((x + w) / scale_x, 2),
                        round((y + h) / scale_y, 2),
                    ]
                    sig_area = (sig_bbox[2] - sig_bbox[0]) * (sig_bbox[3] - sig_bbox[1])
                    results.append(
                        MetadatoImagen(
                            id_imagen=f"sig_p{page_num}_{len(results)+1:02d}",
                            pagina=page_num,
                            tipo_fisico="raster",
                            bbox=sig_bbox,
                            area_ratio=round(sig_area / page_area, 4),
                            clasificacion_semantica="firma_manuscrita",
                        )
                    )
                    break

        # 2. Mascara de tinta roja o carmesi (sellos notariales u oficiales)
        red_mask = (((hsv[:, :, 0] <= 15) | (hsv[:, :, 0] >= 165)) & (sat > 35)).astype(np.uint8) * 255
        red_cnts, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in red_cnts:
            x, y, w, h = cv2.boundingRect(c)
            if w > 30 and h > 30 and (0.55 <= w / h <= 1.8) and cv2.contourArea(c) > min_seal_area_px:
                seal_bbox = [
                    round(x / scale_x, 2),
                    round(y / scale_y, 2),
                    round((x + w) / scale_x, 2),
                    round((y + h) / scale_y, 2),
                ]
                seal_area = (seal_bbox[2] - seal_bbox[0]) * (seal_bbox[3] - seal_bbox[1])
                results.append(
                    MetadatoImagen(
                        id_imagen=f"seal_p{page_num}_{len(results)+1:02d}",
                        pagina=page_num,
                        tipo_fisico="raster",
                        bbox=seal_bbox,
                        area_ratio=round(seal_area / page_area, 4),
                        clasificacion_semantica="sello_oficial",
                    )
                )
                break
    except Exception:
        pass

    return results

