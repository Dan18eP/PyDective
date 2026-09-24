import os
import time
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image
import pymupdf

logger = logging.getLogger("pydective.florence")

_FLORENCE_MODEL = None
_FLORENCE_PROCESSOR = None
_MODEL_ID = "microsoft/Florence-2-base"


def _patch_florence_cpu_imports():
    from unittest.mock import patch
    from transformers.dynamic_module_utils import get_imports

    def fixed_get_imports(filename: str | os.PathLike):
        if not str(filename).endswith("modeling_florence2.py"):
            return get_imports(filename)
        imports = get_imports(filename)
        if "flash_attn" in imports:
            imports.remove("flash_attn")
        return imports

    return patch("transformers.dynamic_module_utils.get_imports", fixed_get_imports)


def get_florence_model_and_processor():
    global _FLORENCE_MODEL, _FLORENCE_PROCESSOR
    if _FLORENCE_MODEL is not None and _FLORENCE_PROCESSOR is not None:
        return _FLORENCE_MODEL, _FLORENCE_PROCESSOR

    import torch
    from transformers import AutoProcessor, AutoModelForCausalLM

    logger.info(f"Cargando modelo Microsoft Florence-2 ({_MODEL_ID}) en CPU...")
    with _patch_florence_cpu_imports():
        _FLORENCE_MODEL = AutoModelForCausalLM.from_pretrained(
            _MODEL_ID,
            torch_dtype=torch.float32,
            trust_remote_code=True,
        ).to("cpu")
        _FLORENCE_PROCESSOR = AutoProcessor.from_pretrained(
            _MODEL_ID,
            trust_remote_code=True,
        )

    logger.info("Modelo Microsoft Florence-2 cargado en CPU exitosamente.")
    return _FLORENCE_MODEL, _FLORENCE_PROCESSOR


def quad_to_bbox(quad: List[float], img_w: float, img_h: float, page_w: float, page_h: float) -> List[float]:
    if len(quad) == 8:
        xs = [quad[0], quad[2], quad[4], quad[6]]
        ys = [quad[1], quad[3], quad[5], quad[7]]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    elif len(quad) == 4:
        x0, y0, x1, y1 = quad[0], quad[1], quad[2], quad[3]
    else:
        return [0.0, 0.0, 100.0, 20.0]

    scale_x = page_w / max(1.0, img_w)
    scale_y = page_h / max(1.0, img_h)

    return [
        round(x0 * scale_x, 2),
        round(y0 * scale_y, 2),
        round(x1 * scale_x, 2),
        round(y1 * scale_y, 2),
    ]


