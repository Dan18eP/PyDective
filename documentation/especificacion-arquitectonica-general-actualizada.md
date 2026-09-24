# Especificación Arquitectónica General
## Pydective: Motor Inteligente, Visión Determinista y Detective Documental

**Versión:** 2.1  
**Estado:** arquitectura de referencia actualizada (extiende ADR-001 y ADR-002)  
**Propósito:** definir la estructura completa, los límites entre módulos, el preprocesamiento determinista (Otsu/Deskew), catálogo de imágenes, chat documental y decisiones de resiliencia de Pydective.

> Este documento sustituye cualquier especificación arquitectónica anterior que presente un flujo o una estructura diferente. Los fragmentos de código previos son ilustrativos y no son fuente de verdad.

---

## 1. Propósito del sistema

El sistema es una aplicación web que recibe un PDF y una lista de parámetros de búsqueda, extrae información textual y visual, mitiga documentos escaneados con ruido y entrega resultados estructurados por página.

El diseño prioriza cuatro resultados:

1. **Velocidad:** resolver primero con caché y extracción local; usar IA solo cuando aporta valor.
2. **Resiliencia:** un fallo o agotamiento de API key afecta solo a la página pendiente, no al documento completo.
3. **Eficiencia de costo:** evitar renderizado, transferencia e inferencia innecesarios.
4. **Trazabilidad:** cada hallazgo conserva su página de origen y cada ejecución expone métricas de rendimiento.

Alcance inicial: PDFs de aproximadamente 20 páginas, carga web individual, SSR con Jinja2 y resultados inmediatos o parciales ante fallos controlados.

---

## 2. Principios arquitectónicos

### 2.1 Trabajo mínimo primero

No se abre el PDF, no se renderiza una página y no se llama a Gemini hasta que la capa anterior haya demostrado que es necesario.

```text
Bytes → Hash → Caché L0 → Caché L1 → Clasificación local → Render + IA → Merge → Caché → HTML
```

### 2.2 Separación por costo

Cada módulo representa una clase de costo distinta:

- HTTP: entrada/salida y protección del servicio.
- Caché: I/O rápido y reutilización de resultados.
- PyMuPDF: CPU local y extracción nativa.
- Render WebP: CPU y RAM para páginas pendientes.
- Gemini: red, cuota y coste variable.
- Jinja2: representación final, sin lógica de extracción.

### 2.3 Fallo aislado por página

No se repite el documento completo por una falla de proveedor, una key agotada o un timeout individual. Las páginas exitosas se preservan; una página pendiente puede hacer failover o retornar un error controlado.

### 2.4 Caché persistente por defecto

La memoria del proceso no es una capa de producción. Redis (o equivalente) guarda caché de resultados y extracción para sobrevivir reinicios y escalar a múltiples instancias.

### 2.5 IA selectiva

Un PDF digital debe resolverse sin IA cuando sea posible. La IA multimodal se reserva para escaneos, OCR local insuficiente y contenido visual que el producto necesite describir.

---

## 3. Vista de alto nivel (Pydective)

```text
                            ┌──────────────────────────────────────────┐
                            │                Navegador                 │
                            │  Carga PDF + parámetros / Pydective Chat │
                            └────────────────────┬─────────────────────┘
                                                 │
                                                 ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ FastAPI / main.py                                                                      │
│ Validación, límites, request_id, SSE streaming (/procesar/stream), Chat (/chat), Jinja2│
└────────────────────────────────────────┬───────────────────────────────────────────────┘
                                         │ JobInput / ChatInput
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ jobs.py — Orquestador                                                                  │
│ hash → L0 → L1 → Fase A (fitz + Otsu/Deskew) → Fase B (WebP + IA) → Merge → Caché     │
└───────┬────────────────────────────────┬───────────────────────────────┬───────────────┘
        │                                │                               │
        ▼                                ▼                               ▼
┌───────────────┐        ┌───────────────────────────────┐     ┌─────────────────────────┐
│ cache_service │        │ Fase A: classifier.py         │     │ chat_service.py         │
│ Redis L0/L1   │        │ PyMuPDF + preprocess_service  │     │ Grounding sobre L1      │
│ In-Memory Fall│        │ (Deskew Hough + Otsu OpenCV)  │     │ + Context Cache L2      │
│ Google L2 ref │        │ + image_service (detección)   │     │ (Citas por página)      │
└───────────────┘        └───────────────┬───────────────┘     └─────────────────────────┘
                                         │ pendientes IA
                                         ▼
                         ┌───────────────────────────────┐
                         │ Fase B                        │
                         │ renderer.py → WebP q70        │
                         │ gemini_service.py (Gemini 2.x)│
                         │ key_pool.py (semáforo/cuota)  │
                         └───────────────┬───────────────┘
                                         │
                                         ▼
                         ┌───────────────────────────────┐
                         │ JobOutput / resultados.html   │
                         └───────────────────────────────┘
```

