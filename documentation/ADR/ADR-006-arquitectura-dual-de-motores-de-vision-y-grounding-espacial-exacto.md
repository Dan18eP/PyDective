# ADR-006: Arquitectura Dual de Motores de Visión (RapidOCR vs Florence-2), Benchmark Comparativo en Tiempo Real e Inyección de Capa de Texto Invisible

- **Estado:** Aceptado
- **Fecha:** 2026-09-24
- **Decisores:** Brandon Carranza (Arquitecto de Software y Lead Engineer)
- **Extiende a:** [ADR-001](file:///C:/Users/Usuario/Desktop/Github/PyDective/documentation/ADR/ADR-001-arquitectura-hibrida-caching-y-failover.md), [ADR-002](file:///C:/Users/Usuario/Desktop/Github/PyDective/documentation/ADR/ADR-002-preprocesamiento-determinista-vision-y-chat-documental.md), [ADR-003](file:///C:/Users/Usuario/Desktop/Github/PyDective/documentation/ADR/ADR-003-extraccion-semantica-clave-valor-y-enriquecimiento.md), [ADR-004](file:///C:/Users/Usuario/Desktop/Github/PyDective/documentation/ADR/ADR-004-optimizacion-rendimiento-precision-y-reutilizacion-documental.md) y [ADR-005](file:///C:/Users/Usuario/Desktop/Github/PyDective/documentation/ADR/ADR-005-visor-pdf-con-grounding-visual-y-buscador-exacto.md)
- **Relacionado con:** PRD, Requisitos del Sistema (RF-104, RF-105, RNF-051) y Especificación Arquitectónica General
- **Etiquetas:** pydective, vision-engine, rapidocr, florence2, benchmark, bounding-box, capa-invisible, cpu-inference

---

## 1. Contexto

En versiones previas, PyDective resolvía documentos digitales mediante PyMuPDF en espacio vectorial nativo, y delegaba las páginas complejas, escaneadas o manuscritas a la API de Google Gemini en la nube. Sin embargo, en entornos corporativos de alta confidencialidad, auditorías desconectadas (on-premise/air-gapped) o cuando no existen claves de API configuradas, surgían deficiencias críticas:

1. **Dependencia Externa de Conectividad Cloud:** La ausencia de una clave válida de Gemini degradaba a cero la extracción en documentos rasterizados o escaneos fotográficos.
2. **Limitaciones de Motores OCR Tradicionales (Tesseract):** Las dependencias basadas en binarios de sistema (`tesseract-ocr`) requieren instalación manual de paquetes a nivel de sistema operativo (`apt-get`, instaladores `.msi`), sufren de baja precisión en caracteres complejos y presentan latencias superiores a 1.2 segundos por página en CPU.
3. **Ausencia de Comparativa Empírica en Vivo:** Los operadores forenses requieren evaluar en tiempo real la discrepancia entre un modelo OCR ultraligero y un modelo multimodal moderno de visión profunda (Vision Foundation Model) antes de seleccionar el pipeline productivo.
4. **Desconexión entre Capa Visual y Visor Interactivo:** En documentos puramente escaneados, el visor de PDF no permitía la selección de texto nativo ni el resaltado dinámico de búsqueda (`Ctrl+F`), pues el PDF carecía de capas de caracteres vectoriales.

---

## 2. Decisión Arquitectónica

Implementar un **Subsistema Dual de Visión y OCR Autónomo sobre CPU**, integrado con un **Selector y Benchmark Concurrente en el Frontend**, una **Capa OCR Invisible Inyectada** y **Extracción de Coordenadas Exactas Bounding Box**.

> [!IMPORTANT]
> La arquitectura garantiza inferencia de visión local 100% sobre CPU sin requerir GPUs dedicadas, aprovechando instrucciones vectoriales AVX2 en inferencia ONNX Runtime y cuantización int8/float32 optimizada.

### 2.1 Especificación de Motores de Visión

El sistema provee dos motores desacoplados bajo interfaces uniformes:

1. **Motor A: RapidOCR (`rapidocr_onnxruntime`):**
   - Basado en arquitectura PaddleOCR ejecutada sobre ONNX Runtime con soporte CPU AVX2.
   - Latencia ultra-baja (<200 ms por página A4 completa).
   - Huella de memoria mínima (~120 MB en RAM).
   - Inyección de texto plano con cajas delimitadoras precisas `[x, y, w, h]`.
2. **Motor B: Florence-2 (`microsoft/Florence-2-base`):**
   - Modelo fundacional de visión multimodal de Microsoft transformado a inferencia de atención espacial.
   - Tarea primaria ejecutada: `<OCR_WITH_REGION>` y `<CAPTION_TO_PHRASE_GROUNDING>`.
   - Generación de bounding boxes normalizados en espacio `[0, 1000]`.
   - Mayor densidad contextual en documentos con tipografía manuscrita, sellos notariales y tablas no estructuradas.

```text
                               ┌──────────────────────────────────────────────┐
                               │             Frontend Selector UI             │
                               │   [ RapidOCR (Rápido) | Florence-2 (Exacto) ]│
                               │   [X] Modo Benchmark Simultáneo              │
                               └──────────────────────┬───────────────────────┘
                                                      │ vision_engine=rapidocr|florence2|both
                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ FastAPl /procesar                                                                                   │
├──────────────────────────────────────────────────────┬──────────────────────────────────────────────┤
│ Modo Individual (RapidOCR o Florence-2)              │ Modo Benchmark (asyncio.gather)              │
│ Inferencia secuencial en ThreadPool                  │ Ejecución en paralelo sobre la misma página  │
│ Generación de JobOutput estándar                     │ Generación de Telemetría Comparativa:        │
│                                                      │ - Latencia A vs Latencia B (ms)              │
│                                                      │ - Conteo de hallazgos A vs B                 │
│                                                      │ - Discrepancia espacial de BBoxes            │
└──────────────────────────────────────────────────────┴──────────────────────────────────────────────┘
```

---

## 3. Evaluación Comparativa de Tecnologías (Big-O y Cómputo)

A continuación se detalla la matriz comparativa de los motores de visión integrados frente a alternativas del estado del arte:

| Motor / Pipeline | Complejidad Temporal | Complejidad Espacial | Latencia p95 (CPU) | Huella RAM | Dependencias de Sistema | Casos de Uso Recomendados |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PyMuPDF Vectorial** | $O(N)$ (caracteres) | $O(1)$ | $<15\text{ ms}$ | $<30\text{ MB}$ | Ninguna (C binario) | PDFs digitales con capa de texto nativa. |
| **RapidOCR (ONNX)** | $O(W \times H)$ | $O(W \times H)$ | $120 - 180\text{ ms}$ | $\sim 120\text{ MB}$ | `onnxruntime` | Escaneos estándar, facturas, formularios, ejecución CPU estricta. |
| **Florence-2-base** | $O(P^2 + L \cdot D)$ | $O(L \cdot D)$ | $850 - 1400\text{ ms}$ | $\sim 850\text{ MB}$ | `transformers`, `torch` | Documentos notariales complejos, manuscritos, grounding multimodal. |
| **Tesseract 5 (legacy)** | $O(W \times H \times K)$ | $O(W \times H)$ | $1100 - 1900\text{ ms}$ | $\sim 180\text{ MB}$ | Binario `tesseract` nativo | No recomendado en arquitecturas modernas portables. |
| **Google Gemini Flash** | $O(1)$ local + red | $O(\text{payload})$ | $1500 - 2800\text{ ms}$ | $<10\text{ MB}$ | Conectividad WAN + API Key | Alta complejidad semántica y razonamiento cruzado cuando hay red. |

> [!NOTE]
> Donde $W, H$ representan dimensiones del lienzo en píxeles, $P$ el número de parches visuales del transformer de visión, $L$ la longitud de secuencia generada y $D$ la dimensionalidad del espacio latente.

---

## 4. Inyección de Capa OCR Invisible en el Binario PDF

Para que los documentos escaneados e imágenes puras se beneficien del Visor de PDF interactivo (`PDF.js`) y del buscador tipo Chrome (`Ctrl+F`), el pipeline incorpora el método de inyección de texto invisible:

```python
# Inserción de capa de texto invisible con render_mode=3 en PyMuPDF
page.insert_text(
    point=fitz.Point(bbox[0], bbox[1]),
    text=detected_text,
    fontsize=font_size,
    render_mode=3,
)
```

> [!TIP]
> El modo de renderizado `render_mode=3` (invisible glyphs) permite que el motor de renderizado de `PDF.js` indexe los caracteres y sus posiciones exactas en el DOM, permitiendo selección de texto con cursor y resaltado de coincidencias sin alterar visualmente el escaneo original.

---

## 5. Cuota de Recomendaciones Técnicas

Siguiendo el protocolo estricto de ingeniería, se establecen las siguientes directivas de evolución:

1. **CRÍTICO - Cuantización INT8 de Pesos Florence-2:**
   - Compilar el modelo `microsoft/Florence-2-base` a formato ONNX Runtime con cuantización dinámica INT8 (`optimum-cli export onnx --task visual-question-answering`).
   - *Fundamento:* Reducirá la huella en memoria de 850 MB a aproximadamente 240 MB, disminuyendo el tiempo de inferencia en CPU en más del 40%.
2. **RECOMENDADO - Pool de Aislamiento para Inferencia Pesada:**
   - Ejecutar las llamadas de RapidOCR y Florence-2 en un `ProcessPoolExecutor` desacoplado del loop asíncrono de FastAPI en lugar de un `ThreadPoolExecutor`.
   - *Fundamento:* Evita el bloqueo del GIL de Python durante etapas de preprocesamiento de OpenCV y transformaciones de tensores.
3. **RECOMENDADO - Caché de Inferencia de Visión a Nivel de Hash de Página:**
   - Incorporar una clave de caché L1 indexada por `sha256(page_webp_bytes)` para reutilizar el dictamen de visión si la misma página escaneada se procesa con distintos parámetros de búsqueda.
   - *Fundamento:* Ahorra el 100% del cómputo de OCR en reprocesamientos forenses.
4. **OPCIONAL - Normalización BBox Interactiva Bidireccional:**
   - Extender el visor frontend para permitir al operador forense trazar un rectángulo manual sobre el canvas y consultar qué texto u objeto visual detectó cada motor en esa región específica.
   - *Fundamento:* Eleva la usabilidad en auditorías judiciales o peritajes forenses.
5. **FUTURO - Ensamble Ponderado de Predicciones Espaciales (NMS Multimodal):**
   - Implementar un algoritmo de Non-Maximum Suppression (NMS) ponderado por confianza que fusione las salidas de RapidOCR y Florence-2 en modo dual para emitir un único grafo de entidades de precisión superior al 98.5%.
   - *Fundamento:* Resuelve ambigüedades en caracteres desgastados o sellos superpuestos sobre firmas.

---

## 6. Siguientes Pasos

1. Mantener sincronizado el endpoint `/procesar` con las métricas de telemetría de ambos motores.
2. Integrar benchmarks automatizados en el pipeline de integración continua (`pytest tests/integration/test_dual_engine_benchmark.py`).
3. Documentar en el PRD y requisitos del sistema la adición de los nuevos códigos funcionales RF-104 y RF-105.
