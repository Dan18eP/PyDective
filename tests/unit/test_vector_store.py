import pytest
from pathlib import Path
from unittest.mock import MagicMock
from app.services.vector_store import (
    get_or_create_vector_store,
    generate_and_save_document_markdown,
    get_document_markdown_path,
    get_document_markdown_context,
    LightweightVectorStore,
    VectorChunk,
    DATA_CONTEXT_DIR,
)
from app.domain.models import ResultadoPagina, MetadatoImagen
from app.domain.enums import TipoPagina


def test_lightweight_vector_store_bm25_ranking():
    store = LightweightVectorStore()
    md = """# [Página 1]
**Folio:** 1 de 2

## Contenido Textual Literal
El contrato de arrendamiento fue celebrado entre el arrendador Juan Pérez y el arrendatario Carlos Gómez.

---

# [Página 2]
**Folio:** 2 de 2

## Contenido Textual Literal
El canon mensual pactado corresponde a la suma de dos millones de pesos colombianos pagaderos los primeros cinco días.
"""
    store.build_from_markdown(md)
    assert len(store.chunks) >= 2

    # Consulta sobre el canon
    results = store.similarity_search("canon mensual dos millones", top_k=2)
    assert len(results) > 0
    best_chunk, score = results[0]
    assert best_chunk.page == 2
    assert "canon" in best_chunk.text.lower()
    assert score > 0.0

    # Consulta sobre los nombres de las partes
    results_partes = store.similarity_search("arrendador Juan Pérez", top_k=2)
    assert len(results_partes) > 0
    assert results_partes[0][0].page == 1


def test_markdown_generation_and_caching_lifecycle(tmp_path):
    import pymupdf

    test_hash = "test_vector_hash_abc12345"
    md_file = get_document_markdown_path(test_hash)
    if md_file.exists():
        md_file.unlink()

    # Crear PDF en memoria con 2 páginas
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Cláusula Primera: Objeto del contrato pericial forense.")
    p2 = doc.new_page()
    p2.insert_text((50, 72), "Firma y sello notarial registrado en el folio dos.")
    pdf_bytes = doc.tobytes()
    doc.close()

    mock_visual = MetadatoImagen(
        id_imagen="vis_01",
        pagina=2,
        bbox=[100.0, 500.0, 300.0, 600.0],
        area_ratio=0.15,
        clasificacion_semantica="firma_manuscrita",
    )
    res_paginas = [
        ResultadoPagina(
            numero_pagina=1,
            tipo=TipoPagina.LOCAL,
        ),
        ResultadoPagina(
            numero_pagina=2,
            tipo=TipoPagina.NEEDS_AI,
            metadatos_visuales=[mock_visual],
        ),
    ]

    try:
        # 1ra petición: Archivo no existe aún, se genera el .md y se persiste
        assert not md_file.exists()
        vstore_1, md_content_1, path_1 = get_or_create_vector_store(
            pdf_hash=test_hash,
            pdf_bytes=pdf_bytes,
            resultados_paginas=res_paginas,
        )

        assert path_1.exists()
        assert md_file.exists()
        assert f"SHA-256:** `{test_hash}`" in md_content_1
        assert "Cláusula Primera: Objeto del contrato pericial" in md_content_1
        assert "Firma_manuscrita" in md_content_1 or "firma_manuscrita" in md_content_1.lower()

        # 2da petición: Debe cargar directamente desde caché / archivo .md existente a ultra-alta velocidad
        vstore_2, md_content_2, path_2 = get_or_create_vector_store(
            pdf_hash=test_hash,
            pdf_bytes=None,  # No se requieren los bytes en la 2da petición
        )

        assert vstore_2 is vstore_1
        assert md_content_2 == md_content_1
        assert path_2 == path_1

        # Búsqueda vectorial sobre el contexto cargado
        hits = vstore_2.similarity_search("objeto del contrato pericial", top_k=1)
        assert len(hits) == 1
        assert hits[0][0].page == 1
    finally:
        if md_file.exists():
            md_file.unlink()
