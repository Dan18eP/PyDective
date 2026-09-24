from typing import List, Optional, Dict, Any, Tuple
import re
import unicodedata
import logging

from app.domain.models import ChatOutput, Evidence, MetadatoImagen
from app.domain.enums import MetodoExtraccion
from app.services.markdown_service import get_or_create_page_indexed_markdown
from app.services.cache_service import get_l1_cache

logger = logging.getLogger("pydective.markdown_search")


def _strip_accents(text: str) -> str:
    """Elimina tildes y diacríticos preservando caracteres alfanuméricos."""
    norm = unicodedata.normalize("NFD", text)
    return "".join(c for c in norm if unicodedata.category(c) != "Mn").lower()


# Diccionario semántico de sinónimos comunes en contratos y documentos técnicos/jurídicos
SYNONYM_MAP: Dict[str, List[str]] = {
    "cliente": [
        "cliente", "arrendatario", "comprador", "contratante", "titular",
        "usuario", "demandante", "suscriptor", "pagador", "arrendataria"
    ],
    "arrendatario": [
        "arrendatario", "arrendataria", "cliente", "inquilino", "ocupante", "arrendatarios"
    ],
    "arrendador": [
        "arrendador", "arrendadora", "propietario", "dueno", "locador", "contratante"
    ],
    "proveedor": [
        "proveedor", "contratista", "arrendador", "vendedor", "prestador", "empresa"
    ],
    "restricciones": [
        "restriccion", "restricciones", "prohibicion", "prohibiciones", "limitacion",
        "limitaciones", "obligaciones", "obligacion", "exclusiones", "reglas", "condiciones"
    ],
    "prohibiciones": [
        "prohibicion", "prohibiciones", "restriccion", "restricciones", "no esta permitido",
        "se prohibe", "queda prohibido", "obligaciones del arrendatario"
    ],
    "obligaciones": [
        "obligaciones", "obligacion", "compromisos", "deberes", "obligaciones del", "restricciones"
    ],
    "canon": [
        "canon", "arriendo", "alquiler", "precio", "renta", "pago mensual", "valor mensual"
    ],
    "valor": [
        "valor", "precio", "canon", "costo", "monto", "total", "suma", "cuantia"
    ],
    "duracion": [
        "duracion", "plazo", "vigencia", "termino", "tiempo", "periodo", "fecha de inicio", "vencimiento"
    ],
    "vigencia": [
        "vigencia", "plazo", "duracion", "termino", "prorroga", "renovacion"
    ],
    "diagrama": [
        "diagrama", "grafico", "grafica", "esquema", "flujo", "figura", "ilustracion", "grafica de barras"
    ],
    "imagen": [
        "imagen", "imagenes", "foto", "fotografia", "figura", "grafico", "diagrama", "elemento visual"
    ],
}


def _extract_pages_from_markdown(markdown_doc: str) -> Dict[int, str]:
    """Extrae las páginas separadas a partir de las etiquetas <!-- INICIO_PAGINA_X -->."""
    pages: Dict[int, str] = {}
    pattern = re.compile(
        r"<!--\s*INICIO_PAGINA_(\d+)\s*-->([\s\S]*?)<!--\s*FIN_PAGINA_\1\s*-->",
        re.IGNORECASE
    )
    matches = pattern.findall(markdown_doc)
    for p_num_str, p_content in matches:
        try:
            p_num = int(p_num_str)
            pages[p_num] = p_content.strip()
        except ValueError:
            continue

    if not pages and markdown_doc:
        # Fallback si el documento no tiene etiquetas: asumir página 1
        pages[1] = markdown_doc.strip()

    return pages


