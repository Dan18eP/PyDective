from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.services.benchmark_service import run_document_benchmark

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_http_middleware_request_id_injection_and_propagation():
    """US-24: Middleware de observabilidad inyecta y propaga X-Request-ID y X-Response-Time-MS."""
    # 1. Petición sin cabecera previa -> el middleware genera un UUID hex
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    generated_id = response.headers["X-Request-ID"]
    assert len(generated_id) >= 16
    assert "X-Response-Time-MS" in response.headers
    assert float(response.headers["X-Response-Time-MS"]) >= 0.0

    # 2. Petición con cabecera personalizada -> el middleware preserva y propaga el ID
    custom_trace_id = "trace-corp-987654321-req"
    resp_custom = client.get("/health", headers={"X-Request-ID": custom_trace_id})
    assert resp_custom.status_code == 200
    assert resp_custom.headers["X-Request-ID"] == custom_trace_id
    assert "X-Response-Time-MS" in resp_custom.headers


def test_job_processing_emits_complete_disaggregated_telemetry():
    """US-24: El pipeline devuelve JobOutput.telemetria con todas las métricas cronometradas."""
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, nit"}
        response = client.post("/procesar", files=files, data=data)

    assert response.status_code == 200
    res_json = response.json()
    assert "telemetria" in res_json
    telem = res_json["telemetria"]

    assert telem["hash_ms"] >= 0.0
    assert telem["fitz_ms"] >= 0.0
    assert telem["classification_ms"] >= 0.0
    assert telem["retrieval_ms"] >= 0.0
    assert telem["total_ms"] > 0.0


def test_automated_benchmark_and_sla_calibration():
    """US-25: Evaluación empírica de fixtures, verificación de presupuestos de latencia y regla de oro."""
    assert FIXTURES_DIR.exists()
    summary = run_document_benchmark(FIXTURES_DIR)

    # 7 documentos representativos evaluados
    assert summary.total_documents == 7
    assert summary.total_pages >= 25

    # Verificación de SLAs
    assert summary.sla_l0_ok is True, f"L0 SLA excedido: {summary.l0_latency_ms} ms (límite 20 ms)"
    assert summary.sla_l1_ok is True, f"L1 SLA excedido: {summary.l1_latency_ms} ms (límite 50 ms)"
    assert summary.cumple_regla_oro_anti_sobreingenieria is True

    # Documentos digitales nativos puros no deben consumir llamadas a Gemini
    digital_docs = [d for d in summary.document_results if d.name in ("digital_factura.pdf", "digital_contrato.pdf")]
    for doc in digital_docs:
        assert doc.gemini_calls == 0, f"Documento digital nativo {doc.name} invocó a Gemini innecesariamente"
        assert doc.carril_predominante == "local"
