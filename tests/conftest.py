import pytest
from app.services.cache_service import in_memory_lru
from app.services.renderer_service import render_cache
from app.main import MOCK_RESULTS_STORE


from app.settings import settings


@pytest.fixture(autouse=True)
def reset_caches_and_stores(monkeypatch):
    """
    Garantiza aislamiento estricto e independencia de estado entre pruebas.
    Evita llamadas accidentales a APIs externas durante la suite de pruebas unitarias/integración.
    """
    monkeypatch.setattr(settings, "GEMINI_API_KEYS", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    in_memory_lru.clear()
    render_cache.clear()
    MOCK_RESULTS_STORE.clear()
    yield
    in_memory_lru.clear()
    render_cache.clear()
    MOCK_RESULTS_STORE.clear()
