import re
from typing import List, Tuple
from dataclasses import dataclass, field
import pymupdf

from app.settings import settings
from app.domain.enums import TipoPagina
from app.domain.models import MetadatoImagen


@dataclass
class PageClassification:
    numero_pagina: int
    tipo: TipoPagina
    readability_score: float
    word_count: int
    metadatos_visuales: List[MetadatoImagen] = field(default_factory=list)
    total_graphics_area_ratio: float = 0.0
    bypass_opencv: bool = False
    motivo: str = ""


def calculate_readability_score(text: str, words: List[str]) -> float:
    """
    Calcula un score compuesto de legibilidad determinista anti-ruido (ADR-004 Sección 7).
    
    Evalúa:
    + densidad_alfa
    + ratio_caracteres_validos
    + separación_lexica
    + consistencia_de_lineas
    + cobertura_textual
    - ratio_reemplazos (\ufffd)
    - caracteres_control
    - palabras_anormalmente_largas (>30 chars sin espacios)
    
    Rango: [0.0, 1.0]. Umbral de corte recomendado: 0.60.
    """
    if not text or not words:
        return 0.0

    total_chars = len(text)
    if total_chars == 0:
        return 0.0

    # 1. Densidad alfabética (letras frente a ruido no textual)
    alpha_chars = sum(1 for c in text if c.isalpha())
    densidad_alfa = alpha_chars / total_chars

    # 2. Ratio de caracteres válidos imprimibles (descontando reemplazos)
    valid_chars = sum(1 for c in text if c.isprintable() and c != "\ufffd")
    ratio_validos = valid_chars / total_chars

    # 3. Penalizaciones por caracteres corruptos
    reemplazos = text.count("\ufffd")
    ratio_reemplazos = reemplazos / total_chars

    # Caracteres de control no imprimibles (excluyendo saltos de línea y tabuladores estándar)
    control_chars = sum(1 for c in text if not c.isprintable() and c not in ("\n", "\r", "\t"))
    ratio_control = control_chars / total_chars

    # 4. Palabras anormalmente largas sin espacios (> 30 caracteres)
    long_words = sum(1 for w in words if len(w) > 30)
    ratio_long_words = long_words / max(len(words), 1)

    # 5. Longitud promedio de palabras (en español/inglés típicamente entre 4.0 y 8.5)
    avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
    if avg_word_len > 25.0:
        penalizacion_longitud = 0.4
    elif avg_word_len > 15.0:
        penalizacion_longitud = 0.2
    else:
        penalizacion_longitud = 0.0

    # 6. Cálculo ponderado
    # Base positiva: combinación de caracteres alfanuméricos válidos y estructura
    score = (0.45 * densidad_alfa) + (0.40 * ratio_validos) + 0.15

    # Penalización severa por caracteres de reemplazo \ufffd (típico de capas OCR rotas)
    if ratio_reemplazos > 0.05:
        score -= 0.50
    else:
        score -= (ratio_reemplazos * 5.0)

    # Penalización por caracteres de control
    score -= (ratio_control * 3.0)

    # Penalización por palabras pegadas sin espacios
    if ratio_long_words > 0.10:
        score -= 0.40
    else:
        score -= (ratio_long_words * 2.0)

    score -= penalizacion_longitud

    # Clamping en el intervalo [0.0, 1.0]
    return max(0.0, min(1.0, round(score, 4)))


def inventory_page_images(page: pymupdf.Page) -> List[MetadatoImagen]:
    """
    Realiza el inventario físico Nivel 1 de objetos gráficos locales con PyMuPDF (0 ms IA).
    (ADR-004 Sección 9.1).
    Detecta tanto imágenes ráster incrustadas como trazos/dibujos vectoriales significativos.
    """
    page_num = page.number + 1
    page_rect = page.rect
    page_area = max(page_rect.width * page_rect.height, 1.0)

    visual_items: List[MetadatoImagen] = []

    # 1. Imágenes ráster
    image_list = page.get_images(full=True)
    for idx, img_info in enumerate(image_list):
        xref = img_info[0]
        img_rects = page.get_image_rects(xref)
        if not img_rects:
            continue

        for r_idx, rect in enumerate(img_rects):
            area = rect.width * rect.height
            area_ratio = min(1.0, area / page_area)

            visual_items.append(
                MetadatoImagen(
                    id_imagen=f"img_p{page_num}_{idx+1}_{r_idx+1}",
                    pagina=page_num,
                    tipo_fisico="raster",
                    bbox=[round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2)],
                    area_ratio=round(area_ratio, 4),
                    clasificacion_semantica=None,
                )
            )

    # 2. Dibujos vectoriales significativos (filtrando bordes de página y líneas)
    drawings = page.get_drawings()
    for d_idx, d in enumerate(drawings):
        r = d.get("rect")
        if r and r.width > 20 and r.height > 20:
            if r.width <= 5.0 or r.height <= 5.0:
                continue
            if r.width > page_rect.width * 0.70 and r.height > page_rect.height * 0.65:
                continue
            area = r.width * r.height
            area_ratio = min(1.0, area / page_area)
            if 0.005 <= area_ratio <= 0.30:  # Acotado entre 0.5% y 30% del área
                visual_items.append(
                    MetadatoImagen(
                        id_imagen=f"vec_p{page_num}_{d_idx+1}",
                        pagina=page_num,
                        tipo_fisico="vector",
                        bbox=[round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)],
                        area_ratio=round(area_ratio, 4),
                        clasificacion_semantica=None,
                    )
                )

    return visual_items


