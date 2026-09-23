from pathlib import Path
import concurrent.futures
import time
import pymupdf
import pytest

from app.services.renderer_service import (
    render_page_to_webp,
    get_or_render_page_webp,
    prefetch_page_render_async,
    render_cache,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_us11_direct_webp_render_without_secondary_scaling():
    # US-11 Escenario 1: Renderizado directo a WebP max_dim=1024 en un solo paso
    pdf_path = FIXTURES_DIR / "escaneo_inclinado_skew.pdf"
    doc = pymupdf.open(str(pdf_path))
    page = doc[0]

    t0 = time.perf_counter()
    webp_bytes = render_page_to_webp(page, max_dim=1024, quality=75)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert len(webp_bytes) > 0
    # WebP magic header check: RIFF....WEBP
    assert webp_bytes[:4] == b"RIFF"
    assert webp_bytes[8:12] == b"WEBP"
    doc.close()


def test_us11_cache_buffer_reuse_in_retries():
    # US-11 Escenario 2: Reutilización de buffer en retries (Un único render por página)
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    dummy_hash = "hash_test_retry_123"

    render_cache.clear(dummy_hash)

    # Primera llamada: Renderiza y almacena en caché
    buf1 = get_or_render_page_webp(page, dummy_hash, 1, max_dim=1024, quality=75)
    assert render_cache.get_render_count(dummy_hash, 1) == 1

    # Segunda llamada (simulación de retry por otra API key): Reutiliza buffer en memoria
    buf2 = get_or_render_page_webp(page, dummy_hash, 1, max_dim=1024, quality=75)
    assert buf1 == buf2
    # El conteo de renders reales no debe aumentar
    assert render_cache.get_render_count(dummy_hash, 1) == 1

    render_cache.clear(dummy_hash)
    doc.close()


def test_us11_prefetch_in_background_thread():
    # US-11 Escenario 3: Prefetch de WebP en segundo plano con ThreadPoolExecutor
    pdf_path = FIXTURES_DIR / "digital_contrato.pdf"
    doc = pymupdf.open(str(pdf_path))
    page2 = doc[1]
    dummy_hash = "hash_test_prefetch_456"

    render_cache.clear(dummy_hash)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    future = prefetch_page_render_async(page2, dummy_hash, 2, executor, max_dim=1024, quality=75)
    assert isinstance(future, concurrent.futures.Future)

    # Esperar el resultado del prefetch
    buf = future.result(timeout=2.0)
    assert len(buf) > 0
    assert render_cache.get(dummy_hash, 2) is not None

    executor.shutdown(wait=False)
    render_cache.clear(dummy_hash)
    doc.close()
