import pytest
from app.domain.models import Evidence, MetadatoImagen
from app.domain.enums import MetodoExtraccion, EstadoCobertura
from app.services.cache_service import set_l1_cache, L1DocumentEntry
from app.services.markdown_search_service import deterministic_search


@pytest.fixture
def sample_indexed_document():
    pdf_hash = "hash_sample_markdown_search_123"
    markdown_content = (
        "<!-- INICIO_PAGINA_1 -->\n"
        "# CONTRATO DE ARRENDAMIENTO DE LOCAL COMERCIAL\n"
        "Entre los suscritos, ROBERTO ANTONIO JARAMILLO OSPINA (Arrendador) y "
        "DISTRIBUCIONES ANDINAS S.A.S. representada por VALERIA MONTOYA (Arrendatario / Cliente).\n\n"
        "## CLÁUSULA PRIMERA: CANON DE ARRENDAMIENTO\n"
        "El canon mensual asciende a la suma de $5.200.000 COP pagaderos los primeros 5 días.\n"
        "<!-- FIN_PAGINA_1 -->\n\n"
        "<!-- INICIO_PAGINA_2 -->\n"
        "## CLÁUSULA SEXTA: RESTRICCIONES Y PROHIBICIONES\n"
        "El arrendatario no podrá subarrendar, ni almacenar sustancias inflamables o explosivas en el inmueble.\n\n"
        "[Elemento Visual: Diagrama de distribución de planta del local comercial | Coordenadas: [50.0, 300.0, 500.0, 650.0]]\n"
        "<!-- FIN_PAGINA_2 -->"
    )
    l1_entry = L1DocumentEntry(
        pdf_hash=pdf_hash,
        pipeline_version="2.2",
        status=EstadoCobertura.COMPLETE,
        paginas_totales=2,
        paginas_completadas=2,
        paginas_pendientes=[],
        resultados_por_pagina=[],
        documento_markdown_indexado=markdown_content,
    )
    set_l1_cache(pdf_hash, l1_entry)
    return pdf_hash


def test_deterministic_search_finds_restrictions(sample_indexed_document):
    out = deterministic_search(sample_indexed_document, "¿Cuáles son las restricciones del contrato?")
    assert out is not None
    assert "[Página 2]" in out.citas
    assert "subarrendar" in out.respuesta.lower() or "prohibiciones" in out.respuesta.lower()
    assert len(out.evidencias_relacionadas) >= 1


def test_deterministic_search_finds_client_name(sample_indexed_document):
    out = deterministic_search(sample_indexed_document, "¿Cuál es el nombre del cliente o arrendatario?")
    assert out is not None
    assert "[Página 1]" in out.citas
    assert "valeria montoya" in out.respuesta.lower() or "distribuciones andinas" in out.respuesta.lower()


def test_deterministic_search_finds_diagram_existence(sample_indexed_document):
    out = deterministic_search(sample_indexed_document, "¿Tiene diagrama o gráfico?")
    assert out is not None
    assert "[Página 2]" in out.citas
    assert "diagrama" in out.respuesta.lower()


def test_deterministic_search_describes_diagram(sample_indexed_document):
    out = deterministic_search(sample_indexed_document, "¿De qué trata el diagrama?")
    assert out is not None
    assert "[Página 2]" in out.citas
    assert "distribución de planta" in out.respuesta.lower() or "planta del local" in out.respuesta.lower()


def test_deterministic_search_finds_image_location(sample_indexed_document):
    out = deterministic_search(sample_indexed_document, "¿Dónde hay una imagen?")
    assert out is not None
    assert "[Página 2]" in out.citas


def test_deterministic_search_returns_none_for_absent_concept(sample_indexed_document):
    out = deterministic_search(sample_indexed_document, "¿Cuál es el color del helicóptero?")
    assert out is None