def extract_page_florence(
    page: pymupdf.Page,
    page_number: int,
    parameters: List[str],
) -> Tuple[List[Dict[str, Any]], float, List[Dict[str, Any]]]:
    t0 = time.perf_counter()
    model, processor = get_florence_model_and_processor()

    pix = page.get_pixmap(dpi=150)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    task_prompt = "<OCR_WITH_REGION>"
    import torch
    inputs = processor(text=task_prompt, images=image, return_tensors="pt").to("cpu", torch.float32)

    with torch.no_grad():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=1024,
            num_beams=3,
            do_sample=False,
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    parsed_answer = processor.post_process_generation(
        generated_text,
        task=task_prompt,
        image_size=(image.width, image.height),
    )

    ocr_results = parsed_answer.get("<OCR_WITH_REGION>", {})
    quad_boxes = ocr_results.get("quad_boxes", [])
    labels = ocr_results.get("labels", [])

    raw_detections = []
    page_w = float(page.rect.width)
    page_h = float(page.rect.height)

    for i, label in enumerate(labels):
        quad = quad_boxes[i] if i < len(quad_boxes) else []
        box = quad_to_bbox(quad, float(image.width), float(image.height), page_w, page_h)
        raw_detections.append({
            "texto": label.replace("</s>", "").strip(),
            "bbox": box,
            "quad": quad,
        })

    from app.services.spatial_extraction_service import (
        normalize_currency_amount,
        normalize_date_string,
        normalize_tax_id,
    )
    from app.services.ocr_service import clean_ocr_line

    matched_findings = []
    for p in parameters:
        p_clean = p.lower().strip()
        found = False

        for det in raw_detections:
            line_txt = clean_ocr_line(det["texto"])

            if "fecha" in p_clean:
                m = re.search(r"\b(202\d[-/]\d{2}[-/]\d{2})\b", line_txt)
                if m:
                    val = m.group(1).replace("/", "-")
                    matched_findings.append({
                        "parametro": p_clean,
                        "valor": val,
                        "confianza": 0.94,
                        "metodo": "florence2_vlm",
                        "bbox": det["bbox"],
                        "valor_normalizado": normalize_date_string(val) or val,
                        "formato_detectado": "ISO-8601",
                        "tipo_entidad": "fecha",
                    })
                    found = True
                    break

            elif "total" in p_clean:
                m = re.search(r"(\$?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?\s*(?:cop|usd)?)", line_txt, re.IGNORECASE)
                if m and any(k in line_txt.lower() for k in ("total", "valor", "declarado", "saldo", "liquidado", "$")):
                    val = m.group(1).strip()
                    norm_curr, curr_code = normalize_currency_amount(val)
                    matched_findings.append({
                        "parametro": p_clean,
                        "valor": val,
                        "confianza": 0.93,
                        "metodo": "florence2_vlm",
                        "bbox": det["bbox"],
                        "valor_normalizado": norm_curr or val,
                        "formato_detectado": curr_code or "COP",
                        "tipo_entidad": "moneda",
                    })
                    found = True
                    break

            elif any(k in p_clean for k in ("nit", "rut", "identificacion")):
                m = re.search(r"\b(\d{3,4}[.,]?\d{3}[.,]?\d{3}-?\d?)\b", line_txt)
                if m:
                    val = m.group(1).strip()
                    matched_findings.append({
                        "parametro": p_clean,
                        "valor": val,
                        "confianza": 0.95,
                        "metodo": "florence2_vlm",
                        "bbox": det["bbox"],
                        "valor_normalizado": normalize_tax_id(val) or val,
                        "formato_detectado": "NIT",
                        "tipo_entidad": "nit",
                    })
                    found = True
                    break

            elif p_clean in line_txt.lower():
                val = line_txt.lower().replace(p_clean, "").strip(" :.-")
                if val:
                    matched_findings.append({
                        "parametro": p_clean,
                        "valor": val.title(),
                        "confianza": 0.88,
                        "metodo": "florence2_vlm",
                        "bbox": det["bbox"],
                        "valor_normalizado": val.upper(),
                        "formato_detectado": "TEXT",
                        "tipo_entidad": "texto",
                    })
                    found = True
                    break

        if not found:
            matched_findings.append({
                "parametro": p_clean,
                "valor": "No detectado en el documento",
                "confianza": 0.0,
                "metodo": "florence2_vlm",
                "bbox": [0.0, 0.0, 0.0, 0.0],
                "valor_normalizado": None,
                "formato_detectado": None,
                "tipo_entidad": None,
            })

    return matched_findings, elapsed_ms, raw_detections


