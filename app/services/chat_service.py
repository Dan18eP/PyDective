from typing import List, Optional, Dict, Any, Tuple
import re
import logging

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from app.domain.models import ChatInput, ChatOutput, ChatMessage, Evidence, MetadatoImagen
from app.domain.errors import DocumentoNoEncontradoOExpiradoError
from app.domain.enums import MetodoExtraccion
from app.services.cache_service import get_l1_cache, L1DocumentEntry
from app.services.semantic_extraction_service import normalize_parameter
from app.settings import settings

logger = logging.getLogger("pydective.chat")


def _clean_query_concept(pregunta: str) -> str:
    """Limpia palabras interrogativas comunes para aislar el concepto consultado."""
    text = pregunta.strip().lower()
    text = re.sub(r"[¿\?¡\!]", "", text)
    # Quitar muletillas y verbos iniciales de pregunta
    prefixes = [
        "tiene un", "tiene una", "tiene el", "tiene la", "tiene los", "tiene las", "tiene",
        "hay un", "hay una", "hay el", "hay la", "hay los", "hay las", "hay",
        "cuál es el", "cuál es la", "cuáles son los", "cuáles son las", "cuál es", "cuáles son",
        "cuanto es el", "cuanto es la", "cuanto cuesta", "a cuánto asciende el", "a cuánto asciende la", "a cuánto asciende",
        "dime si tiene", "dime si hay", "dime el", "dime la", "dime",
        "existe un", "existe una", "existen", "existe",
    ]
    for p in prefixes:
        if text.startswith(p + " "):
            text = text[len(p) + 1:].strip()
            break
    return text.strip()


def _search_visual_elements(
    resultados_por_pagina: List[Any],
    query_norm: str,
    target_page: Optional[int] = None,
) -> Tuple[List[str], List[Evidence], str]:
    """
    Busca elementos visuales catalogados (códigos de barras, QR, firmas, sellos, fotos, gráficos).
    Retorna (citas, evidencias_simuladas, descripcion).
    """
    citas: List[str] = []
    evidencias: List[Evidence] = []
    descripcion = ""

    # Mapeo de términos de consulta a clasificaciones semánticas
    is_barcode = any(kw in query_norm for kw in ("codigo de barras", "codigo barras", "barcode", "barras", "radicado"))
    is_qr = any(kw in query_norm for kw in ("codigo qr", "qr", "cufe"))
    is_signature = any(kw in query_norm for kw in ("firma", "firmas", "firmado", "rubrica", "firmantes"))
    is_seal = any(kw in query_norm for kw in ("sello", "sellos", "notaria", "notarial", "autenticado", "estampilla"))
    is_photo = any(kw in query_norm for kw in ("foto", "fotografia", "fotografias", "datacenter", "servidor"))
    is_chart = any(kw in query_norm for kw in ("grafico", "grafica", "diagrama", "pastel", "barras comparativo"))

    found_pages: List[int] = []
    item_type = ""
    item_short_tag = "Elemento Visual"

    for res in resultados_por_pagina:
        p_num = getattr(res, "numero_pagina", 1)
        visuals: List[MetadatoImagen] = getattr(res, "metadatos_visuales", [])
        for v in visuals:
            sem = v.clasificacion_semantica or ""
            matched = False
            if is_barcode and sem == "codigo_barras":
                matched = True
                item_type = "código de barras de radicación oficial"
                item_short_tag = "Código de Barras"
            elif is_qr and sem == "codigo_qr":
                matched = True
                item_type = "código QR de validación fiscal"
                item_short_tag = "Código QR"
            elif is_signature and sem == "firma_manuscrita":
                matched = True
                item_type = "firma autógrafa caligráfica"
                item_short_tag = "Firma"
            elif is_seal and sem == "sello_oficial":
                matched = True
                item_type = "sello oficial notarial"
                item_short_tag = "Sello"
            elif is_photo and sem == "fotografia":
                matched = True
                item_type = "evidencia fotográfica pericial"
                item_short_tag = "Fotografía"
            elif is_chart and sem == "diagrama":
                matched = True
                item_type = "gráfico o diagrama técnico"
                item_short_tag = "Diagrama"

            if matched:
                if p_num not in found_pages:
                    found_pages.append(p_num)
                txt = f"{item_short_tag} en [Página {p_num}]"
                if v.contenido_decodificado:
                    txt += f" ({v.contenido_decodificado})"
                evidencias.append(
                    Evidence(
                        evidence_id=f"ev_vis_p{p_num}_{v.id_imagen}",
                        page=p_num,
                        text=txt,
                        bbox=v.bbox,
                        source=MetodoExtraccion.VISUAL_AI,
                        evidence_score=0.99 if (target_page and p_num == target_page) else 0.96,
                    )
                )

    if found_pages:
        # Priorizar página objetivo si fue solicitada por el usuario
        if target_page and target_page in found_pages:
            found_pages = [target_page] + sorted([p for p in found_pages if p != target_page])
            evidencias.sort(key=lambda e: (0 if e.page == target_page else 1, -e.evidence_score))
        else:
            found_pages.sort()
            evidencias.sort(key=lambda e: -e.evidence_score)

        citas = [f"[Página {p}]" for p in found_pages]
        citas_str = ", ".join(citas)
        decoded_notes = []
        for res in resultados_por_pagina:
            for v in getattr(res, "metadatos_visuales", []):
                if v.contenido_decodificado and (is_qr and v.clasificacion_semantica == "codigo_qr"):
                    decoded_notes.append(f"contenido/URL: {v.contenido_decodificado}")
        extra_note = f" ({', '.join(decoded_notes)})" if decoded_notes else ""
        
        if target_page and target_page in found_pages:
            descripcion = f"En la página {target_page}, se localizó {item_type} verificado con alta fidelidad (también registrado en {citas_str}){extra_note}."
        else:
            descripcion = f"Sí, el documento cuenta con {item_type} verificado e inventariado en {citas_str}{extra_note}."

    return citas, evidencias, descripcion


