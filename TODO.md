# TODO & Backlog de Deuda Tecnica — PyDective

> [!NOTE]
> Estado sincronizado tras la implementacion de la Arquitectura Dual de Vision (RapidOCR vs Florence-2), Ingesta Universal Multi-Formato, Proveedores Desacoplados y Compatibilidad Multiplataforma Linux/Windows (24/09/2026).
> Cumplimiento estricto con la politica de cero emojis y categorizacion formal de recomendaciones.

---

## 1. Tareas Completadas Recientemente

- [x] **OCR-01 (Motor OCR Local Autonomo para PDFs Escaneados e Imagenes):** Integrar motor OCR local sin dependencia de binarios externos de Tesseract (`rapidocr_onnxruntime` en CPU con AVX2) para permitir que documentos escaneados e imagenes extraigan entidades en modo desconectado. (Resuelto: precision salta al 92.5% global y 96.7% en imagenes).
- [x] **OCR-02 (Capa de Texto OCR Invisible para PDFs Hibridos):** Inyectar capa OCR invisible con PyMuPDF (`render_mode=3`) para habilitar el resaltado de texto nativo, seleccion con cursor y busqueda tipo Chrome (`Ctrl+F`) sobre escaneos e imagenes. (Resuelto).
- [x] **OCR-03 (Arquitectura Dual de Motores de Vision y Benchmark en Vivo):** Incorporar selector de motor de vision en frontend y endpoint `/procesar` con soporte para RapidOCR (rapido, <180ms) y Florence-2 (profundo, grounding denso), permitiendo ejecucion simultanea concurrente con telemetria comparativa. (Resuelto en ADR-006).
- [x] **OCR-04 (Extraccion Espacial de Coordenadas Exactas Bounding Box):** Normalizar y exponer coordenadas `[ymin, xmin, ymax, xmax]` en escala 0–1000 para cada hallazgo y objeto visual detectado, con botones de copiado y visualizacion interactiva. (Resuelto).
- [x] **INGEST-01 (Ingesta Universal Multi-Formato en Memoria):** Soporte transparente para imagenes (PNG, JPG, TIFF) y formatos ofimaticos (DOCX, XLSX, TXT) convertidos en memoria a PDF equivalente. (Resuelto).
- [x] **BUG-XLSX-01 (Correccion de Separador Pipe en Extraccion Espacial):** Corregir corte indebido de delimitador pipe en celdas de hojas de calculo XLSX. (Resuelto: precision 100% en XLSX).
- [x] **BUG-ENC-01 (Soporte UTF-8 Nativo en Conversion DOCX y TXT):** Eliminar restriccion Latin-1 y garantizar codificacion UTF-8 nativa para tildes y caracteres hispanos. (Resuelto: precision 100% en DOCX y TXT).
- [x] **VIS-01 (Segmentacion Morfologica de Firmas y Sellos en Imagenes Puras):** Deteccion de componentes conexos y analisis de contornos con OpenCV para segmentar firmas y sellos en imagenes rasterizadas. (Resuelto).
- [x] **AI-01 (Arquitectura Multi-Proveedor Desacoplada Cloud / Local):** Crear abstraccion `BaseProvider`, `GeminiProvider` y `LocalProvider` (Ollama con modelo Qwen2.5:3b) con gestion automatica de ciclo de vida del daemon. (Resuelto).
- [x] **DEV-01 (Compatibilidad Multiplataforma Linux / Windows y Scripts de Arranque):** Implementar `install_dependencies.py`, `run_app.py`, `run.py`, `install.sh` y `run.sh` con deteccion de binarios en rutas POSIX y aislamiento de procesos con `start_new_session=True`. (Resuelto en ADR-007).
- [x] **UI-03 (Presets de Parametros Rapidos y Fallback de Portapapeles):** Incorporar chips interactivos (+ Nombre / Titular, + Notario, + Valor Declarado, + Cliente), default con 'nombre' y fallback de portapapeles para navegadores Linux Wayland/X11 y entornos sin HTTPS. (Resuelto).
- [x] **AI-02 (Soporte CLI Multimodal Antigravity y OpenCode):** Implementar `AgyCLIProvider` con `--dangerously-skip-permissions` y `OpenCodeCLIProvider` con `opencode run`, ejecutados en directorio temporal aislado con `cwd=tempfile.gettempdir()` y timeout de 65s. (Resuelto en ADR-008).
- [x] **AI-03 (Endpoints de Interoperabilidad OpenAI /v1):** Implementar `GET /v1/models` y `POST /v1/chat/completions` para integracion con IDEs y agentes externos eliminando errores 404 en el log. (Resuelto en ADR-008).
- [x] **CHAT-01 (Lectura Textual de Folios, Mapeo de Capitulos y Resumenes Estrictos):** Integrar lectura directa en PyMuPDF con OCR de diagramas, mapeo regex de capitulos y enrutamiento estricto no determinista hacia el LLM seleccionado. (Resuelto en ADR-008).
- [x] **UI-04 (Renderizado Markdown Enriquecido y Citas Inline Interactivas):** Incorporar libreria local `marked.min.js` con tipografia dark theme para encabezados, tablas, viñetas y botones interactivos `.inline-page-tag` en `[Pagina X]`. (Resuelto en ADR-008).