---

## 4. Flujo de ejecución obligatorio

### 4.1 Entrada y validación

`main.py` recibe `POST /procesar` con PDF y parámetros.

Responsabilidades:

- Verificar tipo de archivo PDF.
- Aplicar tamaño máximo de carga: propuesta inicial 20–25 MB.
- Leer el archivo una única vez como `bytes` en RAM.
- Normalizar los parámetros recibidos.
- Crear `JobInput`.
- Aplicar timeout de request suficientemente superior a las olas de IA y a un cooldown corto.
- Delegar una única llamada a `jobs.process_pdf()`.

`main.py` no contiene lógica de PDF, Redis, Gemini, reintentos ni composición de prompts.

### 4.2 Identidad del documento

`jobs.py` calcula SHA-256 del `bytes` del PDF.

```text
pdf_hash = SHA-256(pdf_bytes)
```

El hash representa la identidad inmutable del archivo. Un byte distinto significa un documento distinto y, por tanto, invalida toda reutilización relacionada con ese archivo.

### 4.3 Caché L0: respuesta de consulta

Antes de abrir el PDF, se busca una respuesta completa mediante:

```text
L0 key = (pdf_hash, keywords_normalizadas)
```

Normalización de keywords:

- trim de espacios;
- `casefold`;
- eliminación de vacíos;
- eliminación de duplicados;
- orden canónico.

Ejemplo:

```text
Entrada: "Factura, total, FECHA, total"
Canónica: ["factura", "fecha", "total"]
```

Si hay hit L0:

- no se instancia PyMuPDF;
- no se genera pixmap;
- no se llama a Gemini;
- se renderiza la respuesta con Jinja2.

### 4.4 Caché L1: conocimiento extraído del PDF

Si L0 hace miss, el sistema consulta:

```text
L1 key = pdf_hash
```

L1 almacena extracción reusable por página:

- texto OCR/nativo limpio;
- descripciones de imágenes;
- origen del dato: local o IA;
- estado de página;
- metadatos de creación y TTL.

Si L1 existe, `keyword_service.py` filtra los parámetros nuevos sobre el texto ya almacenado y construye el resultado de la consulta. Luego escribe L0 para esa combinación de búsqueda.

Este comportamiento evita una nueva pasada de PyMuPDF, renderizado WebP e IA cuando cambia la consulta sobre el mismo PDF.

### 4.5 Fase A: clasificación local y visión determinista (Otsu & Deskew)

Solo ocurre ante miss L0 y L1. Rige el principio fundamental: **Determinismo antes de IA directa**.

Antes de renderizar o clasificar una página escaneada o con baja densidad de texto como `needs_ai`:
1. `preprocess_service.py` aplica **Deskew** (detección del ángulo dominante de texto mediante transformada de Hough o momentos de contorno con OpenCV y rotación correctora).
2. `preprocess_service.py` aplica **Binarización Otsu** (umbralización adaptativa para separar fondo manchado/sombras de los caracteres de texto).
3. `image_service.py` inspecciona los objetos gráficos nativos (`page.get_images()`) y cataloga sellos, firmas, logos y diagramas con su posición y página.
4. Si la página limpia tras Otsu + Deskew permite extracción determinista suficiente sin ambigüedad → Se resuelve como `local` (0 costo de IA).
5. Solo si tras la limpieza persiste texto ilegible o se requiere interpretación semántica visual → Pasa a Fase B como `needs_ai` con imagen WebP preprocesada y libre de ruido.