def classify_page(
    page: pymupdf.Page,
    bypass_threshold: int = settings.OPENCV_BYPASS_WORD_THRESHOLD,
    min_readability_score: float = 0.60,
) -> PageClassification:
    """
    Clasifica de forma determinista una página en TipoPagina.LOCAL, NEEDS_AI o EMPTY (US-04 y US-05).
    """
    page_num = page.number + 1

    # 1. Extracción en C de texto y palabras
    text = page.get_text()
    raw_words = page.get_text("words")
    words = [w[4] for w in raw_words]
    word_count = len(words)

    # 2. Inventario de gráficos raster locales
    visual_items = inventory_page_images(page)
    total_graphics_area_ratio = sum(item.area_ratio for item in visual_items)

    # 3. Detección de página vacía (US-04 Escenario 2)
    if (word_count == 0 or not text.strip()) and total_graphics_area_ratio < 0.05:
        return PageClassification(
            numero_pagina=page_num,
            tipo=TipoPagina.EMPTY,
            readability_score=1.0,
            word_count=0,
            metadatos_visuales=visual_items,
            total_graphics_area_ratio=total_graphics_area_ratio,
            bypass_opencv=True,
            motivo="Página en blanco sin texto ni gráficos relevantes.",
        )

    # 4. Escaneo puro sin capa de texto digital nativo
    if word_count == 0 and total_graphics_area_ratio >= 0.05:
        return PageClassification(
            numero_pagina=page_num,
            tipo=TipoPagina.NEEDS_AI,
            readability_score=0.0,
            word_count=0,
            metadatos_visuales=visual_items,
            total_graphics_area_ratio=total_graphics_area_ratio,
            bypass_opencv=False,
            motivo="Página escaneada (raster puro sin texto nativo).",
        )

    # 5. Cálculo del score compuesto de legibilidad anti-ruido (US-05)
    readability = calculate_readability_score(text, words)

    # 6. Detección de capa OCR corrupta (US-05 Escenario 1)
    if readability < min_readability_score:
        return PageClassification(
            numero_pagina=page_num,
            tipo=TipoPagina.NEEDS_AI,
            readability_score=readability,
            word_count=word_count,
            metadatos_visuales=visual_items,
            total_graphics_area_ratio=total_graphics_area_ratio,
            bypass_opencv=False,
            motivo=f"Capa de texto degradada o corrupta (readability_score={readability} < {min_readability_score}).",
        )

    # 7. Presencia de elementos visuales significativos (sellos, firmas, gráficos grandes)
    # Si la página tiene texto vectorial suficiente y alta legibilidad, solo se envía a AI si los gráficos dominan
    if total_graphics_area_ratio >= 0.15:
        if word_count < 60 or readability < 0.70 or total_graphics_area_ratio >= 0.35:
            return PageClassification(
                numero_pagina=page_num,
                tipo=TipoPagina.NEEDS_AI,
                readability_score=readability,
                word_count=word_count,
                metadatos_visuales=visual_items,
                total_graphics_area_ratio=total_graphics_area_ratio,
                bypass_opencv=False,
                motivo=f"Página con elementos gráficos dominantes (área={total_graphics_area_ratio:.2f} >= 0.15).",
            )

    # 8. Página digital con texto nativo suficiente (US-04 Escenario 1 - Bypass completo)
    if word_count >= bypass_threshold and readability >= min_readability_score:
        return PageClassification(
            numero_pagina=page_num,
            tipo=TipoPagina.LOCAL,
            readability_score=readability,
            word_count=word_count,
            metadatos_visuales=visual_items,
            total_graphics_area_ratio=total_graphics_area_ratio,
            bypass_opencv=True,
            motivo=f"Texto digital nativo suficiente ({word_count} palabras >= {bypass_threshold}) y legible.",
        )

    # 9. Texto corto pero estructurado y limpio (US-05 Escenario 2)
    if readability >= 0.65:
        return PageClassification(
            numero_pagina=page_num,
            tipo=TipoPagina.LOCAL,
            readability_score=readability,
            word_count=word_count,
            metadatos_visuales=visual_items,
            total_graphics_area_ratio=total_graphics_area_ratio,
            bypass_opencv=True,
            motivo=f"Texto breve pero estructurado y limpio (readability_score={readability}).",
        )

    # 10. Fallback por defecto a multimodal si no se tiene certeza determinista
    return PageClassification(
        numero_pagina=page_num,
        tipo=TipoPagina.NEEDS_AI,
        readability_score=readability,
        word_count=word_count,
        metadatos_visuales=visual_items,
        total_graphics_area_ratio=total_graphics_area_ratio,
        bypass_opencv=False,
        motivo="Página requiere análisis multimodal.",
    )
