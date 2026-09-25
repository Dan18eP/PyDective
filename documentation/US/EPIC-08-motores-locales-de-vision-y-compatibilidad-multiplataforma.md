# Épica 8: Motores Locales de Visión, Ingesta Universal y Compatibilidad Multiplataforma

> **Objetivo:** Dotar a PyDective de autonomía operativa 100% desconectada mediante inferencia de visión local en CPU (RapidOCR y Florence-2), benchmark en vivo, soporte de formatos universales (imágenes y suites de oficina) y portabilidad nativa multiplataforma para entornos Linux y Windows.

---

### US-26: Ingesta Universal Multi-Formato con Conversión en Memoria

- **ID:** `US-26`
- **Requisitos asociados:** `RF-104`, `ADR-006`
- **Prioridad:** Alta | **Estimación:** 5 pts

#### Narrativa
**Como** analista documental o auditor forense,  
**Quiero** cargar archivos no PDF (imágenes PNG, JPG, TIFF y documentos DOCX, XLSX, TXT),  
**Para** procesar evidencias documentales heterogéneas sin necesidad de convertirlas manualmente a PDF en herramientas externas.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Carga e ingesta de formatos de imagen**
   - **Dado** un archivo de imagen válido (`.png`, `.jpg`, `.tiff`),
   - **Cuando** se envía al endpoint de procesamiento,
   - **Entonces** `ingestion_service.py` crea en memoria un documento PDF equivalente envolviendo la imagen rasterizada sin pérdidas geométricas.

2. **Escenario: Preservación de UTF-8 y separación tabular en Office**
   - **Dado** una hoja de cálculo `.xlsx` o contrato `.docx` con tildes y caracteres hispanos (`Á`, `É`, `Í`, `Ó`, `Ú`, `ñ`),
   - **Cuando** se genera la conversión vectorial a PDF,
   - **Entonces** los caracteres se preservan con codificación nativa UTF-8 y las celdas conservan sus delimitadores de columna sin vaciar textos.

---

### US-27: Motor OCR Local Autónomo sobre CPU con Inyección de Capa Invisible

- **ID:** `US-27`
- **Requisitos asociados:** `RF-105`, `RNF-051`, `ADR-006`
- **Prioridad:** Crítica | **Estimación:** 5 pts

#### Narrativa
**Como** oficial de cumplimiento en un entorno air-gapped o sin API key de Gemini,  
**Quiero** que el sistema extraiga texto y coordenadas espaciales mediante RapidOCR en CPU,  
**Para** analizar documentos escaneados e inyectar una capa de texto invisible que habilite la búsqueda y selección en el visor interactivo.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Inferencia OCR local en CPU**
   - **Dado** una página clasificada como escaneo o imagen rasterizada,
   - **Cuando** no hay conexión a internet o se selecciona el motor RapidOCR,
   - **Entonces** `ocr_service.py` ejecuta la detección y reconocimiento de texto en menos de 200 ms por página sobre CPU.

2. **Escenario: Inyección de capa invisible**
   - **Dado** el texto extraído y sus coordenadas delimitadoras,
   - **Cuando** se almacena el PDF en caché/disco,
   - **Entonces** se inyectan glifos invisibles con `render_mode=3` de PyMuPDF, permitiendo búsqueda exacta en el visor PDF.js.

---

### US-28: Motor de Visión Profunda Local (Florence-2) y Grounding Multimodal

- **ID:** `US-28`
- **Requisitos asociados:** `RF-106`, `ADR-006`
- **Prioridad:** Alta | **Estimación:** 8 pts

#### Narrativa
**Como** investigador forense,  
**Quiero** procesar documentos notariales o con tipografía degradada mediante el modelo fundacional Florence-2 de Microsoft,  
**Para** obtener coordenadas de bounding box de alta densidad y captions contextuales enriquecidos en modo offline.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Grounding espacial con Florence-2**
   - **Dado** una imagen de documento compleja,
   - **Cuando** se selecciona `vision_engine="florence2"`,
   - **Entonces** `florence_service.py` ejecuta el prompt `<OCR_WITH_REGION>` generando coordenadas `[ymin, xmin, ymax, xmax]` normalizadas a 1000.

---

### US-29: Modo Benchmark Simultáneo y Comparativa de Precisión/Latencia

- **ID:** `US-29`
- **Requisitos asociados:** `RF-107`, `ADR-006`
- **Prioridad:** Media | **Estimación:** 3 pts

#### Narrativa
**Como** evaluador de tecnología,  
**Quiero** activar el switch de benchmark dual en el frontend para ejecutar RapidOCR y Florence-2 al mismo tiempo,  
**Para** contrastar directamente en la interfaz el tiempo de respuesta y la exactitud de los hallazgos extraídos.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Procesamiento concurrente de benchmark**
   - **Dado** la selección `vision_engine="both"`,
   - **Cuando** se procesa el documento,
   - **Entonces** el backend ejecuta ambos motores concurrentemente con `asyncio.gather` y reporta métricas comparativas en la respuesta.

---

### US-30: Arquitectura Multi-Proveedor Desacoplada (Cloud vs Local LLM)

- **ID:** `US-30`
- **Requisitos asociados:** `RF-108`, `ADR-006`
- **Prioridad:** Alta | **Estimación:** 5 pts

