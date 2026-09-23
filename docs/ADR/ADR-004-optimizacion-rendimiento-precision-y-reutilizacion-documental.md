# ADR-004: Optimización de rendimiento, precisión y reutilización documental

- **Estado:** Propuesto — pendiente de validación mediante benchmark
- **Fecha:** 2026-09-23
- **Decisores:** Equipo de Arquitectura e Ingeniería Pydective
- **Extiende a:** [ADR-001: Arquitectura híbrida de extracción, caché escalonada y failover por página](file:///home/dypok/Projects/PyDective/docs/ADR/ADR-001-arquitectura-hibrida-caching-y-failover.md), [ADR-002: Preprocesamiento determinista, visión y chat documental](file:///home/dypok/Projects/PyDective/docs/ADR/ADR-002-preprocesamiento-determinista-vision-y-chat-documental.md) y [ADR-003: Extracción semántica clave-valor y enriquecimiento](file:///home/dypok/Projects/PyDective/docs/ADR/ADR-003-extraccion-semantica-clave-valor-y-enriquecimiento.md)
- **Relacionado con:** Requisitos del Sistema, PRD y Especificación Arquitectónica General
- **Etiquetas:** pydective, rendimiento, precision, benchmark, cache, retrieval, grounding, evidencia, OCR, vision, adaptive-routing

---

## 1. Contexto

La arquitectura actual de Pydective ya establece una estrategia híbrida: calcular el hash del PDF, consultar L0/L1 antes de realizar trabajo costoso, clasificar páginas localmente y enviar a IA multimodal únicamente las páginas que realmente lo requieren. ADR-001 define este orden como el flujo base y establece cachés L0/L1/L2, failover por página y límites de concurrencia. ADR-002 añade preprocesamiento determinista, catalogación visual, chat documental y resiliencia. ADR-003 incorpora extracción clave-valor, KWIC y normalización de entidades.

El objetivo de este ADR no es sustituir esas decisiones, sino endurecerlas para conseguir simultáneamente:

1. menor latencia;
2. menor trabajo de CPU, memoria y red;
3. menor cantidad de llamadas multimodales;
4. mayor precisión y trazabilidad;
5. reutilización segura de resultados parciales y completos;
6. comportamiento medible y calibrable antes de optimizar por intuición.

La arquitectura actual contiene umbrales concretos que deben calibrarse contra un corpus de validación real (tamaño de render, calidad WebP, ratios de área y presupuestos de p95). Este ADR establece la gobernanza empírica del MVP.

---

## 2. Problema

Optimizar únicamente la latencia puede provocar falsos negativos si clasificamos como `local` una página que requiere análisis visual. Optimizar únicamente la precisión puede provocar que demasiadas páginas entren al carril de IA, elevando latencia, coste y riesgo de cuota.

Además, existen cuatro riesgos específicos:

### 2.1 Reutilización incompleta de L1
L1 se indexa por `pdf_hash`, pero un documento puede quedar parcialmente procesado después de un timeout, un error de proveedor o una cuota agotada. Un estado parcial no debe comportarse como si fuera un conocimiento documental completo.

### 2.2 Preprocesamiento confundido con OCR
Deskew y Otsu limpian/alinean una imagen, pero no constituyen por sí mismos un OCR. Por tanto, una página escaneada no puede considerarse “resuelta localmente” solo porque el preprocesamiento haya mejorado su imagen.

### 2.3 Catalogación visual innecesariamente costosa
La presencia de una imagen física en un PDF no implica que haya que describirla semánticamente con IA. Logos pequeños o elementos decorativos no deben forzar inferencia multimodal en el camino feliz.

### 2.4 Umbrales no calibrados e hiper-optimización prematura
Reglas como “80 palabras”, “15% del área”, “1024 px” o scores heurísticos de confianza son hipótesis de diseño, no verdades estadísticas. Toda optimización que aumente complejidad debe respaldarse en datos reales.

---

## 3. Decisión

Se adopta una estrategia de **optimización por evidencia**, gobernada por cinco principios:

1. **Trabajo mínimo primero:** la siguiente capa solo se ejecuta cuando una señal medible demuestre que hace falta.
2. **L1 completo vs. parcial:** el estado de cobertura del documento pasa a formar parte del contrato de caché.
3. **Retrieval local antes de IA:** nuevas búsquedas y preguntas del Chat reducen el conjunto de evidencia localmente antes de enviar contexto a Gemini.
4. **Visual ≠ semántico:** primero se inventarían objetos localmente en PyMuPDF; su descripción semántica se solicita a IA solo cuando aporta valor.
5. **No optimizar antes del benchmark:** los parámetros de rendimiento y clasificación se consideran calibrables y el MVP evita la sobre-ingeniería innecesaria.

---

## 4. Flujo de ejecución revisado

El orden de ejecución oficial pasa a ser:

```text
PDF bytes
   │
   ▼
Validación rápida
   │
   ▼
SHA-256
   │
   ▼
L0: (pdf_hash, query_canonical)
   │
   ├── HIT ───────────────────────────────► HTML
   │
   ▼
L1: (pdf_hash, pipeline_version)
   │
   ├── COMPLETE ─► Retrieval local ─► nuevo L0 ─► HTML
   │
   ├── PARTIAL ──► procesar SOLO páginas pendientes
   │
   └── MISS ────► Fase A
                       │
                       ├── LOCAL ─────────────► índice/evidencia
                       │
                       ├── VISUAL METADATA ──► catálogo local (PyMuPDF)
                       │
                       └── NEEDS_AI
                               │
                               ▼
                      Deskew/Otsu selectivo
                               │
                               ▼
                     Reevaluación de señal
                               │
                       ┌───────┴────────┐
                       │                │
                    LOCAL/         NEEDS_AI
                   VALIDADO            │
                       │                ▼
                       │           Render WebP (1024px, q75)
                       │                │
                       └────────────────▼
                                      Gemini 2.0 Flash
                                         │
                                         ▼
                                Evidencias estructuradas
                                         │
                                         ▼
                                    Merge por página
                                         │
                                         ▼
                                         L1 (Redis / orjson)
                                         │
                                         ▼
                                         L0 (Redis / orjson)
```

Ningún módulo distinto de `jobs.py` debe decidir de forma autónoma escribir L0/L1 ni llamar al proveedor de IA.

---

## 5. L1 debe distinguir `complete` de `partial`

### 5.1 Nuevo contrato

L1 deberá almacenar metadatos de cobertura:

```json
{
  "pdf_hash": "sha256...",
  "pipeline_version": "2.2",
  "schema_version": "1",
  "status": "complete",
  "pages_total": 20,
  "pages_completed": 20,
  "pages_pending": [],
  "created_at": "...",
  "updated_at": "..."
}
```

Para un documento incompleto:

```json
{
  "status": "partial",
  "pages_total": 20,
  "pages_completed": 18,
  "pages_pending": [19, 20]
}
```

### 5.2 Reglas

- `complete` significa que todas las páginas requeridas por la versión de pipeline están procesadas o clasificadas con un estado final válido.
- `partial` conserva páginas exitosas, pero nunca permite afirmar que la ausencia de un hallazgo en el documento completo es concluyente.
- Una consulta sobre L1 parcial responde inmediatamente con las páginas conocidas y, cuando el dato requiera cobertura completa, el orquestador procesa exclusivamente las páginas pendientes.
- Una página con `exito=false` no se convierte en evidencia reutilizable.
- Si una página pendiente se completa posteriormente, L1 se actualiza incrementalmente.

---

## 6. Versionado de caché y evidencia

L0 y L1 no dependen únicamente del hash del PDF para evitar contaminación de esquema ante cambios de código o prompts.

### 6.1 L0
```text
L0 key = pydective:{pipeline_version}:l0:{pdf_hash}:{query_hash}
```
`query_hash` se genera a partir de parámetros canónicos: trim, `casefold`, eliminación de diacríticos NFKD, deduplicación y orden canónico.

### 6.2 L1
```text
L1 key = pydective:{pipeline_version}:l1:{pdf_hash}
```

### 6.3 Metadatos mínimos
L1 registra internamente: `pipeline_version`, `schema_version`, `model_version`, `created_at`, `updated_at`, `status`. Un cambio de versión invalida el namespace de forma natural sin requerir flush global de Redis.

---

## 7. Clasificación local basada en score de legibilidad

El umbral fijo de palabras deja de ser el único criterio. La decisión `local / empty / needs_ai` considerará múltiples señales combinadas en `readability_score`:

```text
readability_score =
    densidad_alfa
  + ratio_caracteres_validos
  + separación_lexica
  + consistencia_de_lineas
  + cobertura_textual
  - ratio_reemplazos (\ufffd)
  - caracteres_control
  - palabras_anormalmente_largas (>30 chars sin espacios)
```

- Una página con pocas palabras sigue siendo `local` si el texto presenta estructura y calidad suficiente.
- Una página con muchas palabras pasa a `needs_ai` si el texto es una capa de OCR corrupta.
- La ausencia de una keyword nunca constituye por sí sola una razón para llamar a IA.
- `get_images()` es una señal física, no una prueba de que el texto sea insuficiente.

---

## 8. Deskew/Otsu como preprocesamiento, no como sustituto de OCR

Se mantiene el principio de **Determinismo antes de IA**, pero se precisa su alcance:
- La limpieza determinista (Deskew $\pm 15^\circ$ y Otsu) optimiza la relación señal/ruido de la imagen.
- La limpieza de imagen **no se considera automáticamente extracción textual**. Si la página carece de texto digital y no hay un motor OCR local determinista ejecutable en milisegundos, pasa a Fase B (Gemini 2.0 Flash) con la imagen optimizada.
- Se conserva el estado de trazabilidad: `preprocessed=true`, `textually_resolved=true|false`.

---

## 9. Catalogación visual de dos niveles

### 9.1 Nivel 1 — Inventario físico local (PyMuPDF, 0 ms IA)
PyMuPDF detecta y registra objetos gráficos sin invocar IA:
```json
{
  "pagina": 3,
  "id_imagen": "img_p3_1",
  "tipo_fisico": "raster",
  "bbox": [120, 540, 280, 700],
  "area_ratio": 0.04
}
```

### 9.2 Nivel 2 — Semántica visual (Gemini 2.0 Flash)
La tipificación semántica (`firma_manuscrita`, `sello_oficial`, `logotipo`, `grafico_diagrama`, `fotografia`) se solicita a IA únicamente cuando:
- El usuario activa la catalogación forense (`catalogar_imagenes: bool = True`);
- Un parámetro solicitado depende de una evidencia visual;
- Una imagen supera las reglas de relevancia geométrica;
- El análisis visual sea necesario para resolver una pregunta de Pydective Chat.

Un logo decorativo pequeño no convierte automáticamente una página digital limpia en una página multimodal.

---

## 10. Índice asociativo simple en L1 (Enfoque Pragmático MVP)

Para el MVP no se implementará un motor de búsqueda complejo. Dado el límite inicial de ~20 páginas por PDF, L1 utilizará un índice asociativo simple basado en `parametro_normalizado` → `list[Evidence]`, conservando texto, bbox, página y `evidence_id`. El índice estará orientado a consultas rápidas en memoria y serialización eficiente con Redis. Su rendimiento se validará mediante benchmarks antes de establecer objetivos específicos de latencia.

```json
{
  "total": [
    { "evidence_id": "ev_p7_004", "page": 7, "text": "Total a pagar: $3.250.000", "bbox": [120, 300, 540, 345], "source": "native_text" }
  ],
  "fecha": [
    { "evidence_id": "ev_p7_002", "page": 7, "text": "Fecha: 2024-04-30", "bbox": [120, 100, 300, 130], "source": "native_text" }
  ],
  "nit": [
    { "evidence_id": "ev_p1_001", "page": 1, "text": "NIT: 900.123.456-7", "bbox": [50, 80, 250, 110], "source": "native_text" }
  ]
}
```

Eso nos da exactamente lo que queremos: búsqueda $O(1)$ aproximada sobre el índice, recuperación de evidencias y luego KWIC/clave-valor sobre un conjunto pequeño.

> **Objetivo de latencia:**
> No se prometerá *"responder en <5 ms"* como requisito a priori, ya que depende de serialización, Redis, cantidad de resultados e infraestructura.
> **Diseñado para resolución sub-decenas de milisegundos en consultas L1 sobre documentos del tamaño objetivo.** Posteriormente se medirán los percentiles p50/p95 durante el benchmark.

---

## 11. Evidence ID y Grounding Fuerte

Cada hallazgo relevante conserva una identidad de evidencia estable:
```json
{
  "evidence_id": "ev_p7_004",
  "pagina": 7,
  "source": "native_text",
  "texto": "El desembolso fue autorizado por Carlos Pérez...",
  "bbox": [120, 300, 540, 345]
}
```

Las respuestas del Chat asocian internamente cada afirmación a uno o más `evidence_id`. La interfaz muestra la cita simple por página `[Página 7]`, pero el backend mantiene la trazabilidad a la coordenada y frase exacta. Si no existe evidencia suficiente, el sistema declara explícitamente su ausencia sin alucinar.

---

## 12. Retrieval antes de Gemini en Pydective Chat

Pydective Chat **no envía automáticamente las 20 páginas completas al modelo**.

Flujo optimizado:
```text
Pregunta del usuario
   ↓
Normalización canónica
   ↓
Recuperación asociativa local sobre L1 (índice asociativo)
   ↓
Selección de evidencias mínimas suficientes (top 2-3 páginas o bloques)
   ↓
Invocación a Gemini 2.0 Flash (thinking_budget=0, streaming)
   ↓
Respuesta estructurada + Citas exactas
```

Ahorro: reduce ~80% de tokens de entrada, acelera el TTFT (<500 ms) y mitiga alucinaciones por exceso de contexto.

---

## 13. Configuración Baseline de Renderizado Multimodal (Resolución Adaptativa Pospuesta)

El MVP utilizará una configuración única de renderizado multimodal: `max_dim = 1024 px` y `WebP q75` (render directo con `fitz.Matrix` en C), salvo que el benchmark demuestre que otra combinación ofrece mejor relación precisión/latencia. La resolución adaptativa multinivel queda fuera del camino crítico del MVP y se mantiene como evolución posterior.

Flujo de procesamiento para páginas que requieren visión en el MVP:
```text
NEEDS_AI
   ↓
1024 px (WebP q75)
   ↓
Gemini 2.0 Flash
   ↓
resultado
```

> [!WARNING]
> **Distinción Crítica: Error de Infraestructura vs. Insuficiencia de Imagen**
> Un error de infraestructura de Gemini (`429 RESOURCE_EXHAUSTED`, `401/403`, timeout de red o error de conexión) **no significa que la imagen tenga poca resolución**. Reinterpretar un error de infraestructura como un fallo de calidad de imagen provocaría reintentos con mayor resolución (e.g. 1536 px), aumentando innecesariamente la carga sobre la red y la cuota.
> **Un error de infraestructura nunca deberá interpretarse automáticamente como insuficiencia de resolución.**
> 
> La resolución adaptativa tendría sentido exclusivamente ante:
> ```text
> Gemini responde exitosamente
>    ↓
> Evidencia insuficiente / baja confianza visual (< threshold)
> ```
> y **no** ante:
> ```text
> Gemini responde 429 / 401 / Timeout
> ```

---

## 14. Preprocesamiento y Renderizado

Se mantiene:
- Deskew sobre miniatura de 500 px acotado a $\pm 15^\circ$;
- Binarización de Otsu solo cuando el contraste lo exija;
- Renderizado directo en C con PyMuPDF;
- Buffer WebP en memoria generado una sola vez por página pendiente y reutilizado en retries;
- **Prefetch de WebP:** si una página se clasifica como `needs_ai` en el loop inicial, su renderizado se despacha de inmediato en segundo plano hacia el thread pool mientras continúa la clasificación del resto del PDF.

---

## 15. L2 / Google Context Cache

L2 continúa siendo una optimización complementaria y opcional:
- No se crea por defecto para todo documento.
- Requiere superar el umbral de $\ge 32.768$ tokens y que el documento justifique reconsultas multimodales.
- Toda reescritura o invalidación de L1 borra de inmediato el puntero L2 en Redis.

---

## 16. Memoria del Fallback In-Memory (Doble Límite Pragmático)

El fallback in-memory utilizará límites simples y medibles. No se realizará un cálculo profundo del tamaño de objetos Python mediante `sys.getsizeof()` (evitando deep traversals de objetos anidados en cada operación).

El tamaño de cada entrada podrá estimarse mediante:
```python
payload = orjson.dumps(document)
size = len(payload)
```

No se eligen `MAX_DOCUMENTS` y `MAX_TOTAL_CACHE_BYTES` como alternativas excluyentes, sino de forma combinada y extremadamente simple:
- `MAX_DOCUMENTS = 100`
- `MAX_DOCUMENT_CACHE_BYTES = X` (límite por documento, e.g. 5 MB)
- `MAX_TOTAL_CACHE_BYTES = Y` (presupuesto global, e.g. 256 MB)

El gestor LRU mantiene dos métricas simples:
- `document_count`
- `total_serialized_bytes`

No necesitamos un gestor sofisticado de memoria. La política exacta se calibrará durante las pruebas de carga.

---

## 17. Singleflight y Lease Renewal

Se mantiene el candado distribuido para prevenir estampidas (dogpile):
```text
lock_key: lock:pdf:{pdf_hash}
owner_id: {worker_uuid}
lease_expire_at: now + 60s
```
- Peticiones concurrentes idénticas esperan el resultado publicado en Redis mediante polling no bloqueante (100 ms).
- Una solicitud concurrente jamás inicia una segunda inferencia del mismo trabajo mientras exista un lease activo.

---

## 18. Métrica de Confianza: `evidence_score`

El índice de extracción espacial y clave-valor se denomina formalmente **`evidence_score`** en todos los contratos y métricas:
- No se presenta al usuario como *"probabilidad estadística del 96%"* sin un sustento empírico formal.
- Combina proximidad métrica (180 pt horizontal / 35 pt vertical), validación regex de entidad y origen vectorial nativo.

---

## 19. Métricas Obligatorias y Telemetría

Cada trabajo instrumenta de forma desagregada:
```text
hash_ms, cache_ms, fitz_ms, classification_ms, preprocess_ms, render_ms, retrieval_ms, gemini_ms, merge_ms, serialization_ms, total_ms
TTFR (Time To First Result)
TTFT (Time To First Token en Chat)
pages_total, pages_local, pages_empty, pages_ai, pages_failed
cache_hit, retry_count, key_failover_count, partial_result
bytes_rendered, bytes_sent_to_ai
```

---

## 20. Presupuesto de Rendimiento Oficial (MVP)

| Escenario | Presupuesto de Diseño |
|---|---:|
| Hit L0 | < 20 ms |
| Hit L1 + refiltrado local | < 50 ms |
| PDF digital ~20 páginas, caché fría (Fase A + Espacial O(N) + KWIC + orjson) | p95 < 200 ms + HTML |
| Pydective Chat TTFT (primer token en streaming) | < 600 ms |
| PDF mixto | IA solo para páginas `needs_ai` (con prefetch WebP) |
| Fallo de API key | Failover aislado sin reprocesar páginas exitosas |
| Peticiones concurrentes repetidas (Dogpile) | 1 ejecución real, N resueltas desde caché (Singleflight) |

---

## 21. Regla de Oro: No Optimizar Antes del Benchmark

### Filosofía: MVP ≠ Arquitectura Definitiva

Tenemos que construir la arquitectura suficiente para resolver el problema, no la infraestructura necesaria para resolver hipotéticamente millones de documentos.

Ahora mismo el proyecto está diseñado para:
- ~20 páginas por documento;
- 1 PDF por solicitud interactiva;
- Alcance acotado de MVP.

> [!IMPORTANT]
> **Regla de Oro Anti-Sobreingeniería:**
> **No se introducirá una optimización adicional en el MVP únicamente por intuición arquitectónica.** Toda optimización que aumente complejidad deberá justificar una mejora medible en latencia, coste, precisión o resiliencia sobre el benchmark correspondiente.

Esta regla protege al proyecto del ciclo vicioso de sobreingeniería sin sustento empírico:
```text
MVP
 ↓
más caching
 ↓
más indexing
 ↓
más workers
 ↓
más heurísticas
 ↓
más niveles de resolución
 ↓
más colas
 ↓
más servicios
```
...sin saber si realmente era necesario.

### Alcance Técnico Delimitado

| Sí necesitamos en el MVP | No necesitamos todavía (Pospuesto) |
|---|---|
| L0 | Lucene / Elasticsearch |
| L1 (`complete` vs `partial`) | Base de datos vectorial (Vector DB) |
| Evidence | Reranker sofisticado |
| Índice asociativo simple | Resolución multimodal multinivel adaptativa |
| Clasificación local + score de legibilidad | Gestor avanzado de memoria con introspección profunda |
| Deskew / Otsu selectivo (como preprocesamiento) | Arquitectura distribuida de colas de búsqueda |
| Gemini 2.0 Flash selectivo (`thinking_budget=0`) | Pipelines distribuidos de microservicios |
| Retry y failover por página | Caching predictivo especulativo |
| Singleflight contra dogpile | Reentrenamiento o fine-tuning de modelos |
| Observabilidad y telemetría desagregada | |
| Benchmark con fixtures representativos | |

---

## 22. Benchmark Obligatorio y Calibración

Antes de congelar los valores definitivos de `OPENCV_BYPASS_WORD_THRESHOLD`, umbrales de legibilidad o calidades WebP, se evaluará una suite de fixtures representativos:
- PDF digital limpio
- PDF digital complejo / tablas densas
- PDF mixto (texto + firmas/sellos)
- Escaneo limpio
- Escaneo con inclinación
- Escaneo con sombras / bajo contraste
- Capa de OCR corrupta (caracteres `\ufffd` o sin espacios)
- Facturas, contratos, actas, historias clínicas

Métricas del benchmark:
- `precision`, `recall`, `false_positive_rate`, `false_negative_rate`
- `latency_p50`, `latency_p95`, `TTFT`, `cache_hit_rate`
- `IA_calls_per_document`, `bytes_sent_to_Gemini`

---

## 23. Criterios de Aceptación del ADR-004

- [ ] L1 distingue explícitamente estados `complete` y `partial`.
- [ ] Las claves de L0 y L1 incluyen `pipeline_version`.
- [ ] El índice asociativo en L1 permite responder nuevas consultas sin reabrir PyMuPDF.
- [ ] El Chat consulta únicamente evidencias relevantes filtradas de L1 con citas `evidence_id`.
- [ ] El renderizado baseline usa 1024 px y WebP q75 en C sin resoluciones multinivel complejas.
- [ ] Errores 429/timeout no se interpretan como insuficiencia de imagen.
- [ ] El fallback in-memory valida `MAX_DOCUMENTS` y `MAX_TOTAL_CACHE_BYTES` calculados con `len(orjson.dumps())`.
- [ ] Toda optimización adicional futura se condiciona a resultados del benchmark.

---

## 24. Consecuencias

### Positivas
- Cero trabajo redundante en CPU y red.
- Cero llamadas a IA en páginas ya resueltas de documentos parciales.
- Ahorro drástico de tokens y latencia en el Chat gracias al retrieval asociativo previo.
- Blindaje total contra sobre-ingeniería innecesaria en el MVP.
- Arquitectura modular, limpia y empíricamente calibrable.

### Costes Aceptados
- Estructura de L1 ligeramente más enriquecida (`Evidence` e índice asociativo).
- Mantenimiento del corpus de fixtures para pruebas automatizadas.
- Instrumentación de métricas de telemetría en el orquestador.

---

## 25. Orden de Implementación Oficial

```text
1. Contratos y modelos de dominio (app/domain/models.py, enums.py, errors.py)
2. Normalización canónica lingüística (app/services/semantic_extraction_service.py)
3. BaseCacheService y fallback InMemoryLRUCacheService con doble límite (app/services/cache_service.py)
4. Clasificación local con PyMuPDF + legibilidad (app/services/classifier.py)
5. L1 complete/partial + versionado en Redis (app/infrastructure/redis_client.py)
6. Índice asociativo simple de texto y evidencias
7. Preprocesamiento determinista selectivo: Deskew miniatura + Otsu (app/services/preprocess_service.py)
8. Catalogación física local en PyMuPDF (app/services/image_service.py)
9. Render WebP directo a 1024px q75 + prefetch (app/services/renderer.py)
10. Integración Gemini 2.0 Flash selectivo con thinking_budget=0 (app/services/gemini_service.py)
11. Pydective Chat con retrieval local sobre L1 y streaming (app/services/chat_service.py)
12. Orquestador único y singleflight (app/services/jobs.py)
13. Borde HTTP FastAPI y streaming SSE (app/main.py)
14. Benchmark, telemetría y calibración de thresholds
```

---

## 26. Relación con ADRs Anteriores

| ADR | Responsabilidad | Relación con ADR-004 |
|---|---|---|
| ADR-001 | Arquitectura híbrida, caché L0/L1/L2 y failover | ADR-004 añade versionado, singleflight con lease y L1 complete/partial |
| ADR-002 | Deskew, Otsu, catalogación, Chat y streaming | ADR-004 acota Deskew/Otsu como preprocesamiento (no OCR) y añade retrieval previo al Chat |
| ADR-003 | Extracción clave-valor, KWIC y normalización | ADR-004 formaliza el índice asociativo simple y evidence_score |
| ADR-004 | Optimización de rendimiento, precisión y regla anti-sobreingeniería | Gobierna la calibración empírica y el alcance estricto del MVP |

---

## 27. Decisión Final

La meta del MVP de Pydective es:

> **Responder en el menor tiempo posible sin perder evidencia, sin inventar información y sin construir sobre-ingeniería que no esté justificada por datos reales.**

Por esta razón, este ADR-004 queda incorporado formalmente como la **brújula de ejecución de ingeniería** para el desarrollo del producto.
