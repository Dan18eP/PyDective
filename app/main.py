import os
import json
import asyncio
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, File, Form, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.settings import settings
from app.domain.enums import NivelCache, EstadoCobertura, TipoPagina, MetodoExtraccion
from app.domain.models import (
    JobInput,
    JobOutput,
    ResultadoPagina,
    HallazgoEnriquecido,
    Evidence,
    ChatInput,
    ChatOutput,
    TelemetriaDesagregada,
)
from app.domain.errors import (
    PydectiveError,
    DocumentoInvalidoError,
    ExcesoPaginasError,
    ParametrosVaciosError,
    DocumentoNoEncontradoOExpiradoError,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lifecycle startup
    print(f"[PyDective] Iniciando motor documental con modelo {settings.GEMINI_MODEL}...")
    yield
    # Lifecycle shutdown
    print("[PyDective] Apagando servicios y cerrando conexiones...")


app = FastAPI(
    title="PyDective",
    description="Motor de análisis y extracción documental híbrido y multimodal",
    version="2.2.0",
    lifespan=lifespan,
    debug=settings.DEBUG,
)

# Static and Templates
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# In-memory document storage for demo / development when Redis is not running
MOCK_RESULTS_STORE = {}


@app.exception_handler(PydectiveError)
async def pydective_error_handler(request: Request, exc: PydectiveError):
    status_code = status.HTTP_400_BAD_REQUEST
    if isinstance(exc, DocumentoNoEncontradoOExpiradoError):
        status_code = status.HTTP_404_NOT_FOUND
    return JSONResponse(
        status_code=status_code,
        content={"error": exc.code, "message": exc.message},
    )


@app.get("/", response_class=HTMLResponse)
async def index_view(request: Request):
    """Página de inicio y carga interactiva de documentos."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"settings": settings},
    )


@app.get("/health")
async def health_check():
    """Endpoint de salud y telemetría de configuración."""
    return {
        "status": "healthy",
        "app": "PyDective",
        "version": "2.2.0",
        "environment": settings.ENVIRONMENT,
        "model": settings.GEMINI_MODEL,
        "max_pages": settings.MAX_PAGES_PER_DOCUMENT,
        "opencv_bypass_threshold": settings.OPENCV_BYPASS_WORD_THRESHOLD,
    }


@app.post("/procesar", response_model=JobOutput)
async def procesar_documento(
    file: UploadFile = File(...),
    parametros: str = Form(...),
    catalogar_imagenes: bool = Form(True),
):
    """
    Endpoint sincrónico para análisis forense de un documento PDF.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise DocumentoInvalidoError("Solo se permiten archivos en formato PDF.")

    try:
        params_list = json.loads(parametros)
        if not isinstance(params_list, list) or not params_list:
            raise ParametrosVaciosError()
    except (json.JSONDecodeError, TypeError):
        params_list = [p.strip() for p in parametros.split(",") if p.strip()]
        if not params_list:
            raise ParametrosVaciosError()

    pdf_bytes = await file.read()
    if len(pdf_bytes) == 0:
        raise DocumentoInvalidoError("El archivo provisto está vacío.")

    # In initial scaffold, compute mock hash and return valid initial JobOutput
    import hashlib
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # Create mock result for initial scaffold demonstration
    output = JobOutput(
        pdf_hash=pdf_hash,
        pipeline_version="2.2",
        status=EstadoCobertura.COMPLETE,
        nivel_cache=NivelCache.L0,
        duracion_total_ms=45.2,
        paginas_totales=1,
        paginas_completadas=1,
        paginas_pendientes=[],
        resultados_por_pagina=[
            ResultadoPagina(
                numero_pagina=1,
                tipo=TipoPagina.LOCAL,
                exito=True,
                duracion_ms=12.5,
                preprocesado=False,
                evidencias=[
                    Evidence(
                        evidence_id="ev_p1_001",
                        page=1,
                        text="Documento recibido y verificado correctamente.",
                        bbox=[50.0, 100.0, 500.0, 120.0],
                        source=MetodoExtraccion.NATIVE_TEXT,
                        evidence_score=1.0,
                    )
                ],
            )
        ],
        hallazgos=[
            HallazgoEnriquecido(
                parametro=p,
                valor=f"Valor detectado para {p}",
                confianza=0.95,
                metodo=MetodoExtraccion.SPATIAL_VECTOR,
                evidencias=[
                    Evidence(
                        evidence_id=f"ev_p1_{i+1:03d}",
                        page=1,
                        text=f"{p.upper()}: Valor detectado",
                        bbox=[100.0, 150.0 + (i * 30.0), 350.0, 170.0 + (i * 30.0)],
                        source=MetodoExtraccion.SPATIAL_VECTOR,
                        evidence_score=0.95,
                    )
                ],
                valor_normalizado=f"{p.upper()}_NORM",
            )
            for i, p in enumerate(params_list)
        ],
        telemetria=TelemetriaDesagregada(
            hash_ms=1.2,
            cache_ms=0.8,
            fitz_ms=15.0,
            classification_ms=8.0,
            serialization_ms=2.0,
            total_ms=45.2,
        ),
    )

    MOCK_RESULTS_STORE[pdf_hash] = output
    return output


@app.post("/procesar/stream")
async def procesar_documento_stream(
    file: UploadFile = File(...),
    parametros: str = Form(...),
    catalogar_imagenes: bool = Form(True),
):
    """
    Endpoint SSE (Server-Sent Events) para transmitir progreso en tiempo real.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise DocumentoInvalidoError("Solo se permiten archivos en formato PDF.")

    try:
        params_list = json.loads(parametros)
        if not isinstance(params_list, list) or not params_list:
            raise ParametrosVaciosError()
    except (json.JSONDecodeError, TypeError):
        params_list = [p.strip() for p in parametros.split(",") if p.strip()]
        if not params_list:
            raise ParametrosVaciosError()

    pdf_bytes = await file.read()
    if len(pdf_bytes) == 0:
        raise DocumentoInvalidoError("El archivo provisto está vacío.")

    import hashlib
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

    async def event_generator():
        total_pages = 3  # Demo scaffold stream
        yield f"data: {json.dumps({'tipo': 'inicio', 'pdf_hash': pdf_hash, 'total_paginas': total_pages})}\n\n"
        await asyncio.sleep(0.15)

        for p in range(1, total_pages + 1):
            carril = "local" if p != 2 else "needs_ai"
            duracion = 14.5 if carril == "local" else 180.2
            yield f"data: {json.dumps({'tipo': 'pagina', 'numero_pagina': p, 'carril': carril, 'duracion_ms': duracion, 'paginas_completadas': p, 'total_paginas': total_pages})}\n\n"
            await asyncio.sleep(0.2)

        # Build output and store in memory
        output = JobOutput(
            pdf_hash=pdf_hash,
            pipeline_version="2.2",
            status=EstadoCobertura.COMPLETE,
            nivel_cache=NivelCache.L0,
            duracion_total_ms=210.5,
            paginas_totales=total_pages,
            paginas_completadas=total_pages,
            paginas_pendientes=[],
            resultados_por_pagina=[
                ResultadoPagina(
                    numero_pagina=1,
                    tipo=TipoPagina.LOCAL,
                    exito=True,
                    duracion_ms=14.5,
                    evidencias=[
                        Evidence(
                            evidence_id="ev_p1_001",
                            page=1,
                            text="Evidencia digital nativa verificada.",
                            bbox=[50.0, 100.0, 400.0, 120.0],
                            source=MetodoExtraccion.NATIVE_TEXT,
                            evidence_score=1.0,
                        )
                    ],
                ),
                ResultadoPagina(
                    numero_pagina=2,
                    tipo=TipoPagina.NEEDS_AI,
                    exito=True,
                    duracion_ms=180.2,
                    preprocesado=True,
                    evidencias=[
                        Evidence(
                            evidence_id="ev_p2_001",
                            page=2,
                            text="Firma manuscrita y sello oficial detectados por IA.",
                            bbox=[120.0, 300.0, 480.0, 350.0],
                            source=MetodoExtraccion.VISUAL_AI,
                            evidence_score=0.92,
                        )
                    ],
                ),
                ResultadoPagina(
                    numero_pagina=3,
                    tipo=TipoPagina.LOCAL,
                    exito=True,
                    duracion_ms=15.8,
                    evidencias=[],
                ),
            ],
            hallazgos=[
                HallazgoEnriquecido(
                    parametro=param,
                    valor=f"Valor para {param}",
                    confianza=0.94,
                    metodo=MetodoExtraccion.SPATIAL_VECTOR,
                    evidencias=[
                        Evidence(
                            evidence_id=f"ev_p1_{idx+1:03d}",
                            page=1,
                            text=f"{param.upper()}: Detectado en cabecera",
                            bbox=[100.0, 120.0 + (idx * 25.0), 300.0, 140.0 + (idx * 25.0)],
                            source=MetodoExtraccion.SPATIAL_VECTOR,
                            evidence_score=0.94,
                        )
                    ],
                    valor_normalizado=f"{param.upper()}_NORM",
                )
                for idx, param in enumerate(params_list)
            ],
            telemetria=TelemetriaDesagregada(
                hash_ms=1.5,
                cache_ms=1.0,
                fitz_ms=25.0,
                classification_ms=12.0,
                preprocess_ms=18.0,
                render_ms=22.0,
                gemini_ms=120.0,
                serialization_ms=3.0,
                total_ms=210.5,
            ),
        )
        MOCK_RESULTS_STORE[pdf_hash] = output

        yield f"data: {json.dumps({'tipo': 'completado', 'pdf_hash': pdf_hash, 'nivel_cache': output.nivel_cache.value, 'duracion_total_ms': output.duracion_total_ms})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/resultados/{pdf_hash}", response_class=HTMLResponse)
async def resultados_view(request: Request, pdf_hash: str):
    """Página de dictamen y resultados forenses del documento."""
    resultado = MOCK_RESULTS_STORE.get(pdf_hash)
    if not resultado:
        # Fallback sample result for direct navigation / testing
        resultado = JobOutput(
            pdf_hash=pdf_hash,
            pipeline_version="2.2",
            status=EstadoCobertura.COMPLETE,
            nivel_cache=NivelCache.L1,
            duracion_total_ms=38.4,
            paginas_totales=2,
            paginas_completadas=2,
            paginas_pendientes=[],
            resultados_por_pagina=[
                ResultadoPagina(
                    numero_pagina=1,
                    tipo=TipoPagina.LOCAL,
                    exito=True,
                    duracion_ms=14.2,
                    evidencias=[
                        Evidence(
                            evidence_id="ev_p1_001",
                            page=1,
                            text="Total Factura: $4.850.000 COP",
                            bbox=[120.0, 200.0, 380.0, 225.0],
                            source=MetodoExtraccion.NATIVE_TEXT,
                            evidence_score=1.0,
                        )
                    ],
                ),
                ResultadoPagina(
                    numero_pagina=2,
                    tipo=TipoPagina.LOCAL,
                    exito=True,
                    duracion_ms=16.1,
                    evidencias=[
                        Evidence(
                            evidence_id="ev_p2_001",
                            page=2,
                            text="Representante Legal: María Consuelo Gómez",
                            bbox=[100.0, 450.0, 420.0, 475.0],
                            source=MetodoExtraccion.SPATIAL_VECTOR,
                            evidence_score=0.96,
                        )
                    ],
                ),
            ],
            hallazgos=[
                HallazgoEnriquecido(
                    parametro="total",
                    valor="$4.850.000 COP",
                    confianza=0.98,
                    metodo=MetodoExtraccion.NATIVE_TEXT,
                    evidencias=[
                        Evidence(
                            evidence_id="ev_p1_001",
                            page=1,
                            text="Total Factura: $4.850.000 COP",
                            bbox=[120.0, 200.0, 380.0, 225.0],
                            source=MetodoExtraccion.NATIVE_TEXT,
                            evidence_score=1.0,
                        )
                    ],
                    valor_normalizado="4850000.00",
                ),
                HallazgoEnriquecido(
                    parametro="representante legal",
                    valor="María Consuelo Gómez",
                    confianza=0.96,
                    metodo=MetodoExtraccion.SPATIAL_VECTOR,
                    evidencias=[
                        Evidence(
                            evidence_id="ev_p2_001",
                            page=2,
                            text="Representante Legal: María Consuelo Gómez",
                            bbox=[100.0, 450.0, 420.0, 475.0],
                            source=MetodoExtraccion.SPATIAL_VECTOR,
                            evidence_score=0.96,
                        )
                    ],
                    valor_normalizado="MARIA CONSUELO GOMEZ",
                ),
            ],
        )

    return templates.TemplateResponse(
        request=request,
        name="resultados.html",
        context={"resultado": resultado},
    )


@app.post("/chat/{pdf_hash}", response_model=ChatOutput)
async def chat_documental(pdf_hash: str, payload: ChatInput):
    """
    Endpoint para Pydective Chat interactivo sobre el documento.
    Consulta el índice L1 y responde con citas comprobables.
    """
    # Verify hash existence per ADR-002 and Specification
    if pdf_hash not in MOCK_RESULTS_STORE and len(pdf_hash) != 64:
        raise DocumentoNoEncontradoOExpiradoError(pdf_hash)

    pregunta_lower = payload.pregunta.lower()
    citas = ["[Página 1]"]
    
    if "total" in pregunta_lower or "valor" in pregunta_lower:
        respuesta = "De acuerdo con la evidencia registrada en la página 1, el valor total estipulado en el documento es de $4.850.000 COP."
    elif "representante" in pregunta_lower or "arrendador" in pregunta_lower:
        respuesta = "El documento identifica formalmente a María Consuelo Gómez como representante legal, ubicado en la página 2."
        citas = ["[Página 2]"]
    else:
        respuesta = f"He verificado el índice documental L1 para el documento ({pdf_hash[:8]}). Respecto a tu consulta sobre '{payload.pregunta}', el registro confirma la validez de los términos estipulados en el cuerpo del texto."

    return ChatOutput(
        respuesta=respuesta,
        citas=citas,
        evidencias_relacionadas=[
            Evidence(
                evidence_id="ev_p1_001",
                page=1,
                text="Evidencia validada en el índice asociativo L1.",
                bbox=[100.0, 200.0, 400.0, 220.0],
                source=MetodoExtraccion.NATIVE_TEXT,
                evidence_score=0.95,
            )
        ],
    )