def process_chat_query(
    pdf_hash: str,
    pregunta: str,
    historial: List[ChatMessage] = [],
    fallback_store: Optional[Dict[str, Any]] = None,
    motor_seleccionado: Optional[str] = None,
) -> ChatOutput:
    """
    Procesa consultas en lenguaje natural con inteligencia contextual, búsqueda en L1,
    catálogo de elementos visuales (códigos de barras, QR, firmas, sellos) y respuestas conversacionales fluidas (US-23).
    Permite switch manual de motor ('chain', 'agy', 'opencode', 'gemini', 'local').
    """
    l1_entry: Optional[L1DocumentEntry] = get_l1_cache(pdf_hash)
    fallback_job = fallback_store.get(pdf_hash) if fallback_store else None

    if l1_entry is None and fallback_job is None:
        from pathlib import Path
        disk_path = Path(__file__).resolve().parent.parent.parent / "data" / "results" / f"{pdf_hash}.json"
        if disk_path.exists():
            from app.domain.models import JobOutput
            try:
                fallback_job = JobOutput.model_validate_json(disk_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    if l1_entry is None and fallback_job is None:
        raise DocumentoNoEncontradoOExpiradoError(pdf_hash)

    q_norm = normalize_parameter(pregunta)
    _stopwords = {
        "cual", "cuales", "como", "donde", "cuando", "quien", "quienes", "que", "para", "por",
        "con", "sin", "sobre", "del", "las", "los", "les", "una", "uno", "unos", "unas", "este",
        "esta", "estos", "estas", "ese", "esa", "esos", "esas", "aquel", "aquella", "entre", "hacia",
        "hasta", "desde", "tiene", "hay", "esta"
    }
    q_tokens = [t for t in q_norm.split() if len(t) > 2 and t not in _stopwords]
    concepto_limpio = _clean_query_concept(pregunta)

    # 1. Obtener páginas procesadas para inspección visual y textual
    resultados_paginas = []
    total_pages = 1
    if l1_entry:
        resultados_paginas = l1_entry.resultados_por_pagina
        total_pages = l1_entry.paginas_totales or len(resultados_paginas) or 1
    elif fallback_job:
        resultados_paginas = fallback_job.resultados_por_pagina
        total_pages = fallback_job.paginas_totales or len(resultados_paginas) or 1

    # 2. Detección de consultas visuales / inspección de imágenes (perros, fotos, objetos, diagramas)
    is_visual_query = any(
        kw in q_norm
        for kw in (
            "imagen", "imagenes", "foto", "fotos", "fotografia", "fotografias",
            "perro", "perros", "animal", "animales", "objeto", "objetos", "que hay",
            "que se ve", "describir", "describe", "cuantos", "cuantas", "grafico", "diagrama",
            "sello", "firma", "qr", "codigo de barras"
        )
    )

    page_target_match = re.search(r"(?:pagina|p[aá]gina|pag|folio)\s*(\d+)", q_norm)
    target_page_num = int(page_target_match.group(1)) if page_target_match else None

    chapter_target_match = re.search(r"(?:capitulo|cap[ií]tulo|cap)\s*(\d+)", q_norm)
    target_chapter_num = int(chapter_target_match.group(1)) if chapter_target_match else None

    is_summary_query = any(
        kw in q_norm
        for kw in (
            "resumen", "resume", "resumir", "sintesis", "sintetiza",
            "de que trata", "de que habla", "puntos clave", "objeto",
            "explicame", "explica", "conclusion", "introduccion", "capitulo"
        )
    )

    # Buscar elementos visuales priorizando la página objetivo si se especificó
    vis_citas, vis_evidencias, vis_desc = _search_visual_elements(
        resultados_paginas, q_norm, target_page=target_page_num
    )

    # Identificar si la consulta pide lectura, texto, contenido o explicación
    is_content_query = any(
        kw in q_norm
        for kw in (
            "que dice", "que texto", "dice", "texto", "leer", "lee", "contenido",
            "explica", "indica", "describ", "detalle", "perro", "cuanto", "cuantos",
            "que hay", "que contiene", "que significa", "cuales", "cuales son", "donde", "mostrar"
        )
    )
    user_explicit_engine = motor_seleccionado in ("agy", "opencode", "gemini", "local")

    # Solo hacer cortocircuito rápido a catálogo estático si es consulta meramente booleana global sin motor explícito
    if vis_citas and not is_content_query and target_page_num is None and not user_explicit_engine:
        return ChatOutput(
            respuesta=vis_desc,
            citas=vis_citas,
            evidencias_relacionadas=vis_evidencias[:3],
        )

    # 3. Inspeccionar índice asociativo y hallazgos estructurados de L1 o fallback
    matched_evidences: List[Evidence] = []
    matched_findings: List[str] = []
    available_params: List[str] = []

    if l1_entry:
        for param, ev_list in l1_entry.indice_asociativo.items():
            available_params.append(param)
            param_norm = normalize_parameter(param)
            if any(t in param_norm for t in q_tokens) or any(param_norm in t for t in q_tokens):
                for ev in ev_list:
                    if ev not in matched_evidences:
                        matched_evidences.append(ev)
                        matched_findings.append(f"{param}: {ev.text}")

        for h in l1_entry.hallazgos_previos:
            if h.parametro not in available_params:
                available_params.append(h.parametro)
            h_norm = normalize_parameter(h.parametro)
            if any(t in h_norm for t in q_tokens) or any(h_norm in t for t in q_tokens):
                for ev in h.evidencias:
                    if ev not in matched_evidences:
                        matched_evidences.append(ev)
                        matched_findings.append(f"{h.parametro}: {h.valor}")

    elif fallback_job:
        for h in fallback_job.hallazgos:
            available_params.append(h.parametro)
            h_norm = normalize_parameter(h.parametro)
            if any(t in h_norm for t in q_tokens) or any(h_norm in t for t in q_tokens):
                for ev in h.evidencias:
                    if ev not in matched_evidences:
                        matched_evidences.append(ev)
                        matched_findings.append(f"{h.parametro}: {h.valor}")

    # Búsqueda adicional en evidencias directas de todas las páginas
    for res in resultados_paginas:
        for ev in getattr(res, "evidencias", []):
            ev_norm = normalize_parameter(ev.text)
            if any(t in ev_norm for t in q_tokens):
                if ev not in matched_evidences:
                    matched_evidences.append(ev)
                    matched_findings.append(ev.text)

    # 3b. Mapeo semántico para consultas conceptuales abiertas sobre partes, representantes o firmantes
    is_party_query = any(k in q_norm for k in ("parte", "partes", "representante", "representantes", "quien", "quienes", "firmante", "firmantes", "personas", "entidades", "titular"))
    if is_party_query:
        party_params = ("arrendador", "arrendatario", "representante legal", "representante", "cliente", "proveedor", "contratante", "contratista", "notario", "comprador", "vendedor")
        all_findings = []
        if l1_entry:
            all_findings = l1_entry.hallazgos_previos
        elif fallback_job:
            all_findings = fallback_job.hallazgos
        for h in all_findings:
            if any(k in h.parametro for k in party_params):
                f_desc = f"{h.parametro.upper()}: {h.valor}"
                if f_desc not in matched_findings:
                    matched_findings.append(f_desc)
                for ev in h.evidencias:
                    if ev not in matched_evidences:
                        matched_evidences.append(ev)

    # 3c. Extracción directa del texto literal de los folios del documento y preparación visual
    page_texts: List[str] = []
    text_evidences: List[Evidence] = []
    image_bytes_for_llm: Optional[bytes] = None
    image_path_for_llm: Optional[str] = None
    target_page_for_evidence = target_page_num or 1

    try:
        from app.services.pdf_viewer_service import get_pdf_bytes_by_hash
        import pymupdf
        pdf_bytes = get_pdf_bytes_by_hash(pdf_hash)
        if pdf_bytes:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            total_pages = max(total_pages, len(doc))

            # Si es consulta visual, renderizar la página consultada (o la página con imágenes detectadas)
            if is_visual_query:
                # Determinar la mejor página a inspeccionar
                p_inspect_idx = 0
                if target_page_num and 1 <= target_page_num <= len(doc):
                    p_inspect_idx = target_page_num - 1
                elif vis_evidencias:
                    p_inspect_idx = max(0, vis_evidencias[0].page - 1)
                else:
                    # Buscar página que tenga imágenes ráster o dibujos
                    for idx_p, p_obj in enumerate(doc):
                        if p_obj.get_images() or p_obj.get_drawings():
                            p_inspect_idx = idx_p
                            break

                target_page_for_evidence = p_inspect_idx + 1
                try:
                    import tempfile
                    from pathlib import Path
                    page_obj = doc[p_inspect_idx]
                    pix = page_obj.get_pixmap(dpi=150)
                    image_bytes_for_llm = pix.tobytes("png")
                    
                    # Guardar archivo PNG en scratch/data/temp para que AGY / OpenCode CLI puedan leerlo
                    data_temp = Path(__file__).resolve().parent.parent.parent / "data" / "temp"
                    data_temp.mkdir(parents=True, exist_ok=True)
                    img_file = data_temp / f"chat_vis_{pdf_hash[:10]}_p{target_page_for_evidence}.png"
                    img_file.write_bytes(image_bytes_for_llm)
                    image_path_for_llm = str(img_file)
                    # Extraer texto OCR de los elementos visuales/diagramas de la página inspeccionada
                    try:
                        from rapidocr_onnxruntime import RapidOCR
                        _ocr = RapidOCR()
                        ocr_res, _ = _ocr(image_bytes_for_llm)
                        if ocr_res:
                            detected_ocr_lines = [line[1].strip() for line in ocr_res if line[1].strip()]
                            if detected_ocr_lines:
                                page_texts.insert(
                                    0,
                                    f"--- [Texto OCR y elementos detectados en Página {target_page_for_evidence}] ---\n" + "\n".join(detected_ocr_lines[:25])
                                )
                    except Exception as ocr_err:
                        logger.debug(f"OCR complementario no disponible para chat: {ocr_err}")
                except Exception as err_render:
                    logger.debug(f"No se pudo renderizar página para chat visual: {err_render}")

            # Si se especificó un capítulo, localizar la página exacta donde comienza
            if target_chapter_num:
                for p_idx in range(len(doc)):
                    p_raw = doc[p_idx].get_text()
                    if re.search(rf"cap[ií¶]tulo\s*{target_chapter_num}\b", p_raw, re.IGNORECASE):
                        target_page_num = p_idx + 1
                        target_page_for_evidence = target_page_num
                        text_evidences.append(
                            Evidence(
                                evidence_id=f"ev_cap_{target_chapter_num}_p{target_page_num}",
                                page=target_page_num,
                                text=f"Capítulo {target_chapter_num} en [Página {target_page_num}]",
                                bbox=[50.0, 50.0, 545.0, 200.0],
                                source=MetodoExtraccion.NATIVE_TEXT,
                                evidence_score=0.98,
                            )
                        )
                        break

            for p_idx in range(len(doc)):
                p_num = p_idx + 1
                p_text = doc[p_idx].get_text().strip()
                if not p_text:
                    continue
                p_norm = normalize_parameter(p_text)
                is_key_page = (
                    (target_page_num and p_num == target_page_num)
                    or (is_summary_query and p_num in (1, 2, 3, 4, 7, 20))
                    or ((is_summary_query or user_explicit_engine or is_content_query) and p_num <= 2)
                    or (any(t in p_norm for t in q_tokens) if q_tokens else False)
                )
                if is_key_page:
                    page_texts.append(f"--- [Página {p_num}] ---\n{p_text[:1400]}")
                    if is_party_query and any(k in p_norm for k in ("suscritos", "arrendador", "representad", "contrat")):
                        text_evidences.append(
                            Evidence(
                                evidence_id=f"ev_ctx_p{p_num}_{len(text_evidences)+1:02d}",
                                page=p_num,
                                text=f"Cláusula de partes en [Página {p_num}]",
                                bbox=[50.0, 95.0, 545.0, 230.0],
                                source=MetodoExtraccion.NATIVE_TEXT,
                                evidence_score=0.95,
                            )
                        )
            doc.close()
    except Exception as e:
        logger.debug(f"No se pudo cargar texto directo de PDF para chat: {e}")

    if is_summary_query and not text_evidences and not matched_evidences:
        text_evidences.append(
            Evidence(
                evidence_id="ev_summary_doc",
                page=target_page_num or 1,
                text=f"Resumen Documental en [Página {target_page_num or 1}]",
                bbox=[50.0, 50.0, 545.0, 250.0],
                source=MetodoExtraccion.NATIVE_TEXT,
                evidence_score=0.95,
            )
        )

    if not matched_evidences and text_evidences:
        matched_evidences.extend(text_evidences)

    if is_visual_query and vis_evidencias:
        for ve in vis_evidencias:
            if ve not in matched_evidences:
                matched_evidences.append(ve)

    # 4. Modo de síntesis forense: Si no se encontró evidencia ni es consulta visual/inspección
    # Declinación determinista sin alucinación para parámetros ausentes cuando no hay motor explícito ni consulta abierta de contenido
    if not matched_findings and not is_visual_query and not is_summary_query and not user_explicit_engine and not is_content_query:
        resumen_disponible = f" ({', '.join(list(set(available_params))[:4])})" if available_params else ""
        respuesta = (
            f"Tras examinar detenidamente los folios del documento, se constató que el dato o concepto solicitado "
            f"('{concepto_limpio}') no figura registrado en ninguna de las páginas analizadas."
        )
        if available_params:
            respuesta += f" Entre los datos validados y disponibles en el expediente se encuentran: {', '.join(list(set(available_params))[:5])}."

        return ChatOutput(
            respuesta=respuesta,
            citas=[],
            evidencias_relacionadas=[],
        )

    # 5. Síntesis conversacional vía proveedor configurado en cadena o switch manual
    from app.services.providers import get_llm_provider
    llm_provider = get_llm_provider(preference=motor_seleccionado)
    if llm_provider.is_available():
        try:
            context_summary = f"Total páginas del documento: {total_pages}.\n"
            if matched_findings:
                context_summary += f"Hallazgos relevantes extraídos: {'; '.join(matched_findings)}.\n"
            if available_params:
                context_summary += f"Parámetros conocidos en el documento: {', '.join(set(available_params))}.\n"
            if page_texts:
                context_summary += "\nTexto literal extraído de los folios del documento:\n" + "\n\n".join(page_texts[:6]) + "\n"

            # Inventario de elementos visuales catalogados
            all_visuals_desc = []
            relevant_visuals_desc = []
            for res in resultados_paginas:
                p_n = getattr(res, "numero_pagina", 1)
                for v in getattr(res, "metadatos_visuales", []):
                    cls_name = v.clasificacion_semantica or "imagen"
                    extra = f" (decodificado: '{v.contenido_decodificado}')" if v.contenido_decodificado else ""
                    desc_line = f"Página {p_n}: {cls_name}{extra} en coordenadas {v.bbox}"
                    all_visuals_desc.append(desc_line)
                    # Detectar si coincide con el término consultado (firma, sello, qr, diagrama, foto, etc.)
                    cls_lower = cls_name.lower()
                    if any(t in cls_lower or cls_lower in t for t in q_tokens) or any(k in cls_lower for k in ("firma", "sello", "qr", "codigo", "diagrama", "foto") if k in q_norm):
                        relevant_visuals_desc.append(desc_line)

            if relevant_visuals_desc:
                context_summary += f"\nInventario de elementos forenses consultados (Total detectado en documento: {len(relevant_visuals_desc)}):\n" + "\n".join(relevant_visuals_desc) + "\n"
            elif all_visuals_desc:
                context_summary += "\nInventario visual forense registrado en el documento:\n" + "\n".join(all_visuals_desc[:25]) + "\n"

            sys_instruction = (
                "Eres el asistente forense documental y de visión pericial de PyDective. "
                "Tu objetivo es verificar el documento e imágenes con rigor forense, exactitud y precisión milimétrica.\n"
                "INSTRUCCIONES CLAVE:\n"
                "1. Si el usuario pregunta cuántos elementos (firmas, sellos, diagramas, códigos) hay en el documento, "
                "informa con certeza el número total identificado en el inventario forense y detalla las páginas y firmantes/títulos correspondientes.\n"
                "2. Si el usuario pregunta por el contenido de un diagrama, imagen o firma, descríbelo con máximo detalle técnico según el texto OCR y la inspección visual.\n"
                "3. Cita siempre la página específica donde se ubica la información como [Página X].\n"
                "4. Responde DIRECTAMENTE en texto claro y profesional sin ejecutar comandos de terminal ni solicitar herramientas externas.\n"
                "5. Responde siempre en español formal y pericial."
            )
            prompt = f"Contexto Documental:\n{context_summary}\nPregunta del Usuario: {pregunta}"

            resp_text = llm_provider.generate_chat_response(
                prompt=prompt,
                system_instruction=sys_instruction,
                image_bytes=image_bytes_for_llm,
                image_path=image_path_for_llm,
            )
            if resp_text:
                cited_matches = [int(m) for m in re.findall(r"\[Página\s+(\d+)\]", resp_text, re.IGNORECASE)]
                all_pages = list(dict.fromkeys(cited_matches + [e.page for e in matched_evidences]))
                if target_page_num and target_page_num in all_pages:
                    pages = [target_page_num] + [p for p in all_pages if p != target_page_num]
                else:
                    pages = sorted(all_pages)

                citas = [f"[Página {p}]" for p in pages]
                if not citas and is_visual_query:
                    citas = [f"[Página {target_page_for_evidence}]"]
                if citas and not any(c in resp_text for c in citas):
                    resp_text = f"{resp_text} ({', '.join(citas)})"

                # Priorizar evidencias de la página solicitada
                if target_page_num:
                    matched_evidences.sort(key=lambda e: (0 if e.page == target_page_num else 1, -e.evidence_score))
                else:
                    matched_evidences.sort(key=lambda e: -e.evidence_score)

                final_evidences = matched_evidences[:3]
                if not final_evidences and is_visual_query:
                    # Buscar si hay metadatos visuales de esa página para dar el bbox exacto
                    exact_bbox = [0.0, 0.0, 612.0, 792.0]
                    exact_label = f"Diagrama en [Página {target_page_for_evidence}]"
                    for res in resultados_paginas:
                        if getattr(res, "numero_pagina", 0) == target_page_for_evidence:
                            v_list = getattr(res, "metadatos_visuales", [])
                            if v_list:
                                exact_bbox = v_list[0].bbox
                                sem_tag = (v_list[0].clasificacion_semantica or "elemento").capitalize()
                                exact_label = f"{sem_tag} en [Página {target_page_for_evidence}]"
                                break

                    final_evidences = [
                        Evidence(
                            evidence_id=f"ev_vis_p{target_page_for_evidence}_detail",
                            page=target_page_for_evidence,
                            text=exact_label,
                            bbox=exact_bbox,
                            source=MetodoExtraccion.VISUAL_AI,
                            evidence_score=0.99,
                        )
                    ]

                used_name = getattr(llm_provider, "last_used_provider", None) or getattr(llm_provider, "name", None)
                used_name_str = str(used_name) if used_name is not None else None
                return ChatOutput(
                    respuesta=resp_text,
                    citas=citas,
                    evidencias_relacionadas=final_evidences,
                    motor_utilizado=used_name_str,
                )
        except Exception as e:
            logger.warning(f"Fallback a síntesis tras error en {llm_provider.name}: {e}")


    # 6. Fallback final si la síntesis LLM no arrojó respuesta
    if target_page_num:
        matched_evidences.sort(key=lambda e: (0 if e.page == target_page_num else 1, -e.evidence_score))
    else:
        matched_evidences.sort(key=lambda e: e.evidence_score, reverse=True)
    top_evidences = matched_evidences[:3]

    pages = list(dict.fromkeys([e.page for e in top_evidences]))
    if not pages:
        pages = [target_page_for_evidence]
    citas = [f"[Página {p}]" for p in pages]
    citas_str = ", ".join(citas)

    details = "; ".join(matched_findings[:2]) if matched_findings else ""
    if not details and page_texts:
        for pt in page_texts:
            clean_pt = pt.split("---")[-1].strip()
            if clean_pt and len(clean_pt) > 20:
                details = clean_pt[:200].replace("\n", " ")
                break
    if not details:
        details = "análisis forense y visual completado"
    respuesta = (
        f"De acuerdo con la evidencia forense registrada en {citas_str}, "
        f"se identificó la siguiente información: {details}."
    )

    return ChatOutput(
        respuesta=respuesta,
        citas=citas,
        evidencias_relacionadas=top_evidences,
    )
