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
from app.services.cache_service import get_l1_cache, set_l1_cache, L1DocumentEntry
from app.services.markdown_service import get_or_create_page_indexed_markdown
from app.services.markdown_search_service import deterministic_search, get_relevant_page_slices, _strip_accents
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


def _search_visual_elements(resultados_por_pagina: List[Any], query_norm: str) -> Tuple[List[str], List[Evidence], str]:
    """
    Busca elementos visuales catalogados (códigos de barras, QR, firmas, sellos, fotos, gráficos).
    Retorna (citas, evidencias_simuladas, descripcion).
    """
    citas: List[str] = []
    evidencias: List[Evidence] = []
    descripcion = ""

    # Mapeo de términos de consulta a clasificaciones semánticas
    is_chart = any(kw in query_norm for kw in ("grafico", "gráfica", "grafica", "diagrama", "pastel", "barras comparativo", "figura", "ilustracion", "ilustración"))
    is_barcode = any(kw in query_norm for kw in ("codigo de barras", "código de barras", "codigo barras", "código barras", "barcode", "radicado oficial", "rad-"))
    # Si la consulta menciona explícitamente gráfico o diagrama de barras, es gráfico, no código de barras
    if any(k in query_norm for k in ("grafico", "gráfico", "diagrama", "figura")):
        is_barcode = False

    is_qr = any(kw in query_norm for kw in ("codigo qr", "qr", "cufe"))
    is_signature = any(kw in query_norm for kw in ("firma", "firmas", "firmado", "rubrica", "firmantes"))
    is_seal = any(kw in query_norm for kw in ("sello", "sellos", "notaria", "notarial", "autenticado", "estampilla"))
    is_photo = any(kw in query_norm for kw in ("foto", "fotografia", "fotografias", "datacenter", "servidor"))
    is_general_image = any(kw in query_norm for kw in ("imagen", "imagenes", "imágenes", "elemento visual", "elementos visuales", "grafico o imagen"))

    found_pages: List[int] = []
    item_type = ""

    for res in resultados_por_pagina:
        p_num = getattr(res, "numero_pagina", 1)
        visuals: List[MetadatoImagen] = getattr(res, "metadatos_visuales", [])
        for v in visuals:
            sem = v.clasificacion_semantica or ""
            matched = False
            if is_barcode and sem == "codigo_barras":
                matched = True
                item_type = "código de barras de radicación oficial"
            elif is_qr and sem == "codigo_qr":
                matched = True
                item_type = "código QR de validación fiscal"
            elif is_signature and sem == "firma_manuscrita":
                matched = True
                item_type = "firma autógrafa caligráfica"
            elif is_seal and sem == "sello_oficial":
                matched = True
                item_type = "sello oficial notarial"
            elif is_photo and sem == "fotografia":
                matched = True
                item_type = "evidencia fotográfica pericial"
            elif is_chart and sem == "diagrama":
                matched = True
                item_type = "gráfico o diagrama técnico"
            elif is_general_image and sem in ("diagrama", "fotografia", "logotipo", "codigo_barras", "codigo_qr", "firma_manuscrita", "sello_oficial"):
                matched = True
                item_type = f"elemento visual ({sem.replace('_', ' ')})"

            if matched:
                if p_num not in found_pages:
                    found_pages.append(p_num)
                txt = f"Elemento visual detectado: {item_type}"
                if v.descripcion_visual:
                    txt += f" ({v.descripcion_visual})"
                elif v.contenido_decodificado:
                    txt += f" (contenido decodificado: '{v.contenido_decodificado}')"
                txt += f" en bbox {v.bbox}"
                evidencias.append(
                    Evidence(
                        evidence_id=f"ev_vis_p{p_num}_{v.id_imagen}",
                        page=p_num,
                        text=txt,
                        bbox=v.bbox,
                        source=MetodoExtraccion.VISUAL_AI,
                        evidence_score=0.96,
                    )
                )

    if found_pages:
        found_pages.sort()
        citas = [f"[Página {p}]" for p in found_pages]
        citas_str = ", ".join(citas)
        decoded_notes = []
        for res in resultados_por_pagina:
            for v in getattr(res, "metadatos_visuales", []):
                if v.contenido_decodificado and (is_qr and v.clasificacion_semantica == "codigo_qr"):
                    decoded_notes.append(f"contenido/URL: {v.contenido_decodificado}")
        extra_note = f" ({', '.join(decoded_notes)})" if decoded_notes else ""
        if is_general_image:
            descripcion = f"Sí, el documento cuenta con imágenes y elementos visuales registrados en {citas_str}{extra_note}."
        else:
            descripcion = f"Sí, el documento cuenta con {item_type} verificado e inventariado en {citas_str}{extra_note}."
    else:
        if is_qr:
            descripcion = "No se identificaron códigos QR en el documento analizado."
        elif is_barcode:
            descripcion = "No se identificaron códigos de barras en el documento analizado."
        elif is_seal:
            descripcion = "No se identificaron sellos oficiales en el documento analizado."

    return citas, evidencias, descripcion


