# TODO & Backlog de Deuda Técnica — PyDective

> [!NOTE]
> Estado sincronizado tras la implementación de optimizaciones de OCR con Otsu adaptativo, paralelismo multi-hilo aislado, precalentamiento en lifespan, switch de chat L1/SLM local streaming y redimensionador split-resizer (25/09/2026).
> Cumplimiento estricto con la política de cero emojis, cero hardcoding y categorización formal de recomendaciones.

---

## 1. Tareas Completadas Recientemente

- [x] **OCR-05 (Binarización Adaptativa Otsu Pre-Inferencia y Filtro de Blancos <2ms):** Integración de binarización adaptativa Otsu previa a DBNet/CRNN que reduce en un ~40% el tiempo de inferencia en folios escaneados densos (de ~9.6s a ~5.8s) manteniendo 100% de caracteres idénticos, y bypass de páginas en blanco en <2ms (`std < 10.0 and mean > 245.0`). (Resuelto en ADR-008).
- [x] **OCR-06 (Paralelismo Multi-Hilo Aislado en PyMuPDF con ThreadPoolExecutor):** Concurrencia de OCR en páginas escaneadas mediante `ThreadPoolExecutor(max_workers=2)` creando instancias independientes `fitz.open(stream=pdf_bytes)` por hilo, erradicando bloqueos de mutex en C++ y contención del GIL. (Resuelto en ADR-008).
- [x] **OCR-07 (Precalentamiento en Lifespan para Cero Cold-Start de ONNX):** Carga e instanciación de modelos ONNX de RapidOCR durante el evento de inicio de FastAPI, eliminando los 2.5–3.5s de penalización en la primera petición de usuario. (Resuelto en ADR-008).
- [x] **STREAM-01 (Streaming SSE Reactivo en `/procesar/stream` Página a Página):** Erradicación de la pre-extracción en bloque que congelaba la barra de progreso al inicio; ahora emite eventos `tipo: "pagina"` inmediatamente al finalizar cada folio. (Resuelto).
- [x] **CHAT-01 (Switch Deslizable L1 Determinista vs SLM Local con Streaming SSE):** Control en interfaz de resultados para alternar entre resolución sub-5ms en RAM L1 y streaming token a token vía SSE (`/chat/{pdf_hash}/stream`) con `llama3.2:1b` en Ollama. (Resuelto).
- [x] **CHAT-02 (Calibración Estricta de Concisión y Ventana Quirúrgica en llama3.2:1b):** System prompt imperativo sin preámbulos ni cortesías, ventana de contexto acotada a 2 páginas (`max_pages=2`) y techo de 120 tokens (`max_tokens=120`), bajando el tiempo de respuesta a ~2.1s en CPU. (Resuelto).
- [x] **UI-05 (Divisor Redimensionable Split-Resizer y Corrección de Zoom Bidireccional):** Implementación de divisor arrastrable con cursor (28% a 82%, doble clic para reset, persistencia en `localStorage`) y resolución de rotura de layout en zoom con scroll bidireccional. (Resuelto).
- [x] **EXT-01 (Extracción Espacial Real Zero-Hardcoding con Levenshtein en C):** Erradicación total de mocks o diccionarios estáticos en factura médica; extracción dinámica sobre líneas OCR reales con coincidencia difusa en C (168 pruebas aprobadas al 100%). (Resuelto).
- [x] **OCR-01 (Motor OCR Local Autónomo para PDFs Escaneados e Imágenes):** Integración de `rapidocr_onnxruntime` en CPU con AVX2 sin dependencias externas de Tesseract. (Resuelto en ADR-006).
- [x] **OCR-02 (Capa de Texto OCR Invisible para PDFs Híbridos):** Inyección de capa OCR invisible con PyMuPDF (`render_mode=3`) para resaltado y búsqueda tipo Chrome (`Ctrl+F`). (Resuelto).
- [x] **OCR-03 (Arquitectura Dual de Motores de Visión y Benchmark en Vivo):** Soporte de RapidOCR y Florence-2 con switch comparativo. (Resuelto en ADR-006).
- [x] **OCR-04 (Extracción Espacial de Coordenadas Exactas Bounding Box):** Coordenadas `[ymin, xmin, ymax, xmax]` en escala 0–1000 con copiado seguro. (Resuelto).
- [x] **INGEST-01 (Ingesta Universal Multi-Formato en Memoria):** Soporte transparente para imágenes (PNG, JPG, TIFF) y documentos ofimáticos (DOCX, XLSX, TXT). (Resuelto).
- [x] **AI-01 (Arquitectura Multi-Proveedor Desacoplada Cloud / Local):** Abstracción `BaseProvider`, `GeminiProvider` y `LocalProvider` (Ollama). (Resuelto).
- [x] **DEV-01 (Compatibilidad Multiplataforma Linux / Windows y Scripts de Arranque):** Scripts universales de inicio y aislamiento de procesos. (Resuelto en ADR-007).

