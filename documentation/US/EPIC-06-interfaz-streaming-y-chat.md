# Épica 6: Interfaz, Streaming y Chat

> **Objetivo:** Proporcionar una experiencia de usuario de primer nivel mediante SSR en FastAPI con Tailwind CSS v4, transmisión reactiva de eventos Server-Sent Events (SSE) para el progreso de extracción y un chat documental conversacional multi-turno con citas rigurosas fundamentadas en L1.

---

### US-20: Interfaz Web SSR Moderna con Tailwind CSS v4 y Jinja2

- **ID:** `US-20`
- **Requisitos asociados:** `RF-001`, `RF-010`, `RF-075`, `ADR-002`
- **Prioridad:** Alta | **Estimación:** 3 pts

#### Narrativa
**Como** usuario que interactúa con la aplicación,  
**Quiero** una interfaz moderna, oscura y estilizada con Glassmorphism donde pueda arrastrar mi PDF y seleccionar parámetros mediante chips interactivos,  
**Para** configurar rápidamente el análisis forense de cualquier documento sin fricción.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Zona de arrastre y suelta (Dropzone) interactiva**
   - **Dado** que el usuario arrastra un archivo PDF sobre la zona `#dropzone-area`,
   - **Cuando** suelta el archivo,
   - **Entonces** se activa el estado de arrastre (`dragover`), se valida la extensión `.pdf` y se muestra el nombre y tamaño formateado en KB/MB.

2. **Escenario: Gestión dinámica de parámetros con tags/chips**
   - **Dado** que el usuario escribe un parámetro o hace clic en un preset (`+ Total`, `+ Arrendador`),
   - **Cuando** presiona Enter o hace clic en "Agregar",
   - **Entonces** se crea un chip visual removible en `#active-params-container` y se actualiza el array de parámetros a enviar.

---

### US-21: Transmisión de Progreso en Tiempo Real vía SSE

- **ID:** `US-21`
- **Requisitos asociados:** `RF-095`, `RNF-001`, `ADR-002 Sección 9`
- **Prioridad:** Alta | **Estimación:** 5 pts

#### Narrativa
**Como** usuario que envía un PDF de hasta 20 páginas,  
**Quiero** observar el avance en tiempo real página por página a través de Server-Sent Events (`/procesar/stream`),  
**Para** tener visibilidad continua del estado de cada página (`local`, `needs_ai`, `empty`) y evitar timeouts en conexiones HTTP prolongadas.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Emisión de eventos SSE en vivo**
   - **Dado** que se envía un PDF al endpoint `POST /procesar/stream`,
   - **Cuando** el orquestador inicia y procesa cada página,
   - **Entonces** emite eventos SSE `tipo: "inicio"`, `tipo: "pagina"` con el carril resuelto y duración en ms, y finalmente `tipo: "completado"`.

2. **Escenario: Actualización visual reactiva en el cliente**
   - **Dado** que el navegador recibe eventos SSE mediante `fetch` y `ReadableStreamReader`,
   - **Cuando** llega el evento de la página 3 como `carril: "local"`,
   - **Entonces** la barra de progreso avanza, el bloque de la página 3 se torna verde (`page-local`) y la consola virtual muestra la telemetría sin recargar la página.

---

### US-22: Visualización de Dictamen y Hallazgos Enriquecidos

- **ID:** `US-22`
- **Requisitos asociados:** `RF-070`, `RF-071`, `RF-072`, `RF-073`, `RF-074`, `RF-076`, `RF-077`
- **Prioridad:** Media | **Estimación:** 3 pts

#### Narrativa
**Como** analista de documentos,  
**Quiero** revisar una tabla estructurada con los hallazgos extraídos, su `evidence_score`, el método de extracción y citas exactas por página,  
**Para** verificar inmediatamente la veracidad de los datos y examinar el desglose técnico de cada página.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Vista de dictamen forense (`/resultados/{pdf_hash}`)**
   - **Dado** un trabajo completado exitosamente,
   - **Cuando** se visualiza `resultados.html`,
   - **Entonces** se muestran las tarjetas de métricas (nivel de caché, tiempo total en ms, páginas completadas) y la tabla con parámetro, valor, valor normalizado, badge del método y barra de confianza.

