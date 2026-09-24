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
) -> str:
    """
    Clasificación semántica de alta precisión basada en proximidad contextual, geometría y visión OpenCV (US-13).
    Tipologías válidas: 'firma_manuscrita', 'sello_oficial', 'codigo_barras', 'codigo_qr', 'fotografia', 'logotipo', 'diagrama'.
    """
    # Si la visión por computador OpenCV ya validó el patrón del código QR
    if is_qr_detected:
        return "codigo_qr"

    bbox = image_meta.bbox
    w = max(1.0, bbox[2] - bbox[0])
    h = max(1.0, bbox[3] - bbox[1])
    aspect_ratio = w / h
    y_center = (bbox[1] + bbox[3]) / 2.0
    is_vector = image_meta.tipo_fisico == "vector"

    local_text = (nearby_text if nearby_text else page_text).lower()
    full_text = f"{nearby_text} {page_text}".lower()

    # 1. Logotipo o cabecera institucional
    if bbox[1] <= 60 and y_center <= 160 and h <= 160:
        return "logotipo"

    # Los gráficos vectoriales de ancho completo o gran superficie son cajas/tablas contenedoras o diagramas
    if is_vector and (w >= 320.0 or h >= 120.0 or image_meta.area_ratio >= 0.08):
        return "diagrama"

    # 2. Código QR (reconocido por aspecto cuadrado y palabras clave EXPLÍCITAS de QR en el entorno inmediato o documento)
    has_qr_text = any(
        kw in full_text for kw in ("código qr", "codigo qr", "qr code", "cufe", "factura electrónica", "factura electronica")
    ) or any(kw in local_text for kw in ("qr", "código qr", "codigo qr"))
    if (0.75 <= aspect_ratio <= 1.30) and (35.0 <= w <= 260.0 and 35.0 <= h <= 260.0) and has_qr_text:
        return "codigo_qr"

    # 3. Sello oficial notarial o de certificación
    has_seal_text = any(
        kw in local_text or kw in full_text for kw in (
            "sello", "notaria", "notaría", "notario", "circulo", "círculo", "alcaldia", "alcaldía",
            "republica", "república", "registraduria", "registraduría", "apostilla", "autenticado", "certifico", "oficial", "peritaje"
        )
    )
    if (0.75 <= aspect_ratio <= 1.35) and (w <= 260.0 and h <= 260.0):
        if has_seal_text or (80.0 <= w <= 240.0 and 80.0 <= h <= 240.0 and any(k in local_text for k in ("notar", "sello"))):
            return "sello_oficial"

    # 4. Firma manuscrita (acotada a dimensiones reales y contexto inmediato de firmante)
    has_signature_text = any(
        kw in local_text for kw in (
            "firma", "firmado", "rubrica", "rúbrica", "representante", "arrendador", "arrendatario",
            "c.c.", "cedula", "cédula", "perito", "viceministro", "interventor", "contratante",
            "contratista", "cardenas", "cárdenas", "gomez", "gómez", "valencia", "jaramillo", "dr.", "dra.", "ing."
        )
    )
    if (1.2 <= aspect_ratio <= 4.5) and (w <= 280.0 and h <= 120.0 and image_meta.area_ratio <= 0.08):
        if has_signature_text or (not is_vector and y_center > 400 and w <= 220 and h <= 80):
            return "firma_manuscrita"

    # 5. Código de barras (raster alargado horizontal)
    if not is_vector:
        has_barcode_text = any(
            kw in full_text for kw in ("radicado", "codigo de barras", "código de barras", "barcode", "rad-", "barras")
        )
        if (aspect_ratio >= 2.2 and h <= 100 and w <= 350) or has_barcode_text:
            return "codigo_barras"

    # 6. Fotografía / Imagen pericial, técnica o de inspección
    if not is_vector:
        page_header = page_text.lstrip()[:250].lower()
        has_annex_photo_header = any(k in page_header for k in ("anexo fotográfico", "anexo fotografico", "registro fotográfico", "acta de inspección", "acta de inspeccion", "inspección", "inspeccion"))
        has_photo_text = any(
            kw in local_text for kw in ("foto", "fotografia", "fotografía", "imagen", "imágenes", "imagenes", "rack", "servidor", "data center", "datacenter", "k-9", "canin", "perro", "perros", "evidencia visual", "inspección")
        ) or has_annex_photo_header
        if (w >= 140 and h >= 80) and (has_photo_text or image_meta.area_ratio >= 0.15):
            return "fotografia"

    # 7. Si el contexto local describe explícitamente gráficos financieros o diagramas
    has_diagram_keywords = any(k in local_text for k in ("presupuesto", "financiero", "diagrama", "flujo", "arquitectura", "cronograma", "distribución porcentual", "distribucion porcentual"))
    if has_diagram_keywords or re.search(r"(?<!foto)gr[aá]fico\b", local_text):
        return "diagrama"

    # 8. Si es una imagen ráster sin otra clasificación específica, clasificar como 'imagen' / 'fotografia'
    if not is_vector and (w >= 100 or h >= 80):
        return "fotografia"

    # 9. Diagrama / Gráfico general por defecto
    return "diagrama"


