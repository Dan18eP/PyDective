# ADR-008: Integración de CLI Multimodales (Antigravity & OpenCode), Interoperabilidad OpenAI, Lectura y Resúmenes Textuales, y Renderizado de Markdown en Pydective Chat

- **Estado:** Aceptado
- **Fecha:** 2026-09-24
- **Decisores:** Brandon Carranza (Arquitecto de Software y Lead Engineer)
- **Extiende a:** [ADR-001](ADR-001-arquitectura-hibrida-caching-y-failover.md), [ADR-002](ADR-002-preprocesamiento-determinista-vision-y-chat-documental.md), [ADR-004](ADR-004-optimizacion-rendimiento-precision-y-reutilizacion-documental.md) y [ADR-007](ADR-007-compatibilidad-multiplataforma-linux-windows-y-ciclo-de-vida-de-servicios.md)
- **Relacionado con:** PRD, Requisitos del Sistema (RF-093, RF-094, RF-108, RF-110, RF-111, RF-112), EPIC-06 (US-23) y EPIC-08
- **Etiquetas:** pydective, llm-providers, cli-integration, agy, opencode, openai-spec, markdown, document-summarization, non-deterministic-routing

---

## 1. Contexto

Durante las pruebas forenses de campo en Pydective Chat sobre contratos y expedientes extensos (tales como el expediente contractual de 20 páginas `14ad4112b...`), se identificaron las siguientes limitaciones funcionales y de integración:

1. **Respuestas 404 en Conexión con Herramientas de Desarrollo:** Extensiones de IDE (Continue, Cline, OpenCode, Antigravity) solicitaban rutas estándar de la especificación OpenAI (`GET /v1/models` y `POST /v1/chat/completions`), generando excepciones `404 Not Found` en el servidor FastAPI.
2. **Bloqueo Silencioso de Herramientas en Antigravity CLI (`agy`):** Al invocar `agy` en modo headless (`agy -p ...`), el subsistema de herramientas (*jetski*) denegaba automáticamente permisos de lectura sobre imágenes y archivos locales sin interacción de consola (`jetski: no output produced — a tool required the "read_file" permission...`). Esto ocasionaba que `AgyCLIProvider` recibiera salidas vacías y conmutara al mensaje de contingencia.
3. **Invocación Errónea de OpenCode CLI:** La llamada utilizaba la sintaxis desactualizada `opencode -p "prompt"`, la cual no correspondía al comando oficial de la versión actual (`opencode run "prompt"`), provocando códigos de salida erróneos y banners de sesión en la respuesta.
4. **Colapso por Escaneo de Repositorio en Procesos CLI:** Ejecutar herramientas CLI desde la raíz del proyecto causaba demoras de hasta 40 segundos e hipertrofia de contexto por indexación recursiva de git y archivos locales.
5. **Cortocircuito Prematuro Determinista en Consultas Abiertas y Capítulos:** Consultas de lectura, síntesis ejecutiva o resúmenes de secciones específicas (ej: *"hazme un resumen sobre el capitulo 2"*) eran interceptadas por la etapa determinista de declinación si los tokens de la pregunta no coincidían con el nombre exacto de un parámetro indexado en L1, impidiendo el enrutamiento a los motores de lenguaje.
6. **Legibilidad Deficiente en la Interfaz (Texto Plano Sin Estructura):** Respuestas complejas generadas por modelos avanzados con títulos Markdown (`###`), viñetas, negritas y tablas se renderizaban como cadenas de texto plano comprimidas sin formato visual en la burbuja del chat.

---

## 2. Decisión Arquitectónica

Se implementa una solución integral de cinco pilares para expandir la inteligencia documental y la experiencia conversacional de Pydective:

```text
                                  ┌────────────────────────────────┐
                                  │      Pydective Chat UI         │
                                  │  (Resultados.html + app.js)    │
                                  └───────────────┬────────────────┘
                                                  │ POST /chat/{hash}
                                                  ▼
                                  ┌────────────────────────────────┐
                                  │       chat_service.py          │
                                  │  - Detección de Capítulos      │
                                  │  - Carga Textual PyMuPDF/OCR   │
                                  │  - Enrutamiento Estricto IA    │
                                  └───────────────┬────────────────┘
                                                  │
                 ┌────────────────────────────────┼────────────────────────────────┐
                 ▼                                ▼                                ▼
   ┌───────────────────────────┐    ┌───────────────────────────┐    ┌───────────────────────────┐
   │    GeminiProvider         │    │     AgyCLIProvider        │    │    OpenCodeCLIProvider    │
   │  (Cloud Multimodal SDK)   │    │ (agy --skip-permissions)  │    │  (opencode run "prompt")  │
   └───────────────────────────┘    └───────────────────────────┘    └───────────────────────────┘
                 │                                │                                │
                 └────────────────────────────────┼────────────────────────────────┘
                                                  │
                                                  ▼
                                  ┌────────────────────────────────┐
                                  │      ChatOutput Structure      │
                                  │  - respuesta (Markdown crudo)  │
                                  │  - citas: ['[Página X]']       │
                                  │  - evidencias_relacionadas     │
                                  │  - motor_utilizado: 'cli:agy'  │
                                  └───────────────┬────────────────┘
                                                  │
                                                  ▼
                                  ┌────────────────────────────────┐
                                  │       Renderizado en UI        │
                                  │  - marked.js GFM / breaks      │
                                  │  - inline-page-tag buttons     │
                                  │  - Pastillas de Evidencia      │
                                  └────────────────────────────────┘
```

