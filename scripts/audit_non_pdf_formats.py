"""
PyDective — Auditoría Técnica Profunda de Formatos Especiales
Evalúa cuantitativa y cualitativamente el comportamiento del pipeline ante:
1. PDFs Escaneados (imágenes raster con deskew y sellos)
2. Imágenes Forenses (PNG, JPG, TIFF con firmas y sellos)
3. Hojas de Cálculo XLSX (tablas, encabezados, montos)
4. Documentos DOCX y Archivos TXT (codificación UTF-8 / acentos)
"""

import io
import json
import time
import sys
from pathlib import Path
from typing import Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pymupdf
from app.domain.enums import TipoPagina
from app.services.ingestion_service import validate_and_read_pdf
from app.services.classifier_service import classify_page
from app.services.spatial_extraction_service import extract_spatial_key_values, consolidate_findings
from app.services.image_service import catalog_page_images
from app.services.semantic_extraction_service import normalize_parameter
from app.services.ocr_service import extract_page_ocr
from app.services.gemini_service import _simulate_page_extraction

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures_100"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


def run_audit():
    if not MANIFEST_PATH.exists():
        print(f"Error: No se encontró {MANIFEST_PATH}")
        return

    manifest: Dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    cohorts = {
        "escaneo_pdf": [f for f, v in manifest.items() if v["categoria"] == "escaneo_vision"],
        "imagen_png": [f for f in manifest if f.endswith(".png")],
        "imagen_jpg": [f for f in manifest if f.endswith(".jpg")],
        "imagen_tiff": [f for f in manifest if f.endswith(".tiff")],
        "ofimatico_xlsx": [f for f, v in manifest.items() if v["categoria"] == "ofimatico_xlsx"],
        "ofimatico_docx": [f for f, v in manifest.items() if v["categoria"] == "ofimatico_docx"],
        "ofimatico_txt": [f for f, v in manifest.items() if v["categoria"] == "ofimatico_txt"],
    }

    summary = {}

    for cohort_name, file_list in cohorts.items():
        print(f"\n=======================================================")
        print(f"  AUDITORÍA: {cohort_name.upper()} ({len(file_list)} archivos)")
        print(f"=======================================================")

        total_fields = 0
        hits = 0
        detected_types = {}
        encoding_issues = []
        visual_detected = 0
        visual_expected = 0
        latencies = []

        for fname in file_list:
            fpath = FIXTURES_DIR / fname
            data = fpath.read_bytes()
            meta = manifest[fname]
            gt = meta.get("ground_truth", {})
            exp_vis = meta.get("visuales", [])

            t0 = time.perf_counter()
            doc_hash, doc, total_pages = validate_and_read_pdf(data, filename=fname)
            page = doc[0]
            classification = classify_page(page)
            dur_ms = (time.perf_counter() - t0) * 1000
            latencies.append(dur_ms)

            detected_types[classification.tipo.value] = detected_types.get(classification.tipo.value, 0) + 1

            # Detección visual
            vis_meta = catalog_page_images(page, catalogar_imagenes=True)
            vis_found_classes = [v.clasificacion_semantica for v in vis_meta]
            for ev in exp_vis:
                visual_expected += 1
                if ev in vis_found_classes:
                    visual_detected += 1

            # Extracción del pipeline completo (carril nativo + OCR / multimodal)
            params = list(gt.keys())
            raw_text = page.get_text()

            # Si es página escaneada o imagen, invocar OCR local autónomo
            if classification.tipo == TipoPagina.NEEDS_AI and len(raw_text.strip()) == 0:
                ocr_full_text, ocr_boxes = extract_page_ocr(page)
                if ocr_full_text.strip():
                    raw_text = ocr_full_text
                    for b in ocr_boxes:
                        try:
                            rect = pymupdf.Rect(b["bbox"])
                            page.insert_textbox(rect, b["text"], fontsize=10, render_mode=3)
                        except Exception:
                            pass

            findings = extract_spatial_key_values(page, params) if len(page.get_text().strip()) > 0 else []
            ai_findings = []
            if classification.tipo == TipoPagina.NEEDS_AI:
                ai_findings = _simulate_page_extraction(1, params, raw_text)

            consolidated = consolidate_findings(findings, ai_findings)
            found_map = {f.parametro: f for f in consolidated}

            raw_text = page.get_text()

            for p_name, exp_val in gt.items():
                total_fields += 1
                f_obj = found_map.get(p_name)
                is_hit = False

                if f_obj:
                    got_val = str(f_obj.valor)
                    got_norm = str(f_obj.valor_normalizado or "")
                    norm_exp = normalize_parameter(exp_val)
                    norm_got = normalize_parameter(got_val)
                    if (
                        exp_val.lower() in got_val.lower()
                        or exp_val.lower() in got_norm.lower()
                        or norm_exp in norm_got
                        or norm_exp in normalize_parameter(got_norm)
                    ):
                        is_hit = True

                if is_hit:
                    hits += 1
                else:
                    # Detectar si el texto crudo contenía el valor pero se perdió por extracción
                    in_raw = exp_val.lower() in raw_text.lower()
                    # Detectar corrupción de encoding (caracteres extraños)
                    has_encoding_glitch = any(c in raw_text for c in ("¶", "»", "«", ""))
                    if has_encoding_glitch and fname not in [e[0] for e in encoding_issues]:
                        encoding_issues.append((fname, p_name, exp_val))

            doc.close()

        avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
        acc_pct = (hits / total_fields * 100) if total_fields else 0.0
        vis_pct = (visual_detected / visual_expected * 100) if visual_expected else 0.0

        summary[cohort_name] = {
            "total_files": len(file_list),
            "classification_distribution": detected_types,
            "accuracy": f"{hits}/{total_fields} ({acc_pct:.1f}%)",
            "visual_accuracy": f"{visual_detected}/{visual_expected} ({vis_pct:.1f}%)" if visual_expected else "N/A",
            "avg_latency_ms": round(avg_lat, 2),
            "encoding_issues_count": len(encoding_issues),
            "encoding_issues": encoding_issues,
        }

        print(f"  • Precisión de Entidades: {hits}/{total_fields} ({acc_pct:.1f}%)")
        print(f"  • Clasificación de Páginas: {detected_types}")
        print(f"  • Detección Visual: {visual_detected}/{visual_expected} ({vis_pct:.1f}%)")
        print(f"  • Latencia Media Ingesta+Clasif: {avg_lat:.2f} ms")
        if encoding_issues:
            print(f"  • Archivos con fallas de encoding: {len(encoding_issues)}")

    # Guardar reporte JSON
    out_json = BASE_DIR / "AUDITORIA_MULTIMODAL_METRICS.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] Métricas consolidadas guardadas en {out_json}")


if __name__ == "__main__":
    run_audit()