def _search_visual_query(
    pregunta_norm: str,
    pages_dict: Dict[int, str],
    resultados_paginas: Optional[List[Any]] = None,
) -> Optional[ChatOutput]:
    """
    Responde consultas orientadas a imágenes, diagramas, códigos de barras o QR
    usando los metadatos y bloques [Elemento Visual: ...].
    """
    is_diagram_query = any(k in pregunta_norm for k in ("diagrama", "grafico", "grafica", "pastel", "figura"))
    is_image_query = any(k in pregunta_norm for k in ("imagen", "imagenes", "foto", "fotografia", "elemento visual"))
    is_barcode_query = any(k in pregunta_norm for k in ("codigo de barras", "codigo barras", "barcode"))
    is_qr_query = any(k in pregunta_norm for k in ("codigo qr", "qr", "cufe"))

    if not (is_diagram_query or is_image_query or is_barcode_query or is_qr_query):
        return None

    # Preguntas de contenido o significado
    is_content_query = any(
        k in pregunta_norm for k in (
            "de que trata", "que trata", "que dice", "que contiene", "que muestra",
            "que representa", "explica", "describ"
        )
    )

    matching_pages: List[int] = []
    descriptions: List[str] = []
    evidences: List[Evidence] = []

    # 1. Búsqueda en los bloques inyectados de Markdown: [Elemento Visual: ...]
    for p_num, content in pages_dict.items():
        v_blocks = re.findall(r"\[Elemento Visual:\s*([^\]]+)\]", content, re.IGNORECASE)
        for b in v_blocks:
            b_norm = _strip_accents(b)
            matched = False
            if is_diagram_query and ("diagrama" in b_norm or "grafico" in b_norm or "figura" in b_norm):
                matched = True
            elif is_image_query and any(k in b_norm for k in ("imagen", "foto", "diagrama", "figura", "logotipo", "fotografia")):
                matched = True
            elif is_barcode_query and "codigo_barras" in b_norm:
                matched = True
            elif is_qr_query and "codigo_qr" in b_norm:
                matched = True

            if matched:
                if p_num not in matching_pages:
                    matching_pages.append(p_num)
                # Extraer descripción legible
                clean_desc = b.split("|")[0].replace("Coordenadas:", "").strip()
                descriptions.append(f"[Página {p_num}]: {clean_desc}")
                evidences.append(
                    Evidence(
                        evidence_id=f"ev_vis_md_p{p_num}",
                        page=p_num,
                        text=f"Elemento visual ({clean_desc}) en [Página {p_num}]",
                        bbox=[50.0, 50.0, 500.0, 400.0],
                        source=MetodoExtraccion.VISUAL_AI,
                        evidence_score=0.98,
                    )
                )

    # 2. Complementar con resultados_paginas si está disponible
    if resultados_paginas:
        for res in resultados_paginas:
            p_num = getattr(res, "numero_pagina", 1)
            visuals: List[MetadatoImagen] = getattr(res, "metadatos_visuales", [])
            for v in visuals:
                sem = v.clasificacion_semantica or ""
                matched = False
                if is_diagram_query and sem == "diagrama":
                    matched = True
                elif is_image_query and sem in ("diagrama", "fotografia", "logotipo", "firma_manuscrita", "sello_oficial"):
                    matched = True
                elif is_barcode_query and sem == "codigo_barras":
                    matched = True
                elif is_qr_query and sem == "codigo_qr":
                    matched = True

                if matched:
                    if p_num not in matching_pages:
                        matching_pages.append(p_num)
                    desc = v.descripcion_visual or sem.replace("_", " ")
                    if v.contenido_decodificado:
                        desc += f" (datos: {v.contenido_decodificado})"
                    desc_str = f"[Página {p_num}]: {desc}"
                    if desc_str not in descriptions:
                        descriptions.append(desc_str)
                    evidences.append(
                        Evidence(
                            evidence_id=f"ev_vis_res_p{p_num}_{v.id_imagen}",
                            page=p_num,
                            text=f"Elemento visual ({desc})",
                            bbox=v.bbox,
                            source=MetodoExtraccion.VISUAL_AI,
                            evidence_score=0.98,
                        )
                    )

    if not matching_pages:
        return None

    matching_pages.sort()
    citas = [f"[Página {p}]" for p in matching_pages]
    citas_str = ", ".join(citas)

    if is_content_query:
        # Responder de qué trata
        detalles = "; ".join(descriptions[:3])
        respuesta = f"El elemento visual en {citas_str} corresponde a: {detalles}."
    else:
        # Pregunta de existencia o ubicación
        if is_diagram_query:
            respuesta = f"Sí, el documento cuenta con un diagrama o gráfico técnico verificado e indexado en {citas_str}."
        elif is_barcode_query:
            respuesta = f"Sí, se identificó código de barras en {citas_str}."
        elif is_qr_query:
            respuesta = f"Sí, se identificó código QR en {citas_str}."
        else:
            respuesta = f"Se identificaron imágenes y elementos visuales registrados en {citas_str}."

    return ChatOutput(
        respuesta=respuesta,
        citas=citas,
        evidencias_relacionadas=evidences[:3],
    )


SPANISH_STOP_WORDS = {
    "que", "cual", "cuales", "donde", "cuando", "quien", "quienes",
    "tiene", "hay", "existe", "existen", "esta", "estan", "sobre",
    "para", "como", "trata", "del", "con", "por", "sin", "entre",
    "los", "las", "les", "una", "uno", "unos", "unas", "este", "esta",
    "estos", "estas", "ese", "esa", "esos", "esas", "aquel", "aquella",
    "sus", "mis", "tus", "nos", "les", "era", "fue", "ser", "sido",
    "son", "fue", "eran", "hace", "hacen", "dice", "dicen", "dar"
}