Una única apertura:

```text
fitz.open(stream=pdf_bytes, filetype="pdf")
```

Por página, `classifier.py` realiza únicamente trabajo local barato:

- extraer texto nativo;
- evaluar calidad y densidad de texto (detección de capas OCR corruptas, ratio de imprimibles y separación léxica);
- detectar imágenes embebidas y calcular su porcentaje de área:
  * Si las imágenes cubren <15% del área (logos/membretes) y el texto es abundante (>80 palabras), **se resuelve en `local`**.
  * Solo si cubren >15% o el usuario solicita explícitamente pistas visuales (`firma`, `sello`, `logo`) se marca `needs_ai`.
- detectar página vacía o visual;
- decidir `local`, `empty` o `needs_ai`.

| Condición | Resultado |
|---|---|
| Texto digital útil, sin necesidad visual (logos <15% área) | `local` |
| Texto digital útil, pero no hay keyword | `local` con coincidencias vacías |
| Texto insuficiente, corrupto o escaneo | `needs_ai` |
| Imagen/diagrama/sello/firma relevante para la solicitud | `needs_ai` |
| Página vacía sin contenido aprovechable | `empty` |

**Prohibido en Fase A:** renderizar pixmaps, usar Pillow, invocar OpenCV o llamar a red.

### 4.6 Fase B: procesamiento multimodal selectivo optimizado

Solo páginas marcadas `needs_ai` pasan a Fase B.

Secuencia:

```text
Página pendiente
  │
  ▼
1. Renderizado directo en C con fitz.Matrix(scale, scale) a max_dim ≤ 1024 px (sin doble paso en Pillow)
  │
  ▼
2. Pre-acondicionamiento determinista en vision_service.py (OpenCV):
   - Deskew selectivo en miniatura (500px), ángulo acotado a [-15°, +15°]
   - Binarización de Otsu ante fondos oscuros o sombras de escaneo
  │
  ▼
3. Conversión a WebP q75 en buffer de memoria
  │
  ▼
4. Invocación asíncrona a Gemini 2.0 Flash:
   - thinking_budget=0 (latencia mínima sin CoT innecesario)
   - temperature=0.0
   - JSON Schema estricto (Pydantic)
```

Reglas:

- El buffer WebP se crea una vez por página pendiente y se reutiliza en reintentos de red o failover.
- En el pool de renderizado concurrente, cada worker instancia su propio handle de `fitz.Document` para evitar fallos de thread-safety en C.
- La memoria de mapas de bits intermedios se libera inmediatamente tras obtener el buffer WebP.

### 4.7 Consolidación y salida

`jobs.py` consolida resultados con orden estable por página.

- Las páginas locales, IA, vacías y con error tienen un contrato uniforme.
- Páginas exitosas se conservan aunque otras fallen.
- Si expira el timeout global, se devuelve resultado parcial con estado explícito; no se reinicia el documento.
- Se actualizan L1 y L0 solo con resultados exitosos y consistentes.
- Jinja2 renderiza `resultados.html`.

---

## 5. Estrategia de caché híbrida

### 5.1 Capas

| Capa | Almacén | Clave | Contenido | Ahorro principal |
|---|---|---|---|---|
| L0 | Redis (`orjson`) / In-Memory LRU | `hash + keywords` | Resultado de una consulta | Evita todo el pipeline |
| L1 | Redis (`orjson`) / In-Memory LRU | `hash` | Extracción por página | Evita PyMuPDF, WebP e IA en nuevas búsquedas |
| L2 | Context Cache Google | `hash + key_id` | Referencia `cache_name` + vencimiento | Reduce reenvío de contenido multimodal (requiere ≥32k tokens) |

### 5.2 Ciclo de escritura

1. Fase A/B obtiene resultados por página.
2. Se persiste L1 con contenido reusable de páginas exitosas.
3. Se filtran keywords actuales sobre L1 mediante `semantic_extraction_service.py`.
4. Se escribe L0 con respuesta específica de la consulta serializada con `orjson`.
5. Si hubo páginas multimodales y el volumen de tokens de imagen supera el umbral de Google (~32.768 tokens), se registra L2 para la key que creó el recurso. De lo contrario, se omite de forma segura.

