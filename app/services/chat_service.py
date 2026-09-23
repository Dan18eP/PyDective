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


def _search_visual_elements(resultados_por_pagina: List[Any], query_norm: str) -> Tuple[List[str], List[Evidence], str]:
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

            if matched:
                if p_num not in found_pages:
                    found_pages.append(p_num)
                evidencias.append(
                    Evidence(
                        evidence_id=f"ev_vis_p{p_num}_{v.id_imagen}",
                        page=p_num,
                        text=f"Elemento visual detectado: {item_type} en bbox {v.bbox}",
                        bbox=v.bbox,
                        source=MetodoExtraccion.VISUAL_AI,
                        evidence_score=0.96,
                    )
                )

    if found_pages:
        found_pages.sort()
        citas = [f"[Página {p}]" for p in found_pages]
        citas_str = ", ".join(citas)
        descripcion = f"Sí, el documento cuenta con {item_type} verificado e inventariado en {citas_str}."

    return citas, evidencias, descripcion


def process_chat_query(
    pdf_hash: str,
    pregunta: str,
    historial: List[ChatMessage] = [],
    fallback_store: Optional[Dict[str, Any]] = None,
) -> ChatOutput:
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
        raise DocumentoNoEncontradoOExpiradoError(pdf_hash)

    q_norm = normalize_parameter(pregunta)
    q_tokens = [t for t in q_norm.split() if len(t) > 2]
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

    # 2. Inspeccionar elementos visuales (códigos de barras, QR, firmas, sellos, fotos)
    vis_citas, vis_evidencias, vis_desc = _search_visual_elements(resultados_paginas, q_norm)
    if vis_citas:
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

    # 4. Si hay API key de Gemini configurada, sintetizar respuesta natural enriquecida
    active_key = settings.api_keys_list[0] if settings.api_keys_list else None
    if active_key and genai is not None:
        try:
            client = genai.Client(api_key=active_key)
            context_summary = f"Total páginas del documento: {total_pages}.\n"
            if matched_findings:
                context_summary += f"Hallazgos relevantes extraídos: {'; '.join(matched_findings)}.\n"
            if available_params:
                context_summary += f"Parámetros conocidos en el documento: {', '.join(set(available_params))}.\n"

            prompt = (
                "Eres el asistente forense documental de PyDective. "
                "Responde en español de forma fluida, precisa y profesional a la siguiente pregunta del usuario, "
                "basándote exclusivamente en el contexto documental proporcionado.\n"
                "REGLAS OBLIGATORIAS:\n"
                "1. Si el dato existe, cítalo con la página exacta como [Página X].\n"
                "2. Si el dato NO figura en el documento, indícalo de forma clara y amable indicando que no figura registrado, sin repetir la pregunta literalmente.\n"
                f"Contexto: {context_summary}\n"
                f"Pregunta: {pregunta}"
            )
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[prompt],
            )
            if response and response.text:
                pages = sorted(list(set(e.page for e in matched_evidences))) if matched_evidences else []
                citas = [f"[Página {p}]" for p in pages]
                return ChatOutput(
                    respuesta=response.text.strip(),
                    citas=citas,
                    evidencias_relacionadas=matched_evidences[:3],
                )
        except Exception as e:
            logger.warning(f"Fallback a síntesis local tras error en Gemini Chat: {e}")

    # 5. Modo de síntesis local: Si no se encontró evidencia, declinación natural y fluida
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

    # 6. Hallazgos encontrados: respuesta fundamentada con citas obligatorias [Página X]
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
