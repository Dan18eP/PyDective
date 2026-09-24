import pytest
from app.domain.models import (
    ResultadoPagina,
    Evidence,
    HallazgoEnriquecido,
    ChatMessage,
    JobOutput,
    TelemetriaDesagregada,
)
from app.domain.enums import TipoPagina, MetodoExtraccion, EstadoCobertura, NivelCache
from app.domain.errors import DocumentoNoEncontradoOExpiradoError
from app.services.cache_service import set_l1_cache, L1DocumentEntry
from app.services.chat_service import process_chat_query


def test_chat_document_not_found_raises_404():
    """US-23 Escenario 3: Documento no encontrado o sesión expirada lanza 404 estructurado."""
    with pytest.raises(DocumentoNoEncontradoOExpiradoError) as exc_info:
        process_chat_query(
            pdf_hash="non_existent_hash_12345",
            pregunta="¿Cuál es el valor total?",
            fallback_store={},
        )
    assert exc_info.value.code == "DOCUMENT_NOT_FOUND_OR_EXPIRED"
    assert "non_existent_hash_12345" in exc_info.value.message


def test_chat_grounded_answer_with_l1_associative_index():
    """US-23 Escenario 1 y 2: Retrieval asociativo previo en L1 con citas obligatorias [Página X]."""
    test_hash = "chat_test_hash_l1_abc"
    evidence_p1 = Evidence(
        evidence_id="ev_p1_001",
        page=1,
        text="Total a pagar: $4.500.000 COP",
        bbox=[100.0, 200.0, 300.0, 220.0],
        source=MetodoExtraccion.NATIVE_TEXT,
        evidence_score=0.98,
    )
    evidence_p2 = Evidence(
        evidence_id="ev_p2_001",
        page=2,
        text="Cláusula penal: $900.000 COP por mora",
        bbox=[100.0, 400.0, 350.0, 420.0],
        source=MetodoExtraccion.SPATIAL_VECTOR,
        evidence_score=0.95,
    )

    hallazgo_total = HallazgoEnriquecido(
        parametro="total",
        valor="$4.500.000 COP",
        confianza=0.98,
        metodo=MetodoExtraccion.NATIVE_TEXT,
        evidencias=[evidence_p1],
        valor_normalizado="4500000.00",
    )
    hallazgo_clausula = HallazgoEnriquecido(
        parametro="clausula penal",
        valor="$900.000 COP",
        confianza=0.95,
        metodo=MetodoExtraccion.SPATIAL_VECTOR,
        evidencias=[evidence_p2],
        valor_normalizado="900000.00",
    )

    l1_entry = L1DocumentEntry(
        pdf_hash=test_hash,
        pipeline_version="2.2",
        status=EstadoCobertura.COMPLETE,
        paginas_totales=2,
        paginas_completadas=2,
        paginas_pendientes=[],
        resultados_por_pagina=[],
        indice_asociativo={
            "total": [evidence_p1],
            "clausula penal": [evidence_p2],
        },
        hallazgos_previos=[hallazgo_total, hallazgo_clausula],
    )
    set_l1_cache(test_hash, l1_entry)

    # Pregunta sobre clausula penal
    output = process_chat_query(
        pdf_hash=test_hash,
        pregunta="¿A cuánto asciende la cláusula penal pecuniaria?",
    )

    assert "[Página 2]" in output.citas
    assert len(output.evidencias_relacionadas) >= 1
    assert output.evidencias_relacionadas[0].evidence_id == "ev_p2_001"
    assert "900.000 COP" in output.respuesta
    assert "[Página 2]" in output.respuesta


def test_chat_explicit_decline_on_absent_data():
    """US-23 Escenario 2: Declinación explícita cuando el concepto no figura en el documento."""
    test_hash = "chat_test_hash_absent_xyz"
    evidence_p1 = Evidence(
        evidence_id="ev_p1_001",
        page=1,
        text="Total a pagar: $4.500.000 COP",
        bbox=[100.0, 200.0, 300.0, 220.0],
        source=MetodoExtraccion.NATIVE_TEXT,
        evidence_score=0.98,
    )
    l1_entry = L1DocumentEntry(
        pdf_hash=test_hash,
        pipeline_version="2.2",
        status=EstadoCobertura.COMPLETE,
        paginas_totales=1,
        paginas_completadas=1,
        paginas_pendientes=[],
        resultados_por_pagina=[],
        indice_asociativo={"total": [evidence_p1]},
        hallazgos_previos=[],
    )
    set_l1_cache(test_hash, l1_entry)

    # Preguntar por un concepto inexistente
    output = process_chat_query(
        pdf_hash=test_hash,
        pregunta="¿Cuál es la placa del vehículo involucrado?",
    )

    assert output.citas == []
    assert output.evidencias_relacionadas == []
    assert "no figura registrado" in output.respuesta