Solo `jobs.py` escribe las capas de caché. Esto evita duplicados, condiciones de carrera y resultados inconsistentes.

### 5.3 TTL, Persistencia y Resiliencia

| Capa | TTL inicial propuesto | Se invalida por |
|---|---:|---|
| L0 | 24 horas / LRU | TTL, nuevo hash, borrado explícito |
| L1 | 24 horas / política de retención | TTL, nuevo hash, borrado explícito |
| L2 | TTL del proveedor, ~60 min inicial | Vencimiento, key inválida/agotada, nuevo hash, tokens <32k |

- **Serialización con `orjson`:** Se adopta para todas las operaciones I/O de Redis por su velocidad extrema (5x-10x superior a `json`).
- **Resiliencia de Caché con `BaseCacheService`:** Si Redis no está disponible, el sistema conmuta automáticamente a `InMemoryLRUCacheService` acotado a un máximo de 100 documentos para evitar agotamiento de memoria en el servidor.
- La caché L2 no se reutiliza entre keys/proyectos distintos. Se crea con la API oficial `client.caches.create` y se referencia como `cached_content`.

---

## 6. Concurrencia, cuota y failover

### 6.1 Separación CPU / I/O

| Recurso | Tipo | Control |
|---|---|---|
| Clasificación PyMuPDF | CPU/C nativo | Iteración local controlada; no abrir PDF por página |
| Render WebP | CPU + RAM | Thread pool pequeño: 2–4 workers |
| Redis | I/O | Cliente async o pool de conexiones |
| Gemini | I/O externo + cuota | `asyncio` + semáforo global |

No se permite renderizar 20 pixmaps simultáneamente por defecto. Tampoco se permite lanzar 20 llamadas de IA sin límite.

### 6.2 Semáforo Gemini

```text
inflight = min(páginas_pendientes, keys/proyectos_útiles, MAX_INFLIGHT_GEMINI)
```

Valores iniciales:

```text
GEMINI_MODEL = "gemini-2.0-flash"        # Modelo canónico unificado fijado para todo el sistema
MAX_RENDER_WORKERS = 2–4
MAX_INFLIGHT_GEMINI = 4–8
MAX_PAGES = 20
```

El semáforo es **global al proceso o al proyecto** mediante `BaseConcurrencyLimiter`, no exclusivo de un request. Así se protege el servicio ante múltiples usuarios concurrentes y se previenen errores `429 RESOURCE_EXHAUSTED`.

### 6.3 Pool de API keys y Política de Fallo

Cada key posee estado y metadatos de salud:

| Estado | Significado | Uso |
|---|---|---|
| `healthy` | Operativa | Elegible por round-robin |
| `cooldown` | 429 temporal o proveedor saturado | No elegible hasta `Retry-After` / backoff |
| `exhausted` | Cuota diaria o límite persistente | No elegible durante TTL largo / proceso |
| `invalid` | 401, 403 o configuración incorrecta | No elegible hasta intervención |

Política de fallo:

| Error | Acción |
|---|---|
| 429 temporal | Key a `cooldown`; reintentar la misma página con otra key sana |
| 429 de cuota dura | Key a `exhausted`; no repetirla en el job |
| 401 / 403 | Key a `invalid`; no repetirla |
| 500 / 503 / timeout externo | Cooldown breve y retry acotado de la misma página |
| 400 por request/schema | No rotar key; error aislado de esa página |
| Expiración de Deadline Global | Cancelación segura: se abortan páginas en cola; tareas in-flight tienen gracia de 1.5s y se cancelan sin degradar la salud de la key (`healthy`). Se consolida `partial_result=True`. |

Una key agotada en la página 19 no afecta las páginas 1–18. Se conserva el WebP de la página 19 y solo esa página rota hacia otra key. Varias keys del mismo proyecto no multiplican automáticamente la cuota.

---

## 7. Contratos de dominio

### 7.1 Entrada

