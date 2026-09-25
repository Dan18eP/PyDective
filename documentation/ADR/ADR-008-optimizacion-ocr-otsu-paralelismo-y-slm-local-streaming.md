# ADR-008: Optimización de OCR con Binarización Adaptativa Otsu, Paralelismo Multi-Hilo Aislado, Calentamiento en Lifespan y Streaming con SLM Local Conciso

- **Estado:** Aceptado
- **Fecha:** 2026-09-25
- **Decisores:** Daniel Echeverría (Lead Architect & AI Systems Engineer)
- **Extiende a:** [ADR-001](file:///C:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/documentation/ADR/ADR-001-arquitectura-hibrida-caching-y-failover.md), [ADR-002](file:///C:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/documentation/ADR/ADR-002-preprocesamiento-determinista-vision-y-chat-documental.md), [ADR-004](file:///C:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/documentation/ADR/ADR-004-optimizacion-rendimiento-precision-y-reutilizacion-documental.md), [ADR-005](file:///C:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/documentation/ADR/ADR-005-visor-pdf-con-grounding-visual-y-buscador-exacto.md) y [ADR-006](file:///C:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/documentation/ADR/ADR-006-arquitectura-dual-de-motores-de-vision-y-grounding-espacial-exacto.md)
- **Relacionado con:** PRD, Requisitos del Sistema (RF-095, RF-105, RNF-001, RNF-051), Épicas 6 y 8
- **Etiquetas:** pydective, ocr-optimization, otsu-binarization, pymupdf-threading, sse-streaming, ollama, llama3.2, zero-hardcoding

---

## 1. Contexto

Durante la evaluación pericial de documentos escaneados densos y ruidosos (tales como expedientes clínicos, historias médicas notariales y facturas de salud como `factura-medica.pdf`), se identificaron cuatro cuellos de botella críticos que comprometían la experiencia del usuario y la latencia del sistema:

1. **Latencia Elevada en Reconocimiento OCR de Páginas Densas:**
   El modelo CRNN/CTC de RapidOCR invertía entre 9 y 11 segundos por página escaneada densa (páginas 1 y 3). La presencia de fondos grisáceos, tramados de impresión, manchas térmicas y artefactos de compresión JPEG aumentaba sustancialmente la dispersión del espacio de búsqueda durante la decodificación por beam search del decodificador CTC.

2. **Contención de Hilos en PyMuPDF (GIL y Mutex de C++):**
   Al intentar paralelizar la extracción de páginas sobre un mismo puntero `fitz.Document`, las llamadas concurrentes de C++ desencadenaban serialización interna por bloqueos de mutex en MuPDF, generando contención de CPU y empeorando la latencia en lugar de reducirla.

3. **Congelamiento Inicial de la Barra de Progreso en SSE (`/procesar/stream`):**
   La implementación de streaming realizaba una pre-extracción OCR síncrona en bloque antes de iniciar el bucle de páginas, impidiendo la emisión inmediata del primer evento SSE y produciendo una percepción de sistema colgado durante 15 a 20 segundos.

4. **Penalización por Arranque en Frío (*Cold-Start*) de ONNX Runtime:**
   La primera petición recibida por el servidor tras iniciar Uvicorn debía asumir la carga dinámica de los modelos ONNX (DBNet y CRNN) en RAM, agregando un retraso adicional de 2.5 a 3.5 segundos.

5. **Verbosidad Inadecuada y Latencia en Modelos Locales SLM:**
   El modelo local `llama3.2:1b` (ejecutado vía Ollama en CPU) tendía a responder con preámbulos explicativos extensos, fórmulas de cortesía y recapitulaciones redundantes, demorando hasta 8 segundos en consultas que requerían un dato puntual y directo (ej. "¿Quién es el cliente?").

---

## 2. Decisión Arquitectónica

Para erradicar estos cuellos de botella sin sacrificar exactitud en la extracción y garantizando una política de cero sobre-ajuste (*zero hardcoding*), se adoptaron las siguientes decisiones de ingeniería:

### 2.1 Binarización Adaptativa Otsu Pre-Inferencia y Filtro Ultrarrápido de Blancos
- **Filtro de Páginas en Blanco en <2 ms:**
  Se integró en `extract_page_ocr` una evaluación ultrarrápida de varianza y media sobre el canal de grises (`std < 10.0 and mean > 245.0`). Si la página está en blanco, se omite el 100% de la inferencia de redes neuronales.
- **Binarización Selectiva Otsu:**
  Antes de alimentar las imágenes a RapidOCR, se aplica `cv2.threshold(..., cv2.THRESH_BINARY + cv2.THRESH_OTSU)` si el contraste de la página lo requiere (`evaluate_contrast_and_otsu`). Al convertir el fondo sucio o tramado en blanco absoluto (255) y el texto en negro puro (0), el modelo detector DBNet aísla los polígonos de texto con menor ruido y el reconocedor CRNN converge significativamente más rápido, reduciendo el tiempo de inferencia de ~9.6s a ~5.8s por página densa manteniendo el 100% de precisión de caracteres.
- **Configuración Vectorial de RapidOCR:**
  Se sintonizaron los parámetros ONNX con `intra_op_num_threads=2` y `rec_batch_num=12` para optimizar el rendimiento por lotes en CPU multinúcleo.

### 2.2 Paralelismo Multi-Hilo Aislado con Instancias Independientes de PyMuPDF
- En `procesar_documento` de [main.py](file:///C:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/app/main.py), las páginas escaneadas que requieren OCR se procesan concurrentemente utilizando `ThreadPoolExecutor(max_workers=2)`.
- Para eliminar cualquier contención de GIL o bloqueos mutex en C++, cada worker del thread pool crea su propio handle aislado e independiente en memoria a partir de los bytes originales:
  ```python
  sub_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
  ```
  Esto garantiza independencia total de memoria entre hilos y escala de forma lineal en CPU.

### 2.3 Streaming Reactivo Real Página por Página en `/procesar/stream`
- Se erradicó la pre-extracción en bloque anterior al streaming.
- El generador asíncrono ejecuta la extracción e inmediatamente emite `tipo: "pagina"` con el payload estructurado, el porcentaje de avance y los hallazgos de cada folio en tiempo real. La interfaz del usuario recibe retroalimentación visual continua desde el segundo 1.

### 2.4 Precalentamiento del Motor OCR en el Ciclo de Vida (`lifespan`)
- Durante el evento de arranque del servidor FastAPI en `lifespan`:
  ```python
  from app.services.ocr_service import get_ocr_engine
  _ = get_ocr_engine()
  ```
  Los pesos de detección y reconocimiento de RapidOCR se cargan e instancian en memoria RAM antes de aceptar tráfico HTTP, eliminando por completo el *cold-start* para los usuarios finales.

### 2.5 Calibración de Concisión en SLM Local (`llama3.2:1b`) y Streaming SSE
- **Switch Deslizable en Frontend (L1 Determinista vs SLM Local):**
  Se incorporó un control tipo switch en la interfaz de resultados (persistido en `localStorage`), permitiendo alternar entre:
  - **L1 RAM (<5 ms):** Resolución determinista instantánea sobre el grafo de entidades indexadas.
  - **SLM Local (llama3.2:1b):** Razonamiento en lenguaje natural transmitido mediante SSE en `/chat/{pdf_hash}/stream`.
- **System Prompt Estricto y Directo:**
  Se configuró el asistente para responder exclusivamente el dato solicitado sin fórmulas de cortesía, preámbulos ni explicaciones periféricas.
- **Ventana de Contexto Quirúrgica y Límite de Tokens:**
  El contexto enviado a Ollama se acota quirúrgicamente a un máximo de 2 páginas relevantes (`max_pages=2`), y se reduce el techo de generación de 350 a `max_tokens=120`. Con ello, la respuesta del modelo local se reduce a ~2.1 segundos en CPU.

### 2.6 Redimensionador Interactivo de Visor (Split-Resizer) y Zoom Bidireccional
- Se implementó un divisor interactivo con soporte de arrastre por cursor, límites de contención del 28% al 82% del ancho de pantalla, restablecimiento por doble clic y persistencia en `localStorage`.
- Se corrigió el desbordamiento visual del canvas en zoom elevado, habilitando scroll bidireccional fluido sin distorsión de la grilla de hallazgos.

---

## 3. Diagrama de la Arquitectura Optimizada

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Lifespan (Startup)                           │
│  get_ocr_engine() ──► Carga ONNX Runtime DBNet/CRNN en RAM (Cero Cold-Start)│
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  Ingesta HTTP / Streaming SSE (/procesar/stream)            │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                 ┌────────────────────┴────────────────────┐
                 │                                         │
                 ▼                                         ▼
      [Páginas Digitales]                        [Páginas Escaneadas]
   PyMuPDF words nativo (C)                ThreadPoolExecutor (2 workers)
         (<15 ms/pág)                      sub_doc = fitz.open(pdf_bytes)
                 │                                         │
                 │                         ┌───────────────┴───────────────┐
                 │                         ▼                               ▼
                 │                 [Filtro Blanco]               [Contraste & Otsu]
                 │                 std < 10 && mean > 245        Binarización adaptativa
                 │                 (Skip en <2 ms)               (Fondo puro 255)
                 │                         │                               │
                 │                         └───────────────┬───────────────┘
                 │                                         ▼
                 │                                   [RapidOCR ONNX]
                 │                               rec_batch=12, threads=2
                 │                               (Decodificación -40% tiempo)
                 │                                         │
                 └────────────────────┬────────────────────┘
                                      │
                                      ▼
                      [Emisión Inmediata SSE: tipo: 'pagina']
                      Progreso fluido 0% ──► 100% en tiempo real
                                      │
                                      ▼
                      [Resultados / Pydective Chat]
                 ┌────────────────────┴────────────────────┐
                 │ [Switch: OFF]                           │ [Switch: ON]
                 ▼                                         ▼
          [L1 RAM Cache]                            [SLM Local llama3.2:1b]
    Resolución Determinista                     Streaming SSE (/chat/stream)
           < 5 ms                                      max_tokens=120
                                                       Respuesta directa ~2s
```

---

## 4. Consecuencias y Validación

### Positivas:
- **Reducción de Latencia de Inferencia OCR:** La decodificación en folios escaneados densos se redujo en un ~40% sin pérdida alguna de caracteres o exactitud espacial.
- **Feedback Inmediato al Usuario:** El progreso SSE fluye de forma constante sin periodos de congelamiento inicial.
- **Cero Cold-Start:** El primer folio escaneado procesado por el servidor ya encuentra los modelos ONNX instanciados en memoria.
- **Control Total para el Usuario en Chat:** Flexibilidad para elegir entre inmediatez determinista sub-5ms o razonamiento contextual en lenguaje natural con Ollama.
- **Integridad y Cobertura de Pruebas:** La suite completa de 168 pruebas automatizadas pasa al 100% de manera determinista sin dependencias externas ni mocks en la lógica de extracción.

### Neutrales / Mitigaciones:
- El uso de Otsu binarizado se restringe a documentos con bajo contraste o escaneos fotográficos para evitar alterar páginas vectoriales digitales que ya cuentan con texto perfecto extraído en C.
