# Épica 1: Ingesta, Validación y Control de Entrada

> **Objetivo:** Garantizar la recepción segura, rápida y en memoria de los documentos PDF, aplicando validaciones binarias tempranas y normalización canónica de los parámetros de búsqueda sin persistir archivos en disco.

---

### US-01: Ingesta en Memoria y Validación Rápida de Integridad PDF

- **ID:** `US-01`
- **Requisitos asociados:** `RF-001`, `RF-002`, `RF-003`, `RF-004`, `RF-005`, `RF-007`, `RNF-022`, `RV-001`, `RV-002`, `RV-003`
- **Prioridad:** Alta | **Estimación:** 2 pts

#### Narrativa
**Como** usuario operativo del sistema,  
**Quiero** cargar un archivo PDF a través de la interfaz web o la API REST,  
**Para** que sea analizado inmediatamente en memoria sin demoras por escrituras innecesarias a disco.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Carga exitosa de un archivo PDF válido**
   - **Dado** que el usuario envía un archivo con firma `%PDF` y tamaño menor o igual al límite configurado (e.g. 25 MB),
   - **Cuando** el endpoint `/procesar` o `/procesar/stream` recibe la petición,
   - **Entonces** el sistema lee los bytes en memoria, genera el hash SHA-256 del contenido binario y no crea archivos temporales en el sistema de archivos.

2. **Escenario: Rechazo de archivos que no son PDF**
   - **Dado** que el usuario envía un archivo ejecutable, imagen aislada o texto plano (`.txt`, `.docx`),
   - **Cuando** se valida la cabecera del archivo,
   - **Entonces** el sistema rechaza la petición de inmediato con código HTTP 400 y mensaje seguro de error (`INVALID_PDF`), sin ejecutar PyMuPDF ni Gemini.

3. **Escenario: Detección de PDF corrupto o con contraseña**
   - **Dado** que se envía un archivo con extensión `.pdf` pero con bytes incompletos o cifrado con contraseña,
   - **Cuando** PyMuPDF intenta abrir el documento en memoria (`fitz.open(stream=bytes)`),
   - **Entonces** se captura la excepción de bajo nivel y se retorna HTTP 400 con error controlado (`CORRUPTED_OR_ENCRYPTED_PDF`).

---

### US-02: Normalización Lingüística Canónica de Parámetros Dinámicos

- **ID:** `US-02`
- **Requisitos asociados:** `RF-010`, `RF-011`, `RF-012`, `RF-013`, `RF-014`, `RF-015`, `RNF-001`, `ADR-003`
- **Prioridad:** Alta | **Estimación:** 3 pts

#### Narrativa
**Como** usuario que busca términos específicos en documentos hispanohablantes o internacionales,  
**Quiero** ingresar parámetros en cualquier orden, con o sin tildes, mayúsculas o espacios accidentales,  
**Para** que el motor encuentre coincidencias semánticas exactas y reutilice la caché L0 sin importar variaciones tipográficas menores.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Normalización NFKD e insensibilidad a mayúsculas y diacríticos**
   - **Dado** que el usuario ingresa la cadena `"  Facturación, TOTAL, número de radicado  "`,
   - **Cuando** el servicio `semantic_extraction_service.py` normaliza los parámetros,
   - **Entonces** genera la lista limpia `['facturacion', 'total', 'numero de radicado']` descomponiendo diacríticos vía Unicode NFKD.

2. **Escenario: Deduplicación y orden canónico para clave L0**
   - **Dado** que dos usuarios envían `["total", "fecha"]` y `["FECHA", "total", "  total  "]` respectivamente para el mismo PDF,
   - **Cuando** se genera la tupla canónica de consulta,
   - **Entonces** ambos generan exactamente el mismo `query_hash`, permitiendo que la segunda solicitud resuelva desde L0 en < 20 ms.

---

### US-03: Control de Límites del Documento (Límite 20 Páginas y Parámetros Vacíos)

- **ID:** `US-03`
- **Requisitos asociados:** `RF-006`, `RF-016`, `RV-006`, `RV-007`, `RNF-025`, `ADR-004`
- **Prioridad:** Crítica | **Estimación:** 2 pts

#### Narrativa
**Como** administrador del sistema y desarrollador,  
**Quiero** restringir el tamaño del documento a un máximo de 20 páginas y exigir al menos un parámetro de búsqueda,  
**Para** proteger la cuota de la API, evitar sobrecargas de memoria y garantizar la promesa del alcance MVP.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Rechazo estricto ante PDFs de más de 20 páginas (RV-006)**
   - **Dado** un PDF que contiene 21 o más páginas,
   - **Cuando** PyMuPDF inspecciona el contador `doc.page_count`,
   - **Entonces** el sistema aborta de inmediato con HTTP 400 y código `PAGE_LIMIT_EXCEEDED`, especificando `max_pages=20` y `received_pages=N`.

2. **Escenario: Rechazo ante lista de parámetros vacía o solo espacios (RV-007)**
   - **Dado** un formulario enviado con `parametros=""` o `parametros="  , ,  "`,
   - **Cuando** se valida la entrada en el borde HTTP de FastAPI,
   - **Entonces** se retorna HTTP 400 con código `EMPTY_SEARCH_PARAMETERS`, impidiendo llamadas a la caché o al motor.
