from pathlib import Path
import json
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.domain.enums import NivelCache, EstadoCobertura
from app.services.cache_service import in_memory_lru

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def setup_function():
    # Limpiar caché antes de cada prueba de integración
    in_memory_lru.clear()


def test_epic5_l0_instant_cache_hit_on_repeated_query():
    # US-14: Consulta L0 en < 20 ms ante peticiones idénticas repetidas
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists()

    # 1. Petición inicial (Miss frío)
    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, nit"}
        res1 = client.post("/procesar", files=files, data=data)

    assert res1.status_code == 200
    out1 = res1.json()
    assert out1["nivel_cache"] == NivelCache.NONE.value

    # 2. Petición idéntica inmediata (Hit L0)
    t0 = time.perf_counter()
    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, nit"}
        res2 = client.post("/procesar", files=files, data=data)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert res2.status_code == 200
    out2 = res2.json()
    assert out2["nivel_cache"] == NivelCache.L0.value
    assert out2["pdf_hash"] == out1["pdf_hash"]
    assert len(out2["hallazgos"]) == len(out1["hallazgos"])
    assert elapsed_ms < 50.0  # Incluyendo overhead HTTP local


def test_epic5_l1_document_cache_reuse_for_new_parameters():
    # US-15: Reutilización de L1 ante nuevos parámetros sin reabrir PyMuPDF ni IA
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"

    # 1. Primera consulta: total, nit
    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, nit"}
        res1 = client.post("/procesar", files=files, data=data)
    assert res1.status_code == 200

    # 2. Segunda consulta: mismos documento pero nuevos parámetros (e.g. subtotal, desconocido)
    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, subtotal"}
        res2 = client.post("/procesar", files=files, data=data)

    assert res2.status_code == 200
    out2 = res2.json()
    # Debe resolver desde L1
    assert out2["nivel_cache"] == NivelCache.L1.value
    assert out2["pdf_hash"] == res1.json()["pdf_hash"]


def test_epic5_stream_serves_l0_instantly():
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"

    # 1. Poblar L0 con petición estándar
    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total"}
        client.post("/procesar", files=files, data=data)

    # 2. Invocar streaming para la misma consulta
    with open(pdf_path, "rb") as f:
        files = {"file": ("factura.pdf", f, "application/pdf")}
        data = {"parametros": "total"}
        response = client.post("/procesar/stream", files=files, data=data)

    assert response.status_code == 200
    lines = [line.strip() for line in response.text.split("\n") if line.startswith("data:")]
    assert len(lines) >= 3

    init_event = json.loads(lines[0].replace("data:", "").strip())
    assert init_event["tipo"] == "inicio"
    assert init_event.get("nivel_cache") == "L0"

    complete_event = json.loads(lines[-1].replace("data:", "").strip())
    assert complete_event["tipo"] == "completado"
    assert complete_event.get("nivel_cache") == "L0"