#### Narrativa
**Como** arquitecto de sistemas,  
**Quiero** una capa de proveedores desacoplada (`BaseProvider`, `GeminiProvider`, `LocalProvider`),  
**Para** alternar transparentemente entre modelos Google Gemini y modelos locales ejecutados en Ollama (ej. Qwen2.5:3b).

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Failover o selección de proveedor local**
   - **Dado** la configuración `LLM_PROVIDER=local` en el archivo `.env`,
   - **Cuando** se solicita una extracción semántica o respuesta del chat,
   - **Entonces** el orquestador delega la llamada a la API REST local de Ollama sin invocar servicios cloud.

---

### US-31: Instalador e Inicializador Multiplataforma (Linux / Windows) y Portapapeles Resiliente

- **ID:** `US-31`
- **Requisitos asociados:** `RF-109`, `RNF-052`, `ADR-007`
- **Prioridad:** Crítica | **Estimación:** 5 pts

#### Narrativa
**Como** usuario o administrador en entornos Linux (Ubuntu, Debian, Fedora, Arch) o Windows,  
**Quiero** scripts universales de arranque (`run_app.py`, `run.py`, `install.sh`, `run.sh`) y copiado de portapapeles sin errores en el navegador,  
**Para** inicializar el entorno y gestionar el servicio daemon de Ollama de forma limpia y consistente en cualquier sistema operativo.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Detección y ciclo de vida de procesos en Linux/POSIX**
   - **Dado** un entorno Linux,
   - **Cuando** se ejecuta `./run.sh` o `python3 run_app.py`,
   - **Entonces** el daemon de Ollama se inicia con `start_new_session=True` y se localizan los binarios en rutas POSIX (`~/.local/bin/uv`, `/usr/local/bin/ollama`).

2. **Escenario: Copia de coordenadas en navegadores Linux**
   - **Dado** una sesión de navegador bajo Wayland o sin contexto HTTPS,
   - **Cuando** el usuario presiona el botón de copiar coordenadas BBox,
   - **Entonces** la función `copyToClipboard()` recurre al fallback de `<textarea>` oculto sin lanzar excepciones de DOM en la consola.

---

### US-32: Aceleración de OCR con Binarización Adaptativa Otsu, Descarte de Blancos y Paralelismo Multi-Hilo

- **ID:** `US-32`
- **Requisitos asociados:** `RF-105`, `RNF-051`, `ADR-008`
- **Prioridad:** Crítica | **Estimación:** 8 pts

#### Narrativa
**Como** sistema de extracción documental de alto rendimiento,  
**Quiero** binarizar adaptativamente con Otsu las imágenes antes de RapidOCR, descartar folios en blanco en <2ms y procesar páginas escaneadas concurrentemente con handles aislados de PyMuPDF,  
**Para** reducir el tiempo de decodificación OCR en un 40% sin contención de hilos ni degradación en la exactitud de los caracteres.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Binarización adaptativa Otsu pre-inferencia**
   - **Dado** una página escaneada con sombras o fondo tramado,
   - **Cuando** `evaluate_contrast_and_otsu` detecta bajo contraste,
   - **Entonces** aplica binarización Otsu convirtiendo el fondo en blanco puro (255) y el texto en negro puro (0), acelerando la inferencia de RapidOCR DBNet/CRNN de ~9.6s a ~5.8s con 100% de coincidencia de caracteres.

2. **Escenario: Detección y omisión de páginas en blanco en <2 ms**
   - **Dado** una página completamente en blanco o vacía,
   - **Cuando** `extract_page_ocr` evalúa la desviación estándar y media (`std < 10.0 and mean > 245.0`),
   - **Entonces** retorna inmediatamente una lista vacía de texto y coordenadas omitiendo por completo la llamada al modelo ONNX.

3. **Escenario: Procesamiento paralelo aislado con ThreadPoolExecutor**
   - **Dado** un documento con múltiples folios escaneados que requieren OCR,
   - **Cuando** el backend orquesta el procesamiento de páginas,
   - **Entonces** utiliza `ThreadPoolExecutor(max_workers=2)` donde cada worker inicializa `sub_doc = fitz.open(stream=pdf_bytes, filetype="pdf")`, eliminando la contención de mutex en C++ y el bloqueo del GIL.

---

### US-33: Calibración y Precalentamiento del Motor OCR en Lifespan para Cero Cold-Start

- **ID:** `US-33`
- **Requisitos asociados:** `RNF-001`, `ADR-008`
- **Prioridad:** Alta | **Estimación:** 3 pts

#### Narrativa
**Como** usuario que interactúa por primera vez con el sistema tras un reinicio del servidor,  
**Quiero** que los modelos de visión de RapidOCR ya se encuentren cargados en memoria RAM,  
**Para** no experimentar retrasos de 2.5 a 3.5 segundos por arranque en frío (*cold-start*) en la primera solicitud.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Precarga de modelos ONNX en el evento de inicio (Lifespan)**
   - **Dado** el inicio del servidor Uvicorn con FastAPI,
   - **Cuando** se ejecuta el contexto `lifespan(app: FastAPI)`,
   - **Entonces** se invoca `get_ocr_engine()` instanciando el motor de RapidOCR en memoria antes de aceptar conexiones HTTP.

