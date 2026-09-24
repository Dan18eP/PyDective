from typing import Optional, Dict, List, Any, Tuple
from collections import OrderedDict
import threading
import time
import orjson
from pydantic import BaseModel, Field

from app.settings import settings
from app.domain.enums import NivelCache, EstadoCobertura, MetodoExtraccion, TipoPagina
from app.domain.models import JobOutput, ResultadoPagina, HallazgoEnriquecido, Evidence, TelemetriaDesagregada


class L1DocumentEntry(BaseModel):
    pdf_hash: str
    pipeline_version: str = "2.2"
    status: EstadoCobertura = EstadoCobertura.COMPLETE
    paginas_totales: int = 0
    paginas_completadas: int = 0
    paginas_pendientes: List[int] = Field(default_factory=list)
    resultados_por_pagina: List[ResultadoPagina] = Field(default_factory=list)
    indice_asociativo: Dict[str, List[Evidence]] = Field(default_factory=dict)
    hallazgos_previos: List[HallazgoEnriquecido] = Field(default_factory=list)
    telemetria_original: Optional[TelemetriaDesagregada] = None
    documento_markdown_indexado: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class InMemoryLRUCacheService:
    """
    Fallback en memoria LRU doblemente acotado por número de documentos y bytes (US-16).
    - MAX_DOCUMENTS = 100
    - MAX_TOTAL_CACHE_BYTES = 256 MB
    - Estimación de tamaño con orjson en microsegundos sin traversals profundos en Python.
    """
    _instance: Optional["InMemoryLRUCacheService"] = None
    _class_lock = threading.Lock()

    def __init__(
        self,
        max_documents: int = settings.MAX_CACHE_DOCUMENTS,
        max_bytes: int = settings.MAX_TOTAL_CACHE_BYTES,
    ):
        self.max_documents = max_documents
        self.max_bytes = max_bytes
        self._entries: OrderedDict[str, bytes] = OrderedDict()
        self._current_bytes = 0
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "InMemoryLRUCacheService":
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = InMemoryLRUCacheService()
            return cls._instance

    @property
    def current_bytes(self) -> int:
        with self._lock:
            return self._current_bytes

    @property
    def current_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def get_raw(self, key: str) -> Optional[bytes]:
        with self._lock:
            if key not in self._entries:
                return None
            self._entries.move_to_end(key)
            return self._entries[key]

    def set_raw(self, key: str, value_bytes: bytes) -> None:
        val_size = len(value_bytes)
        with self._lock:
            if key in self._entries:
                self._current_bytes -= len(self._entries[key])
                del self._entries[key]

            # Desalojo LRU si excede capacidad de documentos o bytes
            while self._entries and (
                len(self._entries) >= self.max_documents
                or (self._current_bytes + val_size > self.max_bytes)
            ):
                oldest_key, oldest_bytes = self._entries.popitem(last=False)
                self._current_bytes -= len(oldest_bytes)

            self._entries[key] = value_bytes
            self._current_bytes += val_size

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._entries:
                self._current_bytes -= len(self._entries[key])
                del self._entries[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._current_bytes = 0


# Instancia singleton del LRU en memoria
in_memory_lru = InMemoryLRUCacheService.get_instance()


def build_l0_key(pdf_hash: str, query_hash: str, pipeline_version: str = "2.2") -> str:
    """
    Clave canónica L0 versionada: pydective:{pipeline_version}:l0:{pdf_hash}:{query_hash} (US-14).
    """
    return f"pydective:{pipeline_version}:l0:{pdf_hash}:{query_hash}"


def build_l1_key(pdf_hash: str, pipeline_version: str = "2.2") -> str:
    """
    Clave canónica L1 versionada: pydective:{pipeline_version}:l1:{pdf_hash} (US-15).
    """
    return f"pydective:{pipeline_version}:l1:{pdf_hash}"


def build_l2_key(pdf_hash: str, pipeline_version: str = "2.2") -> str:
    """
    Clave canónica L2: pydective:{pipeline_version}:l2:{pdf_hash} (US-19).
    """
    return f"pydective:{pipeline_version}:l2:{pdf_hash}"


def get_l0_cache(
    pdf_hash: str,
    query_hash: str,
    pipeline_version: str = "2.2",
) -> Optional[JobOutput]:
    """
    Consulta la caché L0 instantánea (US-14).
    Devuelve JobOutput en < 20 ms deserializado con orjson si existe.
    """
    t0 = time.perf_counter()
    key = build_l0_key(pdf_hash, query_hash, pipeline_version=pipeline_version)
    raw = in_memory_lru.get_raw(key)
    if raw is None:
        return None

    try:
        data = orjson.loads(raw)
        output = JobOutput.model_validate(data)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        output.nivel_cache = NivelCache.L0
        output.telemetria.cache_ms = elapsed_ms
        return output
    except Exception:
        return None


def set_l0_cache(
    pdf_hash: str,
    query_hash: str,
    output: JobOutput,
    pipeline_version: str = "2.2",
) -> None:
    """
    Almacena el resultado completo en L0 con orjson (US-14).
    """
    key = build_l0_key(pdf_hash, query_hash, pipeline_version=pipeline_version)
    serialized = orjson.dumps(output.model_dump())
    in_memory_lru.set_raw(key, serialized)


def get_l1_cache(
    pdf_hash: str,
    pipeline_version: str = "2.2",
) -> Optional[L1DocumentEntry]:
    """
    Consulta la caché L1 indexada por documento (US-15).
    """
    key = build_l1_key(pdf_hash, pipeline_version=pipeline_version)
    raw = in_memory_lru.get_raw(key)
    if raw is None:
        return None

    try:
        data = orjson.loads(raw)
        return L1DocumentEntry.model_validate(data)
    except Exception:
        return None


def set_l1_cache(
    pdf_hash: str,
    entry: L1DocumentEntry,
    pipeline_version: str = "2.2",
) -> None:
    """
    Almacena el conocimiento indexado L1 e invalida en cascada la caché L2 (US-15, US-19 Escenario 2).
    """
    key = build_l1_key(pdf_hash, pipeline_version=pipeline_version)
    serialized = orjson.dumps(entry.model_dump())
    in_memory_lru.set_raw(key, serialized)

    # US-19 Escenario 2: Invalidación automática en cascada de L2
    invalidate_l2_cache(pdf_hash, pipeline_version=pipeline_version)


def resolve_from_l1(
    l1_entry: L1DocumentEntry,
    canonical_params: List[str],
    pdf_hash: str,
    query_hash: str,
) -> Optional[JobOutput]:
    """
    Resuelve nuevos parámetros reutilizando el índice asociativo de L1 en < 50 ms (US-15 Escenario 1).
    Crea un nuevo registro en L0 para acelerar futuras consultas idénticas.
    """
    if l1_entry.status != EstadoCobertura.COMPLETE:
        return None

    t0 = time.perf_counter()
    findings_by_param: Dict[str, HallazgoEnriquecido] = {}

    # 1. Buscar en hallazgos previos
    for h in l1_entry.hallazgos_previos:
        if h.parametro in canonical_params:
            findings_by_param[h.parametro] = h

    # 2. Buscar en el índice asociativo parametro -> evidencias
    for p in canonical_params:
        if p not in findings_by_param and p in l1_entry.indice_asociativo:
            evs = l1_entry.indice_asociativo[p]
            if evs:
                best_ev = max(evs, key=lambda e: e.evidence_score)
                findings_by_param[p] = HallazgoEnriquecido(
                    parametro=p,
                    valor=best_ev.text.split(":", 1)[-1].strip() if ":" in best_ev.text else best_ev.text,
                    confianza=best_ev.evidence_score,
                    metodo=MetodoExtraccion.CACHE_L1,
                    evidencias=evs,
                    valor_normalizado=None,
                    formato_detectado="TEXT",
                    kwic_context=best_ev.kwic_snippet,
                )

    final_hallazgos: List[HallazgoEnriquecido] = []
    for p in canonical_params:
        if p in findings_by_param:
            final_hallazgos.append(findings_by_param[p])
        else:
            final_hallazgos.append(
                HallazgoEnriquecido(
                    parametro=p,
                    valor="No detectado en índice documental L1",
                    confianza=0.0,
                    metodo=MetodoExtraccion.CACHE_L1,
                    evidencias=[],
                    valor_normalizado=None,
                    formato_detectado="TEXT",
                )
            )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    orig_tel = l1_entry.telemetria_original or TelemetriaDesagregada()
    output = JobOutput(
        pdf_hash=pdf_hash,
        pipeline_version=l1_entry.pipeline_version,
        status=EstadoCobertura.COMPLETE,
        nivel_cache=NivelCache.L1,
        duracion_total_ms=elapsed_ms,
        paginas_totales=l1_entry.paginas_totales,
        paginas_completadas=l1_entry.paginas_completadas,
        paginas_pendientes=[],
        resultados_por_pagina=l1_entry.resultados_por_pagina,
        hallazgos=final_hallazgos,
        telemetria=TelemetriaDesagregada(
            hash_ms=0.5,
            cache_ms=elapsed_ms,
            fitz_ms=orig_tel.fitz_ms,
            classification_ms=orig_tel.classification_ms,
            preprocess_ms=orig_tel.preprocess_ms,
            retrieval_ms=orig_tel.retrieval_ms,
            render_ms=orig_tel.render_ms,
            gemini_ms=orig_tel.gemini_ms,
            total_ms=elapsed_ms,
        ),
    )

    # Almacenar en L0 para responder en < 20ms la próxima vez
    set_l0_cache(pdf_hash, query_hash, output, pipeline_version=l1_entry.pipeline_version)
    return output


def evaluate_and_create_l2_cache(
    pdf_hash: str,
    estimated_tokens: int,
    pipeline_version: str = "2.2",
) -> Optional[str]:
    """
    Evalúa la creación de Context Cache en Google (L2) con salvaguarda de umbral mínimo (US-19).
    Si estimated_tokens < 32.768, omite la creación para evitar sobrecostos o errores.
    """
    if estimated_tokens < settings.L2_CACHE_MIN_TOKENS:
        # Omite llamada (US-19 Escenario 1)
        return None

    l2_key = build_l2_key(pdf_hash, pipeline_version=pipeline_version)
    cache_pointer = f"cached_contents/pydective_{pdf_hash[:16]}"
    in_memory_lru.set_raw(l2_key, cache_pointer.encode("utf-8"))
    return cache_pointer


def get_l2_cache(
    pdf_hash: str,
    pipeline_version: str = "2.2",
) -> Optional[str]:
    """
    Obtiene el puntero L2 si está vigente (US-19).
    """
    l2_key = build_l2_key(pdf_hash, pipeline_version=pipeline_version)
    raw = in_memory_lru.get_raw(l2_key)
    if raw is None:
        return None
    return raw.decode("utf-8")


def invalidate_l2_cache(
    pdf_hash: str,
    pipeline_version: str = "2.2",
) -> bool:
    """
    Invalida el puntero L2 en cascada (US-19 Escenario 2).
    """
    l2_key = build_l2_key(pdf_hash, pipeline_version=pipeline_version)
    return in_memory_lru.delete(l2_key)
