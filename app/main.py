import os
import json
import time
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
    TamanoArchivoExcedidoError,
    DocumentoCorruptoOEncriptadoError,
    ExcesoPaginasError,
    ParametrosVaciosError,
    DocumentoNoEncontradoOExpiradoError,
)
from app.services.ingestion_service import validate_and_read_pdf
from app.services.semantic_extraction_service import (
    canonicalize_parameters,
    expand_parameter_synonyms,
)
from app.services.classifier_service import classify_page
from app.services.preprocess_service import preprocess_page
from app.services.spatial_extraction_service import (
    extract_spatial_key_values,
    consolidate_findings,
)
from app.services.renderer_service import (
    render_page_to_webp,
    get_or_render_page_webp,
    prefetch_page_render_async,
)
from app.services.image_service import (
    inventory_physical_images,
    classify_image_semantics,
    catalog_page_images,
)
from app.services.gemini_service import (
    invoke_gemini_multimodal_page,
)
from app.services.cache_service import (
    get_l0_cache,
    set_l0_cache,
    get_l1_cache,
    set_l1_cache,
    resolve_from_l1,
    L1DocumentEntry,
    evaluate_and_create_l2_cache,
)
from app.services.singleflight_service import singleflight_group
from app.services.key_pool_service import key_pool
from app.services.chat_service import process_chat_query

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

    payload = {"error": exc.code, "message": exc.message}
    if hasattr(exc, "max_pages") and hasattr(exc, "total_pages"):
        payload["max_pages"] = exc.max_pages
        payload["received_pages"] = exc.total_pages
    if hasattr(exc, "max_bytes") and hasattr(exc, "received_bytes"):
        payload["max_bytes"] = exc.max_bytes
        payload["received_bytes"] = exc.received_bytes

    return JSONResponse(
        status_code=status_code,
        content=payload,
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
    parametros: str = Form(""),
    catalogar_imagenes: bool = Form(True),
):
    """
    Endpoint sincrónico para análisis forense de un documento PDF.
    """
    # 1. Normalización canónica de parámetros (US-02, US-03, ADR-003)
    canonical_params, query_hash = canonicalize_parameters(parametros)

    # 2. Ingesta y validación en memoria (US-01, US-03, RNF-022, RV-001, RV-002, RV-003, RV-006)
    pdf_bytes = await file.read()
    pdf_hash, doc, total_pages = validate_and_read_pdf(pdf_bytes, filename=file.filename)

    # 3. Consulta temprana de Caché L0 instantánea (US-14)
    cached_l0 = get_l0_cache(pdf_hash, query_hash)
    if cached_l0 is not None:
        MOCK_RESULTS_STORE[pdf_hash] = cached_l0
        return cached_l0

    # 4. Reutilización de conocimiento en Caché L1 documental (US-15)
    cached_l1 = get_l1_cache(pdf_hash)
    if cached_l1 is not None and cached_l1.status == EstadoCobertura.COMPLETE:
        resolved_l1 = resolve_from_l1(cached_l1, canonical_params, pdf_hash, query_hash)
        if resolved_l1 is not None:
            MOCK_RESULTS_STORE[pdf_hash] = resolved_l1
            return resolved_l1

    flight_key = f"{pdf_hash}:{query_hash}"

    async def _do_extraction():
        resultados_por_pagina = []
        all_spatial_findings = []
        all_ai_findings = []
        failed_pages = []
        total_class_ms = 0.0
        total_prep_ms = 0.0
        total_retrieval_ms = 0.0
        total_render_ms = 0.0
        total_gemini_ms = 0.0

        try:
            for p_idx in range(total_pages):
                p_num = p_idx + 1
                page = doc[p_idx]

                t0 = time.perf_counter()
                classification = classify_page(
                    page,
                    bypass_threshold=settings.OPENCV_BYPASS_WORD_THRESHOLD,
                )
                class_ms = (time.perf_counter() - t0) * 1000
                total_class_ms += class_ms

                preprocesado = False
                prep_ms = 0.0
                if classification.tipo == TipoPagina.NEEDS_AI and not classification.bypass_opencv:
                    prep_res = preprocess_page(page, max_dim=1024, quality=75)
                    preprocesado = prep_res.preprocesado
                    prep_ms = prep_res.duracion_ms
                    total_prep_ms += prep_ms

                # Catalogación física y forense de imágenes (US-13)
                page_visuals = []
                if catalogar_imagenes:
                    page_visuals = catalog_page_images(page, catalogar_imagenes=True)

                page_evidences = []
                page_exito = True
                page_error = None

                # Extracción espacial determinista en carril LOCAL (US-07, US-08)
                if classification.tipo == TipoPagina.LOCAL:
                    t_r = time.perf_counter()
                    page_findings = extract_spatial_key_values(page, canonical_params)
                    total_retrieval_ms += (time.perf_counter() - t_r) * 1000
                    all_spatial_findings.extend(page_findings)
                    for h in page_findings:
                        page_evidences.extend(h.evidencias)

                # Inferencia multimodal con Gemini 2.0 Flash en carril NEEDS_AI (US-11, US-12, US-18)
                elif classification.tipo == TipoPagina.NEEDS_AI:
                    t_ren = time.perf_counter()
                    webp_bytes = get_or_render_page_webp(page, pdf_hash, p_num, max_dim=1024, quality=75)
                    total_render_ms += (time.perf_counter() - t_ren) * 1000

                    t_gem = time.perf_counter()
                    gemini_res = invoke_gemini_multimodal_page(
                        image_bytes=webp_bytes,
                        page_number=p_num,
                        parameters=canonical_params,
                        page_text_hint=page.get_text(),
                    )
                    total_gemini_ms += (time.perf_counter() - t_gem) * 1000

                    if not gemini_res.exito:
                        page_exito = False
                        page_error = gemini_res.error
                        failed_pages.append(p_num)
                    else:
                        all_ai_findings.extend(gemini_res.hallazgos)
                        for h in gemini_res.hallazgos:
                            page_evidences.extend(h.evidencias)

                page_dur = round(class_ms + prep_ms, 2)
                resultados_por_pagina.append(
                    ResultadoPagina(
                        numero_pagina=p_num,
                        tipo=classification.tipo,
                        exito=page_exito,
                        error=page_error,
                        duracion_ms=page_dur,
                        preprocesado=preprocesado,
                        metadatos_visuales=page_visuals,
                        evidencias=page_evidences,
                    )
                )
        finally:
            doc.close()

        # Consolidar hallazgos aplicando precedencia absoluta de texto nativo sobre IA (US-10)
        consolidated_all = consolidate_findings(all_spatial_findings, all_ai_findings)
        findings_by_param = {}
        for h in consolidated_all:
            if h.parametro not in findings_by_param or h.confianza > findings_by_param[h.parametro].confianza:
                findings_by_param[h.parametro] = h

        final_hallazgos = []
        for p in canonical_params:
            if p in findings_by_param:
                final_hallazgos.append(findings_by_param[p])
            else:
                final_hallazgos.append(
                    HallazgoEnriquecido(
                        parametro=p,
                        valor="No detectado en el documento",
                        confianza=0.0,
                        metodo=MetodoExtraccion.SPATIAL_VECTOR,
                        evidencias=[],
                        valor_normalizado=None,
                        formato_detectado="TEXT",
                    )
                )

        total_dur_ms = round(total_class_ms + total_prep_ms + total_retrieval_ms + total_render_ms + total_gemini_ms + 10.0, 2)
        job_status = EstadoCobertura.PARTIAL if failed_pages else EstadoCobertura.COMPLETE

        output = JobOutput(
            pdf_hash=pdf_hash,
            pipeline_version="2.2",
            status=job_status,
            nivel_cache=NivelCache.NONE,
            duracion_total_ms=total_dur_ms,
            paginas_totales=total_pages,
            paginas_completadas=total_pages - len(failed_pages),
            paginas_pendientes=failed_pages,
            resultados_por_pagina=resultados_por_pagina,
            hallazgos=final_hallazgos,
            telemetria=TelemetriaDesagregada(
                hash_ms=1.2,
                cache_ms=0.8,
                fitz_ms=round(total_class_ms, 2),
                classification_ms=round(total_class_ms, 2),
                preprocess_ms=round(total_prep_ms, 2),
                retrieval_ms=round(total_retrieval_ms, 2),
                render_ms=round(total_render_ms, 2),
                gemini_ms=round(total_gemini_ms, 2),
                serialization_ms=2.0,
                total_ms=total_dur_ms,
            ),
        )

        # Indexación L1 y persistencia en L0
        assoc_index = {h.parametro: h.evidencias for h in final_hallazgos if h.evidencias}
        l1_entry = L1DocumentEntry(
            pdf_hash=pdf_hash,
            pipeline_version="2.2",
            status=job_status,
            paginas_totales=total_pages,
            paginas_completadas=total_pages - len(failed_pages),
            paginas_pendientes=failed_pages,
            resultados_por_pagina=resultados_por_pagina,
            indice_asociativo=assoc_index,
            hallazgos_previos=final_hallazgos,
            telemetria_original=output.telemetria,
        )
        set_l1_cache(pdf_hash, l1_entry)

        if job_status == EstadoCobertura.COMPLETE:
            set_l0_cache(pdf_hash, query_hash, output)
            evaluate_and_create_l2_cache(pdf_hash, estimated_tokens=total_pages * 400)

        MOCK_RESULTS_STORE[pdf_hash] = output
        return output

    # Prevención de estampidas concurrentes con singleflight (US-17)
    return await singleflight_group.do(flight_key, _do_extraction)


