import io
import pytest
from pathlib import Path
import pymupdf

from app.domain.models import MetadatoImagen, ResultadoPagina, Evidence
from app.domain.enums import MetodoExtraccion, TipoPagina, EstadoCobertura
from app.services.markdown_service import (
    generate_page_indexed_markdown,
    get_or_create_page_indexed_markdown,
)
from app.services.cache_service import set_l1_cache, get_l1_cache, L1DocumentEntry
from app.services.image_service import classify_image_semantics
from app.services.chat_service import process_chat_query


def test_markdown_page_indexing_delimiters():
    """Verifica que el servicio en memoria envuelva cada página con las etiquetas invisibles estándar."""
    pdf_path = Path("tests/fixtures/digital_contrato.pdf")
    pdf_bytes = pdf_path.read_bytes()

    visual_meta = {
        1: [
            MetadatoImagen(
                id_imagen="img_1_01",
                pagina=1,
                bbox=[50.0, 50.0, 200.0, 100.0],
                area_ratio=0.03,
                clasificacion_semantica="diagrama",
                descripcion_visual="Figura 1: Organigrama Institucional",
            )
        ]
    }

    markdown_result = generate_page_indexed_markdown(
        pdf_bytes=pdf_bytes,
        metadatos_visuales_por_pagina=visual_meta,
    )

    assert "<!-- INICIO_PAGINA_1 -->" in markdown_result
    assert "<!-- FIN_PAGINA_1 -->" in markdown_result
    assert "<!-- INICIO_PAGINA_4 -->" in markdown_result
    assert "<!-- FIN_PAGINA_4 -->" in markdown_result
    assert "ROBERTO ANTONIO JARAMILLO OSPINA" in markdown_result
    assert "Figura 1: Organigrama Institucional" in markdown_result


def test_figure_not_misidentified_as_barcode():
    """Verifica que un gráfico de barras con texto 'gráfico de barras' se clasifique como 'diagrama' y no como 'codigo_barras'."""
    img_meta = MetadatoImagen(
        id_imagen="img_chart_01",
        pagina=2,
        tipo_fisico="raster",
        bbox=[100.0, 200.0, 350.0, 280.0],
        area_ratio=0.05,
    )
    
    # Texto de la página que contiene la palabra 'barras' pero en contexto de gráfica
    page_text = "En el siguiente informe presentamos el gráfico de barras comparativo de ventas del trimestre."
    nearby_text = "Gráfico de barras: Ventas Q1 a Q4."

    semantic_class = classify_image_semantics(
        image_meta=img_meta,
        page_text=page_text,
        nearby_text=nearby_text,
        is_qr_detected=False,
    )

    assert semantic_class == "diagrama", f"Se esperaba 'diagrama', se obtuvo '{semantic_class}'"


def test_true_barcode_identification():
    """Verifica que un código de barras legítimo de radicación oficial se clasifique como 'codigo_barras'."""
    img_meta = MetadatoImagen(
        id_imagen="img_bar_01",
        pagina=1,
        tipo_fisico="raster",
        bbox=[400.0, 50.0, 580.0, 90.0],  # w=180, h=40, aspect_ratio=4.5
        area_ratio=0.02,
    )
    
    page_text = "Oficio de radicación número 2026-0045."
    nearby_text = "Radicado oficial No. 2026-0045. Código de barras de correspondencia."

    semantic_class = classify_image_semantics(
        image_meta=img_meta,
        page_text=page_text,
        nearby_text=nearby_text,
        is_qr_detected=False,
    )

    assert semantic_class == "codigo_barras", f"Se esperaba 'codigo_barras', se obtuvo '{semantic_class}'"


def test_markdown_caching_in_l1():
    """Verifica que get_or_create_page_indexed_markdown guarde y recupere el markdown de L1."""
    test_hash = "hash_markdown_cache_test_999"
    pdf_path = Path("tests/fixtures/digital_contrato.pdf")
    pdf_bytes = pdf_path.read_bytes()

    l1_entry = L1DocumentEntry(
        pdf_hash=test_hash,
        pipeline_version="2.2",
        status=EstadoCobertura.COMPLETE,
        paginas_totales=4,
        paginas_completadas=4,
        paginas_pendientes=[],
        resultados_por_pagina=[],
    )
    set_l1_cache(test_hash, l1_entry)

    # 1. Primera llamada genera y almacena
    md1 = get_or_create_page_indexed_markdown(test_hash, pdf_bytes=pdf_bytes)
    assert "<!-- INICIO_PAGINA_1 -->" in md1
    
    cached_entry = get_l1_cache(test_hash)
    assert cached_entry is not None
    assert cached_entry.documento_markdown_indexado == md1

    # 2. Segunda llamada reutiliza directamente
    md2 = get_or_create_page_indexed_markdown(test_hash)
    assert md2 == md1


def test_chat_open_question_with_mocked_llm(monkeypatch):
    """Verifica que el chatbot responda a preguntas abiertas usando el markdown indexado cuando el LLM está activo."""
    test_hash = "hash_open_question_test_111"
    pdf_path = Path("tests/fixtures/digital_contrato.pdf")
    pdf_bytes = pdf_path.read_bytes()

    l1_entry = L1DocumentEntry(
        pdf_hash=test_hash,
        pipeline_version="2.2",
        status=EstadoCobertura.COMPLETE,
        paginas_totales=4,
        paginas_completadas=4,
        paginas_pendientes=[],
        resultados_por_pagina=[],
    )
    set_l1_cache(test_hash, l1_entry)
    get_or_create_page_indexed_markdown(test_hash, pdf_bytes=pdf_bytes)

    # Mock del proveedor LLM
    class MockLLMProvider:
        name = "mock_gemini"

        def is_available(self):
            return True

        def generate_chat_response(self, prompt, system_instruction=None, temperature=0.2):
            assert "--- INICIO DEL DOCUMENTO ---" in prompt
            assert "<!-- INICIO_PAGINA_1 -->" in prompt
            assert "ROBERTO ANTONIO JARAMILLO OSPINA" in prompt
            return "El arrendatario es COMERCIALIZADORA ALIANZA GLOBAL S.A. según consta en [Página 1]."

    from app.services import providers
    monkeypatch.setattr(providers, "get_llm_provider", lambda: MockLLMProvider())

    output = process_chat_query(
        pdf_hash=test_hash,
        pregunta="¿Quién es la empresa arrendataria del local comercial?",
    )

    assert "[Página 1]" in output.citas
    assert "COMERCIALIZADORA ALIANZA GLOBAL S.A." in output.respuesta
    assert len(output.evidencias_relacionadas) >= 1
    assert output.evidencias_relacionadas[0].page == 1