def test_chat_grounded_answer_from_fallback_store():
    """US-23: Si L1 no está en memoria pero el store de jobs contiene el documento."""
    test_hash = "chat_test_fallback_job_123"
    evidence_p1 = Evidence(
        evidence_id="ev_p1_001",
        page=1,
        text="Fecha de vencimiento: 2026-12-31",
        bbox=[100.0, 200.0, 300.0, 220.0],
        source=MetodoExtraccion.NATIVE_TEXT,
        evidence_score=0.99,
    )
    hallazgo = HallazgoEnriquecido(
        parametro="fecha vencimiento",
        valor="2026-12-31",
        confianza=0.99,
        metodo=MetodoExtraccion.NATIVE_TEXT,
        evidencias=[evidence_p1],
        valor_normalizado="2026-12-31",
    )
    job_output = JobOutput(
        pdf_hash=test_hash,
        pipeline_version="2.2",
        status=EstadoCobertura.COMPLETE,
        nivel_cache=NivelCache.NONE,
        duracion_total_ms=45.0,
        paginas_totales=1,
        paginas_completadas=1,
        paginas_pendientes=[],
        resultados_por_pagina=[],
        hallazgos=[hallazgo],
        telemetria=TelemetriaDesagregada(),
    )

    fallback_store = {test_hash: job_output}

    output = process_chat_query(
        pdf_hash=test_hash,
        pregunta="¿Cuándo es la fecha de vencimiento?",
        fallback_store=fallback_store,
    )

    assert "[Página 1]" in output.citas
    assert len(output.evidencias_relacionadas) == 1
    assert "2026-12-31" in output.respuesta


def test_chat_conceptual_parties_and_representatives_grounding():
    """Verifica que consultas conceptuales abiertas sobre 'partes y representantes' mapeen los hallazgos y citen [Página X]."""
    test_hash = "chat_test_hash_parties_legal_789"
    ev_arr = Evidence(
        evidence_id="ev_p1_arr",
        page=1,
        text="ARRENDADOR: ROBERTO ANTONIO JARAMILLO OSPINA",
        bbox=[50.0, 100.0, 300.0, 120.0],
        source=MetodoExtraccion.SPATIAL_VECTOR,
        evidence_score=0.98,
    )
    ev_rep = Evidence(
        evidence_id="ev_p1_rep",
        page=1,
        text="REPRESENTANTE LEGAL: VALERIA MONTOYA DUQUE",
        bbox=[50.0, 130.0, 350.0, 150.0],
        source=MetodoExtraccion.SPATIAL_VECTOR,
        evidence_score=0.98,
    )
    h_arr = HallazgoEnriquecido(
        parametro="arrendador",
        valor="ROBERTO ANTONIO JARAMILLO OSPINA",
        confianza=0.98,
        metodo=MetodoExtraccion.SPATIAL_VECTOR,
        evidencias=[ev_arr],
        valor_normalizado="ROBERTO ANTONIO JARAMILLO OSPINA",
    )
    h_rep = HallazgoEnriquecido(
        parametro="representante legal",
        valor="VALERIA MONTOYA DUQUE",
        confianza=0.98,
        metodo=MetodoExtraccion.SPATIAL_VECTOR,
        evidencias=[ev_rep],
        valor_normalizado="VALERIA MONTOYA DUQUE",
    )
    l1_entry = L1DocumentEntry(
        pdf_hash=test_hash,
        pipeline_version="2.2",
        status=EstadoCobertura.COMPLETE,
        paginas_totales=1,
        paginas_completadas=1,
        paginas_pendientes=[],
        resultados_por_pagina=[],
        indice_asociativo={
            "arrendador": [ev_arr],
            "representante legal": [ev_rep],
        },
        hallazgos_previos=[h_arr, h_rep],
    )
    set_l1_cache(test_hash, l1_entry)

    output = process_chat_query(
        pdf_hash=test_hash,
        pregunta="¿Cuáles son las partes y representantes identificados?",
    )

    assert "[Página 1]" in output.citas
    assert len(output.evidencias_relacionadas) >= 1
    assert "ROBERTO ANTONIO JARAMILLO OSPINA" in output.respuesta
    assert "VALERIA MONTOYA DUQUE" in output.respuesta