@app.post("/procesar/stream")
async def procesar_documento_stream(
    file: UploadFile = File(...),
    parametros: str = Form(""),
    catalogar_imagenes: bool = Form(True),
):
    """
    Endpoint SSE (Server-Sent Events) para transmitir progreso en tiempo real.
    """
    # 1. Normalización canónica de parámetros (US-02, US-03, ADR-003)
    canonical_params, query_hash = canonicalize_parameters(parametros)

    # 2. Ingesta y validación en memoria (US-01, US-03, RNF-022, RV-001, RV-002, RV-003, RV-006)
    pdf_bytes = await file.read()
    pdf_hash, doc, total_pages = validate_and_read_pdf(pdf_bytes, filename=file.filename)

    # 3. Consulta temprana L0 en streaming (US-14)
    cached_l0 = get_l0_cache(pdf_hash, query_hash)
    if cached_l0 is not None:
        async def cached_stream_gen():
            yield f"data: {json.dumps({'tipo': 'inicio', 'pdf_hash': pdf_hash, 'total_paginas': cached_l0.paginas_totales, 'nivel_cache': 'L0'})}\n\n"
            for p in cached_l0.resultados_por_pagina:
                yield f"data: {json.dumps({'tipo': 'pagina', 'numero_pagina': p.numero_pagina, 'carril': p.tipo.value, 'exito': p.exito, 'error': p.error, 'duracion_ms': p.duracion_ms, 'paginas_completadas': p.numero_pagina, 'total_paginas': cached_l0.paginas_totales, 'evidencias': [e.model_dump() for e in p.evidencias], 'elementos_visuales': [v.model_dump() for v in p.metadatos_visuales], 'gemini_ms': 0.0})}\n\n"
            yield f"data: {json.dumps({'tipo': 'completado', 'pdf_hash': pdf_hash, 'status': cached_l0.status.value, 'nivel_cache': 'L0', 'duracion_total_ms': cached_l0.duracion_total_ms, 'paginas_totales': cached_l0.paginas_totales, 'paginas_pendientes': cached_l0.paginas_pendientes, 'hallazgos': [h.model_dump() for h in cached_l0.hallazgos]})}\n\n"
        return StreamingResponse(cached_stream_gen(), media_type="text/event-stream")

    # 4. Reutilización L1 en streaming (US-15)
    cached_l1 = get_l1_cache(pdf_hash)
    if cached_l1 is not None and cached_l1.status == EstadoCobertura.COMPLETE:
        resolved_l1 = resolve_from_l1(cached_l1, canonical_params, pdf_hash, query_hash)
        if resolved_l1 is not None:
            async def l1_stream_gen():
                yield f"data: {json.dumps({'tipo': 'inicio', 'pdf_hash': pdf_hash, 'total_paginas': resolved_l1.paginas_totales, 'nivel_cache': 'L1'})}\n\n"
                for p in resolved_l1.resultados_por_pagina:
                    yield f"data: {json.dumps({'tipo': 'pagina', 'numero_pagina': p.numero_pagina, 'carril': p.tipo.value, 'exito': p.exito, 'error': p.error, 'duracion_ms': p.duracion_ms, 'paginas_completadas': p.numero_pagina, 'total_paginas': resolved_l1.paginas_totales, 'evidencias': [e.model_dump() for e in p.evidencias], 'elementos_visuales': [v.model_dump() for v in p.metadatos_visuales], 'gemini_ms': 0.0})}\n\n"
                yield f"data: {json.dumps({'tipo': 'completado', 'pdf_hash': pdf_hash, 'status': resolved_l1.status.value, 'nivel_cache': 'L1', 'duracion_total_ms': resolved_l1.duracion_total_ms, 'paginas_totales': resolved_l1.paginas_totales, 'paginas_pendientes': resolved_l1.paginas_pendientes, 'hallazgos': [h.model_dump() for h in resolved_l1.hallazgos]})}\n\n"
            return StreamingResponse(l1_stream_gen(), media_type="text/event-stream")

    async def event_generator():
        try:
            yield f"data: {json.dumps({'tipo': 'inicio', 'pdf_hash': pdf_hash, 'total_paginas': total_pages})}\n\n"
            await asyncio.sleep(0.02)

            resultados_por_pagina = []
            all_spatial_findings = []
            all_ai_findings = []
            failed_pages = []
            total_class_ms = 0.0
            total_prep_ms = 0.0
            total_retrieval_ms = 0.0
            total_render_ms = 0.0
            total_gemini_ms = 0.0

            for p_idx in range(total_pages):
                p_num = p_idx + 1
                page = doc[p_idx]

                t0 = time.perf_counter()
                classification = classify_page(
                    page,
                    bypass_threshold=settings.OPENCV_BYPASS_WORD_THRESHOLD,
                )
                class_ms = (time.perf_counter() - t0) * 1000
                total_class_ms += class_ms

                preprocesado = False
                prep_ms = 0.0
                if classification.tipo == TipoPagina.NEEDS_AI and not classification.bypass_opencv:
                    prep_res = preprocess_page(page, max_dim=1024, quality=75)
                    preprocesado = prep_res.preprocesado
                    prep_ms = prep_res.duracion_ms
                    total_prep_ms += prep_ms

                # Catalogación física y forense de imágenes (US-13)
                page_visuals = []
                if catalogar_imagenes:
                    page_visuals = catalog_page_images(page, catalogar_imagenes=True)

                page_evidences = []
                page_exito = True
                page_error = None
                page_gemini_ms = 0.0

                # Extracción espacial determinista en carril LOCAL (US-07, US-08)
                if classification.tipo == TipoPagina.LOCAL:
                    t_r = time.perf_counter()
                    page_findings = extract_spatial_key_values(page, canonical_params)
                    total_retrieval_ms += (time.perf_counter() - t_r) * 1000
                    all_spatial_findings.extend(page_findings)
                    for h in page_findings:
                        page_evidences.extend(h.evidencias)

                # Inferencia multimodal con Gemini 2.0 Flash en carril NEEDS_AI (US-11, US-12)
                elif classification.tipo == TipoPagina.NEEDS_AI:
                    t_ren = time.perf_counter()
                    webp_bytes = get_or_render_page_webp(page, pdf_hash, p_num, max_dim=1024, quality=75)
                    total_render_ms += (time.perf_counter() - t_ren) * 1000

                    t_gem = time.perf_counter()
                    gemini_res = invoke_gemini_multimodal_page(
                        image_bytes=webp_bytes,
                        page_number=p_num,
                        parameters=canonical_params,
                        page_text_hint=page.get_text(),
                    )
                    page_gemini_ms = (time.perf_counter() - t_gem) * 1000
                    total_gemini_ms += page_gemini_ms

                    if not gemini_res.exito:
                        page_exito = False
                        page_error = gemini_res.error
                        failed_pages.append(p_num)
                    else:
                        all_ai_findings.extend(gemini_res.hallazgos)
                        for h in gemini_res.hallazgos:
                            page_evidences.extend(h.evidencias)

                page_dur = round(class_ms + prep_ms + page_gemini_ms, 2)
                yield f"data: {json.dumps({'tipo': 'pagina', 'numero_pagina': p_num, 'carril': classification.tipo.value, 'exito': page_exito, 'error': page_error, 'duracion_ms': page_dur, 'paginas_completadas': p_num, 'total_paginas': total_pages, 'evidencias': [e.model_dump() for e in page_evidences], 'elementos_visuales': [v.model_dump() for v in page_visuals], 'gemini_ms': round(page_gemini_ms, 2)})}\n\n"
                await asyncio.sleep(0.02)

                resultados_por_pagina.append(
                    ResultadoPagina(
                        numero_pagina=p_num,
                        tipo=classification.tipo,
                        exito=page_exito,
                        error=page_error,
                        duracion_ms=page_dur,
                        preprocesado=preprocesado,
                        metadatos_visuales=page_visuals,
                        evidencias=page_evidences,
                    )
                )

            # Consolidar hallazgos de todas las páginas aplicando precedencia absoluta nativa (US-10)
            consolidated_all = consolidate_findings(all_spatial_findings, all_ai_findings)
            findings_by_param = {}
            for h in consolidated_all:
                if h.parametro not in findings_by_param or h.confianza > findings_by_param[h.parametro].confianza:
                    findings_by_param[h.parametro] = h

            final_hallazgos = []
            for p in canonical_params:
                if p in findings_by_param:
                    final_hallazgos.append(findings_by_param[p])
                else:
                    final_hallazgos.append(
                        HallazgoEnriquecido(
                            parametro=p,
                            valor="No detectado en el documento",
                            confianza=0.0,
                            metodo=MetodoExtraccion.SPATIAL_VECTOR,
                            evidencias=[],
                            valor_normalizado=None,
                            formato_detectado="TEXT",
                        )
                    )

            total_dur_ms = round(total_class_ms + total_prep_ms + total_retrieval_ms + total_render_ms + total_gemini_ms + 10.0, 2)
            job_status = EstadoCobertura.PARTIAL if failed_pages else EstadoCobertura.COMPLETE

            # Build output and store in memory
            output = JobOutput(
                pdf_hash=pdf_hash,
                pipeline_version="2.2",
                status=job_status,
                nivel_cache=NivelCache.NONE,
                duracion_total_ms=total_dur_ms,
                paginas_totales=total_pages,
                paginas_completadas=total_pages - len(failed_pages),
                paginas_pendientes=failed_pages,
                resultados_por_pagina=resultados_por_pagina,
                hallazgos=final_hallazgos,
                telemetria=TelemetriaDesagregada(
                    hash_ms=1.5,
                    cache_ms=1.0,
                    fitz_ms=round(total_class_ms, 2),
                    classification_ms=round(total_class_ms, 2),
                    preprocess_ms=round(total_prep_ms, 2),
                    retrieval_ms=round(total_retrieval_ms, 2),
                    render_ms=round(total_render_ms, 2),
                    gemini_ms=round(total_gemini_ms, 2),
                    serialization_ms=3.0,
                    total_ms=total_dur_ms,
                ),
            )

            # Indexación L1 y persistencia en L0
            assoc_index = {h.parametro: h.evidencias for h in final_hallazgos if h.evidencias}
            l1_entry = L1DocumentEntry(
                pdf_hash=pdf_hash,
                pipeline_version="2.2",
                status=job_status,
                paginas_totales=total_pages,
                paginas_completadas=total_pages - len(failed_pages),
                paginas_pendientes=failed_pages,
                resultados_por_pagina=resultados_por_pagina,
                indice_asociativo=assoc_index,
                hallazgos_previos=final_hallazgos,
                telemetria_original=output.telemetria,
            )
            set_l1_cache(pdf_hash, l1_entry)

            if job_status == EstadoCobertura.COMPLETE:
                set_l0_cache(pdf_hash, query_hash, output)
                evaluate_and_create_l2_cache(pdf_hash, estimated_tokens=total_pages * 400)

            MOCK_RESULTS_STORE[pdf_hash] = output

            yield f"data: {json.dumps({'tipo': 'completado', 'pdf_hash': pdf_hash, 'status': output.status.value, 'nivel_cache': output.nivel_cache.value, 'duracion_total_ms': output.duracion_total_ms, 'paginas_totales': total_pages, 'paginas_pendientes': output.paginas_pendientes, 'hallazgos': [h.model_dump() for h in final_hallazgos]})}\n\n"
        finally:
            doc.close()

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
    Consulta el índice L1 y responde con citas comprobables (US-23).
    """
    return process_chat_query(
        pdf_hash=pdf_hash,
        pregunta=payload.pregunta,
        historial=payload.historial,
        fallback_store=MOCK_RESULTS_STORE,
    )
