# TODO & Backlog de Deuda Técnica — PyDective

> Generado durante la auditoría técnica integral (23/09/2026).
> Cumplimiento estricto con la política de cero commits/push automáticos y categorización de recomendaciones.

---

## 🚨 Crítico (Seguridad, Concurrencia y Estabilidad de Memoria)

- [ ] **SEC-01 (Límite de Memoria L0/L1 In-Memory):** Implementar desalojo FIFO/LRU estricto con `max_entries` o tamaño en MB para `MOCK_RESULTS_STORE` y `CACHE_L0_MEMORY` en [cache_service.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/services/cache_service.py) y [main.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/main.py#L127-L140) para prevenir fugas de memoria en escenarios de alta concurrencia.
- [ ] **SEC-02 (Aislamiento de Archivos Temporales en Visor):** Agregar ciclo de vida (TTL/auto-cleanup) para PDFs almacenados en `data/uploads/` y resultados en `data/results/` para evitar saturación de almacenamiento en disco en producción.

---

## 🛠️ Recomendado (Arquitectura, Modularidad y Tipado)

- [ ] **ARCH-01 (Modularización de Endpoints en Routers):** Desacoplar [main.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/main.py) (actualmente >900 líneas) en submódulos `APIRouter` dedicados (`app/routers/ingest.py`, `app/routers/viewer.py`, `app/routers/chat.py`).
- [ ] **PERF-01 (Optimización de Hashing para Archivos Grandes):** Implementar streaming digest chunk-by-chunk en [ingestion_service.py](file:///C:/Users/Usuario/Desktop/Github/PyDective/app/services/ingestion_service.py) para calcular SHA-256 sin requerir la carga completa duplicada en buffers de memoria intermedia.
- [ ] **TEST-01 (Actualización de Starlette TestClient / Httpx):** Resolver warning de deprecación reportado por pytest (`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`).

---

## 💡 Opcional (Refactorizaciones y Experiencia de Desarrollo)

- [ ] **DEV-01 (Scripts de CLI para Entorno Windows):** Incorporar script `run_server.ps1` o Makefile para empaquetar comandos comunes de `uv` con detección automática del ejecutable en `%USERPROFILE%\.local\bin`.
- [ ] **UI-01 (Feedback Visual de Errores de Conexión Redis):** Mejorar telemetría de UI cuando Redis no está disponible y el sistema cae elegantemente en memoria local (in-memory fallback).

---

## 🔭 Futuro (Escalabilidad a Largo Plazo)

- [ ] **SCALE-01 (Workers Distribuidos Celery / ARQ):** Migrar orquestación de procesamiento masivo en segundo plano hacia workers asíncronos distribuidos si el volumen de PDFs concurrentes supera las 100 peticiones simultáneas.
- [ ] **AI-01 (Soporte Multi-Proveedor de Modelos Multimodales):** Abstraer interfaz de proveedor en `gemini_service.py` para permitir fallback directo a modelos locales de visión (ej. ONNX Runtime / DocLayout-YOLOv8 o vLLM) en despliegues offline/on-premise.
