import re
from typing import List, Optional
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


def classify_image_semantics(
    image_meta: MetadatoImagen,
    page_text: str = "",
    nearby_text: str = "",
) -> str:
    """
    Clasificación semántica de alta precisión basada en proximidad contextual y geometría (US-13).
    Tipologías válidas: 'firma_manuscrita', 'sello_oficial', 'codigo_barras', 'codigo_qr', 'fotografia', 'logotipo', 'diagrama'.
    """
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

    # 2. Código QR (reconocido por aspecto cuadrado y palabras clave en el entorno o documento)
    has_qr_text = any(
        kw in full_text for kw in ("qr", "cufe", "dian", "verificacion", "verificación", "código qr", "codigo qr", "factura electrónica", "factura electronica")
    )
    if (0.80 <= aspect_ratio <= 1.25) and (50.0 <= w <= 240.0 and 50.0 <= h <= 240.0) and has_qr_text:
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

    # Si el contexto local describe explícitamente gráficos financieros o diagramas
    has_diagram_keywords = any(k in local_text for k in ("presupuesto", "financiero", "diagrama", "flujo", "arquitectura", "cronograma", "distribución porcentual", "distribucion porcentual"))
    if has_diagram_keywords or re.search(r"(?<!foto)gr[aá]fico\b", local_text):
        return "diagrama"

    # 6. Fotografía pericial o técnica
    if not is_vector:
        page_header = page_text.lstrip()[:200].lower()
        has_annex_photo_header = any(k in page_header for k in ("anexo fotográfico", "anexo fotografico", "registro fotográfico", "acta de inspección", "acta de inspeccion"))
        has_photo_text = any(
            kw in local_text for kw in ("foto", "fotografia", "fotografía", "rack", "servidor", "data center", "datacenter")
        ) or has_annex_photo_header
        if (w >= 180 and h >= 100) and has_photo_text:
            return "fotografia"

    # 7. Diagrama / Gráfico general por defecto
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
        img.clasificacion_semantica = classify_image_semantics(
            img,
            page_text=full_text,
            nearby_text=nearby_text,
        )

    return images