```text
JobInput
- pdf_bytes: bytes
- keywords: list[str]                   # normalizadas canónicamente
- request_id: str
- timeout_deadline: datetime
- catalogar_imagenes: bool = True       # catalogación forense activa por defecto
```

### 7.2 Resultado por página y fórmula de confianza

```json
{
  "pagina": 1,
  "exito": true,
  "origen": "local",
  "datos": {
    "ocr_texto_limpio": "...",
    "palabras_clave_encontradas": ["total"],
    "hallazgos_enriquecidos": [
      {
        "parametro_solicitado": "total",
        "termino_encontrado": "Total a Pagar",
        "valor_extraido": "$ 3.250.000 COP",
        "valor_normalizado": {
          "tipo": "currency",
          "monto": 3250000.0,
          "moneda": "COP"
        },
        "contexto_oracion": "El Total a Pagar antes de la fecha límite es de $ 3.250.000 COP.",
        "confianza": 0.96,
        "metodo_extraccion": "espacial_determinista",
        "evidencia_visual_asociada": "img_p1_2"
      }
    ],
    "imagenes_detectadas": [
      {
        "id_imagen": "img_p1_1",
        "tipo": "logotipo",
        "descripcion": "Logotipo corporativo de la empresa emisora",
        "ubicacion_aproximada": "superior_izquierda"
      },
      {
        "id_imagen": "img_p1_2",
        "tipo": "sello_oficial",
        "descripcion": "Sello notarial circular con fecha legible",
        "ubicacion_aproximada": "inferior_derecha"
      }
    ]
  }
}
```

**Fórmula de Confianza Determinista:**
Para el método `espacial_determinista`:
$$\text{confianza} = \text{base\_score} \times (1 - \text{penalización\_distancia}) \times \text{score\_regex}$$
- $\text{base\_score} = 1.0$ (texto vectorial nativo) o $0.75$ (fallback de kerning apretado).
- $\text{penalización\_distancia} = \min(0.25, (\text{distancia\_pt} / 180.0) \times 0.25)$.
- $\text{score\_regex} = 1.0$ (entidad validada) o $0.85$ (texto genérico).
- Rango: $[0.50, 1.00]$.

Posibles valores de `origen`: `local`, `ia`, `cache_l1`, `empty`.

Fallo aislado:

```json
{
  "pagina": 19,
  "exito": false,
  "origen": "ia",
  "error": "Quota temporal agotada; se agotaron los reintentos disponibles"
}
```

### 7.3 Contratos del Módulo Pydective Chat (Multi-Turno)

```text
ChatMessage
- role: "user" | "model"
- content: str
- timestamp: datetime

ChatInput
- pdf_hash: str
- pregunta: str
- session_id: str | None = None
- historial: list[ChatMessage] = []      # memoria de los últimos turnos de conversación

ChatOutput
- respuesta: str
- paginas_citadas: list[int]
- evidencias_visuales: list[dict]
- cache_hit: l1 | l2 | none
- session_id: str
```

**Comportamiento ante hash no existente o expirado:**
Si `pdf_hash` no se encuentra en L1 (documento nunca procesado o expirado tras TTL 24h), el endpoint responde **HTTP 404 Not Found**:
```json
{
  "error": "DOCUMENT_NOT_FOUND_OR_EXPIRED",
  "message": "El documento no se encuentra en el índice de memoria o su sesión ha expirado (TTL 24h). Por favor cargue el PDF nuevamente para iniciar un nuevo análisis.",
  "pdf_hash": "..."
}
```

### 7.4 Salida del job

```text
JobOutput
- pdf_hash: str
- resultados: list[ResultadoPagina]
- cache_hit: l0 | l1 | l2 | none
- pages_local: int
- pages_ai: int
- partial_result: bool
- metrics: JobMetrics
```

---

## 8. Estructura de proyecto