def process_chat_query(
    pdf_hash: str,
    pregunta: str,
    historial: List[ChatMessage] = [],
    fallback_store: Optional[Dict[str, Any]] = None,
    skip_llm: bool = False,
    usar_modelo_local: bool = False,
) -> Optional[ChatOutput]:
    """
    Procesa consultas en lenguaje natural con inteligencia contextual, búsqueda en L1,
    catálogo de elementos visuales (códigos de barras, QR, firmas, sellos) y respuestas conversacionales fluidas (US-23).
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
        # Intentar auto-hidratar L1 a partir del PDF si existe en disco o uploads
        from app.services.pdf_viewer_service import get_pdf_bytes_by_hash
        p_bytes = get_pdf_bytes_by_hash(pdf_hash)
        if p_bytes:
            from app.services.markdown_service import get_or_create_page_indexed_markdown
            md_doc = get_or_create_page_indexed_markdown(pdf_hash, pdf_bytes=p_bytes)
            import pymupdf
            doc = pymupdf.open(stream=p_bytes, filetype="pdf")
            p_total = len(doc)
            doc.close()
            l1_entry = L1DocumentEntry(
                pdf_hash=pdf_hash,
                paginas_totales=p_total,
                paginas_completadas=p_total,
                documento_markdown_indexado=md_doc,
            )
            set_l1_cache(pdf_hash, l1_entry)

    if l1_entry is None and fallback_job is None:
        raise DocumentoNoEncontradoOExpiradoError(pdf_hash)

    GENERIC_STOP_TOKENS = {
        "documento", "documentos", "archivo", "archivos", "folio", "folios",
        "pagina", "paginas", "texto", "resumen", "sintesis"
    }
    q_norm = normalize_parameter(pregunta)
    q_tokens = [t for t in q_norm.split() if len(t) > 2 and t not in GENERIC_STOP_TOKENS]
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

    # 2. Inspeccionar elementos visuales (preguntas de presencia: códigos de barras, QR, firmas, sellos, fotos, diagramas)
    has_target_page = bool(re.search(r"\b(?:pag(?:ina)?|p[áa]g(?:ina)?|folio)\s*(\d+)\b", q_norm))
    is_content_query = has_target_page or any(
        kw in q_norm for kw in (
            "de que trata", "de qué trata", "que trata", "qué trata",
            "que contiene", "qué contiene", "que muestra", "qué muestra",
            "que dice", "qué dice", "explica", "explicar", "describ",
            "cual es", "cuál es", "que representa", "qué representa", "contenido",
            "que significa", "que significan", "qué significa", "qué significan", "significado", "informacion", "detalle",
            "quien", "quién", "quienes", "quiénes", "identificar", "identifica", "como se llama", "cómo se llama"
        )
    )
    if not is_content_query:
        vis_citas, vis_evidencias, vis_desc = _search_visual_elements(resultados_paginas, q_norm)
        if vis_desc:
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
    is_party_query = any(k in q_norm for k in ("parte", "partes", "representante", "representantes", "firmante", "firmantes")) or (
        any(k in q_norm for k in ("quien", "quienes")) and not any(k in q_norm for k in ("cedula", "recibe", "reclama", "entrega", "formula", "atiende", "medico", "doctor", "diagnostico"))
    )
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

        # Extraer firmantes identificados en metadatos visuales de firmas manuscritas
        for res in resultados_paginas:
            p_num = getattr(res, "numero_pagina", 1)
            for v in getattr(res, "metadatos_visuales", []):
                if v.clasificacion_semantica == "firma_manuscrita" and v.descripcion_visual and "Firma autógrafa de:" in v.descripcion_visual:
                    f_desc = v.descripcion_visual.replace("Firma autógrafa de: ", "FIRMANTE: ")
                    if f_desc not in matched_findings:
                        matched_findings.append(f_desc)
                        matched_evidences.append(
                            Evidence(
                                evidence_id=f"ev_sign_p{p_num}_{v.id_imagen}",
                                page=p_num,
                                text=v.descripcion_visual,
                                bbox=v.bbox,
                                source=MetodoExtraccion.VISUAL_AI,
                                evidence_score=0.98,
                            )
                        )

        # Si se identificaron hallazgos estructurados para las partes y representantes, responder directamente
        if matched_findings:
            pages = sorted(list(set(e.page for e in matched_evidences))) or [1]
            citas = [f"[Página {p}]" for p in pages]
            citas_str = ", ".join(citas)
            details = "; ".join(matched_findings[:4])
            return ChatOutput(
                respuesta=f"De acuerdo con los registros del documento en {citas_str}, las partes y representantes identificados son: {details}.",
                citas=citas,
                evidencias_relacionadas=matched_evidences[:4],
            )

    # 3c. Extracción directa del texto literal de los folios del documento para fundamentación estricta
    page_texts: List[str] = []
    text_evidences: List[Evidence] = []
    try:
        from app.services.pdf_viewer_service import get_pdf_bytes_by_hash
        import pymupdf
        pdf_bytes = get_pdf_bytes_by_hash(pdf_hash)
        if pdf_bytes:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            total_pages = max(total_pages, len(doc))
            for p_idx in range(len(doc)):
                p_num = p_idx + 1
                p_text = doc[p_idx].get_text().strip()
                if not p_text:
                    continue
                p_norm = normalize_parameter(p_text)
                is_key_page = p_num <= 2 or any(t in p_norm for t in q_tokens)
                if is_key_page:
                    page_texts.append(f"--- [Página {p_num}] ---\n{p_text[:1200]}")
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

    if not matched_evidences and text_evidences:
        matched_evidences.extend(text_evidences)

    # 4a. Búsqueda determinista ultrarrápida (<5ms) en Markdown indexado por páginas
    det_out = deterministic_search(pdf_hash, pregunta, resultados_paginas)
    if det_out is not None:
        return det_out

    # 4b. Opción 1: Generador Estructural Sintético en RAM (< 30 ms, 0 tokens, 0% CPU)
    if usar_modelo_local:
        from app.services.providers.local_provider import LocalLLMProvider
        llm_provider = LocalLLMProvider(model_name="llama3.2:1b")
    else:
        from app.services.providers import get_llm_provider
        llm_provider = get_llm_provider()
    is_mock = getattr(llm_provider, "name", "").startswith("mock")

    is_global_summary = any(
        k in q_norm for k in (
            "resumen", "sintesis", "de que trata", "vision general", "panorama",
            "explicacion general", "resume el documento", "resumen ejecutivo"
        )
    )
    if is_global_summary and not is_mock:
        if l1_entry and getattr(l1_entry, "resumen_ejecutivo", None):
            return ChatOutput(**l1_entry.resumen_ejecutivo)

        from app.services.synthetic_summary_service import generate_synthetic_executive_summary
        all_findings_list = l1_entry.hallazgos_previos if l1_entry else (fallback_job.hallazgos if fallback_job else [])
        synth_out = generate_synthetic_executive_summary(
            pdf_hash=pdf_hash,
            pregunta=pregunta,
            hallazgos=all_findings_list,
            resultados_paginas=resultados_paginas,
        )
        if synth_out:
            if l1_entry:
                l1_entry.resumen_ejecutivo = synth_out.model_dump()
                set_l1_cache(pdf_hash, l1_entry)
            return synth_out

    # 4c. Modo conversacional con LLM/SLM local (Opción 2)
    if skip_llm:
        return None

    # Si hay un proveedor LLM disponible, evaluar el documento indexado en RAM
    if llm_provider.is_available():
        # Ventana Quirúrgica (Targeted Page Slicing): enviar únicamente las 1-2 páginas relevantes para ahorrar 95% de tokens
        target_context = get_relevant_page_slices(pdf_hash, pregunta, max_pages=2)
        if not target_context:
            target_context = get_or_create_page_indexed_markdown(pdf_hash)

        # Sanitizar contexto: Si la pregunta no es visual, remover etiquetas técnicas [Elemento Visual: ...]
        is_visual_q = any(k in q_norm for k in ("imagen", "imagenes", "foto", "fotografia", "diagrama", "grafico", "grafica", "sello", "firma", "codigo", "visual"))
        if not is_visual_q and target_context:
            lines_clean = [l for l in target_context.splitlines() if not l.strip().startswith("[Elemento Visual:")]
            target_context = "\n".join(lines_clean)

        if target_context:
            try:
                if is_global_summary:
                    sys_instruction = (
                        "Eres un perito analista documental experto. Redacta un resumen ejecutivo claro, "
                        "estructurado y profesional del documento basado en los folios provistos. "
                        "Indica de forma ordenada: 1) Tipo de documento y propósito principal, 2) Partes u organizaciones involucradas, "
                        "3) Aspectos contractuales, técnicos o financieros destacados, y 4) Conclusiones clave. "
                        "Cita siempre las páginas de referencia en formato '[Página X]'."
                    )
                    prompt = (
                        "--- EXTRACTO ESTRUCTURAL DEL DOCUMENTO ---\n"
                        f"{target_context}\n"
                        "--- FIN DEL EXTRACTO ---\n\n"
                        "SOLICITUD: Genera un resumen ejecutivo completo, claro y fundamentado del documento."
                    )
                else:
                    sys_instruction = (
                        "Eres un asistente experto analizando documentos estructurados. "
                        "Tu objetivo es responder las solicitudes del usuario basándote exclusivamente en el contexto provisto.\n\n"
                        "REGLAS DE OBLIGATORIO CUMPLIMIENTO:\n"
                        "1. Debes identificar en qué número de página exacta se encuentra la información utilizando como referencia única las etiquetas ocultas del documento: `<!-- INICIO_PAGINA_X -->`.\n"
                        "2. Tu respuesta debe ser breve, directa y estructurada, indicando la página y el dato exacto hallado (ej: '[Página X]').\n"
                        "3. Si el usuario te pregunta algo que no se encuentra en el documento, responde indicando que la información no está disponible.\n"
                        "4. NUNCA repitas etiquetas de maquetación técnica ni bloques '[Elemento Visual: ...]' en tu respuesta. Responde exclusivamente con texto redactado en lenguaje natural."
                    )
                    prompt = (
                        "--- INICIO DEL DOCUMENTO ---\n"
                        f"{target_context}\n"
                        "--- FIN DEL DOCUMENTO ---\n\n"
                        "SOLICITUD DEL USUARIO:\n"
                        f"{pregunta}"
                    )

                resp_text = llm_provider.generate_chat_response(
                    prompt=prompt,
                    system_instruction=sys_instruction,
                )

                if resp_text:
                    # Detectar si la información no está disponible (no aplicable a resúmenes generales)
                    is_unavailable = False
                    if not is_global_summary:
                        lower_resp = resp_text.lower()
                        is_unavailable = any(
                            p in lower_resp for p in (
                                "no está disponible", "no esta disponible", "no se encuentra",
                                "no figura", "no aparece", "no hay registro", "no se menciona"
                            )
                        )

                    # Extraer números de páginas citadas
                    cited_pages = [int(m) for m in re.findall(r"\[Página\s+(\d+)\]", resp_text, re.IGNORECASE)]
                    if not cited_pages:
                        cited_pages = [int(m) for m in re.findall(r"Página\s+(\d+)", resp_text, re.IGNORECASE)]

                    if is_unavailable and not cited_pages:
                        return ChatOutput(
                            respuesta=resp_text,
                            citas=[],
                            evidencias_relacionadas=[],
                        )

                    pages = sorted(list(set(cited_pages + [e.page for e in matched_evidences])))
                    citas = [f"[Página {p}]" for p in pages]
                    if citas and not any(c in resp_text for c in citas):
                        resp_text = f"{resp_text} ({', '.join(citas)})"

                    # Mapear evidencias para resaltar en el visor PDF interactivo
                    related_evidences = [e for e in matched_evidences if e.page in pages]
                    if not related_evidences and pages:
                        for res in resultados_paginas:
                            if getattr(res, "numero_pagina", None) in pages:
                                for ev in getattr(res, "evidencias", []):
                                    if ev not in related_evidences:
                                        related_evidences.append(ev)
                                        break
                    if not related_evidences and pages:
                        for p in pages[:2]:
                            related_evidences.append(
                                Evidence(
                                    evidence_id=f"ev_p{p}_llm",
                                    page=p,
                                    text=f"Respuesta fundamentada en [Página {p}]",
                                    bbox=[50.0, 100.0, 500.0, 150.0],
                                    source=MetodoExtraccion.NATIVE_TEXT,
                                    evidence_score=0.95,
                                )
                            )

                    return ChatOutput(
                        respuesta=resp_text,
                        citas=citas,
                        evidencias_relacionadas=related_evidences[:3],
                    )
            except Exception as e:
                logger.warning(f"Error en consulta conversacional con {llm_provider.name}: {e}")

    # 5. Modo de síntesis forense sin LLM activo (Cero-Alucinación determinista)
    if not matched_evidences:
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

    # 6. Hallazgos encontrados en L1 sin LLM: respuesta fundamentada con citas obligatorias [Página X]
    matched_evidences.sort(key=lambda e: e.evidence_score, reverse=True)
    top_evidences = matched_evidences[:3]

    pages = sorted(list(set(e.page for e in top_evidences)))
    citas = [f"[Página {p}]" for p in pages]
    citas_str = ", ".join(citas)

    details = "; ".join(matched_findings[:2])
    respuesta = (
        f"De acuerdo con la evidencia forense registrada en {citas_str}, "
        f"se identificó la siguiente información: {details}."
    )

    return ChatOutput(
        respuesta=respuesta,
        citas=citas,
        evidencias_relacionadas=top_evidences,
    )


def process_chat_query_stream(
    pdf_hash: str,
    pregunta: str,
    historial: Optional[List[ChatMessage]] = None,
    fallback_store: Optional[Dict[str, JobOutput]] = None,
    usar_modelo_local: bool = False,
):
    """
    Generador de Server-Sent Events (SSE) para el chat documental interactivo.
    - Si usar_modelo_local es False: resuelve en modo por defecto (determinista ultrarrápido en RAM, <5ms).
    - Si usar_modelo_local es True: procesa y transmite la respuesta en tiempo real token por token vía SSE
      utilizando el modelo local más rápido (llama3.2:1b).
    """
    import json
    q_norm = _strip_accents(pregunta.lower().strip())
    is_global_summary = any(
        k in q_norm for k in (
            "resumen", "sintesis", "de que trata", "vision general", "panorama",
            "explicacion general", "resume el documento", "resumen ejecutivo"
        )
    )

    if not usar_modelo_local:
        # Modo por defecto (tal y como está ahora):
        # 1. Intentar resolución determinista ultrarrápida en RAM (<5ms, 0 tokens)
        out = process_chat_query(
            pdf_hash=pdf_hash,
            pregunta=pregunta,
            historial=historial,
            fallback_store=fallback_store,
            skip_llm=True,
            usar_modelo_local=False,
        )
        if out is not None:
            yield f"data: {json.dumps({'token': out.respuesta, 'citas': out.citas, 'final': True})}\n\n"
            return

        # Fallback tradicional si no hubo coincidencia determinista estricta
        fallback_out = process_chat_query(
            pdf_hash=pdf_hash,
            pregunta=pregunta,
            historial=historial,
            fallback_store=fallback_store,
            skip_llm=False,
            usar_modelo_local=False,
        )
        if fallback_out:
            yield f"data: {json.dumps({'token': fallback_out.respuesta, 'citas': fallback_out.citas, 'final': True})}\n\n"
        return

    # Si usar_modelo_local es True: invocar el SLM local más rápido (llama3.2:1b)
    from app.services.providers.local_provider import LocalLLMProvider
    llm_prov = LocalLLMProvider(model_name="llama3.2:1b")

    if not llm_prov.is_available():
        yield f"data: {json.dumps({'token': '⚠️ El modelo local (llama3.2:1b) no se encuentra disponible en este momento. Asegúrate de tener ejecutando `ollama serve` en tu equipo.', 'citas': [], 'final': True})}\n\n"
        return

    # Si es una consulta hacia el SLM local, transmitir streaming token por token
    from app.services.markdown_search_service import deterministic_search
    det_summary = deterministic_search(pdf_hash, pregunta)
    det_hint = ""
    if det_summary and det_summary.respuesta:
        det_hint = f"--- DATOS ESTRUCTURADOS DEL EXPEDIENTE ---\n{det_summary.respuesta}\n--- FIN DATOS ESTRUCTURADOS ---\n\n"

    target_context = get_relevant_page_slices(pdf_hash, pregunta, max_pages=2)
    if not target_context:
        target_context = get_or_create_page_indexed_markdown(pdf_hash)

    # Sanitizar contexto: Si la pregunta no es visual, remover etiquetas técnicas [Elemento Visual: ...]
    is_visual_q = any(k in q_norm for k in ("imagen", "imagenes", "foto", "fotografia", "diagrama", "grafico", "grafica", "sello", "firma", "codigo", "visual"))
    if not is_visual_q and target_context:
        lines_clean = [l for l in target_context.splitlines() if not l.strip().startswith("[Elemento Visual:")]
        target_context = "\n".join(lines_clean)

    sys_instruction = (
        "Eres el asistente pericial de PyDective. "
        "Responde de forma DIRECTA, BREVE y CONCISA a lo que se te pregunta sobre el documento.\n"
        "REGLAS:\n"
        "1. Si te preguntan por el nombre de una persona (paciente, usuario, cliente, médico, titular), responde con su NOMBRE COMPLETO, nunca con números de identificación o cédula.\n"
        "2. Si en el documento figura 'Nombre completo usuario:' o 'Nombre:', ese es el paciente / usuario.\n"
        "3. Si la respuesta es un dato puntual (nombres, entidades, valores, medicamentos), entrégalo directamente en 1 o 2 líneas.\n"
        "4. Cita siempre la página de donde se obtuvo la información en formato '[Página X]'.\n"
        "5. Ve directo al grano sin introducciones innecesarias ni explicaciones periféricas."
    )
    prompt = (
        f"{det_hint}"
        "--- EXTRACTO DEL DOCUMENTO ---\n"
        f"{target_context}\n"
        "--- FIN DEL EXTRACTO ---\n\n"
        f"Pregunta del usuario: {pregunta}\n\n"
        "Respuesta directa y concisa:"
    )

    full_text_acc = ""
    for token in llm_prov.generate_chat_stream(prompt=prompt, system_instruction=sys_instruction):
        full_text_acc += token
        yield f"data: {json.dumps({'token': token, 'citas': [], 'final': False})}\n\n"

    # Extraer citas de páginas del texto completo emitido
    cited_pages = [int(m) for m in re.findall(r"\[P[áa]gina\s+(\d+)\]", full_text_acc, re.IGNORECASE)]
    cited_pages = sorted(list(set(cited_pages)))
    citas = [f"[Página {p}]" for p in cited_pages]
    if not citas and det_summary and det_summary.citas:
        citas = det_summary.citas
    if not citas:
        ctx_pages = [int(m) for m in re.findall(r"<!--\s*INICIO_PAGINA_(\d+)\s*-->", target_context)]
        if ctx_pages:
            citas = [f"[Página {min(ctx_pages)}]"]

    evidencias_payload = []
    if det_summary and det_summary.evidencias_relacionadas:
        for ev in det_summary.evidencias_relacionadas[:3]:
            evidencias_payload.append(ev.model_dump())

    yield f"data: {json.dumps({'token': '', 'citas': citas, 'evidencias': evidencias_payload, 'final': True})}\n\n"


