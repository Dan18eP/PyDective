import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.settings import settings
from app.domain.models import TelemetriaDesagregada
from app.services.benchmark_service import BenchmarkDocumentResult, BenchmarkSummary

client = TestClient(app)


def test_telemetria_desagregada_fields_and_types():
    """US-24: Verificación de precisión y presencia de todos los campos en TelemetriaDesagregada."""
    telem = TelemetriaDesagregada(
        hash_ms=1.23,
        cache_ms=0.45,
        fitz_ms=12.50,
        classification_ms=8.10,
        preprocess_ms=0.0,
        retrieval_ms=15.20,
        render_ms=0.0,
        gemini_ms=0.0,
        serialization_ms=2.15,
        total_ms=39.63,
    )

    dump = telem.model_dump()
    expected_fields = [
        "hash_ms",
        "cache_ms",
        "fitz_ms",
        "classification_ms",
        "preprocess_ms",
        "retrieval_ms",
        "render_ms",
        "gemini_ms",
        "serialization_ms",
        "total_ms",
    ]
    for field in expected_fields:
        assert field in dump
        assert isinstance(dump[field], float)


def test_health_check_endpoint_contract():
    """US-24: Endpoint GET /health entrega versión 2.2.0, modelo canónico y límites operativos."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["app"] == "PyDective"
    assert data["version"] == "2.2.0"
    assert data["environment"] == settings.ENVIRONMENT
    assert data["model"] == settings.GEMINI_MODEL
    assert data["max_pages"] == 20
    assert data["opencv_bypass_threshold"] == settings.OPENCV_BYPASS_WORD_THRESHOLD


def test_benchmark_models_structure():
    """US-25: Estructura de modelos de resumen de benchmark y auditoría de SLA."""
    doc_res = BenchmarkDocumentResult(
        name="digital_factura.pdf",
        pages=1,
        carril_predominante="local",
        gemini_calls=0,
        latency_ms=45.2,
        findings_count=3,
        precision=1.0,
        recall=1.0,
    )

    summary = BenchmarkSummary(
        total_documents=1,
        total_pages=1,
        total_gemini_calls=0,
        latency_p50_ms=45.2,
        latency_p95_ms=45.2,
        l0_latency_ms=0.25,
        l1_latency_ms=0.35,
        sla_l0_ok=True,
        sla_l1_ok=True,
        sla_digital_p95_ok=True,
        cumple_regla_oro_anti_sobreingenieria=True,
        document_results=[doc_res],
    )

    assert summary.sla_l0_ok is True
    assert summary.sla_l1_ok is True
    assert summary.cumple_regla_oro_anti_sobreingenieria is True
    assert len(summary.document_results) == 1
