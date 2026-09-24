# PyDective — Motor Documental Multimodal Ultra-Rapido

> [!NOTE]
> Extraccion documental quirurgica y agnostica (~20 paginas) a velocidad nativa en C con PyMuPDF, preprocesamiento determinista selectivo con OpenCV, motores locales de vision autonoma (RapidOCR / Florence-2 en CPU) e IA multimodal selectiva (Gemini Flash o LLM local con Ollama).

---

## 1. Filosofia Arquitectonica: Evidencia y Cero Sobre-Ingenieria

PyDective es un motor de inteligencia documental universal disenado para analizar **contratos, polizas, actas, soportes legales, balances financieros, historias clinicas y cualquier tipo documental** a partir de parametros arbitrarios provistos por el usuario o seleccionados mediante chips interactivos.

### Pilares de Rendimiento (ADR-001 a ADR-008)
1. **Carril Digital Cero-IA (PyMuPDF):** Extraccion espacial $O(N)$ nativa en C (`page.get_text("words")`) sin costo de red ni inferencia.
2. **Motores Locales de Vision Autonoma en CPU:**
   - **RapidOCR:** Inferencia ultrarrapida (<180 ms por pagina) con ONNX Runtime y extensiones vectoriales AVX2.
   - **Florence-2:** Inferencia profunda de Microsoft con grounding denso y generacion de bounding boxes normalizados `[ymin, xmin, ymax, xmax]` en escala 0–1000.
   - **Modo Benchmark Simultaneo:** Evaluacion comparativa en vivo ejecutando ambos motores concurrentemente.
3. **Ingesta Universal Multi-Formato en Memoria:** Conversion automatica en memoria a PDF equivalente para imagenes (PNG, JPG, TIFF) y formatos ofimaticos (DOCX, XLSX, TXT) preservando UTF-8 nativo y estructura tabular.
4. **Inyeccion de Capa OCR Invisible (`render_mode=3`):** Habilita la seleccion de texto con cursor y la busqueda interactiva tipo Chrome (`Ctrl+F`) sobre documentos escaneados e imagenes en el visor interactivo (PDF.js).
5. **Arquitectura Multi-Proveedor Desacoplada & CLI:** Operacion en la nube con Google Gemini, local offline con Ollama (`qwen2.5:3b`) o ejecucion directa de CLI de vanguardia (**Antigravity CLI `agy`** con `--dangerously-skip-permissions` y **OpenCode CLI `opencode run`**) en directorios temporales aislados.
6. **Interoperabilidad OpenAI:** Endpoints estandar `/v1/models` y `/v1/chat/completions` para conexion sin fisuras con Continue, Cline y agentes externos sin errores 404.
7. **Pydective Chat con Resumenes y Markdown Enriquecido:** Lectura textual de folios en PyMuPDF, mapeo de capitulos (ej: capitulo 2 $\rightarrow$ Folio 4), enrutamiento estricto no determinista hacia el LLM seleccionado, renderizado local de Markdown (`marked.js`) y pastillas interactivas `[Pagina X]` con navegacion al visor.
8. **Preprocesamiento Determinista Selectivo (OpenCV):** Deskew acotado a $\pm 15^\circ$ en miniatura de 500 px + binarizacion Otsu solo para paginas escaneadas o degradadas.
9. **Cache Escalonada y Singleflight:**
   - **L0:** Respuestas HTML/JSON instantaneas por `(pdf_hash, query_hash)` (<20 ms).
   - **L1:** Indice asociativo `parametro_normalizado -> list[Evidence]` reutilizable entre distintas consultas sin reabrir el PDF (<50 ms).
   - **Singleflight:** Candado distribuido en Redis / asyncio lock en memoria para evitar estampidas (*dogpile effect*).

---

## 2. Instalacion y Arranque Multiplataforma

El proyecto provee scripts autonomos de instalacion e inicio compatibles de forma nativa con **Linux (Ubuntu, Debian, Fedora, Arch)** y **Windows**.

### Opcion A: Inicio Rapido en Linux / POSIX

```bash
# 1. Clonar el repositorio
git clone https://github.com/Dan18eP/PyDective.git
cd PyDective

# 2. Conceder permisos de ejecucion y correr instalador
chmod +x install.sh run.sh
./install.sh

# 3. Iniciar la aplicacion
./run.sh
```

### Opcion B: Inicio Rapido en Windows

```powershell
# 1. Clonar el repositorio
git clone https://github.com/Dan18eP/PyDective.git
cd PyDective

# 2. Ejecutar el instalador automatizado
python install_dependencies.py

# 3. Iniciar la aplicacion
python run.py
```

### Opcion C: Gestion Avanzada con `uv`

Si utilizas el gestor [`uv`](https://github.com/astral-sh/uv):

```bash
# Sincronizar el entorno virtual
uv sync

# Ejecutar el servidor con recarga en caliente
uv run python run.py
```

Abre en tu navegador: [http://localhost:8000](http://localhost:8000)

> [!TIP]
> Si el proveedor local `LLM_PROVIDER=local` esta configurado en `.env`, el lanzador `run.py` detectara o iniciara automaticamente el daemon de Ollama en segundo plano sin intervencion manual.

---

## 3. Endpoints Principales de la API

| Metodo | Endpoint | Descripcion |
|---|---|---|
| `GET` | `/` | Interfaz interactiva de usuario (Jinja2 SSR + Tailwind CSS v4) |
| `GET` | `/health` | Chequeo de salud, version del pipeline, modelo activo y telemetria |
| `POST` | `/procesar` | Procesamiento sincronico directo devolviendo `JobOutput` |
| `POST` | `/procesar/stream` | Transmision de progreso en tiempo real via Server-Sent Events (SSE) |
| `GET` | `/documentos/{pdf_hash}/raw` | Entrega segura del binario PDF para el visor interactivo PDF.js |
| `GET` | `/documentos/{pdf_hash}/search` | Buscador de coincidencias exactas estilo Chrome en el PDF |
| `GET` | `/resultados/{pdf_hash}` | Vista de dictamen forense en Split-View con visor y tabla de hallazgos |
| `POST` | `/chat/{pdf_hash}` | Pydective Chat documental multi-turno con grounding en L1 y Markdown |
| `GET` | `/v1/models` | Catálogo de modelos compatibles con la especificación OpenAI |
| `POST` | `/v1/chat/completions` | Endpoint conversacional estándar OpenAI para integración con IDEs |

---

## 4. Pruebas Automatizadas

La suite de pruebas contiene 139 tests automatizados que cubren validacion de entrada, clasificacion determinista, extraccion espacial, proveedores LLM (Cloud, Local y CLI), caching y visor interactivo:

```bash
uv run pytest
```
