# Arquitectura de ejecución
## Encaje de capas para máxima velocidad

Este documento **alinea** módulos, caché, CPU y red para que cada etapa haga el mínimo trabajo y el camino feliz sea el más corto. Complementa la especificación; si hay conflicto, **gana este orden de ejecución**.

---

## 1. Regla de oro

> No se abre el PDF, no se pinta pixmap, no se llama a Gemini, hasta que la capa anterior demuestre que hace falta.

Velocidad = **evitar trabajo**, no paralelizar trabajo inútil.

Orden fijo:

1. Bytes en RAM  
2. SHA-256  
3. Caché L0 `(hash, keywords)` y L1 `(hash)`  
4. Clasificación local con PyMuPDF + Visión Determinista (Deskew Hough + Binarización Otsu con OpenCV)  
5. Catalogación forense de imágenes (firmas, sellos, logotipos, diagramas) por página  
6. Carril IA multimodal **solo** para páginas que persistan ilegibles o requieran descripción visual, con semáforo acotado  
7. Merge estable por número de página  
8. Escritura de caché L1 y L0 en `jobs.py` (con fallback in-memory ante fallo de Redis)  
9. HTML / SSE streaming de progreso + Interfaz conversacional (Pydective Chat)  

---

## 2. Por qué encaja (mapa de dependencias)

```
main.py          borde HTTP: tamaño, timeout, form
    │
    ▼
hash SHA-256     CPU barato, una pasada sobre bytes
    │
    ▼
cache.py         HIT → return (0 PyMuPDF, 0 Gemini)
    │ MISS
    ▼
pipeline.fase_A  fitz.open en RAM → texto nativo + has_images
                 │
                 ├── páginas ESCANEADAS/SUCIAS → preprocess_service (Deskew + Otsu)
                 │                                │
                 │                                ├── limpias deterministas → RESUELTAS local
                 │                                └── persisten sucias      → PENDIENTES IA
                 │
                 ├── catálogo visual            → image_service (firmas, sellos, logos)
                 ├── páginas RESUELTAS           → lista resultados (0 I/O red)
                 └── páginas PENDIENTES          → fase_B
                           │
                           ▼
                      WebP optimizado (150 DPI, q70, una vez por página pendiente)
              │
              ▼
         Gemini async + semáforo = f(keys sanas, RPM)
              │ 429 → otra key, mismo WebP
              ▼
cache.py write  Redis + (opcional) puntero Context Cache
    │
    ▼
Jinja2          no espera I/O extra
```

Ningún módulo llama a Gemini por su cuenta. `config.py` solo entrega clientes sanos. `cache.py` no renderiza. `main.py` no conoce páginas.

---

## 3. Fase A — clasificar barato (el acelerador real)

Una sola apertura `fitz.open(stream=bytes)`. Para cada página, **solo** operaciones C:

| Señal | Umbral de diseño | Destino |
|---|---|---|
| Texto nativo largo y keywords presentes, logos <15% área | éxito local | no pixmap |
| Texto nativo largo, keywords ausentes, logos <15% área | éxito local con lista vacía | no pixmap (no alucinar con IA si el PDF es digital) |
| Página inclinada o fondo con sombras/ruido (needs_ai) | Preprocesamiento determinista: Deskew (±15°, miniatura 500px) + Otsu | Limpieza rápida antes de evaluar |
| Post-Otsu: texto legible alcanzado | éxito local | no pixmap, 0 costo IA |
| Poco texto / texto corrupto persistente / escaneo complejo | pendiente IA | Fase B optimizada |
| Hay sellos, firmas manuscritas o solicitud visual explícita | catalogación image_service + pendiente IA | Fase B optimizada |

Heurística de “texto basura” (producto, no magia):

- pocos caracteres alfanuméricos por página, o  
- alta ratio de reemplazos/control chars (`\ufffd`), o  
- palabras sin separación léxica o promedio de longitud >30 chars, o  
- `get_images()` cubre más del 50% del rect de la página con texto casi nulo.

**Prohibido en fase A:** `get_pixmap`, Pillow, OpenCV en páginas digitales limpias, red.

