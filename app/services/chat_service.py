from typing import List, Optional, Dict, Any
import logging

from app.domain.models import ChatInput, ChatOutput, ChatMessage, Evidence
from app.domain.errors import DocumentoNoEncontradoOExpiradoError
from app.domain.enums import MetodoExtraccion
from app.services.cache_service import get_l1_cache
from app.services.semantic_extraction_service import normalize_parameter

logger = logging.getLogger("pydective.chat")


def process_chat_query(
    pdf_hash: str,
    pregunta: str,
    historial: List[ChatMessage] = [],
    fallback_store: Optional[Dict[str, Any]] = None,
) -> ChatOutput:
    """
    Procesa una consulta en lenguaje natural sobre el documento analizado (US-23).
    Aplica:
    1. Verificación de existencia del documento en L1 o store; si no existe, 404 (US-23 Escenario 3).
    2. Retrieval asociativo previo sobre L1 (ahorro de tokens y latencia < 600ms) (US-23 Escenario 1).
    3. Citas obligatorias [Página X] enlazadas a Evidence y declinación ante datos ausentes (US-23 Escenario 2).
    """
    l1_entry = get_l1_cache(pdf_hash)
    fallback_job = fallback_store.get(pdf_hash) if fallback_store else None

    if l1_entry is None and fallback_job is None:
        raise DocumentoNoEncontradoOExpiradoError(pdf_hash)

    q_norm = normalize_parameter(pregunta)
    q_tokens = [t for t in q_norm.split() if len(t) > 2]

    # Recopilar candidatos de evidencia de L1 o fallback
    matched_evidences: List[Evidence] = []
    matched_findings: List[str] = []

    # 1. Buscar en índice asociativo de L1 si está disponible
    if l1_entry:
        for param, ev_list in l1_entry.indice_asociativo.items():
            param_norm = normalize_parameter(param)
            if any(t in param_norm for t in q_tokens) or any(param_norm in t for t in q_tokens):
                for ev in ev_list:
                    if ev not in matched_evidences:
                        matched_evidences.append(ev)
                        matched_findings.append(f"{param}: {ev.text}")

        for h in l1_entry.hallazgos_previos:
            h_norm = normalize_parameter(h.parametro)
            if any(t in h_norm for t in q_tokens) or any(h_norm in t for t in q_tokens):
                for ev in h.evidencias:
                    if ev not in matched_evidences:
                        matched_evidences.append(ev)
                        matched_findings.append(f"{h.parametro}: {h.valor}")

    elif fallback_job:
        for h in fallback_job.hallazgos:
            h_norm = normalize_parameter(h.parametro)
            if any(t in h_norm for t in q_tokens) or any(h_norm in t for t in q_tokens):
                for ev in h.evidencias:
                    if ev not in matched_evidences:
                        matched_evidences.append(ev)
                        matched_findings.append(f"{h.parametro}: {h.valor}")

    # Escenario 2: Declinación explícita ante datos ausentes sin alucinación
    if not matched_evidences:
        return ChatOutput(
            respuesta=f"El dato o concepto consultado ('{pregunta}') no figura registrado en ninguna de las páginas del documento analizado.",
            citas=[],
            evidencias_relacionadas=[],
        )

    # Ordenar evidencias por score
    matched_evidences.sort(key=lambda e: e.evidence_score, reverse=True)
    top_evidences = matched_evidences[:3]

    # Construir citas obligatorias únicas ordenadas
    pages = sorted(list(set(e.page for e in top_evidences)))
    citas = [f"[Página {p}]" for p in pages]

    # Sintetizar respuesta fundamentada
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