```text
pydective/
│
├── app/
│   ├── main.py                 # FastAPI, rutas, middleware, Jinja2
│   ├── settings.py             # Entorno, límites, configuración
│   ├── dependencies.py         # Dependencias FastAPI y lifecycle
│   │
│   ├── domain/
│   │   ├── models.py           # JobInput, JobOutput, ResultadoPagina
│   │   ├── enums.py            # EstadoKey, TipoPagina, NivelCache
│   │   └── errors.py           # Errores de dominio
│   │
│   ├── services/
│   │   ├── jobs.py             # Orquestador y único escritor de caché
│   │   ├── classifier.py       # Fase A: texto + decisión de carril
│   │   ├── preprocess_service.py # Visión determinista: Deskew (Hough) + Otsu
│   │   ├── image_service.py    # Catálogo forense de imágenes (firmas, sellos, logos)
│   │   ├── chat_service.py     # Pydective Chat: Q&A documental con citas por página
│   │   ├── renderer.py         # Fase B CPU: pixmap → WebP
│   │   ├── gemini_service.py   # Fase B red: IA y reintento por página
│   │   ├── key_pool.py         # Pool, salud, cooldown, semáforo por proyecto
│   │   ├── cache_service.py    # L0, L1, L2 + InMemoryLRUCache fallback
│   │   ├── pdf_viewer_service.py # Búsqueda de coordenadas exactas en C y streaming PDF
│   │   └── semantic_extraction_service.py # Extracción clave-valor, sinónimos y KWIC
│   │
│   ├── infrastructure/
│   │   ├── redis_client.py     # Cliente Redis y serialización
│   │   ├── gemini_client.py    # Fábrica de clientes Google
│   │   └── observability.py    # Logs, métricas y trazas
│   │
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   └── resultados.html
│   │
│   └── static/
│       ├── css/
│       └── js/                 # pdf_viewer.js y scripts de interacción
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml          # App + Redis
└── README.md
```

### Responsabilidades no negociables

- `main.py` no importa PyMuPDF ni SDK de Gemini.
- `jobs.py` es el único punto que combina fases y escribe L0/L1/L2.
- `classifier.py` no genera pixmaps y no hace I/O de red.
- `renderer.py` no conoce keys ni prompts.
- `gemini_service.py` no abre PDFs ni sabe de Jinja2.
- `key_pool.py` no recibe páginas ni crea resultados de negocio.
- `cache_service.py` no decide reglas de búsqueda.
- `pdf_viewer_service.py` encapsula la búsqueda geométrica `page.search_for()` y entrega de binarios.

---

## 9. Interfaz HTTP

| Método | Ruta | Finalidad |
|---|---|---|
| GET | `/` | Mostrar formulario `index.html` (interfaz Pydective) |
| POST | `/procesar` | Procesar PDF sincrónicamente y devolver `resultados.html` |
| GET | `/procesar/stream` | Streaming reactivo SSE del procesamiento página por página |
| GET | `/documentos/{pdf_hash}/raw` | Entrega segura del archivo PDF binario para renderizado en PDF.js |
| GET | `/documentos/{pdf_hash}/search` | Búsqueda de ocurrencias exactas con coordenadas bboxes en PyMuPDF |
| POST | `/chat/{pdf_hash}` | Interrogar al PDF en lenguaje natural con citas por página |
| GET | `/health` | Salud de aplicación y dependencias esenciales |

Políticas de borde:

- límite de carga antes de lectura completa cuando sea posible;
- MIME y firma PDF validados;
- máximo de páginas configurable;
- timeout por request;
- `request_id` para logs y soporte;
- respuesta parcial visible si una o varias páginas no se resuelven.

---

## 10. Observabilidad y métricas

Cada trabajo debe producir eventos y métricas estructuradas:

```text
request_id
pdf_hash
page_count
cache_hit: l0 | l1 | l2 | none
pages_local
pages_ai
pages_failed
render_ms
gemini_ms
total_ms
retry_count
key_failover_count
partial_result
```

Indicadores operativos iniciales (Re-presupuestados con pipeline semántico y clave-valor completo):

| Indicador | Objetivo de diseño |
|---|---:|
| Hit L0 | < 20 ms |
| Hit L1, refiltrado con nuevas keywords | < 50 ms |
| PDF digital ~20 páginas, caché fría (Fase A + Clave-Valor Espacial O(N) + KWIC + Normalización) | p95 < 200 ms + render HTML |
| Time-To-First-Token (TTFT) en Pydective Chat | < 600 ms |
| PDF mixto | IA solo para páginas pendientes (WebP prefetch en background) |
| Key caída / agotada | sin reprocesar páginas exitosas |
| Peticiones concurrentes repetidas (Dogpile) | 1 procesamiento real, N servidas desde caché (Singleflight) |