Concurrencia fase A: `asyncio.to_thread` / pool acotado al número de CPU, no a 20 ciegas. PyMuPDF no es siempre thread-safe sobre el **mismo** `Document`: o se itera en un hilo, o se abre un doc por worker. Decisión de implementación: **un hilo, loop de 20 páginas de texto es ~ms**; no vale la pena pelear el GIL aquí. El win es no pintar. [web:35]

Cierre de iteración: cada resultado local se construye con `pagina=i+1` y un dict **ya copiado**, no un lambda que cierra sobre `i`.

---

## 4. Fase B — pintar y ver solo lo sucio

### 4.1 Pixmap y WebP (CPU)

- Solo páginas pendientes marcadas `needs_ai`.  
- **Renderizado directo en C:** `page.get_pixmap(matrix=fitz.Matrix(scale, scale))` escalando directo al tamaño objetivo (max_dim ≤ 1024 px). Elimina el paso intermedio de renderizar a 150 DPI y redimensionar con Pillow.
- Pre-acondicionamiento en `preprocess_service.py` (Deskew acotado a $\pm 15^\circ$ sobre miniatura 500px + Otsu si hay contraste bajo).
- Liberar pixmap en cuanto existe el buffer WebP (`pix = None`).  
- WebP q75 en buffer de memoria: el cuello pasa a ser **RTT de Gemini**, no la transferencia de imagen.  
- CPU en thread pool pequeño (2–4). Cada worker abre su propio handle `fitz.Document(stream=pdf_bytes)` para total thread-safety.

### 4.2 Ráfaga Gemini (I/O)

- `asyncio.gather` **solo** de pendientes, no de las 20.  
- Semáforo: `min(pendientes, keys_sanas, MAX_INFLIGHT_POR_PROYECTO)`.  
  - `MAX_INFLIGHT` arranca en 4–8. Subir no linealiza: 429 serializa peor que un semáforo. [web:40]
- Un WebP, N reintentos de key.  
- `thinking_budget=0` (latencia mínima sin CoT innecesario), JSON schema estricto, `temperature` 0.0.  
- Streaming reactivo SSE en `/procesar/stream` mediante `AsyncGenerator` compartido con `/procesar`.  
- Batch API de Google **no** entra: es cola de horas, no request web. [web:31][web:32]

### 4.3 Keys y cuota

Varias keys **del mismo proyecto de Google no multiplican RPM**. El pool sirve para keys **de proyectos distintos** o para aislar keys muertas, no para 20 disparos simultáneos contra un solo cupo. [web:40]

Encaje: semáforo global del **proyecto** + rotación solo al ver 429/401 en esa key.

---

## 5. Caché que acelera de verdad

Tres lecturas, una escritura, sin pisa-pisas:

| Capa | Clave | Se consulta | Ahorra |
|---|---|---|---|
| L0 Redis aplicación | `(sha256, keywords_canónicas)` | **antes** de fitz | 100% CPU+red |
| L1 Redis OCR | `sha256` → texto/descripciones por página | miss de L0, mismo PDF otras keywords | Gemini + pixmap |
| L2 Google Context Cache | `sha256 + key_id` → `cache_name` + `expire_at` | miss L1, misma key, páginas imagen | tokens de imagen |

Camino más rápido posible:

1. Hit L0 → HTML.  
2. Hit L1 → refiltrar keywords en CPU → escribir L0 → HTML.  
3. Miss L1, hit L2 y key sana = la del cache → Gemini **sin** reenviar WebP.  
4. Else → fase A/B.

Escritura:

- L1 se llena con OCR/descripciones de páginas `exito: true` (independiente de keywords).  
- L0 se llena con el JSON **ya filtrado** de esta request.  
- L2 se crea **una vez por (pdf, key)** tras la primera ráfaga de imágenes, TTL ~60 min; no se crea si todas las páginas fueron locales. [web:16]

Invalidación: hash distinto; TTL; key `invalid`; no mezclar `cache_name` entre keys.

---

## 6. Presupuesto de latencia (20 páginas, diseño actualizado)

