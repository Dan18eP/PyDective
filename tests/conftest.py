import pytest
from app.services.cache_service import in_memory_lru
from app.services.renderer_service import render_cache
from app.main import MOCK_RESULTS_STORE


@pytest.fixture(autouse=True)
def reset_caches_and_stores():
    """
    Garantiza aislamiento estricto e independencia de estado entre pruebas.
    """
    in_memory_lru.clear()
    render_cache.clear()
    MOCK_RESULTS_STORE.clear()
    yield
    in_memory_lru.clear()
    render_cache.clear()
    MOCK_RESULTS_STORE.clear()
