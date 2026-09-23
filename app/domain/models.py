from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.domain.enums import TipoPagina, NivelCache, MetodoExtraccion, EstadoCobertura


class Evidence(BaseModel):
    evidence_id: str
    page: int
    text: str
    bbox: List[float] = Field(
        default_factory=list,
        description="Coordenadas [x0, y0, x1, y1] en puntos PDF"
    )
    source: MetodoExtraccion = MetodoExtraccion.NATIVE_TEXT
    evidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Score determinista de calidad y proximidad"
    )


class HallazgoEnriquecido(BaseModel):
    parametro: str
    valor: str
    confianza: float = Field(ge=0.0, le=1.0)
    metodo: MetodoExtraccion
    evidencias: List[Evidence] = Field(default_factory=list)
    valor_normalizado: Optional[str] = None
    formato_detectado: Optional[str] = None


class MetadatoImagen(BaseModel):
    id_imagen: str
    pagina: int
    tipo_fisico: str = "raster"
    bbox: List[float]
    area_ratio: float
    clasificacion_semantica: Optional[str] = None


class ResultadoPagina(BaseModel):
    numero_pagina: int
    tipo: TipoPagina
    exito: bool = True
    error: Optional[str] = None
    duracion_ms: float = 0.0
    preprocesado: bool = False
    metadatos_visuales: List[MetadatoImagen] = Field(default_factory=list)
    evidencias: List[Evidence] = Field(default_factory=list)


class JobInput(BaseModel):
    parametros: List[str] = Field(
        min_length=1,
        description="Lista de parámetros o entidades a detectar en el documento"
    )
    catalogar_imagenes: bool = Field(
        default=True,
        description="Indica si se inventarían sellos, firmas y logos visuales"
    )


class TelemetriaDesagregada(BaseModel):
    hash_ms: float = 0.0
    cache_ms: float = 0.0
    fitz_ms: float = 0.0
    classification_ms: float = 0.0
    preprocess_ms: float = 0.0
    render_ms: float = 0.0
    retrieval_ms: float = 0.0
    gemini_ms: float = 0.0
    merge_ms: float = 0.0
    serialization_ms: float = 0.0
    total_ms: float = 0.0


class JobOutput(BaseModel):
    pdf_hash: str
    pipeline_version: str = "2.2"
    status: EstadoCobertura = EstadoCobertura.COMPLETE
    nivel_cache: NivelCache = NivelCache.NONE
    duracion_total_ms: float = 0.0
    paginas_totales: int = 0
    paginas_completadas: int = 0
    paginas_pendientes: List[int] = Field(default_factory=list)
    resultados_por_pagina: List[ResultadoPagina] = Field(default_factory=list)
    hallazgos: List[HallazgoEnriquecido] = Field(default_factory=list)
    telemetria: TelemetriaDesagregada = Field(default_factory=TelemetriaDesagregada)


class ChatMessage(BaseModel):
    role: str = Field(description="'user' o 'assistant'")
    content: str
    timestamp: Optional[str] = None


class ChatInput(BaseModel):
    pregunta: str = Field(min_length=1)
    historial: List[ChatMessage] = Field(default_factory=list)


class ChatOutput(BaseModel):
    respuesta: str
    citas: List[str] = Field(
        default_factory=list,
        description="Citas formateadas para la UI, ej: ['Página 7']"
    )
    evidencias_relacionadas: List[Evidence] = Field(default_factory=list)
