# Épica 7: Observabilidad y Benchmark

> **Objetivo:** Instrumentar métricas desagregadas por fase de ejecución, trazabilidad estructurada con `request_id`, suite de benchmark automatizada sobre fixtures representativos y gobierno estricto de la regla de oro: *"No optimizar antes del benchmark"*.

---

### US-24: Telemetría Desagregada por Fase y Métricas de Rendimiento

- **ID:** `US-24`
- **Requisitos asociados:** `RF-080`, `RF-081`, `RF-082`, `RF-083`, `RF-084`, `RNF-003`, `ADR-004 Sección 19 y 20`
- **Prioridad:** Media | **Estimación:** 3 pts

#### Narrativa
**Como** ingeniero de confiabilidad y desarrollador,  
**Quiero** registrar trazas estructuradas con `request_id` y tiempos desagregados por cada etapa (`hash_ms`, `fitz_ms`, `classification_ms`, `preprocess_ms`, `render_ms`, `gemini_ms`),  
**Para** detectar cuellos de botella en milisegundos y verificar el cumplimiento de los presupuestos de latencia (L0 < 20 ms, L1 < 50 ms, digital nativo p95 < 200 ms).

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Registro de telemetría desagregada**
   - **Dado** la ejecución de cualquier trabajo de procesamiento,
   - **Cuando** concluye el pipeline en `jobs.py`,
   - **Entonces** el modelo `JobOutput.telemetria` contiene todos los campos cronometrados con precisión decimal en milisegundos.

2. **Escenario: Health check estructurado**
   - **Dado** una petición `GET /health`,
   - **Cuando** responde el servicio,
   - **Entonces** entrega estado `"healthy"`, versión `"2.2.0"`, modelo activo `"gemini-2.0-flash"` y los límites operativos vigentes.

---

### US-25: Suite de Benchmark Automatizado y Calibración Empírica

- **ID:** `US-25`
- **Requisitos asociados:** `ADR-004 Sección 21 y 22`
- **Prioridad:** Alta | **Estimación:** 5 pts

#### Narrativa
**Como** equipo de arquitectura de PyDective,  
**Quiero** ejecutar pruebas automatizadas de rendimiento y precisión contra los fixtures de prueba generados (`digital_factura`, `digital_contrato`, `escaneo_inclinado_skew`, etc.),  
**Para** calibrar empíricamente los umbrales (`OPENCV_BYPASS_WORD_THRESHOLD`, WebP quality, ratios de área) e impedir que se introduzcan optimizaciones por mera intuición arquitectónica (Regla de Oro).

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Evaluación empírica de fixtures**
   - **Dado** los 7 archivos PDF en `tests/fixtures/`,
   - **Cuando** se ejecuta la suite de evaluación con `pytest`,
   - **Entonces** se miden y reportan formalmente `precision`, `recall`, `latency_p50`, `latency_p95` y `calls_to_Gemini`.

2. **Escenario: Cumplimiento de la regla anti-sobreingeniería**
   - **Dado** una propuesta técnica para añadir bases de datos vectoriales o motores Lucene al MVP,
   - **Cuando** se evalúa frente al benchmark de documentos de ~20 páginas,
   - **Entonces** se rechaza la sobreingeniería si la búsqueda asociativa en memoria y orjson ya cumple la resolución en sub-decenas de milisegundos.
