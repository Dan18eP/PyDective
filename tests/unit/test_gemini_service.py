from pathlib import Path
import pytest

from app.domain.enums import MetodoExtraccion
from app.services.gemini_service import (
    build_canonical_genai_config,
    invoke_gemini_multimodal_page,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_us12_canonical_config_low_latency():
    # US-12 Escenario 1: Configuración canónica para baja latencia
    config = build_canonical_genai_config()
    assert config is not None
    assert config.temperature == 0.0
    assert config.thinking_config.thinking_budget == 0
    assert config.response_mime_type == "application/json"


def test_us12_page_failure_isolation():
    # US-12 Escenario 2: Aislamiento estricto de fallo por página
    # Un error por imagen corrupta en la página 4 debe encapsularse con exito=False sin elevar excepción
    corrupt_image = b"CORRUPT_IMAGE_BYTES"
    result = invoke_gemini_multimodal_page(
        image_bytes=corrupt_image,
        page_number=4,
        parameters=["total", "fecha"],
        mock_mode=False,
    )
    assert result.numero_pagina == 4
    assert result.exito is False
    assert result.error is not None
    assert "página 4" in result.error
    assert len(result.hallazgos) == 0


def test_us12_multimodal_extraction_structure():
    # Extracción multimodal con evidencias y metadatos
    dummy_webp = b"RIFF....WEBPVP8X...."
    result = invoke_gemini_multimodal_page(
        image_bytes=dummy_webp,
        page_number=1,
        parameters=["total", "fecha", "nit"],
        mock_mode=True,
    )
    assert result.numero_pagina == 1
    assert result.exito is True
    assert result.error is None
    assert len(result.hallazgos) == 3

    for h in result.hallazgos:
        assert h.metodo == MetodoExtraccion.VISUAL_AI
        assert len(h.evidencias) == 1
        ev = h.evidencias[0]
        assert ev.evidence_id.startswith("ev_p1_ai_")
        assert ev.page == 1
        assert ev.source == MetodoExtraccion.VISUAL_AI
        assert 0.50 <= ev.evidence_score <= 1.00
        assert h.valor_normalizado is not None
