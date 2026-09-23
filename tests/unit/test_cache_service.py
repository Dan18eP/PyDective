import time
import pytest
from app.domain.enums import NivelCache, EstadoCobertura, MetodoExtraccion, TipoPagina
from app.domain.models import JobOutput, ResultadoPagina, HallazgoEnriquecido, Evidence, TelemetriaDesagregada
from app.services.cache_service import (
    InMemoryLRUCacheService,
    build_l0_key,
    get_l0_cache,
    set_l0_cache,
    L1DocumentEntry,
    get_l1_cache,
    set_l1_cache,
    resolve_from_l1,
    evaluate_and_create_l2_cache,
    get_l2_cache,
    invalidate_l2_cache,
)


def test_us14_l0_hit_instantaneous_and_versioned():
    # US-14: Caché L0 instantánea y versionado de namespace
    pdf_hash = "hash_l0_test_123"
    query_hash = "qhash_total_nit"
    v22 = "2.2"

    dummy_out = JobOutput(
        pdf_hash=pdf_hash,
        pipeline_version=v22,
        status=EstadoCobertura.COMPLETE,
        nivel_cache=NivelCache.L0,
        duracion_total_ms=12.5,
        paginas_totales=1,
        paginas_completadas=1,
        hallazgos=[
            HallazgoEnriquecido(
                parametro="total",
                valor="$ 9.579.500 COP",
                confianza=0.98,
                metodo=MetodoExtraccion.SPATIAL_VECTOR,
            )
        ],
    )

    set_l0_cache(pdf_hash, query_hash, dummy_out, pipeline_version=v22)

    # 1. Hit en L0 responde en < 20 ms
    t0 = time.perf_counter()
    cached = get_l0_cache(pdf_hash, query_hash, pipeline_version=v22)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert cached is not None
    assert cached.nivel_cache == NivelCache.L0
    assert cached.pdf_hash == pdf_hash
    assert len(cached.hallazgos) == 1
    assert cached.hallazgos[0].parametro == "total"
    assert elapsed_ms < 20.0

    # 2. Versionado de namespace: Versión 2.3 produce MISS natural
    cached_v23 = get_l0_cache(pdf_hash, query_hash, pipeline_version="2.3")
    assert cached_v23 is None


def test_us15_l1_associative_index_and_incremental():
    # US-15: Caché L1 con Cobertura y Reutilización Incremental
    pdf_hash = "hash_l1_doc_456"
    ev_total = Evidence(
        evidence_id="ev_p1_001",
        page=1,
        text="TOTAL: $ 5.000.000",
        bbox=[100, 200, 250, 220],
        source=MetodoExtraccion.SPATIAL_VECTOR,
        evidence_score=0.95,
    )
    ev_canon = Evidence(
        evidence_id="ev_p1_002",
        page=1,
        text="CANON: $ 2.500.000",
        bbox=[100, 230, 250, 250],
        source=MetodoExtraccion.SPATIAL_VECTOR,
        evidence_score=0.92,
    )

    l1_entry = L1DocumentEntry(
        pdf_hash=pdf_hash,
        pipeline_version="2.2",
        status=EstadoCobertura.COMPLETE,
        paginas_totales=2,
        paginas_completadas=2,
        paginas_pendientes=[],
        indice_asociativo={
            "total": [ev_total],
            "canon": [ev_canon],
        },
        hallazgos_previos=[],
    )

    set_l1_cache(pdf_hash, l1_entry)

    # Reutilización de L1 completo ante nuevos parámetros en < 50 ms
    t0 = time.perf_counter()
    out = resolve_from_l1(l1_entry, ["canon", "desconocido"], pdf_hash, "qhash_new_param")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert out is not None
    assert out.nivel_cache == NivelCache.L1
    assert elapsed_ms < 50.0
    findings = {h.parametro: h for h in out.hallazgos}
    assert "canon" in findings
    assert findings["canon"].confianza == 0.92
    assert findings["canon"].metodo == MetodoExtraccion.CACHE_L1
    assert "desconocido" in findings


def test_us16_in_memory_lru_limits_and_eviction():
    # US-16: Fallback en Memoria LRU Doblemente Acotado
    # Crear un LRU pequeño para verificar el desalojo
    lru = InMemoryLRUCacheService(max_documents=3, max_bytes=1000)

    lru.set_raw("k1", b"12345")
    lru.set_raw("k2", b"67890")
    lru.set_raw("k3", b"abcde")
    assert lru.current_count == 3

    # Acceder k1 para moverlo al final
    _ = lru.get_raw("k1")

    # Insertar k4 debe desalojar el más antiguo (k2)
    lru.set_raw("k4", b"fghij")
    assert lru.current_count == 3
    assert lru.get_raw("k2") is None
    assert lru.get_raw("k1") is not None
    assert lru.get_raw("k3") is not None
    assert lru.get_raw("k4") is not None


def test_us19_l2_token_safeguard_and_cascade_invalidation():
    # US-19: Caché contextual de proveedor L2
    pdf_hash = "hash_l2_test_789"

    # 1. Menos de 32.768 tokens -> Omite creación
    l2_ptr = evaluate_and_create_l2_cache(pdf_hash, estimated_tokens=15000)
    assert l2_ptr is None

    # 2. Igual o superior a 32.768 tokens -> Crea puntero
    l2_ptr_valid = evaluate_and_create_l2_cache(pdf_hash, estimated_tokens=45000)
    assert l2_ptr_valid is not None
    assert "cached_contents" in l2_ptr_valid

    # 3. Invalidación en cascada al escribir L1
    entry = L1DocumentEntry(
        pdf_hash=pdf_hash,
        paginas_totales=1,
        paginas_completadas=1,
    )
    # Al llamar a set_l1_cache, se invalida L2 automáticamente
    set_l1_cache(pdf_hash, entry)
    assert get_l2_cache(pdf_hash) is None