def deterministic_search(
    pdf_hash: str,
    pregunta: str,
    resultados_paginas: Optional[List[Any]] = None,
) -> Optional[ChatOutput]:
    """
    Motor determinista ultrarrápido (<5ms) en RAM sobre el Markdown indexado por páginas.
    Busca correspondencias léxicas, sinónimos y cláusulas estructuradas.
    Si encuentra la respuesta con alta certidumbre, retorna ChatOutput directamente.
    Si no encuentra coincidencia precisa o la pregunta requiere síntesis abstracta, retorna None.
    """
    markdown_doc = get_or_create_page_indexed_markdown(pdf_hash)
    if not markdown_doc:
        return None

    pages_dict = _extract_pages_from_markdown(markdown_doc)
    if not pages_dict:
        return None

    q_clean = _strip_accents(pregunta)
    q_tokens = [w for w in re.findall(r"\b\w{3,}\b", q_clean) if w not in SPANISH_STOP_WORDS]

    # 1. Verificar si es una consulta sobre elementos visuales (diagramas, fotos, barras, qr)
    vis_output = _search_visual_query(q_clean, pages_dict, resultados_paginas)
    if vis_output is not None:
        return vis_output

    if not q_tokens:
        return None

    # Si la consulta es una pregunta abierta, de síntesis o de identificación que requiere comprensión contextual
    # (ej: "¿Quién es...", "¿Quiénes son...", "resume", "explica", "por qué"), delegar al LLM en Tier 2
    is_open_or_synthesis = any(
        re.search(r"\b" + re.escape(w) + r"\b", q_clean)
        for w in ("quien", "quienes", "resume", "resumen", "sintesis", "sintetiza", "explica", "explicar", "por que", "opina")
    )
    if is_open_or_synthesis:
        return None

    # 2. Expandir lista de términos de búsqueda con sinónimos
    expanded_search_terms: List[str] = list(q_tokens)
    for token in q_tokens:
        for root_word, synonyms in SYNONYM_MAP.items():
            if root_word in token or token in root_word:
                for syn in synonyms:
                    if syn not in expanded_search_terms:
                        expanded_search_terms.append(syn)

    # 3. Buscar correspondencias en las páginas de Markdown
    page_matches: List[Tuple[int, str, float]] = []  # (p_num, matched_snippet, score)

    for p_num, content in pages_dict.items():
        content_norm = _strip_accents(content)
        lines = content.splitlines()

        for line_idx, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("<!--") or line_stripped.startswith("[Elemento Visual:"):
                continue

            line_norm = _strip_accents(line_stripped)

            # Buscar menciones directas o cláusulas
            matched_terms_in_line = [t for t in expanded_search_terms if re.search(r"\b" + re.escape(t) + r"\b", line_norm)]
            if matched_terms_in_line:
                # Si la línea es un encabezado o cláusula (ej: "CLÁUSULA CUARTA: PROHIBICIONES")
                # tomar la línea y las siguientes 2-3 líneas para dar contexto completo
                context_lines = [line_stripped]
                for next_idx in range(line_idx + 1, min(len(lines), line_idx + 4)):
                    nxt = lines[next_idx].strip()
                    if nxt and not nxt.startswith("<!--") and not nxt.startswith("#"):
                        context_lines.append(nxt)
                    elif nxt.startswith("#"):
                        break

                snippet = " ".join(context_lines)
                # Limpiar markdown excesivo
                snippet = re.sub(r"[*_#`]", "", snippet).strip()
                if len(snippet) > 280:
                    snippet = snippet[:277] + "..."

                score = len(matched_terms_in_line) * 1.0
                if any(k in line_norm for k in ("clausula", "articulo", "seccion", "paragrafo", "obligacion", "prohibicion")):
                    score += 0.8
                page_matches.append((p_num, snippet, score))

    if not page_matches:
        return None

    # Ordenar por relevancia
    page_matches.sort(key=lambda x: x[2], reverse=True)
    best_p_num, best_snippet, best_score = page_matches[0]

    # Requerir un umbral mínimo de certidumbre para no dar falsos positivos
    if best_score < 1.0:
        return None

    # Reunir páginas relevantes
    top_matches = [m for m in page_matches if m[2] >= best_score * 0.7][:2]
    unique_pages = sorted(list(set(m[0] for m in top_matches)))
    citas = [f"[Página {p}]" for p in unique_pages]
    citas_str = ", ".join(citas)

    # Redactar respuesta concisa y natural en español
    respuesta = f"En {citas_str} se indica lo siguiente: \"{best_snippet}\"."

    evidences = [
        Evidence(
            evidence_id=f"ev_md_p{m[0]}_{i}",
            page=m[0],
            text=m[1],
            bbox=[50.0, 100.0, 520.0, 250.0],
            source=MetodoExtraccion.NATIVE_TEXT,
            evidence_score=min(0.99, 0.85 + (m[2] * 0.03)),
        )
        for i, m in enumerate(top_matches)
    ]

    return ChatOutput(
        respuesta=respuesta,
        citas=citas,
        evidencias_relacionadas=evidences,
    )