Escenario A — PDF digital, keywords en texto, hit frío L0 (con extracción espacial clave-valor O(N) + KWIC + normalización de entidades):

- hash SHA-256 ~5–10 ms  
- fitz extracción texto + palabras `words` ~15–35 ms  
- análisis espacial horizontal/vertical + regex de entidades ~10–25 ms  
- consolidación y serialización `orjson` ~5–10 ms  
- 0 red (cero Gemini)  
- **objetivo p95 < 200 ms** más HTML  

Escenario B — mismo PDF, otras keywords, hit L1:

- hash + Redis (`orjson`) + refiltrado espacial/léxico  
- **objetivo p95 < 50 ms**

Escenario C — 20 escaneos sucios, 4 keys/proyectos, semáforo 4:

- fase A + pre-acondicionamiento OpenCV (Deskew en miniatura + Otsu)  
- render WebP directo con `fitz.Matrix` (en background durante clasificación)  
- 5 olas de 4 RTT Gemini 2.0 Flash (`thinking_budget=0`)  
- failover no reinicia olas ya OK  
- **objetivo: 1–3 RTT efectivos**  

Escenario D — hit L0:

- **objetivo < 20 ms**

Escenario E — 5 peticiones concurrentes idénticas en caché fría (Prevención de Dogpile):

- 1 petición adquiere candado Singleflight (`SET lock:pdf:{hash} NX EX 60`) y ejecuta el pipeline.  
- 4 peticiones concurrentes esperan el resultado publicado en Redis sin duplicar inferencia ni CPU.  
- **objetivo: 0 llamadas duplicadas a IA**, todas servidas desde L0 en cuanto finaliza la primera.

Estos números son **presupuestos de diseño**, no promesas de SLA.

---

## 7. Encaje HTTP ↔ pipeline

| Pieza | Rol de velocidad |
|---|---|
| `file.read()` directo a RAM | cero disco |
| Límite 20–25 MB | rechazar antes del hash |
| Timeout HTTP > (olas_IA × RTT + cooldown corto) | no matar jobs casi listos |
| Un job por request | sin cola en v1; simplicidad > throughput multi-usuario |
| Jinja2 al final | no serializar JSON extra al browser como API |

Si el timeout pisa el failover, se **devuelve parcial** (páginas OK + errores), nunca se relanza el documento.

---

## 8. Módulos y contratos (Estructura oficial alineada con Especificación v2.1)

