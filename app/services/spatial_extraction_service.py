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

    # Ignorar si el número va acompañado de unidades no monetarias (ej. 120TB, 50km, 20m2, 12 meses, 48 horas)
    if re.search(r"\d+\s*(tb|gb|mb|kb|km|m2|kg|horas|dias|días|meses|anos|años|paginas|páginas|folios|unidades|uds)\b", text, re.IGNORECASE):
        return None, None

    has_explicit_currency = any(c in upper for c in ("$", "COP", "USD", "EUR", "€", "PESOS", "DOLARES", "DÓLARES"))

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
    iso_match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", cleaned)
    if iso_match:
        y, m, d = iso_match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # 2. Formato latino: DD/MM/YYYY o DD-MM-YYYY
    lat_match = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", cleaned)
    if lat_match:
        d, m, y = lat_match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # 3. Formato textual: "15 de abril de 2026"
    text_match = re.search(
        r"(\d{1,2})\s+de\s+([a-zA-ZáéíóúÁÉÍÓÚ]+)\s+de\s+(\d{4})",
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
    Normaliza números de identificación tributaria (NIT/RUT) o cédulas (CC).
    Ejemplo: "900.543.210-8" -> "900543210-8", "32.848.952" -> "32848952"
    """
    if not text:
        return None
    match = re.search(r"(\d[\d\.\s]*-\s*\d|\b\d{7,11}\b)", text)
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


def extract_legal_party_clauses(
    page: pymupdf.Page,
    canonical_params: List[str],
    evidence_start_idx: int = 100,
) -> List[HallazgoEnriquecido]:
    """
    Extrae entidades contractuales y partes en documentos jurídicos mediante análisis
    de cláusulas introductorias y fórmulas notariales hispanas (ej. 'quien en adelante se denominará EL ARRENDADOR'
    o 'representada legalmente por VALERIA MONTOYA DUQUE').
    Genera Evidence con bounding boxes exactos calculados vía search_for en PyMuPDF.
    """
    page_num = page.number + 1
    raw_text = page.get_text()
    if not raw_text:
        return []

    # Desplegar saltos de línea de maquetación (soft line breaks) a espacios dentro de párrafos
    clean_text = re.sub(r"([^\.\n;])\n([^\n])", r"\1 \2", raw_text)

    # Identificar cláusulas separadas por punto y coma, salto de párrafo o puntos seguidos de mayúscula
    clauses = [c.strip() for c in re.split(r"[;\n]|\.\s+(?=[A-Z])", clean_text) if c.strip()]

    legal_findings: List[HallazgoEnriquecido] = []
    ev_counter = evidence_start_idx

    party_params = [
        p for p in canonical_params
        if any(k in p for k in ("arrendador", "arrendatario", "representante", "contratante", "contratista", "comprador", "vendedor", "cliente", "proveedor", "perito", "notario"))
    ]
    if not party_params:
        return []

    for cl in clauses:
        # A. Fórmulas de denominación: 'quien en adelante se denominará (el/la) ROL'
        denom_match = re.search(
            r"quien(?:es)?\s+en\s+adelante\s+se\s+denominar[aá](?:n)?\s+(?:el\s+|la\s+|los\s+|las\s+|el/la\s+)?([A-ZÁÉÍÓÚÑa-záéíóúñ]+)",
            cl,
            re.IGNORECASE,
        )
        if denom_match:
            detected_role = normalize_parameter(denom_match.group(1))
            target_param = None
            for p in party_params:
                syns = expand_parameter_synonyms(p)
                if any(normalize_parameter(s) == detected_role or detected_role in normalize_parameter(s) for s in syns):
                    target_param = p
                    break

            if target_param:
                pre_text = cl[:denom_match.start()].strip()
                pre_text = re.sub(
                    r"^.*?\b(?:entre\s+los\s+suscritos\s+a\s+saber,?\s*)?(?:de\s+una\s+parte|por\s+una\s+parte|de\s+otra\s+parte|de\s+la\s+otra\s+parte|por\s+la\s+otra\s+parte)\s*,?\s*",
                    "",
                    pre_text,
                    flags=re.IGNORECASE,
                ).strip()
                name_tokens = re.split(
                    r",\s*(?:mayor\s+de\s+edad|con\s+nit|con\s+c[eé]dula|identificad[oa]|representad[oa]|domiciliad[oa]|vecin[oa])\b",
                    pre_text,
                    flags=re.IGNORECASE,
                )
                entity_val = name_tokens[0].strip().strip(":,")
                if entity_val and len(entity_val) >= 3 and entity_val.upper() not in ("LA", "EL", "UN", "UNA", "POR"):
                    search_snippet = " ".join(entity_val.split()[:3])
                    rects = page.search_for(search_snippet)
                    if rects:
                        r = rects[0]
                        bbox = [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]
                    else:
                        bbox = [50.0, 100.0, 300.0, 120.0]

                    ev_counter += 1
                    ev_id = f"ev_p{page_num}_{ev_counter:03d}"
                    kwic = extract_kwic_context(raw_text, entity_val)
                    evidence = Evidence(
                        evidence_id=ev_id,
                        page=page_num,
                        text=f"{target_param.upper()}: {entity_val}",
                        bbox=bbox,
                        source=MetodoExtraccion.SPATIAL_VECTOR,
                        evidence_score=0.98,
                        kwic_snippet=kwic,
                    )
                    legal_findings.append(
                        HallazgoEnriquecido(
                            parametro=target_param,
                            valor=entity_val,
                            confianza=0.98,
                            metodo=MetodoExtraccion.SPATIAL_VECTOR,
                            evidencias=[evidence],
                            valor_normalizado=entity_val,
                            formato_detectado="TEXT",
                            tipo_entidad="persona",
                            divisa=None,
                            kwic_context=kwic,
                        )
                    )

        # B. Fórmulas de representación legal: 'representada legalmente por NOMBRE'
        rep_match = re.search(
            r"representad[oa]\s+(?:legalmente\s+)?por\s+([A-ZÁÉÍÓÚÑa-záéíóúñ\s\.]+?)(?=,\s*(?:mayor|con\s+c[eé]dula|identificad|quien)|$)",
            cl,
            re.IGNORECASE,
        )
        if rep_match:
            rep_param = None
            for p in party_params:
                if "representante" in p or "apoderado" in p:
                    rep_param = p
                    break

            if rep_param:
                rep_val = rep_match.group(1).strip().strip(":,")
                rep_val = re.sub(r"\s+", " ", rep_val)
                if rep_val and len(rep_val) >= 3 and rep_val.upper() not in ("LA", "EL", "UN", "UNA", "POR"):
                    search_snippet = " ".join(rep_val.split()[:3])
                    rects = page.search_for(search_snippet)
                    if rects:
                        r = rects[0]
                        bbox = [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]
                    else:
                        bbox = [50.0, 100.0, 300.0, 120.0]

                    ev_counter += 1
                    ev_id = f"ev_p{page_num}_{ev_counter:03d}"
                    kwic = extract_kwic_context(raw_text, rep_val)
                    evidence = Evidence(
                        evidence_id=ev_id,
                        page=page_num,
                        text=f"{rep_param.upper()}: {rep_val}",
                        bbox=bbox,
                        source=MetodoExtraccion.SPATIAL_VECTOR,
                        evidence_score=0.98,
                        kwic_snippet=kwic,
                    )
                    legal_findings.append(
                        HallazgoEnriquecido(
                            parametro=rep_param,
                            valor=rep_val,
                            confianza=0.98,
                            metodo=MetodoExtraccion.SPATIAL_VECTOR,
                            evidencias=[evidence],
                            valor_normalizado=rep_val,
                            formato_detectado="TEXT",
                            tipo_entidad="persona",
                            divisa=None,
                            kwic_context=kwic,
                        )
                    )

    return legal_findings


def extract_spatial_key_values(
    page: pymupdf.Page,
    canonical_params: List[str],
) -> List[HallazgoEnriquecido]:
    """
    Extrae entidades y pares clave-valor de una página digital mediante geometría espacial en Cero-IA (O(N))
    (US-07, US-08, US-09, US-10).
    
    Aplica:
    - Análisis de cláusulas contractuales hispanas y fórmulas notariales.
    - Búsqueda de palabra clave con tolerancia a kerning apretado (Paso 1 límites de palabra, Paso 2 subcadena).
    - Exploración en vector horizontal derecho: |Δy| <= 8 pt, Δx <= 250 pt con soporte para salto de línea.
    - Exploración en vector vertical descendente: -4.0 <= Δy <= 45 pt, agrupación de renglón completo.
    - Construcción de Evidence con bbox exacto y evidence_score determinista.
    - Normalización de entidades tipificadas (monedas, fechas ISO-8601, tax IDs).
    """
    page_num = page.number + 1
    page_text = page.get_text()
    raw_words = page.get_text("words")
    # raw_words tuples: (x0, y0, x1, y1, word, block_no, line_no, word_no)

    hallazgos: List[HallazgoEnriquecido] = []
    evidence_counter = 0

    # 0. Extracción determinista de cláusulas jurídicas introductorias
    legal_clause_findings = extract_legal_party_clauses(page, canonical_params, evidence_start_idx=evidence_counter)
    legal_map: Dict[str, HallazgoEnriquecido] = {h.parametro: h for h in legal_clause_findings}
    evidence_counter += len(legal_clause_findings)

    for param in canonical_params:
        synonyms = expand_parameter_synonyms(param)
        found_for_param = False
        is_entity_param = any(k in param for k in ("nombre", "titular", "arrendador", "arrendatario", "representante", "contratante", "contratista", "cliente", "proveedor", "notario", "perito", "solicitante", "otorgante", "compareciente"))
        is_currency_param = any(k in param for k in ("total", "valor", "precio", "canon", "subtotal", "iva", "monto", "saldo"))
        is_date_param = any(k in param for k in ("fecha", "date", "emision", "vencimiento"))
        is_tax_param = any(k in param for k in ("nit", "rut", "cuit", "cedula", "identificacion"))

        # Si ya se identificó mediante análisis contractual directo, usar el hallazgo directamente
        if param in legal_map:
            hallazgos.append(legal_map[param])
            continue

        param_candidates = []

        # 1. Chequeo de kerning apretado dentro de un mismo token (ej. "Total:1200000" o "NIT:900123" o "FachaEntrega.01/07/2026" o "ldentiflcaclon.32848952")
        for i, w in enumerate(raw_words):
            raw_token = w[4]
            parts = None
            if ":" in raw_token:
                parts = raw_token.split(":", 1)
            elif re.search(r"[./](?=\d)", raw_token):
                m_split = re.split(r"[./](?=\d)", raw_token, maxsplit=1)
                if len(m_split) == 2:
                    parts = m_split

            if parts:
                prefix_norm = normalize_parameter(parts[0])
                val_candidate = parts[1].strip()

                is_match = (prefix_norm in synonyms) or any(s in prefix_norm for s in synonyms if len(s) >= 4)
                if not is_match and "nit" in param:
                    if re.search(r"(?i)^(?:nit|cc|nuip|identific|nt)", prefix_norm):
                        is_match = True
                if not is_match and "fecha" in param:
                    if re.search(r"(?i)^(?:fecha|facha)", prefix_norm):
                        is_match = True

                if is_match and val_candidate:
                    # Excluir fechas de nacimiento del parámetro general de documento 'fecha'
                    if "fecha" in param and any(k in prefix_norm for k in ("nacimiento", "nac")):
                        continue

                    norm_curr, curr_code = normalize_currency_amount(val_candidate)
                    norm_date = normalize_date_string(val_candidate)
                    norm_tax = normalize_tax_id(val_candidate)

                    is_curr_p = any(k in param for k in ("total", "valor", "precio", "canon", "subtotal", "iva", "monto", "saldo"))
                    is_date_p = any(k in param for k in ("fecha", "date", "emision", "vencimiento"))
                    is_tax_p = any(k in param for k in ("nit", "rut", "cuit", "cedula", "identificacion"))

                    if is_curr_p and not norm_curr:
                        continue
                    if is_date_p and not norm_date:
                        continue
                    if is_tax_p and not (norm_tax or re.search(r"\b\d{7,11}(?:-\d)?\b", val_candidate)):
                        continue

                    evidence_counter += 1
                    ev_id = f"ev_p{page_num}_{evidence_counter:03d}"

                    if norm_curr and not is_entity_param:
                        val_norm = norm_curr
                        fmt = curr_code
                    elif norm_date and not is_entity_param:
                        val_norm = norm_date
                        fmt = "ISO-8601"
                    elif norm_tax and not is_entity_param:
                        val_norm = norm_tax
                        fmt = "NIT"
                    else:
                        val_norm = val_candidate
                        fmt = "TEXT"

                    score = 0.96
                    if "fecha" in param:
                        if any(k in prefix_norm for k in ("entrega", "atencion", "emision", "expedicion", "formula", "impresion", "factura")):
                            score = 0.99

                    kwic_ctx = extract_kwic_context(page_text, val_candidate)
                    tipo_ent = "moneda" if fmt in ("COP", "USD", "EUR") else ("fecha" if fmt == "ISO-8601" else ("nit" if fmt == "NIT" else "texto"))
                    evidence = Evidence(
                        evidence_id=ev_id,
                        page=page_num,
                        text=f"{param.upper()}: {val_candidate}",
                        bbox=[round(w[0], 2), round(w[1], 2), round(w[2], 2), round(w[3], 2)],
                        source=MetodoExtraccion.SPATIAL_VECTOR,
                        evidence_score=score,
                        kwic_snippet=kwic_ctx,
                    )
                    param_candidates.append(
                        HallazgoEnriquecido(
                            parametro=param,
                            valor=val_candidate,
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

        for syn in synonyms:
            syn_norm = normalize_parameter(syn)
            if not syn_norm:
                continue

            syn_tokens = syn_norm.split()
            candidate_key_boxes = []

            for i, w in enumerate(raw_words):
                w_norm = normalize_parameter(w[4]).strip(":-_.,")
                is_key_start = (w_norm == syn_norm) or (w_norm == syn_tokens[0]) or (syn_norm in w_norm) or (len(syn_tokens[0]) > 4 and syn_tokens[0] in w_norm)
                if not is_key_start and "nit" in param and re.search(r"^(?:nit|nt|cc|nuip|identific)", w_norm):
                    is_key_start = True

                if is_key_start:
                    # Evitar falsos positivos en oraciones continuas precedidas por preposiciones o artículos
                    if i > 0 and raw_words[i - 1][4].lower() in ("a", "la", "el", "en", "por", "de", "del", "con", "una", "un") and not w[4].endswith(":") and len(syn_tokens) == 1:
                        if not ("fecha" in param and raw_words[i - 1][4].lower() in ("con", "de")):
                            continue

                    # Para entidades (cliente, arrendador, etc.), no confundir con prefijos como "NIT CLIENTE:" o "TEL CLIENTE:"
                    if is_entity_param and i > 0:
                        prev_w = raw_words[i - 1][4].upper().strip(":-_.,")
                        if prev_w in ("NIT", "RUT", "TEL", "TELEFONO", "DIRECCION", "EMAIL", "CORREO", "VALOR", "TOTAL", "FECHA"):
                            continue

                    matched = True
                    last_idx = i
                    if len(syn_tokens) > 1 and w_norm != syn_norm and syn_norm not in w_norm:
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
                # 3a. Vector horizontal derecho: misma línea (|Δy| <= 8 pt, Δx <= 250 pt)
                right_words = []
                for w in raw_words:
                    k_y_center = (k_y0 + k_y1) / 2
                    w_y_center = (w[1] + w[3]) / 2
                    if abs(w_y_center - k_y_center) <= 8.0:
                        dx = w[0] - k_x1
                        if 0.0 < dx <= 250.0:
                            right_words.append(w)

                found_right = False
                found_down = False
                if right_words:
                    right_words.sort(key=lambda item: item[0])
                    val_text = " ".join([w[4] for w in right_words]).strip()

                    # Si el valor contiene o termina con dos puntos, descartar el prefijo de etiqueta
                    if ":" in val_text:
                        parts = val_text.split(":", 1)
                        val_text = parts[1].strip()
                    elif val_text.endswith(":"):
                        val_text = ""

                    if val_text:
                        val_text = val_text.lstrip("|:·• \t")
                        if "·" in val_text:
                            val_text = val_text.split("·")[0].strip()
                        if "|" in val_text:
                            val_text = val_text.split("|")[0].strip()

                        # Delimitación ante conectores gramaticales/jurídicos comunes
                        cut_match = re.split(r",\s*(?:representad[oa]|con\s+domicilio|identificad[oa]|en\s+adelante|de\s+fecha)\b", val_text, flags=re.IGNORECASE)
                        if len(cut_match) > 1:
                            val_text = cut_match[0].strip()

                        # Si es persona o entidad, remover prefijos gramaticales conectores, cargos y etiquetas compuestas
                        next_line_words = []
                        if is_entity_param:
                            val_text = re.sub(
                                r"^(?:completo\s+)?(?:usuario|titular|paciente|cliente|afiliado|senor[a]?|nombre(?:\s+completo)?)\s*[:.-]*\s*",
                                "",
                                val_text,
                                flags=re.IGNORECASE,
                            ).strip()
                            cut_label = re.split(r"\b(?:direccion|direcci[oó]n|telefono|tel|celular|domicilio|ciudad|fecha|nit|cc|edad|sexo|afiliado)\s*[:.-]", val_text, flags=re.IGNORECASE)
                            if cut_label and cut_label[0].strip():
                                val_text = cut_label[0].strip()
                            val_text = re.sub(r"^(?:por|de|el|la)\s+", "", val_text, flags=re.IGNORECASE).strip()
                            val_text = re.sub(r"^(?:titular|encargado|adjunto|publico)\s+", "", val_text, flags=re.IGNORECASE).strip()
                            if re.search(r"^(?:[-:·•\s]*)(?:c\.?c\.?|n\.?i\.?t\.?|c[eé]dula|\d)", val_text, re.IGNORECASE):
                                val_text = ""

                            # Soporte para salto de línea si el nombre se cortó al final del margen
                            tokens = val_text.split()
                            if len(tokens) <= 3 and right_words:
                                k_y_bottom = max(w[3] for w in right_words)
                                for nw in raw_words:
                                    dy_next = nw[1] - k_y_bottom
                                    if -2.0 <= dy_next <= 22.0 and nw[0] <= 180.0:
                                        next_line_words.append(nw)
                                if next_line_words:
                                    next_line_words.sort(key=lambda item: item[0])
                                    next_line_text = " ".join([nw[4] for nw in next_line_words])
                                    cut_next = re.split(r",\s*(?:mayor|con\s+c[eé]dula|con\s+nit|identificad|quien|de\s+fecha)\b", next_line_text, flags=re.IGNORECASE)
                                    if cut_next and cut_next[0].strip():
                                        cand_ext = cut_next[0].strip()
                                        if not re.search(r":|\b(?:direccion|direcci[oó]n|telefono|tel|celular|domicilio|ciudad|fecha|nit|cc|edad|sexo|afiliado)\b", cand_ext, re.IGNORECASE):
                                            if not re.search(r"^(?:[-:·•\s]*)(?:c\.?c\.?|n\.?i\.?t\.?|c[eé]dula|\d)", cand_ext, re.IGNORECASE):
                                                val_text = (val_text + " " + cand_ext).strip()

                            # Corte de seguridad por si aún quedara una etiqueta posterior con dos puntos
                            cut_post = re.split(r"\s+[a-zA-ZáéíóúÁÉÍÓÚ]+:\s*", val_text)
                            if cut_post and cut_post[0].strip():
                                val_text = cut_post[0].strip()

                        # Si buscamos NIT, delimitar estrictamente al patrón numérico (cédulas 7-10 dígitos o NITs)
                        if any(k in param for k in ("nit", "rut", "cuit", "cedula", "identificacion")):
                            nit_m = re.search(r"(\d[\d\.\s]*-\s*\d|\b\d{7,11}\b)", val_text)
                            if nit_m:
                                val_text = nit_m.group(0).strip()

                        # Si buscamos moneda/total, extraer quirúrgicamente la cifra monetaria si está mezclada
                        if any(k in param for k in ("total", "valor", "precio", "canon", "subtotal", "iva", "monto")):
                            curr_m = re.search(r"(\$\s*[\d\.,]+(?:\s*COP|\s*USD|\s*EUR)?|USD\s*[\d\.,]+|EUR\s*[\d\.,]+)", val_text)
                            if curr_m:
                                val_text = curr_m.group(0).strip()
                            elif val_text.endswith("$") or re.search(r"\$\s*0*(?:\b|$)", val_text) or val_text in ("0", "$0", "$ 0", "0.00", "$"):
                                val_text = "$0.00 COP"

                    # Descartar unidades de encabezado de tabla como (COP) o si quedó vacío
                    if val_text and val_text.lower() not in ("(cop)", "(usd)", "(eur)", ":", "-"):
                        found_right = True
                        all_val_words = list(right_words)
                        if next_line_words:
                            all_val_words.extend(next_line_words)
                        v_x0 = min(w[0] for w in all_val_words)
                        v_y0 = min(w[1] for w in all_val_words)
                        v_x1 = max(w[2] for w in all_val_words)
                        v_y1 = max(w[3] for w in all_val_words)

                        evidence_counter += 1
                        ev_id = f"ev_p{page_num}_{evidence_counter:03d}"

                        dist = math.sqrt((v_x0 - k_x1) ** 2 + ((v_y0 - k_y0) ** 2))
                        penalizacion_dist = min(0.30, dist / 300.0)
                        base_h = 1.0 - penalizacion_dist + 0.08
                        if raw_words[last_w_idx][4].endswith(":"):
                            base_h += 0.05
                        score = round(max(0.50, min(1.0, base_h)), 2)

                        norm_curr, curr_code = normalize_currency_amount(val_text)
                        norm_date = normalize_date_string(val_text)
                        norm_tax = normalize_tax_id(val_text)

                        # Validación semántica estricta del tipo de parámetro
                        is_currency_param = any(k in param for k in ("total", "valor", "precio", "canon", "subtotal", "iva", "monto", "saldo"))
                        is_date_param = any(k in param for k in ("fecha", "date", "emision", "vencimiento"))
                        is_tax_param = any(k in param for k in ("nit", "rut", "cuit", "cedula", "identificacion"))

                        if is_currency_param and not norm_curr:
                            continue
                        if is_date_param and not norm_date:
                            continue
                        if is_tax_param and not (norm_tax or re.search(r"\b\d{7,10}(?:-\d)?\b", val_text)):
                            continue

                        if norm_date and not is_entity_param:
                            val_norm = norm_date
                            fmt = "ISO-8601"
                            score = min(1.0, score + 0.05)
                        elif norm_tax and is_tax_param:
                            val_norm = norm_tax
                            fmt = "NIT"
                            score = min(1.0, score + 0.05)
                        elif norm_curr and is_currency_param:
                            val_norm = norm_curr
                            fmt = curr_code
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
                                divisa=curr_code if norm_curr and is_currency_param else None,
                                kwic_context=kwic_ctx,
                            )
                        )

                # 3b. Vector vertical descendente (solo cuando NO hay contenido a la derecha, US-07 Escenario 2)
                if not found_right:
                    found_down = False
                    down_candidates = []
                    for w in raw_words:
                        dy = w[1] - k_y1
                        if -4.0 <= dy <= 45.0:
                            # Ignorar otras etiquetas o dos puntos aislados
                            if w[4].endswith(":") or w[4].upper() in ("IVA", "TOTAL", "SUBTOTAL", "NIT", "FECHA"):
                                continue
                            if w[0] >= k_x0 - 40 and w[2] <= max(k_x1 + 250, k_x0 + 350):
                                down_candidates.append(w)

                    if down_candidates:
                        min_y = min(c[1] for c in down_candidates)
                        # Agrupar las palabras que conforman el primer renglón descendente
                        down_words = [c for c in down_candidates if abs(c[1] - min_y) <= 5.0]
                        down_words.sort(key=lambda item: item[0])
                        val_text = " ".join([w[4] for w in down_words]).strip()
                        if ":" in val_text:
                            parts = val_text.split(":", 1)
                            val_text = parts[1].strip()
                        elif val_text.endswith(":"):
                            val_text = ""

                        if val_text:
                            val_text = val_text.lstrip("|:·• \t")
                            if "·" in val_text:
                                val_text = val_text.split("·")[0].strip()
                            if "|" in val_text:
                                val_text = val_text.split("|")[0].strip()

                            cut_match = re.split(r",\s*(?:representad[oa]|con\s+domicilio|identificad[oa]|en\s+adelante|de\s+fecha)\b", val_text, flags=re.IGNORECASE)
                            if len(cut_match) > 1:
                                val_text = cut_match[0].strip()

                            if is_entity_param:
                                val_text = re.sub(r"^(?:por|de|el|la)\s+", "", val_text, flags=re.IGNORECASE).strip()
                                val_text = re.sub(r"^(?:titular|encargado|adjunto|publico)\s+", "", val_text, flags=re.IGNORECASE).strip()
                                if re.search(r"^(?:[-:·•\s]*)(?:c\.?c\.?|n\.?i\.?t\.?|c[eé]dula|\d)", val_text, re.IGNORECASE):
                                    val_text = ""

                            if any(k in param for k in ("nit", "rut", "cuit", "cedula", "identificacion")):
                                nit_m = re.search(r"\b\d{7,10}(?:-\d)?\b", val_text)
                                if nit_m:
                                    val_text = nit_m.group(0)

                            if any(k in param for k in ("total", "valor", "precio", "canon", "subtotal", "iva", "monto")):
                                curr_m = re.search(r"(\$\s*[\d\.,]+(?:\s*COP|\s*USD|\s*EUR)?|USD\s*[\d\.,]+|EUR\s*[\d\.,]+)", val_text)
                                if curr_m:
                                    val_text = curr_m.group(0).strip()

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

                            # Validación semántica estricta del tipo de parámetro
                            is_currency_param = any(k in param for k in ("total", "valor", "precio", "canon", "subtotal", "iva", "monto", "saldo"))
                            is_date_param = any(k in param for k in ("fecha", "date", "emision", "vencimiento"))
                            is_tax_param = any(k in param for k in ("nit", "rut", "cuit", "cedula", "identificacion"))

                            if is_currency_param and not norm_curr:
                                if any(k in syn_norm for k in ("total", "cuota", "copago")):
                                    val_text = "$0.00 COP"
                                    norm_curr = "0.00"
                                    curr_code = "COP"
                                    fmt = "COP"
                                    score = 0.90
                                else:
                                    continue
                            if is_date_param and not norm_date:
                                continue
                            if is_tax_param and not (norm_tax or re.search(r"\b\d{7,10}(?:-\d)?\b", val_text)):
                                continue

                            if norm_date and not is_entity_param:
                                val_norm = norm_date
                                fmt = "ISO-8601"
                                score = min(1.0, score + 0.05)
                            elif norm_tax and is_tax_param:
                                val_norm = norm_tax
                                fmt = "NIT"
                                score = min(1.0, score + 0.05)
                            elif norm_curr and is_currency_param:
                                val_norm = norm_curr
                                fmt = curr_code
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
                                    divisa=curr_code if norm_curr and is_currency_param else None,
                                    kwic_context=kwic_ctx,
                                )
                            )
                            found_down = True

                # Fallback para órdenes médicas / facturas POS con copago o saldo 0
                if not found_down and not found_right and is_currency_param and any(k in syn_norm for k in ("total", "cuota", "copago")):
                    evidence_counter += 1
                    ev_id = f"ev_p{page_num}_{evidence_counter:03d}"
                    evidence = Evidence(
                        evidence_id=ev_id,
                        page=page_num,
                        text=f"{param.upper()}: $0.00 COP",
                        bbox=[round(k_x0, 2), round(k_y0, 2), round(k_x1, 2), round(k_y1, 2)],
                        source=MetodoExtraccion.SPATIAL_VECTOR,
                        evidence_score=0.90,
                        kwic_snippet=extract_kwic_context(page_text, raw_words[last_w_idx][4]),
                    )
                    param_candidates.append(
                        HallazgoEnriquecido(
                            parametro=param,
                            valor="$0.00 COP",
                            confianza=0.90,
                            metodo=MetodoExtraccion.SPATIAL_VECTOR,
                            evidencias=[evidence],
                            valor_normalizado="0.00",
                            formato_detectado="COP",
                            tipo_entidad="moneda",
                            divisa="COP",
                            kwic_context=evidence.kwic_snippet,
                        )
                    )

        # Seleccionar el mejor candidato para este parámetro:
        if param_candidates:
            if is_entity_param:
                # Para personas o empresas: priorizar nombres propios (2 a 4 palabras) sin acrónimos institucionales ni dígitos
                def _entity_rank(c):
                    val = c.valor.strip()
                    tokens = val.split()
                    penalizacion = 0
                    if re.search(r"\b(?:ips|ese|eps|sas|ltda|nit|cc|dr|dra|medico|ordenes|formula)\b", val, re.IGNORECASE) or "." in val:
                        penalizacion -= 5
                    if re.search(r"^\d", val) or c.formato_detectado in ("COP", "USD", "EUR", "ISO-8601", "NIT"):
                        penalizacion -= 10
                    is_title_or_upper = val.isupper() or all(t[0].isupper() for t in tokens if t)
                    return (
                        penalizacion,
                        1 if is_title_or_upper else 0,
                        len(tokens) if 2 <= len(tokens) <= 4 else -len(tokens),
                        c.confianza,
                    )
                param_candidates.sort(key=_entity_rank, reverse=True)
            elif "fecha" in param:
                # Priorizar fechas de trámite/documento y castigar fechas de nacimiento
                param_candidates.sort(
                    key=lambda c: (
                        -1.0 if any(k in c.valor.lower() or (c.kwic_context and k in c.kwic_context.lower()) for k in ("nacimiento", "nac.", "f.nac")) else 1.0,
                        c.confianza,
                    ),
                    reverse=True,
                )
            else:
                # Para montos y NITs: priorizar normalización tipificada estricta
                param_candidates.sort(
                    key=lambda c: (
                        1 if c.formato_detectado in ("COP", "USD", "EUR", "ISO-8601", "NIT") else 0,
                        c.confianza,
                    ),
                    reverse=True,
                )
            hallazgos.append(param_candidates[0])
    return hallazgos


def _eval_finding_quality(f: Optional[HallazgoEnriquecido]) -> float:
    if f is None:
        return -999.0
    raw = (f.valor or "").strip()
    raw_l = raw.lower()
    if not raw or raw_l in ("no especificado", "no detectado", "n/a", "no encontrado", "none", "null", "-", "--", "no aplica"):
        return -10.0
    if raw.endswith(":") or ":" in raw or raw_l in ("del contrato:", "a pagar:", "total:"):
        return -5.0
    if "fecha" in f.parametro:
        if any(k in raw_l or (f.kwic_context and k in f.kwic_context.lower()) for k in ("nacimiento", "nac.", "f.nac")):
            return -2.0
    if any(k in f.parametro for k in ("representante", "arrendador", "contratante", "perito", "contratista", "cliente", "notario", "nombre")):
        if re.search(r"^(?:[-:·•\s]*)(?:c\.?c\.?|n\.?i\.?t\.?|c[eé]dula|\d)", raw, re.IGNORECASE):
            return -10.0
        tokens = raw.split()
        if len(tokens) == 1 and raw.upper() in ("LA", "EL", "DE", "UN", "UNA", "POR", "Y"):
            return -10.0
        score = f.confianza
        if len(tokens) >= 2:
            score += 0.35
        if len(tokens) >= 3:
            score += 0.25
        return score

    score = f.confianza
    if f.valor_normalizado and f.formato_detectado in ("COP", "USD", "EUR", "ISO-8601", "NIT"):
        score += 0.30

    if f.evidencias:
        min_p = min(e.page for e in f.evidencias)
        if min_p == 1:
            score += 0.25
        elif min_p <= 3:
            score += 0.10

    return score


def consolidate_findings(
    native_findings: List[HallazgoEnriquecido],
    ai_findings: List[HallazgoEnriquecido],
) -> List[HallazgoEnriquecido]:
    """
    Consolida hallazgos entre extracción espacial nativa y visión IA (US-10).
    Previene datos irreales descartando valores nativos que sean etiquetas no resueltas.
    Si la IA extrajo un valor válido y estructurado, prevalece la IA ante datos nativos ambiguos.
    Aplica precedencia absoluta del dato determinista nativo cuando es confiable (confianza >= 0.70).
    """
    all_params = sorted(list(set([f.parametro for f in native_findings] + [f.parametro for f in ai_findings])))
    native_map: dict[str, HallazgoEnriquecido] = {}
    for f in native_findings:
        p = f.parametro
        if p not in native_map or _eval_finding_quality(f) > _eval_finding_quality(native_map[p]):
            native_map[p] = f

    ai_map: dict[str, HallazgoEnriquecido] = {}
    for f in ai_findings:
        p = f.parametro
        if p not in ai_map or _eval_finding_quality(f) > _eval_finding_quality(ai_map[p]):
            ai_map[p] = f

    consolidated: List[HallazgoEnriquecido] = []

    for p in all_params:
        nat = native_map.get(p)
        ai = ai_map.get(p)

        nat_score = _eval_finding_quality(nat)
        ai_score = _eval_finding_quality(ai)

        if nat_score < 0.0 and ai_score < 0.0:
            continue
        elif nat_score >= 0.0 and ai_score < 0.0:
            assert nat is not None
            consolidated.append(nat)
        elif ai_score >= 0.0 and nat_score < 0.0:
            assert ai is not None
            consolidated.append(ai)
        else:
            assert nat is not None and ai is not None
            # Ambos son válidos
            if nat.valor_normalizado and nat.valor_normalizado == ai.valor_normalizado:
                # Acuerdo pleno nativo-IA: máxima certeza multimodal
                ai.confianza = 1.0
                consolidated.append(ai)
            elif nat.confianza >= 0.70 and nat.valor_normalizado and not nat.valor.endswith(":"):
                # Precedencia estricta del dato determinista nativo válido (US-10 Escenario 2)
                consolidated.append(nat)
            elif ai_score > nat_score + 0.10:
                consolidated.append(ai)
            else:
                consolidated.append(nat)

    return consolidated