def catalog_page_images(
    page: pymupdf.Page,
    catalogar_imagenes: bool = True,
) -> List[MetadatoImagen]:
    """
    Orquesta el inventario físico y extrae contexto espacial de proximidad para clasificación semántica (US-13).
    """
    images = inventory_physical_images(page)
    if not catalogar_imagenes or not images:
        return images

    page_rect = page.rect
    full_text = page.get_text()

    for img in images:
        # Extraer texto de proximidad (borde de 40pt alrededor del elemento)
        clip = pymupdf.Rect(
            max(0.0, img.bbox[0] - 30.0),
            max(0.0, img.bbox[1] - 40.0),
            min(page_rect.width, img.bbox[2] + 30.0),
            min(page_rect.height, img.bbox[3] + 40.0),
        )
        nearby_text = page.get_text("text", clip=clip).strip()

        # Detección y decodificación de código QR mediante visión por computador (OpenCV)
        is_qr = False
        w = max(1.0, img.bbox[2] - img.bbox[0])
        h = max(1.0, img.bbox[3] - img.bbox[1])
        aspect_ratio = w / h
        if 0.70 <= aspect_ratio <= 1.40 and (w >= 30.0 and h >= 30.0):
            is_qr, decoded = detect_qr_with_opencv(page, img.bbox)
            if is_qr and decoded:
                img.contenido_decodificado = decoded

        img.clasificacion_semantica = classify_image_semantics(
            img,
            page_text=full_text,
            nearby_text=nearby_text,
            is_qr_detected=is_qr,
        )

    # Si ningún elemento fue catalogado como QR, evaluar salvaguarda de escaneo completo
    has_qr = any(i.clasificacion_semantica == "codigo_qr" for i in images)
    if not has_qr:
        page_has_qr_hint = any(kw in full_text.lower() for kw in ("qr", "cufe", "dian", "verificacion", "código qr", "codigo qr"))
        if not full_text.strip() or page_has_qr_hint:
            try:
                import cv2
                import numpy as np

                pix = page.get_pixmap(dpi=120)
                img_arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
                if pix.n == 4:
                    img_arr = cv2.cvtColor(img_arr, cv2.COLOR_BGRA2BGR)
                elif pix.n == 1:
                    img_arr = cv2.cvtColor(img_arr, cv2.COLOR_GRAY2BGR)

                detector = cv2.QRCodeDetector()
                decoded_info, points, _ = detector.detectAndDecode(img_arr)
                if points is not None or (decoded_info and len(decoded_info.strip()) > 0):
                    scale = 72.0 / 120.0
                    pts = points.reshape(-1, 2)
                    qr_bbox = [
                        round(float(pts[:, 0].min() * scale), 2),
                        round(float(pts[:, 1].min() * scale), 2),
                        round(float(pts[:, 0].max() * scale), 2),
                        round(float(pts[:, 1].max() * scale), 2),
                    ]
                    page_area = max(1.0, page_rect.width * page_rect.height)
                    qr_area_ratio = max(0.001, (qr_bbox[2] - qr_bbox[0]) * (qr_bbox[3] - qr_bbox[1]) / page_area)

                    # Si ya existe una imagen que contiene o solapa este QR, actualizarla
                    matched_img = None
                    for img in images:
                        if (img.bbox[0] <= qr_bbox[0] + 10 and img.bbox[1] <= qr_bbox[1] + 10 and
                            img.bbox[2] >= qr_bbox[2] - 10 and img.bbox[3] >= qr_bbox[3] - 10):
                            matched_img = img
                            break

                    if matched_img:
                        matched_img.clasificacion_semantica = "codigo_qr"
                        if decoded_info and len(decoded_info.strip()) > 0:
                            matched_img.contenido_decodificado = decoded_info.strip()
                    else:
                        page_num = page.number + 1
                        images.append(
                            MetadatoImagen(
                                id_imagen=f"qr_p{page_num}_{len(images)+1:02d}",
                                pagina=page_num,
                                tipo_fisico="raster",
                                bbox=qr_bbox,
                                area_ratio=round(qr_area_ratio, 4),
                                clasificacion_semantica="codigo_qr",
                                contenido_decodificado=decoded_info.strip() if decoded_info and len(decoded_info.strip()) > 0 else None,
                            )
                        )
            except Exception:
                pass

    # Salvaguarda VIS-01: Deteccion de firmas y sellos por segmentacion morfologica cromatica
    has_signature = any(i.clasificacion_semantica == "firma_manuscrita" for i in images)
    has_seal = any(i.clasificacion_semantica == "sello_oficial" for i in images)
    has_full_page_raster = any(i.area_ratio >= 0.40 for i in images)

    if (not has_signature or not has_seal) and (has_full_page_raster or not full_text.strip()):
        morph_items = detect_morphological_visual_elements(page)
        added_specific = False
        for item in morph_items:
            if item.clasificacion_semantica == "firma_manuscrita" and not has_signature:
                images.append(item)
                has_signature = True
                added_specific = True
            elif item.clasificacion_semantica == "sello_oficial" and not has_seal:
                images.append(item)
                has_seal = True
                added_specific = True

        # Si se detectaron elementos especificos dentro del escaneo, filtrar lienzo de fondo redundante
        if added_specific:
            images = [i for i in images if not (i.area_ratio >= 0.75 and i.clasificacion_semantica == "diagrama")]

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

