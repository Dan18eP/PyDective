# PyDective — Motor Documental Multimodal Ultra-Rápido

> [!NOTE]
> Extracción documental quirúrgica y agnóstica a velocidad nativa en C con PyMuPDF, preprocesamiento determinista selectivo con OpenCV (Deskew + Otsu adaptativo), motores locales de visión autónoma en CPU (RapidOCR optimizado / Florence-2) e IA multimodal selectiva con proveedores desacoplados (Google Gemini o SLM local `llama3.2:1b` vía Ollama).

---

## 1. Filosofía Arquitectónica: Evidencia y Cero Sobre-Ingeniería

PyDective es un motor de inteligencia documental universal diseñado para auditar y extraer evidencia forense de **contratos, pólizas, actas notariales, soportes legales, balances financieros, historias clínicas, facturas médicas y cualquier tipología documental** a partir de parámetros arbitrarios o chips interactivos predefinidos.

### Pilares de Rendimiento (ADR-001 a ADR-008)
1. **Carril Digital Cero-IA (PyMuPDF):** Extracción espacial $O(N)$ nativa en C (`page.get_text("words")`) sin costo de red ni latencia de inferencia en documentos vectoriales.
2. **Motores Locales de Visión Autónoma en CPU:**
   - **RapidOCR Acelerado (ONNX Runtime):** Binarización adaptativa Otsu pre-inferencia que reduce en un ~40% el tiempo de decodificación en folios escaneados densos, descarte de páginas en blanco en <2 ms, y ejecución paralela multi-hilo con `ThreadPoolExecutor(max_workers=2)` aislando instancias `fitz.open(stream=pdf_bytes)`.
   - **Florence-2:** Inferencia profunda de Microsoft con grounding denso y generación de bounding boxes normalizados `[ymin, xmin, ymax, xmax]` en escala 0–1000.
   - **Precalentamiento en Lifespan:** Instanciación de pesos de visión durante el arranque de FastAPI, erradicando el *cold-start* para los usuarios.
3. **Ingesta Universal Multi-Formato en Memoria:** Conversión automática en memoria a PDF equivalente para imágenes (PNG, JPG, TIFF) y formatos ofimáticos (DOCX, XLSX, TXT) preservando UTF-8 nativo y estructura tabular.
4. **Inyección de Capa OCR Invisible (`render_mode=3`):** Habilita la selección de texto con cursor y la búsqueda interactiva tipo Chrome (`Ctrl+F`) sobre documentos escaneados e imágenes en el visor interactivo (PDF.js).
5. **Arquitectura Multi-Proveedor Desacoplada:** Operación en la nube con Google Gemini o 100% offline con proveedores locales vía Ollama (`llama3.2:1b` / `qwen2.5:3b`).
6. **Pydective Chat con Switch de Modo Dual:**
   - **Modo Determinista (L1 RAM):** Resolución instantánea sub-5ms sobre el grafo de entidades y coordenadas indexadas.
   - **Modo Modelo Local (SLM Local):** Razonamiento contextual en lenguaje natural transmitido mediante SSE (`/chat/{pdf_hash}/stream`), calibrado con respuestas directas, sin preámbulos y con ventana quirúrgica de 2 páginas (`max_tokens=120`).
7. **Visor Interactivo Redimensionable (Split-Resizer):** Divisor arrastrable con cursor para ajustar el ancho relativo entre el visor PDF y la consola de hallazgos/chat, con límites seguros (28% a 82%), persistencia en `localStorage` y zoom bidireccional estable.
8. **Caché Escalonada y Singleflight:**
   - **L0:** Respuestas directas por `(pdf_hash, query_hash)` (<20 ms).
   - **L1:** Índice asociativo en memoria `parametro_normalizado -> list[Evidence]` reutilizable entre consultas (<50 ms).
   - **Singleflight:** Candado concurrente en memoria / Redis para evitar estampidas (*dogpile effect*).

---

## 2. Instalación y Arranque Multiplataforma

El proyecto provee scripts autónomos de instalación e inicio compatibles de forma nativa con **Linux (Ubuntu, Debian, Fedora, Arch)** y **Windows**.

### Opción A: Inicio Rápido en Linux / POSIX

```bash
# 1. Clonar el repositorio
git clone https://github.com/Dan18eP/PyDective.git
cd PyDective

# 2. Conceder permisos de ejecución y correr instalador
chmod +x install.sh run.sh
./install.sh

# 3. Iniciar la aplicación
./run.sh
```

### Opción B: Inicio Rápido en Windows

```powershell
# 1. Clonar el repositorio
git clone https://github.com/Dan18eP/PyDective.git
cd PyDective

# 2. Ejecutar el instalador automatizado
python install_dependencies.py

# 3. Iniciar la aplicación
python run.py
```

### Opción C: Gestión con `uv`

```bash
# Sincronizar el entorno virtual
uv sync

# Ejecutar el servidor
uv run python run.py
```

Abre en tu navegador: [http://localhost:8000](http://localhost:8000)

> [!TIP]
> Si el proveedor local `LLM_PROVIDER=local` está configurado en `.env`, el lanzador `run.py` detectará o iniciará automáticamente el daemon de Ollama en segundo plano sin intervención manual.

---

## 3. Endpoints Principales de la API

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/` | Interfaz interactiva de usuario (Jinja2 SSR + Tailwind CSS v4) |
| `GET` | `/health` | Chequeo de salud, versión del pipeline, modelo activo y telemetría |
| `POST` | `/procesar` | Procesamiento sincrónico directo devolviendo `JobOutput` estructurado |
| `POST` | `/procesar/stream` | Transmisión de progreso en tiempo real página a página vía Server-Sent Events (SSE) |
| `GET` | `/documentos/{pdf_hash}/raw` | Entrega segura del binario PDF para el visor interactivo PDF.js |
| `GET` | `/documentos/{pdf_hash}/search` | Buscador de coincidencias exactas estilo Chrome sobre el PDF |
| `GET` | `/resultados/{pdf_hash}` | Vista de dictamen forense en Split-View con divisor redimensionable, visor y chat |
| `POST` | `/chat/{pdf_hash}` | Chat documental multi-turno sincrónico con grounding en L1 |
| `POST` | `/chat/{pdf_hash}/stream` | Chat documental con streaming token a token vía SSE (SLM local o Gemini) |

---

## 4. Pruebas Automatizadas

La suite de pruebas contiene **168 tests automatizados** (100% aprobados) que cubren validación de entrada, preprocesamiento OpenCV, extracción espacial estricta, proveedores LLM, caching L0/L1, visor interactivo y no-contaminación (*zero-hardcoding*):

```bash
uv run pytest
```
