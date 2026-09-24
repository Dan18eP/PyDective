import pytest
from app.domain.models import Evidence, MetadatoImagen
from app.domain.enums import MetodoExtraccion, EstadoCobertura
from app.services.cache_service import set_l1_cache, L1DocumentEntry
from app.services.markdown_search_service import (
    deterministic_search,
    get_relevant_page_slices,
    _is_structural_toc_line,
)


@pytest.fixture
def sample_multi_page_document():
    pdf_hash = "hash_sample_multi_page_doc_999"
    markdown_content = (
        "<!-- INICIO_PAGINA_1 -->\n"
        "# MANUAL DE GESTIÓN Y ESPECIFICACIONES TÉCNICAS\n"
        "## TABLA DE CONTENIDO\n"
        "Módulo I: Alcance y Partes del Proyecto ............. 2\n"
        "Módulo II: Cronograma, Hitos de Avance y Entregas .... 4\n"
        "Módulo III: Verificación Forense y Catalogación ....... 5\n"
        "<!-- FIN_PAGINA_1 -->\n\n"
        "<!-- INICIO_PAGINA_2 -->\n"
        "# MÓDULO I: ALCANCE Y PARTES\n"
        "Entre los suscritos, INGENIERÍA Y CONSTRUCCIONES DEL NORTE S.A. (Contratista) y "
        "BANCO DE COLOMBIA (Cliente / Contratante).\n\n"
        "## RESTRICCIONES Y OBLIGACIONES\n"
        "Queda estrictamente prohibido divulgar planos confidenciales sin autorización escrita.\n"
        "[Elemento Visual: Logotipo institucional del contratante | Coordenadas: [30.0, 30.0, 150.0, 80.0]]\n"
        "<!-- FIN_PAGINA_2 -->\n\n"
        "<!-- INICIO_PAGINA_4 -->\n"
        "# MÓDULO II: CRONOGRAMA E HITOS DE AVANCE\n"
        "El cronograma de trabajo comprende 3 hitos obligatorios:\n"
        "1. Hito 1: Entrega de planos estructurales en Semana 4.\n"
        "2. Hito 2: Cimentación y pruebas de carga en Semana 12.\n"
        "3. Hito 3: Entrega final de obra y liquidación en Semana 24.\n\n"
        "[Elemento Visual: Diagrama de Gantt del cronograma de obra | Coordenadas: [50.0, 250.0, 520.0, 450.0]]\n"
        "[Elemento Visual: Código QR de radicación oficial | Coordenadas: [450.0, 700.0, 550.0, 800.0]]\n"
        "<!-- FIN_PAGINA_4 -->"
    )
    l1_entry = L1DocumentEntry(
        pdf_hash=pdf_hash,
        pipeline_version="2.2",
        status=EstadoCobertura.COMPLETE,
        paginas_totales=3,
        paginas_completadas=3,
        paginas_pendientes=[],
        resultados_por_pagina=[],
        documento_markdown_indexado=markdown_content,
    )
    set_l1_cache(pdf_hash, l1_entry)
    return pdf_hash


def test_is_structural_toc_line_detection():
    assert _is_structural_toc_line("Módulo II: Cronograma de Obra ............. 14") is True
    assert _is_structural_toc_line("Capítulo 1: Introducción 5") is True
    assert _is_structural_toc_line("## TABLA DE CONTENIDO") is True
    assert _is_structural_toc_line("Módulo I: Alcance Módulo II: Cronograma") is True
    assert _is_structural_toc_line("El cronograma comprende 3 hitos obligatorios:") is False
    assert _is_structural_toc_line("CLÁUSULA CUARTA: PROHIBICIONES Y SANCIONES") is False


def test_visual_query_describes_meaning_and_content(sample_multi_page_document):
    """Verifica que 'qué significan las imágenes' devuelva el desglose real en 0 tokens."""
    out = deterministic_search(sample_multi_page_document, "¿Qué significan las imágenes?")
    assert out is not None
    assert "[Página 2]" in out.citas or "[Página 4]" in out.citas
    assert "logotipo institucional" in out.respuesta.lower() or "diagrama de gantt" in out.respuesta.lower()
    assert "código qr" in out.respuesta.lower() or "radicación oficial" in out.respuesta.lower()


def test_schedule_query_skips_toc_and_extracts_real_milestones(sample_multi_page_document):
    """Verifica que 'cuáles son los hitos del cronograma' ignore la TOC de Pág 1 y extraiga los hitos de Pág 4."""
    out = deterministic_search(sample_multi_page_document, "¿Cuáles son los hitos del cronograma?")
    assert out is not None
    assert "[Página 4]" in out.citas
    # Debe contener los hitos reales, no solo el título del índice
    assert "semana 4" in out.respuesta.lower() or "hito 1" in out.respuesta.lower() or "planos estructurales" in out.respuesta.lower()


def test_restrictions_found_in_technical_or_legal_doc(sample_multi_page_document):
    out = deterministic_search(sample_multi_page_document, "¿Cuáles son las restricciones u obligaciones?")
    assert out is not None
    assert "[Página 2]" in out.citas
    assert "prohibido divulgar planos" in out.respuesta.lower() or "confidenciales" in out.respuesta.lower()


def test_targeted_page_slicing_token_reduction(sample_multi_page_document):
    """Verifica que get_relevant_page_slices extraiga solo la página más relevante (Página 4 para cronograma)."""
    slice_text = get_relevant_page_slices(sample_multi_page_document, "cuáles son los hitos y cronograma", max_pages=1)
    assert "<!-- INICIO_PAGINA_4 -->" in slice_text
    assert "<!-- INICIO_PAGINA_1 -->" not in slice_text  # Debe descartar la página de la TOC
    assert len(slice_text) < 1500  # Máximo ~300 tokens vs documento entero
