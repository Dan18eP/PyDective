# Índice Maestro de Historias de Usuario (US) — PyDective

> **Suite completa de historias de usuario para el MVP de PyDective: Motor Documental Multimodal Ultra-Rápido (~20 páginas).**  
> Basado en el [PRD](file:///home/dypok/Projects/PyDective/documentation/PRD-motor-pdf-multimodal.md), los [Requisitos del Sistema](file:///home/dypok/Projects/PyDective/documentation/requirements-motor-pdf-multimodal.md), la [Especificación Arquitectónica](file:///home/dypok/Projects/PyDective/documentation/especificacion-arquitectonica-general-actualizada.md) y las Decisiones de Arquitectura ([ADR-001](file:///home/dypok/Projects/PyDective/documentation/ADR/ADR-001-arquitectura-hibrida-caching-y-failover.md) a [ADR-004](file:///home/dypok/Projects/PyDective/documentation/ADR/ADR-004-optimizacion-rendimiento-precision-y-reutilizacion-documental.md)).

---

## 🗺️ Mapa de Épicas y Cobertura

| Épica | Archivo | Historias | Alcance Clave |
|---|---|---|---|
| **Épica 1: Ingesta, Validación y Control de Entrada** | [EPIC-01-ingesta-y-validacion.md](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-01-ingesta-y-validacion.md) | US-01, US-02, US-03 | Validación binaria en memoria, normalización NFKD lingüística, límites duros (20 págs). |
| **Épica 2: Clasificación y Preprocesamiento** | [EPIC-02-clasificacion-y-preprocesamiento.md](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-02-clasificacion-y-preprocesamiento.md) | US-04, US-05, US-06 | Clasificación local en PyMuPDF, `readability_score` anti-ruido, Deskew OpenCV $\pm 15^\circ$ y Otsu. |
| **Épica 3: Extracción Espacial y Grounding** | [EPIC-03-extraccion-espacial-y-grounding.md](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-03-extraccion-espacial-y-grounding.md) | US-07, US-08, US-09, US-10 | Extracción clave-valor $O(N)$, `Evidence` con `evidence_score`, normalización tipificada y KWIC. |
| **Épica 4: Inferencia Multimodal Gemini** | [EPIC-04-inferencia-multimodal-gemini.md](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-04-inferencia-multimodal-gemini.md) | US-11, US-12, US-13 | Render baseline 1024px WebP q75 en C, `gemini-2.0-flash` estructurado (`thinking_budget=0`), catálogo visual. |
| **Épica 5: Caching, Resiliencia y Singleflight** | [EPIC-05-caching-resiliencia-y-singleflight.md](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-05-caching-resiliencia-y-singleflight.md) | US-14, US-15, US-16, US-17, US-18, US-19 | L0 (<20ms), L1 asociativo (`complete` vs `partial`), fallback LRU orjson, Singleflight anti-dogpile, KeyPool y L2. |
| **Épica 6: Interfaz, Streaming y Chat** | [EPIC-06-interfaz-streaming-y-chat.md](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-06-interfaz-streaming-y-chat.md) | US-20, US-21, US-22, US-23 | SSR con Tailwind CSS v4, SSE `/procesar/stream` reactivo, tabla forense y Pydective Chat grounded en L1. |
| **Épica 7: Observabilidad y Benchmark** | [EPIC-07-observabilidad-y-benchmark.md](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-07-observabilidad-y-benchmark.md) | US-24, US-25 | Telemetría desagregada, `request_id`, suite de benchmark y regla de oro anti-sobreingeniería. |

---

## 📌 Matriz de Trazabilidad Rápida

| Código de Requisito | Historias de Usuario Asociadas |
|---|---|
| **RF-001 .. RF-007** (Carga y validación) | [US-01](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-01-ingesta-y-validacion.md#us-01), [US-03](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-01-ingesta-y-validacion.md#us-03) |
| **RF-010 .. RF-016** (Parámetros dinámicos) | [US-02](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-01-ingesta-y-validacion.md#us-02) |
| **RF-020 .. RF-028** (Caché L0 / L1) | [US-14](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-05-caching-resiliencia-y-singleflight.md#us-14), [US-15](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-05-caching-resiliencia-y-singleflight.md#us-15) |
| **RF-030 .. RF-037** (Clasificación local Fase A) | [US-04](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-02-clasificacion-y-preprocesamiento.md#us-04), [US-05](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-02-clasificacion-y-preprocesamiento.md#us-05) |
| **RF-040 .. RF-047** (Extracción multimodal Fase B) | [US-11](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-04-inferencia-multimodal-gemini.md#us-11), [US-12](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-04-inferencia-multimodal-gemini.md#us-12) |
| **RF-050 .. RF-060** (Concurrencia, Keys y Failover) | [US-17](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-05-caching-resiliencia-y-singleflight.md#us-17), [US-18](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-05-caching-resiliencia-y-singleflight.md#us-18) |
| **RF-065 .. RF-069** (Context Cache L2) | [US-19](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-05-caching-resiliencia-y-singleflight.md#us-19) |
| **RF-070 .. RF-077** (Presentación de resultados) | [US-22](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-06-interfaz-streaming-y-chat.md#us-22) |
| **RF-080 .. RF-084** (Observabilidad y telemetría) | [US-24](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-07-observabilidad-y-benchmark.md#us-24) |
| **RF-090 .. RF-095** (Visión determinista, Catálogo, SSE y Chat) | [US-06](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-02-clasificacion-y-preprocesamiento.md#us-06), [US-13](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-04-inferencia-multimodal-gemini.md#us-13), [US-21](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-06-interfaz-streaming-y-chat.md#us-21), [US-23](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-06-interfaz-streaming-y-chat.md#us-23) |
| **RF-096 .. RF-099** (Extracción semántica y normalización) | [US-07](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-03-extraccion-espacial-y-grounding.md#us-07), [US-08](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-03-extraccion-espacial-y-grounding.md#us-08), [US-09](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-03-extraccion-espacial-y-grounding.md#us-09), [US-10](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-03-extraccion-espacial-y-grounding.md#us-10) |
| **RNF-001 .. RNF-007** (Presupuestos de latencia y CPU) | [US-14](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-05-caching-resiliencia-y-singleflight.md#us-14), [US-15](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-05-caching-resiliencia-y-singleflight.md#us-15), [US-04](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-02-clasificacion-y-preprocesamiento.md#us-04), [US-11](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-04-inferencia-multimodal-gemini.md#us-11) |
| **RNF-015 .. RNF-016** (Fallback LRU y Singleflight) | [US-16](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-05-caching-resiliencia-y-singleflight.md#us-16), [US-17](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-05-caching-resiliencia-y-singleflight.md#us-17) |
| **Benchmark y Gobernanza Empírica** | [US-25](file:///home/dypok/Projects/PyDective/documentation/US/EPIC-07-observabilidad-y-benchmark.md#us-25) |
