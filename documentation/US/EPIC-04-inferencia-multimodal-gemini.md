# Épica 4: Inferencia Multimodal Gemini

> **Objetivo:** Ejecutar la extracción multimodal exclusivamente sobre las páginas que realmente lo requieren (`needs_ai`), utilizando el modelo canónico `gemini-2.0-flash` configurado para latencia mínima (`thinking_budget=0`, temperatura 0.0) y renderizado directo en C a WebP (1024 px, q75).

---

### US-11: Renderizado Baseline Directo a WebP con PyMuPDF

- **ID:** `US-11`
- **Requisitos asociados:** `RF-040`, `RF-041`, `RF-045`, `RF-050`, `RNF-004`, `RNF-006`, `ADR-004 Sección 13 y 14`
- **Prioridad:** Crítica | **Estimación:** 3 pts

#### Narrativa
**Como** servicio de renderizado de imágenes (`renderer.py`),  
**Quiero** renderizar las páginas pendientes directamente a WebP a escala 1024 px usando `fitz.Matrix` en C,  
**Para** evitar duplicación de memoria, eliminar dependencias de escalado en Pillow y despachar el renderizado en segundo plano (prefetch) mientras se clasifica el resto del PDF.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Renderizado directo sin reescalado secundario**
   - **Dado** una página con dimensiones $595 \times 842\text{ pt}$ clasificada como `needs_ai`,
   - **Cuando** se calcula el factor de escala `scale = 1024 / max(width, height)` y se ejecuta `page.get_pixmap(matrix=fitz.Matrix(scale, scale))`,
   - **Entonces** genera directamente la imagen con `max_dim=1024` px y compresión `WebP q75` en un solo paso en C en < 35 ms.

2. **Escenario: Reutilización de buffer en retries (Un único render por página)**
   - **Dado** una página cuyo envío a Gemini falla por error transitorio de red o 429,
   - **Cuando** el orquestador reintenta la llamada con otra API key sana,
   - **Entonces** reutiliza el buffer WebP existente en memoria sin volver a invocar `get_pixmap`.

3. **Escenario: Prefetch de WebP en segundo plano**
   - **Dado** que en el bucle inicial de clasificación la página 2 se identifica como `needs_ai`,
   - **Cuando** el clasificador continúa evaluando las páginas 3 a 20,
   - **Entonces** el renderizado WebP de la página 2 se despacha de inmediato al ThreadPoolExecutor para que esté listo cuando inicie la Fase B.

---

### US-12: Invocación Multimodal Quirúrgica con Gemini 2.0 Flash

- **ID:** `US-12`
- **Requisitos asociados:** `RF-042`, `RF-043`, `RF-044`, `RF-046`, `ADR-002`, `ADR-004`
- **Prioridad:** Crítica | **Estimación:** 5 pts

#### Narrativa
**Como** cliente de IA multimodal (`gemini_service.py`),  
**Quiero** invocar a `gemini-2.0-flash` con esquema JSON estricto, temperatura 0.0 y `thinking_budget=0`,  
**Para** transcribir con precisión quirúrgica texto manuscrito, sellos o tablas degradadas en menos de 900 ms sin costo de tokens de razonamiento superfluos.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Configuración canónica para baja latencia**
   - **Dado** un buffer WebP de una página escaneada y la lista de parámetros a buscar,
   - **Cuando** se formula la llamada con el SDK `google-genai`,
   - **Entonces** se establece `model="gemini-2.0-flash"`, `temperature=0.0`, `thinking_budget=0` y se suministra el JSON Schema Pydantic para `ResultadoPagina`.

2. **Escenario: Aislamiento estricto de fallo por página**
   - **Dado** un documento de 10 páginas donde la página 4 recibe un error 400 por imagen no decodificable o formato corrupto,
   - **Cuando** concluye la ejecución de la Fase B,
   - **Entonces** la página 4 se registra con `exito=False` y mensaje seguro de error, mientras que las páginas 1 a 3 y 5 a 10 se entregan completas con `partial_result=True`.

---

### US-13: Catalogación Física y Forense de Imágenes

- **ID:** `US-13`
- **Requisitos asociados:** `RF-037`, `RF-047`, `RF-092`, `ADR-004 Sección 9`
- **Prioridad:** Media | **Estimación:** 3 pts

#### Narrativa
**Como** usuario que audita documentos legales y contractuales,  
**Quiero** un inventario estructurado de firmas manuscritas, sellos notariales y logotipos presentes en el PDF,  
**Para** verificar la validez documental y asegurar que las cifras pactadas estén debidamente rubricadas.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Inventario físico local en Cero-IA (PyMuPDF)**
   - **Dado** un documento con imágenes incrustadas,
   - **Cuando** `image_service.py` ejecuta `page.get_images()`,
   - **Entonces** filtra logos minúsculos decorativos (<15% del área o <80x80 pt) e inventaría las coordenadas de objetos gráficos relevantes con 0 ms de costo IA.

2. **Escenario: Clasificación semántica selectiva**
   - **Dado** que el usuario activa `catalogar_imagenes=True` en `JobInput`,
   - **Cuando** una imagen supera las dimensiones de relevancia geométrica,
   - **Entonces** Gemini clasifica su tipología semántica (`firma_manuscrita`, `sello_oficial`, `logotipo`, `diagrama`).
