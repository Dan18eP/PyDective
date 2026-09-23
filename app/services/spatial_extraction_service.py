import re
import math
import unicodedata
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime
import pymupdf

from app.domain.enums import MetodoExtraccion, TipoEntidad
from app.domain.models import Evidence, HallazgoEnriquecido
from app.services.semantic_extraction_service import (
    normalize_parameter,
    expand_parameter_synonyms,
)

SPANISH_MONTHS = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "setiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}


def normalize_currency_amount(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Normaliza montos económicos hispanos y anglosajones (US-09 Escenario 1).
    Detecta símbolos/códigos de moneda y emite el valor numérico en formato decimal estándar ("12500000.50").
    
    Ejemplos:
        "$ 12.500.000,50 COP" -> ("12500000.50", "COP")
        "USD 4,500.00"       -> ("4500.00", "USD")
        "$ 8.050.000 COP"     -> ("8050000.00", "COP")
        "$3.200.000"          -> ("3200000.00", "COP")
    """
    if not text:
        return None, None

    # Detectar divisa
    currency = "COP"
    upper = text.upper()
    if "USD" in upper or "DOLARES" in upper or "DÓLARES" in upper:
        currency = "USD"
    elif "EUR" in upper or "EUROS" in upper or "€" in text:
        currency = "EUR"
    elif "COP" in upper or "PESOS" in upper:
        currency = "COP"

    # Ignorar si el texto es claramente una fecha (ej. 2026-04-15 o 15/04/2026)
    if re.search(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", text) or re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b", text):
        return None, None

    # Extraer el bloque numérico más significativo
    # Permite dígitos, puntos y comas
    match = re.search(r"(\d[\d\.,\s]*\d|\d+)", text)
    if not match:
        return None, None

    raw_num = match.group(1).replace(" ", "")

    # Decidir si los separadores son formato hispano (1.250.000,50) o anglosajón (1,250,000.50)
    if "," in raw_num and "." in raw_num:
        last_comma = raw_num.rfind(",")
        last_dot = raw_num.rfind(".")
        if last_comma > last_dot:
            # Hispano: puntos de miles, coma de decimal
            clean_num = raw_num.replace(".", "").replace(",", ".")
        else:
            # Anglosajón: comas de miles, punto de decimal
            clean_num = raw_num.replace(",", "")
    elif "," in raw_num:
        # Solo coma: si tiene 2 dígitos al final es decimal, si tiene 3 dígitos es miles
        parts = raw_num.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            clean_num = f"{parts[0]}.{parts[1]}"
        else:
            clean_num = raw_num.replace(",", "") + ".00"
    elif "." in raw_num:
        # Solo puntos: si tiene 2 dígitos tras el último punto es decimal, si tiene 3 dígitos es miles
        parts = raw_num.split(".")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            clean_num = f"{parts[0]}.{parts[1]}"
        else:
            clean_num = raw_num.replace(".", "") + ".00"
    else:
        clean_num = f"{raw_num}.00"

    try:
        val_float = float(clean_num)
        return f"{val_float:.2f}", currency
    except ValueError:
        return None, None


def normalize_date_string(text: str) -> Optional[str]:
    """
    Normaliza fechas hispanas y estándar a formato ISO-8601 (YYYY-MM-DD) (US-09 Escenario 2).
    
    Ejemplos:
        "15/04/2026" -> "2026-04-15"
        "2026-04-15" -> "2026-04-15"
        "22 de mayo de 2026" -> "2026-05-22"
    """
    if not text:
        return None

    cleaned = text.strip()

    # 1. ISO format: YYYY-MM-DD
    iso_match = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", cleaned)
    if iso_match:
        y, m, d = iso_match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # 2. Formato latino: DD/MM/YYYY o DD-MM-YYYY
    lat_match = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", cleaned)
    if lat_match:
        d, m, y = lat_match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # 3. Formato textual: "15 de abril de 2026"
    text_match = re.search(
        r"\b(\d{1,2})\s+de\s+([a-zA-ZáéíóúÁÉÍÓÚ]+)\s+de\s+(\d{4})\b",
        cleaned,
        re.IGNORECASE,
    )
    if text_match:
        d, month_name, y = text_match.groups()
        m_norm = unicodedata.normalize("NFKD", month_name).encode("ASCII", "ignore").decode().lower()
        if m_norm in SPANISH_MONTHS:
            m = SPANISH_MONTHS[m_norm]
            return f"{int(y):04d}-{m}-{int(d):02d}"

    return None


def normalize_tax_id(text: str) -> Optional[str]:
    """
    Normaliza números de identificación tributaria (NIT/RUT).
    Ejemplo: "900.543.210-8" -> "900543210-8"
    """
    if not text:
        return None
    match = re.search(r"(\d[\d\.\s]*-\s*\d|\d{8,11})", text)
    if match:
        clean = re.sub(r"[\.\s]", "", match.group(1))
        return clean
    return None


def extract_kwic_context(full_page_text: str, match_text: str, max_chars: int = 240) -> str:
    """
    Extrae la oración forense completa que rodea a la coincidencia (KWIC) (US-10 Escenario 1).
    Delimitada por puntos ortográficos o saltos de párrafo dobles.
    """
    if not full_page_text or not match_text:
        return match_text or ""

    idx = full_page_text.lower().find(match_text.lower())
    if idx == -1:
        return match_text

    # Buscar inicio de oración hacia atrás
    start_idx = 0
    for p in range(idx - 1, -1, -1):
        if full_page_text[p] in (".", "\n") and (p + 1 < len(full_page_text) and full_page_text[p+1] in (" ", "\n")):
            start_idx = p + 1
            break

    # Buscar fin de oración hacia adelante
    end_idx = len(full_page_text)
    for p in range(idx + len(match_text), len(full_page_text)):
        if full_page_text[p] in (".", "\n") and (p + 1 == len(full_page_text) or full_page_text[p+1] in (" ", "\n")):
            end_idx = p + 1
            break

    sentence = full_page_text[start_idx:end_idx].strip()
    sentence_clean = re.sub(r"\s+", " ", sentence)

    if len(sentence_clean) > max_chars:
        return sentence_clean[:max_chars] + "..."
    return sentence_clean


def extract_spatial_key_values(
    page: pymupdf.Page,
    canonical_params: List[str],
) -> List[HallazgoEnriquecido]:
    """
    Extrae entidades y pares clave-valor de una página digital mediante geometría espacial en Cero-IA (O(N))
    (US-07, US-08, US-09, US-10).
    
    Aplica:
    - Búsqueda de palabra clave con tolerancia a kerning apretado (Paso 1 límites de palabra, Paso 2 subcadena).
    - Exploración en vector horizontal derecho: |Δy| <= 8 pt, Δx <= 180 pt.
    - Exploración en vector vertical descendente: Δy <= 35 pt, solapamiento horizontal >= 60%.
    - Construcción de Evidence con bbox exacto y evidence_score determinista.
    - Normalización de entidades tipificadas (monedas, fechas ISO-8601, tax IDs).
    """
    page_num = page.number + 1
    page_text = page.get_text()
    raw_words = page.get_text("words")
    # raw_words tuples: (x0, y0, x1, y1, word, block_no, line_no, word_no)

    hallazgos: List[HallazgoEnriquecido] = []
    evidence_counter = 0

    for param in canonical_params:
        synonyms = expand_parameter_synonyms(param)
        found_for_param = False

        # 1. Chequeo de kerning apretado dentro de un mismo token (ej. "Total:1200000" o "NIT:900123")
        for i, w in enumerate(raw_words):
            raw_token = w[4]
            if ":" in raw_token:
                parts = raw_token.split(":", 1)
                prefix_norm = normalize_parameter(parts[0])
                val_candidate = parts[1].strip()
                if prefix_norm in synonyms and val_candidate:
                    evidence_counter += 1
                    ev_id = f"ev_p{page_num}_{evidence_counter:03d}"

                    norm_curr, curr_code = normalize_currency_amount(val_candidate)
                    norm_date = normalize_date_string(val_candidate)
                    norm_tax = normalize_tax_id(val_candidate)

                    if norm_curr:
                        val_norm = norm_curr
                        fmt = curr_code
                    elif norm_date:
                        val_norm = norm_date
                        fmt = "ISO-8601"
                    elif norm_tax:
                        val_norm = norm_tax
                        fmt = "NIT"
                    else:
                        val_norm = val_candidate
                        fmt = "TEXT"

                    kwic_ctx = extract_kwic_context(page_text, val_candidate)
                    tipo_ent = "moneda" if fmt in ("COP", "USD", "EUR") else ("fecha" if fmt == "ISO-8601" else ("nit" if fmt == "NIT" else "texto"))
                    evidence = Evidence(
                        evidence_id=ev_id,
                        page=page_num,
                        text=f"{param.upper()}: {val_candidate}",
                        bbox=[round(w[0], 2), round(w[1], 2), round(w[2], 2), round(w[3], 2)],
                        source=MetodoExtraccion.SPATIAL_VECTOR,
                        evidence_score=0.96,
                        kwic_snippet=kwic_ctx,
                    )
                    hallazgos.append(
                        HallazgoEnriquecido(
                            parametro=param,
                            valor=val_candidate,
                            confianza=0.96,
                            metodo=MetodoExtraccion.SPATIAL_VECTOR,
                            evidencias=[evidence],
                            valor_normalizado=val_norm,
                            formato_detectado=fmt,
                            tipo_entidad=tipo_ent,
                            divisa=curr_code if norm_curr else None,
                            kwic_context=kwic_ctx,
                        )
                    )
                    found_for_param = True
                    break

        if found_for_param:
            continue

        param_candidates: List[HallazgoEnriquecido] = []

        for syn in synonyms:
            syn_norm = normalize_parameter(syn)
            if not syn_norm:
                continue

            syn_tokens = syn_norm.split()
            candidate_key_boxes = []

            for i, w in enumerate(raw_words):
                w_norm = normalize_parameter(w[4]).strip(":-_.,")
                if w_norm == syn_tokens[0] or (len(syn_tokens[0]) > 4 and syn_tokens[0] in w_norm):
                    matched = True
                    last_idx = i
                    if len(syn_tokens) > 1:
                        for k in range(1, len(syn_tokens)):
                            if i + k < len(raw_words):
                                next_w_norm = normalize_parameter(raw_words[i + k][4]).strip(":-_.,")
                                if next_w_norm != syn_tokens[k] and (len(syn_tokens[k]) <= 4 or syn_tokens[k] not in next_w_norm):
                                    matched = False
                                    break
                                last_idx = i + k
                            else:
                                matched = False
                                break

                    if matched:
                        k_x0 = w[0]
                        k_y0 = min(raw_words[j][1] for j in range(i, last_idx + 1))
                        k_x1 = raw_words[last_idx][2]
                        k_y1 = max(raw_words[j][3] for j in range(i, last_idx + 1))
                        candidate_key_boxes.append((k_x0, k_y0, k_x1, k_y1, last_idx))

            # Exploración espacial para cada clave candidata encontrada
            for k_x0, k_y0, k_x1, k_y1, last_w_idx in candidate_key_boxes:
                # 3a. Vector horizontal derecho: misma línea (|Δy| <= 8 pt, Δx <= 180 pt)
                right_words = []
                for w in raw_words:
                    k_y_center = (k_y0 + k_y1) / 2
                    w_y_center = (w[1] + w[3]) / 2
                    if abs(w_y_center - k_y_center) <= 8.0:
                        dx = w[0] - k_x1
                        if 0.0 < dx <= 180.0:
                            right_words.append(w)

                found_right = False
                if right_words:
                    right_words.sort(key=lambda item: item[0])
                    val_text = " ".join([w[4] for w in right_words]).strip()
                    if val_text.startswith(":"):
                        val_text = val_text[1:].strip()
                    if ":" in val_text:
                        after_colon = val_text.split(":", 1)[1].strip()
                        if after_colon:
                            val_text = after_colon
                    if "·" in val_text:
                        first_chunk = val_text.split("·")[0].strip()
                        if normalize_tax_id(first_chunk) or normalize_currency_amount(first_chunk)[0] or normalize_date_string(first_chunk):
                            val_text = first_chunk

                    # Descartar unidades de encabezado de tabla como (COP)
                    if val_text and val_text.lower() not in ("(cop)", "(usd)", "(eur)", ":", "-"):
                        found_right = True
                        v_x0 = right_words[0][0]
                        v_y0 = min(w[1] for w in right_words)
                        v_x1 = right_words[-1][2]
                        v_y1 = max(w[3] for w in right_words)

                        evidence_counter += 1
                        ev_id = f"ev_p{page_num}_{evidence_counter:03d}"

                        dist = math.sqrt((v_x0 - k_x1) ** 2 + ((v_y0 - k_y0) ** 2))
                        penalizacion_dist = min(0.30, dist / 300.0)
                        # Bonificación por vector horizontal explícito (más específico que columna de tabla)
                        base_h = 1.0 - penalizacion_dist + 0.08
                        if raw_words[last_w_idx][4].endswith(":"):
                            base_h += 0.05
                        score = round(max(0.50, min(1.0, base_h)), 2)

                        norm_curr, curr_code = normalize_currency_amount(val_text)
                        norm_date = normalize_date_string(val_text)
                        norm_tax = normalize_tax_id(val_text)

                        if norm_date:
                            val_norm = norm_date
                            fmt = "ISO-8601"
                            score = min(1.0, score + 0.05)
                        elif norm_tax and any(k in param for k in ("nit", "rut", "cuit", "cedula", "identificacion")):
                            val_norm = norm_tax
                            fmt = "NIT"
                            score = min(1.0, score + 0.05)
                        elif norm_curr:
                            val_norm = norm_curr
                            fmt = curr_code
                            score = min(1.0, score + 0.05)
                        elif norm_tax:
                            val_norm = norm_tax
                            fmt = "NIT"
                            score = min(1.0, score + 0.05)
                        else:
                            val_norm = val_text
                            fmt = "TEXT"

                        kwic_ctx = extract_kwic_context(page_text, val_text)
                        tipo_ent = "moneda" if fmt in ("COP", "USD", "EUR") else ("fecha" if fmt == "ISO-8601" else ("nit" if fmt == "NIT" else "texto"))

                        evidence = Evidence(
                            evidence_id=ev_id,
                            page=page_num,
                            text=f"{param.upper()}: {val_text}",
                            bbox=[round(v_x0, 2), round(v_y0, 2), round(v_x1, 2), round(v_y1, 2)],
                            source=MetodoExtraccion.SPATIAL_VECTOR,
                            evidence_score=score,
                            kwic_snippet=kwic_ctx,
                        )

                        param_candidates.append(
                            HallazgoEnriquecido(
                                parametro=param,
                                valor=val_text,
                                confianza=score,
                                metodo=MetodoExtraccion.SPATIAL_VECTOR,
                                evidencias=[evidence],
                                valor_normalizado=val_norm,
                                formato_detectado=fmt,
                                tipo_entidad=tipo_ent,
                                divisa=curr_code if norm_curr else None,
                                kwic_context=kwic_ctx,
                            )
                        )

                # 3b. Vector vertical descendente (solo cuando NO hay contenido a la derecha, US-07 Escenario 2)
                if not found_right:
                    down_words = []
                    for w in raw_words:
                        dy = w[1] - k_y1
                        if 0.0 < dy <= 35.0:
                            # Ignorar otras etiquetas o dos puntos aislados
                            if w[4].endswith(":") or w[4].upper() in ("IVA", "TOTAL", "SUBTOTAL", "NIT", "FECHA"):
                                continue
                            overlap_x = max(0.0, min(k_x1, w[2]) - max(k_x0, w[0]))
                            w_width = w[2] - w[0]
                            k_width = k_x1 - k_x0
                            if min(w_width, k_width) > 0:
                                overlap_ratio = overlap_x / min(w_width, k_width)
                                if overlap_ratio >= 0.40 or (w[0] >= k_x0 - 15 and w[2] <= k_x1 + 60):
                                    down_words.append(w)

                    if down_words:
                        down_words.sort(key=lambda item: item[0])
                        val_text = " ".join([w[4] for w in down_words]).strip()
                        if val_text.startswith(":"):
                            val_text = val_text[1:].strip()
                        if ":" in val_text:
                            after_colon = val_text.split(":", 1)[1].strip()
                            if after_colon:
                                val_text = after_colon
                        if "·" in val_text:
                            first_chunk = val_text.split("·")[0].strip()
                            if normalize_tax_id(first_chunk) or normalize_currency_amount(first_chunk)[0] or normalize_date_string(first_chunk):
                                val_text = first_chunk
                        if val_text and val_text.lower() not in ("(cop)", "(usd)", "(eur)", ":", "-"):
                            v_x0 = down_words[0][0]
                            v_y0 = min(w[1] for w in down_words)
                            v_x1 = down_words[-1][2]
                            v_y1 = max(w[3] for w in down_words)

                            evidence_counter += 1
                            ev_id = f"ev_p{page_num}_{evidence_counter:03d}"

                            dist = math.sqrt((v_x0 - k_x0) ** 2 + ((v_y0 - k_y1) ** 2))
                            penalizacion_dist = min(0.30, dist / 250.0)
                            score = round(max(0.50, min(1.0, 0.95 - penalizacion_dist)), 2)

                            norm_curr, curr_code = normalize_currency_amount(val_text)
                            norm_date = normalize_date_string(val_text)
                            norm_tax = normalize_tax_id(val_text)

                            if norm_date:
                                val_norm = norm_date
                                fmt = "ISO-8601"
                                score = min(1.0, score + 0.05)
                            elif norm_tax and any(k in param for k in ("nit", "rut", "cuit", "cedula", "identificacion")):
                                val_norm = norm_tax
                                fmt = "NIT"
                                score = min(1.0, score + 0.05)
                            elif norm_curr:
                                val_norm = norm_curr
                                fmt = curr_code
                                score = min(1.0, score + 0.05)
                            elif norm_tax:
                                val_norm = norm_tax
                                fmt = "NIT"
                                score = min(1.0, score + 0.05)
                            else:
                                val_norm = val_text
                                fmt = "TEXT"

                            kwic_ctx = extract_kwic_context(page_text, val_text)
                            tipo_ent = "moneda" if fmt in ("COP", "USD", "EUR") else ("fecha" if fmt == "ISO-8601" else ("nit" if fmt == "NIT" else "texto"))

                            evidence = Evidence(
                                evidence_id=ev_id,
                                page=page_num,
                                text=f"{param.upper()}: {val_text}",
                                bbox=[round(v_x0, 2), round(v_y0, 2), round(v_x1, 2), round(v_y1, 2)],
                                source=MetodoExtraccion.SPATIAL_VECTOR,
                                evidence_score=score,
                                kwic_snippet=kwic_ctx,
                            )

                            param_candidates.append(
                                HallazgoEnriquecido(
                                    parametro=param,
                                    valor=val_text,
                                    confianza=score,
                                    metodo=MetodoExtraccion.SPATIAL_VECTOR,
                                    evidencias=[evidence],
                                    valor_normalizado=val_norm,
                                    formato_detectado=fmt,
                                    tipo_entidad=tipo_ent,
                                    divisa=curr_code if norm_curr else None,
                                    kwic_context=kwic_ctx,
                                )
                            )

        # Seleccionar el mejor candidato para este parámetro:
        # Priorizar aquellos que lograron normalización de entidad (moneda, fecha, nit)
        if param_candidates:
            param_candidates.sort(
                key=lambda c: (
                    1 if c.formato_detectado in ("COP", "USD", "EUR", "ISO-8601", "NIT") else 0,
                    c.confianza,
                ),
                reverse=True,
            )
            hallazgos.append(param_candidates[0])
    return hallazgos


def consolidate_findings(
    native_findings: List[HallazgoEnriquecido],
    ai_findings: List[HallazgoEnriquecido],
) -> List[HallazgoEnriquecido]:
    """
    Resuelve conflictos de extracción entre texto espacial determinista y visión IA (US-10 Escenario 2).
    
    Regla de precedencia absoluta:
    - Si el hallazgo proviene de texto vectorial nativo con alta certeza (confianza >= 0.70),
      prevalece de forma estricta e inmutable el dato determinista de PyMuPDF.
    - La respuesta de IA solo se adopta si no hay dato determinista o si la confianza nativa es deficiente.
    """
    native_map = {f.parametro: f for f in native_findings}
    consolidated: List[HallazgoEnriquecido] = []

    # Incluir todos los hallazgos nativos deterministas
    for f in native_findings:
        consolidated.append(f)

    # Evaluar hallazgos de IA
    for ai_f in ai_findings:
        if ai_f.parametro in native_map:
            existing = native_map[ai_f.parametro]
            # Si el nativo tiene buena confianza, se descarta la IA
            if existing.confianza >= 0.70:
                continue
            else:
                # Reemplazar por IA si el nativo es débil
                consolidated = [f for f in consolidated if f.parametro != ai_f.parametro]
                consolidated.append(ai_f)
        else:
            consolidated.append(ai_f)

    return consolidated
