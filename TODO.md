# TODO & Backlog de Deuda Técnica — PyDective

> Generado durante la auditoría técnica integral (23/09/2026).
> Cumplimiento estricto con la política de cero commits/push automáticos y categorización de recomendaciones.

---

## 🚨 Crítico (Seguridad, Concurrencia y Estabilidad de Memoria)

- [ ] **OCR-01 (Motor OCR Local Autónomo para PDFs Escaneados e Imágenes):** Integrar motor OCR local sin dependencia de binarios externos de Tesseract (ej. `rapidocr_onnxruntime` en CPU con AVX2 o VLM local en Ollama) para permitir que los 10 PDFs escaneados y 25 imágenes forenses (`.png`, `.jpg`, `.tiff`) extraigan entidades cuando no hay claves de Google Gemini configuradas.
- [x] **BUG-XLSX-01 (Corrección de Separador Pipe en Extracción Espacial):** Corregir el corte de delimitador en [spatial_extraction_service.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/services/spatial_extraction_service.py#L523-L525) (`if "|" in val_text: val_text = val_text.split("|")[0].strip()`), el cual vacía el 100% de los valores en celdas de [doc_091_balance.xlsx](file:///C:/Users/Usuario/Desktop/Github/PyDective/tests/fixtures_100/doc_091_balance.xlsx) a `doc_095`. (Resuelto: precisión 100% en XLSX).
- [ ] **SEC-01 (Límite de Memoria L0/L1 In-Memory):** Implementar desalojo FIFO/LRU estricto con `max_entries` o tamaño en MB para `MOCK_RESULTS_STORE` y `CACHE_L0_MEMORY` en [cache_service.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/services/cache_service.py) y [main.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/main.py#L127-L140) para prevenir fugas de memoria en escenarios de alta concurrencia.
- [ ] **SEC-02 (Aislamiento de Archivos Temporales en Visor):** Agregar ciclo de vida (TTL/auto-cleanup) para PDFs almacenados en `data/uploads/` y resultados en `data/results/` para evitar saturación de almacenamiento en disco en producción.

---

## 🛠️ Recomendado (Arquitectura, Modularidad y Tipado)

- [x] **BUG-ENC-01 (Soporte UTF-8 Nativo en Conversión DOCX y TXT):** Eliminar la bandera restrictiva `encoding=pymupdf.TEXT_ENCODING_LATIN` en [ingestion_service.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/services/ingestion_service.py#L56-L125) que convierte caracteres acentuados hispanos (`Í`, `Ó`, `Á`) en símbolos corruptos (`¶`, `»`, `«`) en contratos DOCX y extractos TXT. (Resuelto: precisión 100% en DOCX y TXT).
- [ ] **VIS-01 (Segmentación Morfológica de Firmas y Sellos en Imágenes Puras):** Incorporar detección de componentes conexos y análisis de contornos en OpenCV para segmentar firmas y sellos en imágenes `.png`, `.jpg` y `.tiff` donde `page.get_images()` solo reporta el lienzo completo.
- [ ] **ARCH-01 (Modularización de Endpoints en Routers):** Desacoplar [main.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/main.py) (actualmente >900 líneas) en submódulos `APIRouter` dedicados (`app/routers/ingest.py`, `app/routers/viewer.py`, `app/routers/chat.py`).
- [ ] **PERF-01 (Optimización de Hashing para Archivos Grandes):** Implementar streaming digest chunk-by-chunk en [ingestion_service.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/services/ingestion_service.py) para calcular SHA-256 sin requerir la carga completa duplicada en buffers de memoria intermedia.
- [ ] **TEST-01 (Actualización de Starlette TestClient / Httpx):** Resolver warning de deprecación reportado por pytest (`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`).

---

## 💡 Opcional (Refactorizaciones y Experiencia de Desarrollo)

- [ ] **XLSX-02 (Plantilla de Renderizado Grid en Conversión Excel):** Generar grillas con coordenadas X calculadas por ancho de columna en lugar de concatenación plana con `|` en `_convert_xlsx_to_pdf_in_memory()`.
- [x] **UI-02 (Resaltado y Enfoque de Evidencias en Visor PDF y Tabla):** Añadir resaltado temático de grounding por tipo de parámetro (moneda, entidad, fecha, ID, visual), balizas con pulsación radiante (`.pdf-grounding-ripple`), selección bidireccional interactiva entre filas de hallazgos y el visor de documentos, y búsqueda de coincidencias de alto contraste.
- [ ] **DEV-01 (Scripts de CLI para Entorno Windows):** Incorporar script `run_server.ps1` o Makefile para empaquetar comandos comunes de `uv` con detección automática del ejecutable en `%USERPROFILE%\.local\bin`.
- [ ] **UI-01 (Feedback Visual de Errores de Conexión Redis):** Mejorar telemetría de UI cuando Redis no está disponible y el sistema cae elegantemente en memoria local (in-memory fallback).

---

## 🔭 Futuro (Escalabilidad a Largo Plazo)

- [ ] **OCR-02 (Capa de Texto OCR Invisible para PDFs Híbridos):** Inyectar capa OCR invisible con PyMuPDF para habilitar el resaltado de texto nativo en el visor interactivo sobre documentos escaneados e imágenes raster.
- [ ] **SCALE-01 (Workers Distribuidos Celery / ARQ):** Migrar orquestación de procesamiento masivo en segundo plano hacia workers asíncronos distribuidos si el volumen de PDFs concurrentes supera las 100 peticiones simultáneas.
- [ ] **AI-01 (Soporte Multi-Proveedor de Modelos Multimodales):** Abstraer interfaz de proveedor en `gemini_service.py` para permitir fallback directo a modelos locales de visión (ej. ONNX Runtime / DocLayout-YOLOv8 o vLLM) en despliegues offline/on-premise.