def florence_findings_to_domain(
    florence_findings: List[Dict[str, Any]],
    page_number: int,
):
    from app.domain.models import HallazgoEnriquecido, Evidence, MetodoExtraccion

    results = []
    for f in florence_findings:
        bbox = f.get("bbox", [0.0, 0.0, 0.0, 0.0])
        val = f.get("valor", "No detectado en el documento")
        conf = f.get("confianza", 0.0)
        evs = []
        if val != "No detectado en el documento" and bbox != [0.0, 0.0, 0.0, 0.0]:
            evs.append(
                Evidence(
                    evidence_id=f"ev_florence_p{page_number}_{f['parametro']}",
                    page=page_number,
                    text=f"{f['parametro']}: {val}",
                    bbox=bbox,
                    source=MetodoExtraccion.SPATIAL_VECTOR,
                    evidence_score=conf,
                )
            )
        results.append(
            HallazgoEnriquecido(
                parametro=f["parametro"],
                valor=val,
                confianza=conf,
                metodo=MetodoExtraccion.SPATIAL_VECTOR,
                evidencias=evs,
                valor_normalizado=f.get("valor_normalizado"),
                formato_detectado=f.get("formato_detectado", "TEXT"),
            )
        )
    return results


def build_engine_benchmark(
    rapid_findings: list,
    rapid_duration_ms: float,
    florence_findings: List[Dict[str, Any]],
    florence_duration_ms: float,
    canonical_params: List[str],
) -> Dict[str, Any]:
    rapid_by_param = {h.parametro: h for h in rapid_findings}
    florence_by_param = {f["parametro"]: f for f in florence_findings}

    rapid_ms = max(1.0, round(rapid_duration_ms, 2))
    florence_ms = max(1.0, round(florence_duration_ms, 2))
    speedup = round(florence_ms / rapid_ms, 1)

    rapid_detected = sum(1 for h in rapid_findings if h.valor != "No detectado en el documento" and h.confianza > 0)
    florence_detected = sum(1 for f in florence_findings if f.get("valor") != "No detectado en el documento" and f.get("confianza", 0) > 0)

    filas_comparativas = []
    for p in canonical_params:
        p_clean = p.lower().strip()
        rh = rapid_by_param.get(p_clean)
        fh = florence_by_param.get(p_clean)

        r_val = rh.valor if (rh and rh.valor != "No detectado en el documento") else "No detectado"
        r_bbox = rh.evidencias[0].bbox if (rh and rh.evidencias) else [0.0, 0.0, 0.0, 0.0]
        r_conf = rh.confianza if rh else 0.0

        f_val = fh.get("valor", "No detectado") if (fh and fh.get("valor") != "No detectado en el documento") else "No detectado"
        f_bbox = fh.get("bbox", [0.0, 0.0, 0.0, 0.0]) if fh else [0.0, 0.0, 0.0, 0.0]
        f_conf = fh.get("confianza", 0.0) if fh else 0.0

        if r_val != "No detectado" and f_val != "No detectado":
            r_norm = "".join(r_val.lower().split())
            f_norm = "".join(f_val.lower().split())
            if r_norm == f_norm:
                concordancia = "Exacta"
            elif r_norm in f_norm or f_norm in r_norm:
                concordancia = "Cercana"
            else:
                concordancia = "Discrepante"
        elif r_val != "No detectado":
            concordancia = "Solo RapidOCR"
        elif f_val != "No detectado":
            concordancia = "Solo Florence-2"
        else:
            concordancia = "No detectado"

        filas_comparativas.append({
            "parametro": p_clean,
            "rapid_valor": r_val,
            "rapid_bbox": r_bbox,
            "rapid_confianza": round(r_conf, 2),
            "florence_valor": f_val,
            "florence_bbox": f_bbox,
            "florence_confianza": round(f_conf, 2),
            "concordancia": concordancia,
        })

    return {
        "habilitado": True,
        "factor_aceleracion": speedup,
        "resumen": f"RapidOCR ONNX fue {speedup}x más rápido que Microsoft Florence-2 en CPU.",
        "rapidocr": {
            "nombre": "RapidOCR ONNX (C++/AVX2)",
            "duracion_total_ms": rapid_ms,
            "hallazgos_detectados": rapid_detected,
        },
        "florence2": {
            "nombre": "Microsoft Florence-2 (230M VLM)",
            "duracion_total_ms": florence_ms,
            "hallazgos_detectados": florence_detected,
        },
        "filas_comparativas": filas_comparativas,
    }

