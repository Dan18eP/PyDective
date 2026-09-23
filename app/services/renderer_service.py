from typing import Optional, Dict, Tuple
import threading
import concurrent.futures
import time
import pymupdf


class RenderCache:
    """
    Caché en memoria indexada por (pdf_hash, page_number) para reutilizar buffers WebP
    en caso de reintentos y evitar re-renderizados duplicados (US-11 Escenario 2).
    """
    _instance: Optional["RenderCache"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._cache: Dict[Tuple[str, int], bytes] = {}
        self._render_counts: Dict[Tuple[str, int], int] = {}
        self._inner_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "RenderCache":
        with cls._lock:
            if cls._instance is None:
                cls._instance = RenderCache()
            return cls._instance

    def get(self, pdf_hash: str, page_number: int) -> Optional[bytes]:
        with self._inner_lock:
            return self._cache.get((pdf_hash, page_number))

    def put(self, pdf_hash: str, page_number: int, data: bytes) -> None:
        with self._inner_lock:
            key = (pdf_hash, page_number)
            self._cache[key] = data
            self._render_counts[key] = self._render_counts.get(key, 0) + 1

    def get_render_count(self, pdf_hash: str, page_number: int) -> int:
        with self._inner_lock:
            return self._render_counts.get((pdf_hash, page_number), 0)

    def clear(self, pdf_hash: Optional[str] = None) -> None:
        with self._inner_lock:
            if pdf_hash is None:
                self._cache.clear()
                self._render_counts.clear()
            else:
                keys_to_del = [k for k in self._cache.keys() if k[0] == pdf_hash]
                for k in keys_to_del:
                    self._cache.pop(k, None)
                    self._render_counts.pop(k, None)


render_cache = RenderCache.get_instance()


def render_page_to_webp(
    page: pymupdf.Page,
    max_dim: int = 1024,
    quality: int = 75,
) -> bytes:
    """
    Renderiza una página directamente a WebP a escala máx 1024 px usando fitz.Matrix en C (US-11 Escenario 1).
    Evita duplicación de memoria y dependencias de reescalado secundario en Pillow.
    """
    rect = page.rect
    width = rect.width
    height = rect.height

    if width <= 0 or height <= 0:
        scale = 1.0
    else:
        scale = min(max_dim / width, max_dim / height)

    mat = pymupdf.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    webp_bytes = pix.pil_tobytes("webp", quality=quality)
    return webp_bytes


def get_or_render_page_webp(
    page: pymupdf.Page,
    pdf_hash: str,
    page_number: int,
    max_dim: int = 1024,
    quality: int = 75,
) -> bytes:
    """
    Obtiene el buffer WebP de la caché o lo genera si es la primera vez (US-11 Escenario 2).
    Garantiza un único render por página.
    """
    cached = render_cache.get(pdf_hash, page_number)
    if cached is not None:
        return cached

    rendered = render_page_to_webp(page, max_dim=max_dim, quality=quality)
    render_cache.put(pdf_hash, page_number, rendered)
    return rendered


def prefetch_page_render_async(
    page: pymupdf.Page,
    pdf_hash: str,
    page_number: int,
    executor: concurrent.futures.ThreadPoolExecutor,
    max_dim: int = 1024,
    quality: int = 75,
) -> concurrent.futures.Future:
    """
    Despacha el renderizado WebP en segundo plano a un ThreadPoolExecutor (US-11 Escenario 3).
    """
    return executor.submit(
        get_or_render_page_webp,
        page,
        pdf_hash,
        page_number,
        max_dim,
        quality,
    )
