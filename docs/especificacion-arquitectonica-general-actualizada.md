# Especificación Arquitectónica General
## Sistema Ultra-Veloz de Extracción Multimodal Anti-Ruido

**Versión:** 2.0  
**Estado:** arquitectura de referencia previa a implementación  
**Propósito:** definir la estructura completa, los límites entre módulos, el flujo de ejecución y las decisiones de rendimiento del sistema.

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

## 3. Vista de alto nivel

```text
                            ┌─────────────────────────────┐
                            │          Navegador          │
                            │ Carga PDF + parámetros      │
                            └──────────────┬──────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ FastAPI / main.py                                                    │
│ Validación, tamaño, timeout, lectura RAM, request_id, Jinja2        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ JobInput
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ jobs.py — Orquestador                                                │
│ hash → L0 → L1 → fase A → fase B → merge → persistencia             │
└───────┬─────────────────────────────┬───────────────────────────────┘
        │                             │
        ▼                             ▼
┌───────────────┐            ┌───────────────────────────────────────┐
│ cache.py      │            │ Fase A: classifier.py                 │
│ Redis L0/L1   │            │ PyMuPDF, texto nativo, decisión       │
│ Google L2 ref │            └──────────────────┬────────────────────┘
└───────────────┘                               │ pendientes IA
                                                 ▼
                              ┌──────────────────────────────────────┐
                              │ Fase B                               │
                              │ renderer.py → WebP                   │
                              │ gemini_service.py → IA estructurada  │
                              │ key_pool.py → cuota/failover         │
                              └──────────────────┬───────────────────┘
                                                 │
                                                 ▼
                              ┌──────────────────────────────────────┐
                              │ JobOutput / resultados.html          │
                              └──────────────────────────────────────┘
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

### 4.5 Fase A: clasificación local

Solo ocurre ante miss L0 y L1.

Una única apertura:

```text
fitz.open(stream=pdf_bytes, filetype="pdf")
```

Por página, `classifier.py` realiza únicamente trabajo local barato:

- extraer texto nativo;
- evaluar calidad y densidad de texto;
- detectar imágenes embebidas;
- detectar página vacía o visual;
- decidir `local`, `empty` o `needs_ai`.

| Condición | Resultado |
|---|---|
| Texto digital útil, sin necesidad visual | `local` |
| Texto digital útil, pero no hay keyword | `local` con coincidencias vacías |
| Texto insuficiente, basura o escaneo | `needs_ai` |
| Imagen/diagrama/logo relevante para la solicitud | `needs_ai` |
| Página vacía sin contenido aprovechable | `empty` |

**Prohibido en Fase A:** renderizar pixmaps, usar Pillow o llamar a red.

### 4.6 Fase B: procesamiento multimodal selectivo

Solo páginas marcadas `needs_ai` pasan a Fase B.

Secuencia:

```text
Página pendiente → Pixmap 150 DPI → thumbnail ≤1024 px → WebP q70 → Gemini → JSON estructurado
```

Reglas:

- DPI inicial: 150.
- DPI 200: únicamente si la estrategia detecta texto pequeño y las métricas justifican el costo.
- No usar 300+ DPI en v1.
- El buffer WebP se crea una vez por página.
- Un retry de red o failover reutiliza el mismo WebP.
- Pixmap se libera tras obtener WebP para reducir presión de RAM.

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
| L0 | Redis | `hash + keywords` | Resultado de una consulta | Evita todo el pipeline |
| L1 | Redis | `hash` | Extracción por página | Evita PyMuPDF, WebP e IA en nuevas búsquedas |
| L2 | Context Cache Google | `hash + key_id` | Referencia `cache_name` + vencimiento | Reduce reenvío de contenido multimodal |

### 5.2 Ciclo de escritura

1. Fase A/B obtiene resultados por página.
2. Se persiste L1 con contenido reusable de páginas exitosas.
3. Se filtran keywords actuales sobre L1.
4. Se escribe L0 con respuesta específica de la consulta.
5. Si hubo páginas multimodales y aplica, se registra L2 para la key que creó el recurso.

Solo `jobs.py` escribe las capas de caché. Esto evita duplicados, condiciones de carrera y resultados inconsistentes.

### 5.3 TTL e invalidación

| Capa | TTL inicial propuesto | Se invalida por |
|---|---:|---|
| L0 | 24 horas / LRU | TTL, nuevo hash, borrado explícito |
| L1 | 24 horas / política de retención | TTL, nuevo hash, borrado explícito |
| L2 | TTL del proveedor, ~60 min inicial | Vencimiento, key inválida/agotada, nuevo hash |

La caché L2 no se reutiliza entre keys/proyectos distintos. El cache explícito de Google se crea con la API de `caches.create` y se referencia como `cached_content`; no se asume que un campo de versión en `GenerateContentConfig` active esta función. [web:16][web:18][web:24]

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
MAX_RENDER_WORKERS = 2–4
MAX_INFLIGHT_GEMINI = 4–8
MAX_PAGES = 20
```

El semáforo es **global al proceso o al proyecto**, no exclusivo de un request. Así se protege el servicio ante múltiples usuarios y se reducen 429. Los límites de Gemini dependen de modelo, proyecto y nivel de uso; excederlos ocasiona `429 RESOURCE_EXHAUSTED`. [web:31]

### 6.3 Pool de API keys

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

Una key agotada en la página 19 no afecta las páginas 1–18. Se conserva el WebP de la página 19 y solo esa página rota hacia otra key.

Varias keys del mismo proyecto no deben asumirse como multiplicador de cuota. El semáforo se dimensiona por proyectos y límites realmente disponibles, no por el número de páginas.

---

## 7. Contratos de dominio

### 7.1 Entrada

```text
JobInput
- pdf_bytes: bytes
- keywords: list[str]              # ya normalizadas
- request_id: str
- timeout_deadline: datetime
```

### 7.2 Resultado por página

```json
{
  "pagina": 1,
  "exito": true,
  "origen": "local",
  "datos": {
    "ocr_texto_limpio": "...",
    "palabras_clave_encontradas": ["factura", "total"],
    "descripcion_de_imagenes_detectadas": []
  }
}
```

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

### 7.3 Salida del job

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
app_pdf_veloz/
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
│   │   ├── renderer.py         # Fase B CPU: pixmap → WebP
│   │   ├── gemini_service.py   # Fase B red: IA y reintento por página
│   │   ├── key_pool.py         # Pool, salud, cooldown, semáforo
│   │   ├── cache_service.py    # L0, L1 y puntero L2
│   │   └── keyword_service.py  # Normalización y filtro local
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
│       └── js/
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

---

## 9. Interfaz HTTP

| Método | Ruta | Finalidad |
|---|---|---|
| GET | `/` | Mostrar formulario `index.html` |
| POST | `/procesar` | Procesar PDF y devolver `resultados.html` |
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

Indicadores operativos iniciales:

| Indicador | Objetivo de diseño |
|---|---:|
| Hit L0 | < 20 ms |
| Hit L1, otras keywords | < 50 ms |
| PDF digital de ~20 páginas, caché fría | p95 < 150 ms + render HTML |
| PDF mixto | IA solo para páginas pendientes |
| Key caída / agotada | sin reprocesar páginas exitosas |

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