---

## 2. Cuota de Recomendaciones y Backlog Priorizado

### CRITICO (Seguridad, Concurrencia y Estabilidad de Memoria)

1. **SEC-01 (Limite de Memoria L0/L1 In-Memory):**
   - *Descripcion:* Implementar desalojo FIFO/LRU estricto con `max_entries=500` y cuota maxima en MB (ej. 512 MB) para `MOCK_RESULTS_STORE` y `CACHE_L0_MEMORY` en [cache_service.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/services/cache_service.py) y [main.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/main.py).
   - *Fundamento:* Previene fugas de memoria y agotamiento de RAM (*OOM kill*) bajo cargas concurrentes intensivas cuando Redis opera en modo fallback in-memory.
2. **SEC-02 (Ciclo de Vida y Limpieza Automatica de Archivos Temporales):**
   - *Descripcion:* Incorporar un recolector periodico con TTL (ej. 24 horas) para limpiar archivos generados en `data/uploads/` y `data/results/`.
   - *Fundamento:* Evita el desbordamiento silencioso del disco en despliegues productivos de larga duracion.

### RECOMENDADO (Arquitectura, Modularidad y Rendimiento)

3. **ARCH-01 (Modularizacion de Endpoints en Routers Dedicados):**
   - *Descripcion:* Desacoplar [main.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/main.py) (actualmente >1000 lineas) en controladores `APIRouter` independientes: `app/routers/ingest.py`, `app/routers/viewer.py`, `app/routers/chat.py` y `app/routers/benchmark.py`.
   - *Fundamento:* Mejora radicalmente la mantenibilidad, legibilidad del codigo y facilita la incorporacion de pruebas unitarias aisladas por endpoint.
4. **PERF-01 (Streaming Digest de Hashing para Documentos Voluminosos):**
   - *Descripcion:* Sustituir la lectura total duplicada en RAM por calculo de digest SHA-256 en bloques de 64 KB en [ingestion_service.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/services/ingestion_service.py).
   - *Fundamento:* Reduce el pico de memoria transitorio a la mitad durante la carga de documentos cercanos al limite maximo.
5. **PERF-02 (Cuantizacion Dinamica INT8 para Modelo Florence-2):**
   - *Descripcion:* Exportar los pesos de `microsoft/Florence-2-base` a ONNX Runtime cuantizado INT8 mediante `optimum-cli`.
   - *Fundamento:* Reduce el consumo de RAM de 850 MB a ~240 MB y acelera la inferencia espacial en CPU en un 40%.
6. **TEST-01 (Actualizacion de Starlette TestClient / Httpx):**
   - *Descripcion:* Resolver la advertencia de deprecacion reportada por pytest (`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead`).
   - *Fundamento:* Mantiene la suite de pruebas al dia con las ultimas dependencias del ecosistema FastAPI/Starlette.

### OPACIONAL (Refactorizaciones y Experiencia de Usuario)

7. **XLSX-02 (Plantilla de Renderizado Grid en Conversion Excel):**
   - *Descripcion:* Dibujar lineas de cuadricula visuales y calcular coordenadas X proporcionales al ancho de cada celda en lugar de texto concatenado plano.
   - *Fundamento:* Optimiza el grounding visual en el visor PDF para balances y tablas financieras complejas.
8. **UI-04 (Sondeo Reactivo de Estado del Servidor Ollama):**
   - *Descripcion:* Mostrar un indicador de salud en tiempo real en el frontend si el servicio local Ollama esta respondiendo o iniciando en segundo plano.
   - *Fundamento:* Ofrece retroalimentacion clara al usuario durante los primeros segundos de inicializacion del modelo local.

### FUTURO (Escalabilidad a Gran Escala)

9. **SCALE-01 (Workers Distribuidos con Celery / ARQ):**
   - *Descripcion:* Desacoplar la orquestacion de extraccion pesada hacia workers en cola cuando el volumen concurrente supere las 50 peticiones simultaneas.
   - *Fundamento:* Garantiza latencias predecibles en la API principal al delegar el computo intensivo a nodos de trabajo especializados.
10. **VISION-02 (Non-Maximum Suppression Ponderado para Ensamble Dual):**
    - *Descripcion:* Implementar un algoritmo NMS ponderado que unifique las predicciones de RapidOCR y Florence-2 en un grafo de entidades de precision ultra-alta (>98.5%).
    - *Fundamento:* Resuelve discrepancias en sellos borrosos o documentos con tipografia mixta.