```text
pydective/
├── app/
│   ├── main.py                 # Borde HTTP: SSE streaming (/procesar/stream), Chat (/chat/{hash}), Jinja2
│   ├── settings.py             # Configuración central: GEMINI_MODEL="gemini-2.0-flash", límites, timeouts
│   ├── dependencies.py         # Inyección de dependencias FastAPI y lifecycle (startup/shutdown)
│   │
│   ├── domain/
│   │   ├── models.py           # Modelos Pydantic v2: JobInput, JobOutput, ChatInput, ChatOutput, HallazgoEnriquecido
│   │   ├── enums.py            # Enums: EstadoKey, TipoPagina, NivelCache, MetodoExtraccion
│   │   └── errors.py           # Jerarquía de excepciones de dominio
│   │
│   ├── services/
│   │   ├── jobs.py             # Orquestador único y singleflight: hash → L0/L1 → Fase A → Fase B → persistencia
│   │   ├── classifier.py       # Fase A: extracción nativa con PyMuPDF y evaluación de legibilidad
│   │   ├── preprocess_service.py # Visión determinista: Deskew acotado (Hough) + Binarización Otsu con OpenCV
│   │   ├── image_service.py    # Detección y catalogación forense de imágenes (firmas, sellos, logos)
│   │   ├── chat_service.py     # Pydective Chat: Grounding sobre L1 + historial multi-turno con citas
│   │   ├── renderer.py         # Fase B CPU: fitz.Matrix directo a WebP q75 en thread pool
│   │   ├── gemini_service.py   # Fase B red: gemini-2.0-flash con thinking_budget=0 + retry por página
│   │   ├── key_pool.py         # Pool con estados healthy/cooldown/exhausted/invalid + BaseConcurrencyLimiter
│   │   ├── cache_service.py    # BaseCacheService: Redis (orjson) + Fallback transparente InMemoryLRUCacheService
│   │   └── semantic_extraction_service.py # Extracción espacial O(N), KWIC, sinónimos y normalización
│   │
│   ├── infrastructure/
│   │   ├── redis_client.py     # Cliente Redis async y locks de Singleflight
│   │   ├── gemini_client.py    # Fábrica de clientes google-genai persistentes
│   │   └── observability.py    # Logs estructurados y métricas de latencia por fase
│   │
│   ├── templates/              # Vistas SSR: index.html y resultados.html con chat interactivo
│   └── static/                 # Estilos y JavaScript para SSE y chat
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── requirements.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

`jobs.py` es el único que escribe caché. Ningún módulo llama a Gemini por su cuenta. `classifier.py` no hace I/O ni pixmaps.

Contrato interno:

```text
JobInput  = { bytes, keywords[], request_id, timeout_deadline, catalogar_imagenes }
JobOutput = { hash, resultados[página], cache_hit: l0|l1|l2|none, partial_result, metrics }
```

`jobs.py` es el único que escribe caché. Así no hay doble write ni condiciones de carrera.

---

## 9. Paralelismo permitido vs prohibido

**Permitido**

- Redis get/set async mientras no hay CPU pesada.  
- Gather de llamadas Gemini ≤ semáforo por proyecto (`ConcurrencyLimiter`).  
- Thread pool chico para WebP de pendientes.  
- **Prefetch de WebP durante Fase A:** si una página se clasifica como `needs_ai` en el loop inicial, despachar su renderizado WebP en background hacia el thread pool mientras el hilo continúa clasificando las páginas restantes.  
- **Singleflight:** candado distribuido `SET lock:pdf:{hash} NX EX 60` para evitar dogpile en peticiones idénticas.  
- **Cache de compilación de regex:** compilar patrones léxicos y de entidades una sola vez en el startup del módulo (`re.compile()`).  
- **Pydantic v2:** serializar con `model_dump(mode="json")` y `orjson`.

**Prohibido (ralentiza)**

- 20 pixmaps simultáneos en RAM.  
- Gather de 20 Gemini contra un solo proyecto sin semáforo.  
- Reabrir el PDF por cada página.  
- Recomprimir WebP en cada retry de key.  
- Relanzar fase A porque falló la página 19.  
- Context Cache en el primer hit local (no hay imágenes que cachear).  
- Batch API para el POST interactivo `/procesar`.  
- Compilar expresiones regulares por cada request o por cada página.  
- Usar `.dict()` heredado de Pydantic v1.

---

## 10. Checklist de encaje (aceptación de velocidad)

- [ ] Hit L0 no importa `fitz` ni crea clientes Gemini extra.  
- [ ] PDF digital de 20 páginas no genera ningún WebP.  
- [ ] PDF mixto (3 sucias / 17 limpias) = 3 llamadas IA máximo.  
- [ ] Retry de key reutiliza el mismo `bytes` WebP.  
- [ ] Semáforo ≤ keys/proyectos útiles, no ≤ número de páginas.  
- [ ] L1 permite cambiar keywords sin visión.  
- [ ] L2 no se consulta con una key distinta a la que lo creó.  
- [ ] Reinicio de Uvicorn no borra L0/L1 (Redis).  
- [ ] Respuesta parcial si el tiempo se acaba; páginas hechas se cachean.

---

## 11. Qué se implementa primero (cuando haya código)

1. `keys.py` + semáforo (sin esto, más paralelismo = más 429).  
2. `classify.py` + `jobs.py` fase A (el mayor win de velocidad).  
3. `cache.py` L0/L1 (el mayor win de repetición).  
4. `render.py` + `gemini_io.py` fase B.  
5. L2 Context Cache.  
6. Ajuste de `MAX_INFLIGHT` y DPI con un PDF real de 20 páginas.

No se escribe HTML ni se pulen plantillas hasta que el job devuelva el contrato `JobOutput` estable.
