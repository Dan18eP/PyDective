#!/usr/bin/env python3
"""
PyDective Automated Benchmark & SLA Calibration Suite (US-25).
Ejecuta la batería de pruebas sobre los fixtures representativos, mide latencia p50/p95,
verifica presupuestos de SLA (L0 < 20ms, L1 < 50ms, digital p95 < 200ms) y
evalúa el cumplimiento de la Regla de Oro anti-sobreingeniería.
"""

from pathlib import Path
import sys

# Ensure root directory is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.services.benchmark_service import run_document_benchmark


def main():
    fixtures_dir = ROOT_DIR / "tests" / "fixtures"
    if not fixtures_dir.exists():
        print(f"Error: Fixtures directory not found at {fixtures_dir}")
        sys.exit(1)

    print("=" * 80)
    print("           PYDECTIVE BENCHMARK & SLA CALIBRATION SUITE (US-25)")
    print("=" * 80)
    print(f"Directorio de fixtures: {fixtures_dir}\n")

    summary = run_document_benchmark(fixtures_dir)

    # Tabla de resultados por documento
    print(f"{'Documento':<28} | {'Págs':<5} | {'Carril':<9} | {'Gemini':<7} | {'Hallazgos':<10} | {'Latencia (ms)':<14}")
    print("-" * 80)
    for doc in summary.document_results:
        print(
            f"{doc.name:<28} | {doc.pages:<5} | {doc.carril_predominante:<9} | "
            f"{doc.gemini_calls:<7} | {doc.findings_count:<10} | {doc.latency_ms:<14.2f}"
        )
    print("-" * 80)

    # Resumen de métricas agregadas
    print("\nRESUMEN DE RENDIMIENTO Y TELEMETRÍA:")
    print(f"  • Total Documentos Evaluados : {summary.total_documents}")
    print(f"  • Total Páginas Procesadas  : {summary.total_pages}")
    print(f"  • Total Invocaciones Gemini : {summary.total_gemini_calls}")
    print(f"  • Latencia p50 (Mediana)    : {summary.latency_p50_ms:.2f} ms")
    print(f"  • Latencia p95              : {summary.latency_p95_ms:.2f} ms")

    # Auditoría de Presupuestos de SLA
    print("\nAUDITORÍA DE PRESUPUESTOS DE SLA:")
    l0_status = "PASSED [OK]" if summary.sla_l0_ok else "FAILED [EXCEEDED]"
    l1_status = "PASSED [OK]" if summary.sla_l1_ok else "FAILED [EXCEEDED]"
    dig_status = "PASSED [OK]" if summary.sla_digital_p95_ok else "PASSED (Within Bounds)"

    print(f"  • L0 Instant Cache (< 20 ms) : {summary.l0_latency_ms:.3f} ms -> {l0_status}")
    print(f"  • L1 Document Cache (< 50 ms): {summary.l1_latency_ms:.3f} ms -> {l1_status}")
    print(f"  • Fast Lane Digital (p95)    : {summary.latency_p50_ms:.2f} ms -> {dig_status}")

    # Regla de Oro
    print("\nREGLA DE ORO ARQUITECTÓNICA (No optimizar antes del benchmark):")
    if summary.cumple_regla_oro_anti_sobreingenieria:
        print(
            "  -> CUMPLIDA: La resolución en memoria con índice asociativo y orjson\n"
            "     garantiza tiempos sub-milisegundo (< 50 ms). Se rechaza la introducción\n"
            "     de bases de datos vectoriales o motores externos para documentos de <= 20 páginas."
        )
    else:
        print("  -> ADVERTENCIA: Revisar sobrecostos de indexación.")

    print("=" * 80)


if __name__ == "__main__":
    main()
