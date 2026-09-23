# PyDective — Motor Documental Multimodal Ultra-Rápido

> **Extracción documental quirúrgica y agnóstica (~20 páginas) a velocidad nativa en C con PyMuPDF, preprocesamiento determinista selectivo con OpenCV e IA multimodal selectiva con Gemini 2.0 Flash.**

---

## ⚡ Filosofía Arquitectónica: Evidencia y Cero Sobre-Ingeniería

PyDective no es solo para facturas. Es un motor de inteligencia documental universal diseñado para analizar **contratos, pólizas, actas, soportes legales, historias clínicas y cualquier tipo documental** a partir de parámetros arbitrarios provistos por el usuario.

### Pilares de Rendimiento (ADR-001 a ADR-004)
1. **Carril Digital Cero-IA (PyMuPDF):** Extracción espacial $O(N)$ nativa en C (`page.get_text("words")`) sin costo de red ni inferencia.
2. **Preprocesamiento Determinista Selectivo (OpenCV):** Deskew acotado a $\pm 15^\circ$ en miniatura de 500 px + binarización Otsu solo para páginas escaneadas o degradadas.
3. **Visión Multimodal Quirúrgica (Gemini 2.0 Flash):** Renderizado baseline a 1024 px WebP q75 únicamente para páginas con señal física deficiente (`NEEDS_AI`), firmas manuscritas o sellos oficiales.
4. **Caché Escalonada y Singleflight:**
   - **L0:** Respuestas HTML/JSON instantáneas por `(pdf_hash, query_hash)`.
   - **L1:** Índice asociativo `parametro_normalizado -> list[Evidence]` reutilizable entre distintas consultas sin reabrir el PDF.
   - **Singleflight:** Candado distribuido en Redis para evitar estampidas (dogpile effect).
5. **Pydective Chat Grounded:** Búsqueda previa en el índice L1 antes de invocar a Gemini, reduciendo un 80% de tokens de entrada con citas verificables `[Página X]`.

---

## 🚀 Inicio Rápido con `uv`

El proyecto utiliza [`uv`](https://github.com/astral-sh/uv) para la gestión ultrarrápida del entorno y dependencias en Python 3.12+.

### 1. Clonar y configurar entorno
```bash
# Clonar el repositorio
git clone https://github.com/Dan18eP/PyDective.git
cd PyDective

# Crear y sincronizar el entorno virtual
uv sync
```

### 2. Variables de entorno
Copia la plantilla y configura tus claves:
```bash
cp .env.example .env
# Edita .env agregando tus GEMINI_API_KEYS
```

### 3. Ejecutar el servidor de desarrollo
```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Abre en tu navegador: [http://localhost:8000](http://localhost:8000)

---

## 📡 API Endpoints Principales

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/` | Interfaz interactiva de usuario (Jinja2 SSR + Vanilla CSS/JS) |
| `GET` | `/health` | Chequeo de salud, versión del pipeline y modelo activo |
| `POST` | `/procesar` | Procesamiento sincrónico directo devolviendo `JobOutput` |
| `POST` | `/procesar/stream` | Transmisión de progreso en tiempo real vía Server-Sent Events (SSE) |
| `GET` | `/resultados/{pdf_hash}` | Vista de dictamen forense y desglose por página |
| `POST` | `/chat/{pdf_hash}` | Pydective Chat documental multi-turno con grounding en L1 |

---

## 🧪 Pruebas Automatizadas

```bash
uv run pytest
```