Los objetivos son presupuestos de diseño, no SLA comercial.

---

## 11. Seguridad y datos

- El PDF se procesa en RAM durante la ejecución; no se persiste por defecto como archivo original.
- Redis almacena resultados y metadatos con TTL definido.
- Variables `GEMINI_KEY_*`, URL Redis y configuración sensible se inyectan por entorno.
- Se recomienda cifrado en tránsito y en reposo en producción.
- Debe existir mecanismo de borrado explícito de resultados por hash/cuenta cuando se agregue autenticación.
- El uso de IA externa debe comunicarse de forma transparente a usuarios empresariales.

Autenticación, multi-tenant, roles y auditoría se consideran evolución posterior al MVP, pero los módulos no deben impedir agregarlos.

---

## 12. Dependencias previstas

Las versiones exactas se fijan en la fase de implementación y se verifican contra la documentación vigente del SDK.

- `fastapi`, `uvicorn`, `python-multipart`, `jinja2`
- `pymupdf`, `pillow`
- `google-genai`, `pydantic`
- `redis`
- `pytest`, `pytest-asyncio`, herramientas de calidad y tipado

No se asumen atributos de SDK no verificados. En particular, la creación y uso de Context Cache se validará con la versión fijada de `google-genai`, usando interfaces reales como `client.caches.create(...)` y `cached_content` cuando correspondan. [web:24][web:30]

---

## 13. Restricciones y decisiones de v1

Incluido:

- Un PDF por solicitud.
- ~20 páginas por documento como límite inicial.
- Búsqueda por parámetros escritos manualmente.
- Extracción híbrida local + IA.
- Caché L0/L1 Redis.
- Failover por página.
- SSR Jinja2.

Fuera de alcance:

- Carga masiva y colas de trabajos.
- Progreso por WebSocket.
- Persistencia de PDFs originales.
- OCR clásico (ej. Tesseract) como tercer carril.
- Multi-tenant y autenticación.
- Integraciones externas de negocio.
- Compartir Context Cache entre keys distintas.
- Batch API para el endpoint interactivo: se reserva para procesamiento asíncrono masivo, no para el POST web. [web:31][web:32]

---

## 14. Criterios de aceptación arquitectónica

- [ ] Hit L0 devuelve resultados sin abrir el PDF.
- [ ] Cambio de keywords para el mismo PDF usa L1 y no llama a IA.
- [ ] PDF digital de 20 páginas no genera WebP si el texto nativo es suficiente.
- [ ] PDF mixto con 3 páginas pendientes genera como máximo 3 tareas IA iniciales.
- [ ] Un retry de API reutiliza el WebP existente.
- [ ] Una key que se agota en la última página no cancela las páginas ya terminadas.
- [ ] No hay `asyncio.gather` sin protección que cancele el lote por una excepción individual.
- [ ] Redis conserva L0 y L1 tras reiniciar Uvicorn.
- [ ] L2 respeta key/proyecto y TTL; un cache vencido se recrea o se omite sin 500.
- [ ] `main.py` no incluye lógica de extracción, caché ni IA.
- [ ] Todas las respuestas tienen resultados ordenados por página y estado explícito.

---

## 15. Orden de implementación

1. Modelos de dominio, configuración y contratos.
2. Normalización de keywords.
3. Redis: L0 y L1.
4. Fase A: `classifier.py` y resultados locales.
5. `jobs.py`: orquestación, merge y métricas sin IA.
6. `key_pool.py`: semáforo, estados de keys y failover.
7. `renderer.py` y `gemini_service.py`.
8. Context Cache L2.
9. Middleware HTTP, pruebas de integración y carga.
10. Plantillas finales y refinamiento de UX.

La prioridad es validar el contrato `JobOutput` y el camino local/cacheado antes de integrar o pulir la capa visual.
