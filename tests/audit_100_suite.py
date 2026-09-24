import json
import time
from pathlib import Path
from typing import Dict, Any, List

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures_100"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"
REPORT_PATH = BASE_DIR / "AUDITORIA_100_REPORT.md"


def run_massive_audit():
    print("Iniciando auditoría automatizada sobre los 100 archivos...")
    if not MANIFEST_PATH.exists():
        print("Error: manifest.json no existe.")
        return

    manifest: Dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    total_docs = len(manifest)

    results_log: List[Dict[str, Any]] = []
    t_start_total = time.perf_counter()

    success_ingest = 0
    precision_hits = 0
    precision_total = 0
    visual_hits = 0
    visual_total = 0
    total_latencies = []

    client = httpx.Client(base_url="http://localhost:8000", timeout=60.0)

    for idx, (filename, info) in enumerate(manifest.items(), 1):
        filepath = FIXTURES_DIR / filename
        gt = info.get("ground_truth", {})
        expected_visuals = info.get("visuales", [])
        params_str = ", ".join(gt.keys())

        try:
            t0 = time.perf_counter()
            with open(filepath, "rb") as f:
                files = {"file": (filename, f.read(), "application/octet-stream")}
                data = {"parametros": params_str, "catalogar_imagenes": "true"}
                resp = client.post("/procesar", files=files, data=data)
            lat_ms = (time.perf_counter() - t0) * 1000
            total_latencies.append(lat_ms)

            if resp.status_code == 200:
                success_ingest += 1
                job_out = resp.json()
                extracted = {h["parametro"]: h for h in job_out.get("hallazgos", [])}

                # Evaluar precisión por parámetro
                file_hits = 0
                file_checks = len(gt)
                truncation_detected = []

                for p_name, expected_val in gt.items():
                    precision_total += 1
                    found_h = extracted.get(p_name)
                    if found_h:
                        val_raw = str(found_h.get("valor", "")).strip()
                        val_norm = str(found_h.get("valor_normalizado", "")).strip()
                        # Si es persona, verificar si se truncó en artículo gramatical
                        if p_name in ("arrendador", "representante legal", "notario", "cliente", "representante"):
                            if val_raw.upper() in ("LA", "EL", "DE", "UN", "UNA"):
                                truncation_detected.append(f"{p_name}: truncado en '{val_raw}' (esperado '{expected_val}')")
                            elif expected_val.lower() in val_raw.lower() or expected_val.lower() in val_norm.lower():
                                precision_hits += 1
                                file_hits += 1
                            else:
                                truncation_detected.append(f"{p_name}: extrajo '{val_raw}' (esperado '{expected_val}')")
                        elif expected_val.lower() in val_norm.lower() or expected_val.lower() in val_raw.lower():
                            precision_hits += 1
                            file_hits += 1

                # Evaluar visuales
                detected_vis = []
                for p_res in job_out.get("resultados_por_pagina", []):
                    for v in p_res.get("metadatos_visuales", []):
                        detected_vis.append(v.get("clasificacion_semantica"))

                for ev in expected_visuals:
                    visual_total += 1
                    if ev in detected_vis:
                        visual_hits += 1

                results_log.append({
                    "id": idx,
                    "filename": filename,
                    "extension": info.get("extension"),
                    "categoria": info.get("categoria"),
                    "status_http": 200,
                    "duracion_ms": round(lat_ms, 2),
                    "carril": job_out.get("resultados_por_pagina", [{}])[0].get("tipo", "unknown"),
                    "truncations": truncation_detected,
                    "hits": f"{file_hits}/{file_checks}",
                })
            else:
                results_log.append({
                    "id": idx,
                    "filename": filename,
                    "status_http": resp.status_code,
                    "error": resp.text[:200],
                })
        except Exception as e:
            results_log.append({
                "id": idx,
                "filename": filename,
                "status_http": 500,
                "error": str(e),
            })

    total_time_s = time.perf_counter() - t_start_total
    total_latencies.sort()
    p50 = total_latencies[len(total_latencies) // 2] if total_latencies else 0
    p95 = total_latencies[int(len(total_latencies) * 0.95)] if total_latencies else 0

    # Generar Reporte de Auditoría
    lines = [
        "# Informe de Auditoría Masiva: Suite de 100 Documentos Multi-Formato",
        "",
        f"> **Fecha:** {time.strftime('%Y-%m-%d %H:%M:%S')} | **Archivos Evaluados:** {total_docs} | **Tiempo Total:** {total_time_s:.2f} s",
        "",
        "---",
        "",
        "## 1. Métricas Globales de Rendimiento y SLA",
        "",
        f"- **Tasa de Ingesta Exitosa (HTTP 200):** {success_ingest}/{total_docs} ({success_ingest / total_docs * 100:.1f}%)",
        f"- **Precisión Global de Entidades:** {precision_hits}/{precision_total} ({precision_hits / precision_total * 100:.1f}%)",
        f"- **Detección Forense de Elementos Visuales:** {visual_hits}/{visual_total} ({visual_hits / max(1, visual_total) * 100:.1f}%)",
        f"- **Latencia P50 (Mediana):** {p50:.2f} ms",
        f"- **Latencia P95:** {p95:.2f} ms",
        "",
        "---",
        "",
        "## 2. Diagnóstico de Anomalías y Truncamiento de Entidades",
        "",
    ]

    truncation_cases = [r for r in results_log if r.get("truncations")]
    if truncation_cases:
        lines.append(f"Se detectaron **{len(truncation_cases)} documentos** con truncamiento o extracción incompleta de entidades personales:")
        lines.append("")
        for tc in truncation_cases[:15]:
            lines.append(f"- **{tc['filename']}** ({tc['categoria']}):")
            for t_msg in tc['truncations']:
                lines.append(f"  • {t_msg}")
        if len(truncation_cases) > 15:
            lines.append(f"- ... y {len(truncation_cases) - 15} documentos adicionales con anomalías similares.")
    else:
        lines.append("No se detectaron problemas de truncamiento.")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. Desglose de Desempeño por Formato y Categoría")
    lines.append("")
    lines.append("| ID | Archivo | Ext | Categoría | Carril | Latencia (ms) | Aciertos | Estado |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results_log[:40]:
        st = "✅ OK" if not r.get("truncations") and r.get("status_http") == 200 else "⚠️ Parcial"
        lines.append(f"| {r.get('id')} | {r.get('filename')} | {r.get('extension')} | {r.get('categoria')} | {r.get('carril')} | {r.get('duracion_ms')} | {r.get('hits')} | {st} |")
    if len(results_log) > 40:
        lines.append(f"| ... | ({len(results_log) - 40} archivos más evaluados con éxito) | | | | | | |")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Reporte generado con éxito en: {REPORT_PATH}")
    print(f"Resumen: Ingesta {success_ingest}/100, Precisión {precision_hits}/{precision_total}, P50={p50:.1f}ms, P95={p95:.1f}ms")


if __name__ == "__main__":
    run_massive_audit()
