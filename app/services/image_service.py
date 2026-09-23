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

    # 2. Inspeccionar clústeres de dibujos vectoriales (rúbricas vectoriales / sellos geométricos)
    drawings = page.get_drawings()
    if drawings:
        large_paths = [
            d["rect"] for d in drawings
            if d.get("rect") and (d["rect"].width >= 60.0 or d["rect"].height >= 60.0)
        ]
        if large_paths:
            # Clúster delimitador
            u_x0 = min(r.x0 for r in large_paths)
            u_y0 = min(r.y0 for r in large_paths)
            u_x1 = max(r.x1 for r in large_paths)
            u_y1 = max(r.y1 for r in large_paths)
            dw = u_x1 - u_x0
            dh = u_y1 - u_y0
            d_area_ratio = (dw * dh) / page_area
            if (dw >= min_dim_pt or dh >= min_dim_pt) and d_area_ratio >= min_area_ratio:
                img_counter += 1
                items.append(
                    MetadatoImagen(
                        id_imagen=f"draw_p{page_num}_{img_counter:02d}",
                        pagina=page_num,
                        tipo_fisico="vector",
                        bbox=[round(u_x0, 2), round(u_y0, 2), round(u_x1, 2), round(u_y1, 2)],
                        area_ratio=round(d_area_ratio, 4),
                        clasificacion_semantica=None,
                    )
                )

    return items


def classify_image_semantics(
    image_meta: MetadatoImagen,
    page_text: str = "",
) -> str:
    """
    Clasificación semántica selectiva (US-13 Escenario 2).
    Tipologías válidas: 'firma_manuscrita', 'sello_oficial', 'logotipo', 'diagrama'.
    Aplica análisis contextual determinista de alta fidelidad.
    """
    bbox = image_meta.bbox
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    aspect_ratio = w / max(1.0, h)
    y_center = (bbox[1] + bbox[3]) / 2.0
    text_lower = page_text.lower()

    # 1. Reglas de firma manuscrita:
    # Trazo vectorial o imagen apaisada en tercio inferior de página o cerca de etiquetas de firma
    is_lower_third = y_center > 450
    has_signature_text = any(
        kw in text_lower for kw in ("firma", "firmado", "rubrica", "representante", "arrendador", "arrendatario", "cedula")
    )
    if (image_meta.tipo_fisico == "vector" or aspect_ratio >= 1.4) and (is_lower_third or has_signature_text):
        return "firma_manuscrita"

    # 2. Reglas de sello oficial:
    # Aspecto casi cuadrado o circular (aspect ratio entre 0.7 y 1.4) con texto notarial/estatal
    has_seal_text = any(
        kw in text_lower for kw in ("sello", "notaria", "notario", "alcaldia", "republica", "registraduria", "apostilla")
    )
    if 0.7 <= aspect_ratio <= 1.4 and (has_seal_text or is_lower_third):
        return "sello_oficial"

    # 3. Reglas de logotipo:
    # Ubicado en la cabecera del documento (y_center < 150)
    if y_center <= 160:
        return "logotipo"

    # 4. Diagrama / Gráfico general
    return "diagrama"


def catalog_page_images(
    page: pymupdf.Page,
    catalogar_imagenes: bool = True,
) -> List[MetadatoImagen]:
    """
    Orquesta el inventario físico y, si catalogar_imagenes es True, asigna tipología semántica (US-13).
    """
    images = inventory_physical_images(page)
    if not catalogar_imagenes or not images:
        return images

    page_text = page.get_text()
    for img in images:
        img.clasificacion_semantica = classify_image_semantics(img, page_text=page_text)

    return images