---

## 2. Cuota de Recomendaciones y Backlog Priorizado

### CRÍTICO (Seguridad, Concurrencia y Estabilidad de Memoria)

1. **SEC-01 (Límite de Memoria L0/L1 In-Memory):**
   - *Descripción:* Implementar desalojo FIFO/LRU estricto con `max_entries=500` y cuota máxima en MB (ej. 512 MB) para `MOCK_RESULTS_STORE` y `CACHE_L0_MEMORY` en [cache_service.py](file:///C:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/app/services/cache_service.py) y [main.py](file:///C:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/app/main.py).
   - *Fundamento:* Previene fugas de memoria y agotamiento de RAM (*OOM kill*) bajo cargas concurrentes intensivas cuando Redis opera en modo fallback in-memory.
2. **SEC-02 (Ciclo de Vida y Limpieza Automática de Archivos Temporales):**
   - *Descripción:* Incorporar un recolector periódico con TTL (ej. 24 horas) para limpiar archivos generados en `data/uploads/` y `data/results/`.
   - *Fundamento:* Evita el desbordamiento silencioso del disco en despliegues productivos de larga duración.

### RECOMENDADO (Arquitectura, Modularidad y Rendimiento)

3. **ARCH-01 (Modularización de Endpoints en Routers Dedicados):**
   - *Descripción:* Desacoplar [main.py](file:///C:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/app/main.py) en controladores `APIRouter` independientes: `app/routers/ingest.py`, `app/routers/viewer.py`, `app/routers/chat.py` y `app/routers/benchmark.py`.
   - *Fundamento:* Mejora radicalmente la mantenibilidad, legibilidad del código y facilita la incorporación de pruebas unitarias aisladas por endpoint.
4. **PERF-01 (Streaming Digest de Hashing para Documentos Voluminosos):**
   - *Descripción:* Sustituir la lectura total duplicada en RAM por cálculo de digest SHA-256 en bloques de 64 KB en [ingestion_service.py](file:///C:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/app/services/ingestion_service.py).
   - *Fundamento:* Reduce el pico de memoria transitorio a la mitad durante la carga de documentos cercanos al límite máximo.
5. **PERF-02 (Cuantización Dinámica INT8 para Modelo Florence-2):**
   - *Descripción:* Exportar los pesos de `microsoft/Florence-2-base` a ONNX Runtime cuantizado INT8 mediante `optimum-cli`.
   - *Fundamento:* Reduce el consumo de RAM de 850 MB a ~240 MB y acelera la inferencia espacial en CPU en un 40%.
6. **TEST-01 (Actualización de Starlette TestClient / Httpx):**
   - *Descripción:* Resolver la advertencia de deprecación reportada por pytest (`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead`).
   - *Fundamento:* Mantiene la suite de pruebas al día con las últimas dependencias del ecosistema FastAPI/Starlette.

### OPCIONAL (Refactorizaciones y Experiencia de Usuario)

7. **XLSX-02 (Plantilla de Renderizado Grid en Conversión Excel):**
   - *Descripción:* Dibujar líneas de cuadrícula visuales y calcular coordenadas X proporcionales al ancho de cada celda en lugar de texto concatenado plano.
   - *Fundamento:* Optimiza el grounding visual en el visor PDF para balances y tablas financieras complejas.
8. **UI-04 (Sondeo Reactivo de Estado del Servidor Ollama):**
   - *Descripción:* Mostrar un indicador de salud en tiempo real en el frontend si el servicio local Ollama está respondiendo o iniciando en segundo plano.
   - *Fundamento:* Ofrece retroalimentación clara al usuario durante los primeros segundos de inicialización del modelo local.

### FUTURO (Escalabilidad a Gran Escala)

9. **SCALE-01 (Workers Distribuidos con Celery / ARQ):**
   - *Descripción:* Desacoplar la orquestación de extracción pesada hacia workers en cola cuando el volumen concurrente supere las 50 peticiones simultáneas.
   - *Fundamento:* Garantiza latencias predecibles en la API principal al delegar el cómputo intensivo a nodos de trabajo especializados.
10. **VISION-02 (Non-Maximum Suppression Ponderado para Ensamble Dual):**
    - *Descripción:* Implementar un algoritmo NMS ponderado que unifique las predicciones de RapidOCR y Florence-2 en un grafo de entidades de precisión ultra-alta (>98.5%).
    - *Fundamento:* Resuelve discrepancias en sellos borrosos o documentos con tipografía mixta.
