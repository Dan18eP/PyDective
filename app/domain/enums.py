from enum import Enum


class EstadoKey(str, Enum):
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    EXHAUSTED = "exhausted"
    INVALID = "invalid"


class TipoPagina(str, Enum):
    LOCAL = "local"
    NEEDS_AI = "needs_ai"
    EMPTY = "empty"


class NivelCache(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    NONE = "none"


class MetodoExtraccion(str, Enum):
    NATIVE_TEXT = "native_text"
    SPATIAL_VECTOR = "spatial_vector"
    VISUAL_AI = "visual_ai"
    CACHE_L0 = "cache_l0"
    CACHE_L1 = "cache_l1"


class TipoEntidad(str, Enum):
    FECHA = "fecha"
    MONEDA = "moneda"
    NUMERO = "numero"
    TEXTO = "texto"
    IDENTIFICADOR = "identificador"


class EstadoCobertura(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