2. **Escenario: Citas exactas y desglose por página**
   - **Dado** que un hallazgo fue extraído en la página 2 y respaldado por una firma,
   - **Cuando** se revisa el desglose inferior,
   - **Entonces** la tarjeta de la página 2 refleja el tiempo invertido, las evidencias detectadas y los metadatos visuales inventariados.

---

### US-23: Pydective Chat con Grounding en L1 y Citas Verificables

- **ID:** `US-23`
- **Requisitos asociados:** `RF-093`, `RF-094`, `RF-110`, `RF-111`, `RF-112`, `ADR-004 Sección 12`, `ADR-008`
- **Prioridad:** Alta | **Estimación:** 8 pts

#### Narrativa
**Como** usuario o perito que examina contratos y expedientes complejos,  
**Quiero** realizar consultas libres, pedir lecturas de cláusulas y resúmenes ejecutivos por capítulo a través de Pydective Chat (`POST /chat/{pdf_hash}`), pudiendo alternar entre motores de lenguaje (Gemini, agy, opencode, local) y visualizando respuestas formateadas en Markdown enriquecido con citas interactivas,  
**Para** analizar el expediente con máxima fidelidad, sin bloqueos deterministas prematuros y navegando directamente al folio citado en el visor.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Retrieval asociativo previo antes de Gemini (Ahorro del 80% de tokens)**
   - **Dado** una pregunta del usuario como *"¿A cuánto asciende la cláusula penal pecuniaria?"*,
   - **Cuando** se procesa la consulta en `chat_service.py`,
   - **Entonces** se recuperan de L1 únicamente las 2-3 páginas o bloques relevantes y se envían como contexto acotado a Gemini, logrando un TTFT < 600 ms.

2. **Escenario: Citas obligatorias y declinación ante datos ausentes**
   - **Dado** que la respuesta del modelo localiza el dato en la página 3,
   - **Cuando** se emite la respuesta al usuario,
   - **Entonces** incluye la cita `[Página 3]` enlazada al `evidence_id`. Si el dato no figura en el documento y la consulta es cerrada, declara explícitamente su ausencia sin alucinar.

3. **Escenario: Lectura textual y resúmenes por capítulo con enrutamiento estricto a IA**
   - **Dado** una pregunta como *"hazme un resumen sobre el capitulo 2"* con motor `agy` u `opencode` seleccionado,
   - **Cuando** `chat_service.py` detecta el número de capítulo,
   - **Entonces** localiza la página exacta (Pág 4: Cláusulas Económicas), extrae el texto nativo con PyMuPDF / RapidOCR y transfiere la síntesis al motor CLI sin interceptar deterministamente, retornando las cláusulas con cita `[Página 4]`.

4. **Escenario: Renderizado de Markdown y citas inline interactivas en cliente**
   - **Dado** una respuesta del modelo con formato Markdown (encabezados `###`, viñetas, negritas, tablas),
   - **Cuando** `app.js` recibe el payload,
   - **Entonces** procesa el contenido con `marked.min.js` y transforma las citas `[Página X]` en botones `.inline-page-tag` que saltan inmediatamente al folio correspondiente en el visor PDF.

5. **Escenario: Documento no encontrado o sesión expirada (HTTP 404)**
   - **Dado** una petición de chat para un `pdf_hash` no existente o expirado en L1,
   - **Cuando** el endpoint recibe la llamada,
   - **Entonces** responde HTTP 404 con error estructurado `DOCUMENT_NOT_FOUND_OR_EXPIRED`, solicitando recargar el PDF para iniciar una nueva sesión.