### 2.1 Proveedores CLI Nativos y Aislamiento de Entorno (`cli_provider.py`)
- **`AgyCLIProvider`:** Invoca el binario oficial con flags `--dangerously-skip-permissions` y `--disable-slash-commands`, permitiendo que el motor headless inspeccione recortes de imágenes y texto sin pausas de aprobación.
- **`OpenCodeCLIProvider`:** Invoca la sintaxis nativa `opencode run "<prompt>"`, filtrando cabeceras y secuencias ANSI del terminal.
- **Aislamiento de Directorio:** Ambos proveedores ejecutan con `cwd=tempfile.gettempdir()` y `stdin=subprocess.DEVNULL`, eliminando el escaneo recursivo del proyecto y reduciendo el tiempo de respuesta a 5–7 segundos.
- **Tiempo Límite Dinámico:** Se incrementó `CLI_SUBPROCESS_TIMEOUT_SECONDS` a 65 segundos en `settings.py`.

### 2.2 Endpoints de Interoperabilidad OpenAI (`main.py`)
- `GET /v1/models`: Retorna la lista formal de modelos soportados (`chain`, `agy`, `opencode`, `gemini-2.5-flash-lite`, `local`), con id y metadatos estándar OpenAI.
- `POST /v1/chat/completions`: Traduce llamadas entrantes al pipeline interno `process_chat_query`, devolviendo el payload estándar `ChatCompletionResponse`.

### 2.3 Comprensión Textual, Mapeo de Capítulos y OCR Complementario
- **Extracción de Texto Directo:** PyMuPDF lee el contenido literal de los folios relevantes incorporándolos en el contexto (`--- [Página X] ---`).
- **Detección de Capítulos:** Regex `r"(?:capitulo|capítulo|cap)\s*(\d+)"` identifica el capítulo consultado y localiza el folio exacto en el documento.
- **OCR Complementario para Diagramas:** Si la consulta involucra elementos visuales, se extrae el texto de diagramas mediante `RapidOCR` y se alimenta al prompt del modelo.

### 2.4 Enrutamiento Estricto No-Determinista
- Cuando el usuario selecciona un motor explícito (`agy`, `opencode`, `gemini`, `local`), o cuando la consulta es de resumen o contenido abierto (`is_summary_query`, `is_content_query`), se elude la interrupción determinista estática. La consulta se transfiere de forma obligatoria y estricta al LLM seleccionado, garantizando razonamiento autónomo con citas verificables `[Página X]`.

### 2.5 Renderizado Enriquecido de Markdown con `marked.js`
- Se incorpora la librería `marked.min.js` en formato local estático (`app/static/js/marked.min.js`), eliminando dependencias de CDN externas y asegurando operación offline.
- Se configura `marked.setOptions({ breaks: true, gfm: true })` para convertir la respuesta del asistente en HTML limpio con encabezados (`###`), viñetas, tablas y bloques monoespaciados con estilos dark theme en `pdf_viewer.css`.
- Las citas textuales `[Página X]` dentro del markdown se transforman automáticamente mediante expresiones regulares en botones interactivos (`.inline-page-tag`), permitiendo navegación inmediata en el visor PDF.

---

## 3. Consecuencias y Beneficios

### Positivas
- **Interoperabilidad Total:** Compatibilidad transparente con herramientas CLI y extensiones externas sin generar errores 404 en el backend.
- **Capacidad Analítica Integral:** Capacidad de sintetizar capítulos específicos y resumir expedientes completos con fidelidad jurídica y forense.
- **Grounding Dinámico y Navegable:** Cada punto del resumen incluye su cita de origen, que al pulsarse resalta el bounding box exacto en el visor PDF.
- **Presentación Visual Superior:** Los dictámenes y resúmenes se leen con formato profesional, títulos claros y tablas organizadas.
- **Operación Desconectada y Segura:** Tanto los proveedores CLI locales como la librería de renderizado Markdown operan sin depender de servicios en la nube.

### Negativas / Mitigaciones
- **Consumo de CPU Durante Ejecución CLI:** Invocaciones a `opencode` o `agy` consumen ciclos de cómputo en la máquina host. Se mitiga mediante aislamiento en `tempfile.gettempdir()`, límites de tiempo (`timeout=65.0s`) y control de procesos en segundo plano.
