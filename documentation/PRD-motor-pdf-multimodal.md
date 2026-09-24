# PRD — Pydective: Motor Inteligente y Detective de Documentos PDF

**Versión:** 2.0  
**Estado:** definición de producto actualizada para MVP  
**Fecha:** 2026-09-23  
**Producto:** Pydective — aplicación web B2B de extracción asistida, visión determinista y chat interactivo sobre PDFs

---

## 1. Resumen

**Pydective** es un motor inteligente de extracción, catalogación visual y análisis conversacional de documentos PDF de cualquier naturaleza (contratos, pólizas, actas, historias clínicas, expedientes, facturas o especificaciones técnicas). Permite a un usuario cargar un PDF, buscar cualquier parámetro de interés (ej. `arrendatario`, `clausula penal`, `diagnostico`, `vigencia`, `radicado`, `total`, `NIT`, `fecha de vencimiento`), catalogar elementos gráficos e **interrogar conversacionalmente al documento** como un detective forense documental, recibiendo hallazgos y respuestas estructuradas por página.

El producto funciona tanto con PDFs digitales como con escaneos de baja calidad, documentos inclinados (*skewed*), manchados o mixtos. Aplica un principio estricto de **"Determinismo antes de IA"**: utiliza visión por computadora clásica (binarización Otsu y corrección de inclinación Deskew) antes de acudir a modelos multimodales, reduciendo ruido, costes y latencia.

La promesa de Pydective es:

> Encuentra datos clave, cataloga firmas y sellos, e interroga a cualquier PDF digital o escaneado en segundos, con trazabilidad exacta por página y sin reprocesar trabajo.

---

## 2. Problema

Los equipos administrativos, contables, jurídicos, operativos y de auditoría reciben PDFs constantemente: facturas, contratos, certificados, soportes, informes, órdenes y expedientes.

La revisión manual crea cuatro problemas principales:

1. **Tiempo:** localizar una fecha, un total, un código o una cláusula obliga a leer páginas completas.
2. **Errores:** la lectura repetitiva aumenta omisiones y digitación incorrecta.
3. **Documentos imperfectos:** muchos PDFs son escaneos, tienen manchas, sombras, baja resolución o no contienen texto seleccionable.
4. **Repetición:** cada nueva pregunta sobre el mismo PDF puede obligar a revisar el documento de nuevo.

El usuario no quiere “extraer todo el texto”; quiere responder rápidamente preguntas concretas sobre un documento y poder verificar de qué página provino cada hallazgo.

---

## 3. Objetivos

### Objetivo principal

Reducir el tiempo necesario para encontrar y verificar parámetros definidos por el usuario dentro de un PDF.

### Objetivos de producto

- Permitir cargar un PDF y buscar múltiples parámetros en una sola operación.
- Resolver documentos digitales rápidamente sin depender de IA cuando no sea necesaria.
- Manejar escaneos y contenido visual mediante análisis multimodal selectivo.
- Presentar los hallazgos ordenados por página.
- Permitir consultas posteriores sobre el mismo PDF con latencia mínima.
- Mostrar resultados parciales de forma transparente si una página no puede procesarse.

### Objetivos de negocio

- Validar que equipos operativos pagarían por ahorrar tiempo de revisión documental.
- Mantener el costo variable de IA bajo mediante procesamiento selectivo y caché.
- Crear una base que permita evolucionar hacia plantillas por industria, carga masiva e integraciones B2B.

---

## 4. No objetivos del MVP

El MVP no busca:

- Reemplazar un gestor documental, ERP, CRM o sistema de firma electrónica.
- Tomar decisiones legales, financieras, médicas o de cumplimiento sin revisión humana.
- Garantizar OCR perfecto en documentos extremadamente deteriorados.
- Procesar lotes masivos de miles de PDFs.
- Guardar documentos originales indefinidamente.
- Tener multi-tenant, roles empresariales o integración profunda con sistemas externos.
- Clasificar automáticamente todos los tipos documentales del mercado.

---

## 5. Usuarios objetivo

### Usuario operativo principal

Persona que revisa documentos repetitivamente y necesita encontrar datos específicos.

Ejemplos:

- Auxiliar administrativo.
- Analista contable.
- Asistente jurídico.
- Auditor documental.
- Analista de operaciones o logística.
- Consultor que revisa soportes de clientes.

### Comprador o patrocinador

Persona responsable por productividad, tiempos de operación o transformación digital.

Ejemplos:

- Coordinador administrativo.
- Jefe de contabilidad.
- Líder de operaciones.
- Responsable de cumplimiento.
- Dueño o gerente de una pyme.

### Segmento inicial recomendado

Pymes y equipos administrativos que trabajan con facturas, soportes contables, contratos sencillos y documentos operativos.

---

## 6. Propuesta de valor

| Dolor del usuario | Respuesta del producto |
|---|---|
| Revisar páginas una por una toma mucho tiempo | Búsqueda por parámetros y resultados por página |
| El PDF no deja seleccionar texto | Procesamiento multimodal para escaneos y contenido visual |
| Los documentos tienen ruido o baja calidad | Análisis selectivo de páginas que requieren interpretación |
| Se hacen nuevas preguntas sobre el mismo archivo | Reutilización de extracción y resultados previos |
| No se confía en texto extraído sin contexto | Hallazgos asociados a número de página y origen |
| Una falla técnica bloquea todo el documento | Resultado parcial y error aislado por página |

---

## 7. Alcance del MVP

### Flujo principal

1. El usuario abre la página principal de Pydective.
2. Carga un archivo PDF válido.
3. Escribe uno o más parámetros separados por coma (ej. `factura, total, fecha`).
4. Envía el formulario (con soporte de progreso en tiempo real).
5. El sistema procesa el documento aplicando visión determinista (Deskew + Otsu) y análisis multimodal selectivo para imágenes/escaneos, o reutiliza la caché L0/L1.
6. El usuario visualiza los resultados ordenados por página, incluyendo el texto extraído, parámetros encontrados y el **catálogo de imágenes identificadas (sellos, firmas, logos)**.
7. El usuario puede **iniciar una conversación (Chat)** con el documento para formular preguntas contextuales complejas ("¿Quién autorizó el pago?", "¿Tiene sello notarial?"), con respuestas referenciadas por página.
8. El usuario puede reconsultar otros parámetros sobre el mismo PDF con latencia mínima (<50 ms).

### Funciones incluidas

- Carga de un PDF por operación (hasta ~20 páginas en MVP).
- Parámetros de búsqueda libres, normalizados canónicamente.
- **Visión por computadora determinista previa a IA:**
  - Corrección de inclinación (*Deskew* con transformada de Hough).
  - Binarización y limpieza de ruido (*Otsu Thresholding*).
- **Inventario y catalogación de imágenes por página:**
  - Detección física de objetos visuales en la página.
  - Tipificación y descripción semántica (firmas, sellos, logotipos, diagramas, fotos).
- **Extracción semántica clave-valor y contexto forense (KWIC):**
  - Extracción de la entidad o valor asociado al parámetro (montos, fechas, NITs, porcentajes).
  - Normalización estructurada de datos (`currency`, `date`, `tax_id`, `percentage`).
  - Ventana contextual de la oración o cláusula completa que da sentido a la coincidencia.
  - Expansión semántica y reconocimiento automático de sinónimos canónicos (ej. `total` $\rightarrow$ `importe`, `saldo`).
  - Vinculación con evidencias visuales adyacentes (firmas y sellos cercanos).
- Extracción de texto limpio y detección de coincidencias nativas.
- Análisis multimodal selectivo (Gemini Flash con semáforo global) solo para páginas `needs_ai`.
- **Arquitectura Dual de Visión Local en CPU:** Alternancia dinámica entre **RapidOCR** (detección/reconocimiento ultrarrápido <180ms) y **Florence-2** (visión profunda y grounding denso).
- **Modo Benchmark Simultáneo:** Capacidad de ejecutar ambos motores concurrentemente en paralelo para evaluar latencia y exactitud en vivo.
- **Ingesta Universal Multi-Formato:** Soporte nativo para imágenes rasterizadas (PNG, JPG, TIFF) y formatos ofimáticos (DOCX, XLSX, TXT) convertidos en memoria a PDF.
- **Inyección de Capa OCR Invisible (`render_mode=3`):** Los documentos escaneados adquieren una capa de texto invisible que permite seleccionarlos y buscarlos como PDFs digitales en el visor.
- **Arquitectura Multi-Proveedor Desacoplada y Soporte CLI:** Operación en la nube (Google Gemini), local offline vía Ollama (Qwen2.5:3b) y ejecución directa de CLI de vanguardia (**Antigravity CLI `agy`** con `--dangerously-skip-permissions` y **OpenCode CLI `opencode run`**) en directorios temporales aislados.
- **Endpoints de Interoperabilidad OpenAI:** Rutas compatibles `GET /v1/models` y `POST /v1/chat/completions` para integrar extensiones de IDE y agentes autónomos sin errores 404.
- **Módulo Pydective Chat y Resúmenes Textuales:**
  - Interfaz conversacional conectada a L1/L2 para interrogar al PDF con citas obligatorias de página.
  - Lectura integral de folios con PyMuPDF y OCR complementario (`RapidOCR`) para diagramas y esquemas visuales.
  - Detección autónoma de capítulos y resúmenes ejecutivos no deterministas cuando el usuario selecciona un motor explícito de IA.
  - **Renderizado de Markdown Enriquecido:** Formateo dinámico con `marked.js` local (encabezados, negritas, viñetas, tablas, citas en bloque y bloques de código) y citas textuales `[Página X]` convertidas en pastillas interactivas que saltan al visor con un clic.
- **Visor de PDF interactivo con buscador de texto exacto estilo Chrome (`Ctrl+F`):**
  - Renderizado de alta fidelidad del PDF en la interfaz mediante PDF.js.
  - Buscador de texto exacto con contador dinámico ($N$ de $M$), botones anterior/siguiente y atajos de teclado (`Enter`, `Shift+Enter`).
  - Resaltado global de todas las ocurrencias en amarillo y la activa en naranja con desplazamiento suave (*auto-scroll*).
- **Visual Grounding bidireccional 100% confiable y Coordenadas BBox Exactas:**
  - Al pulsar una cita de chat o hallazgo, el visor salta a la página y resalta el recuadro delimitador (*bounding box*) exacto de la evidencia (texto, sello, firma, código de barras, logo), permitiendo copiar coordenadas `[ymin, xmin, ymax, xmax]`.
- **Cero datos mock:** Todas las coordenadas, extracciones y respuestas se calculan directamente del binario del PDF analizado de punta a punta.
- Soporte para resultados parciales aislados por página.
- Modo degradado tolerante a fallos de Redis (memoria local automática).
- Soporte de streaming de progreso por Server-Sent Events (SSE).
- **Compatibilidad Multiplataforma Total:** Instaladores y lanzadores universales para distribuciones Linux (POSIX) y Windows.

### Tipos de documentos soportados

| Tipo de documento | Expectativa MVP |
|---|---|
| PDF digital con texto | Resolución local ultrarrápida (<150 ms) sin coste de IA |
| PDF digital con imágenes/logos | Texto local; catalogación y descripción de imágenes por página |
| Escaneo inclinado o manchado | Preprocesamiento determinista (Deskew + Otsu) antes de evaluar IA |
| Escaneo sin capa de texto | OCR local (RapidOCR/Florence-2) con inyección de capa invisible |
| Imágenes (PNG, JPG, TIFF) | Conversión en memoria a PDF y extracción OCR/visión profunda |
| Documentos Office (DOCX, XLSX, TXT) | Conversión en memoria preservando UTF-8 y separación de celdas |
| Página vacía | Detección determinista; resultado vacío sin llamar a IA |

---

## 8. Experiencia de usuario

### Pantalla inicial

Debe incluir:

- Identidad del producto: **Pydective — Tu Detective Documental con IA**.
- Área de carga de PDF (drag & drop y explorador de archivos).
- Indicador claro de tipo (.pdf) y tamaño permitido (hasta 25 MB).
- Campo de parámetros de búsqueda con chips interactivos de ejemplo: `factura`, `fecha`, `total`, `NIT`, `firma`.
- Botón de procesamiento con indicador de estado accesible.

### Estado de procesamiento

Soporta progreso visual en tiempo real vía SSE (o feedback de carga accesible `aria-live="polite"`), mostrando qué páginas se han completado y qué fase se está ejecutando (Clasificación local, Deskew/Otsu, Inferencia visual).

### Pantalla de resultados y Panel de Detective (Layout Split-View)

Debe mostrar un espacio de trabajo forense interactivo de dos columnas:

1. **Panel Izquierdo — Visor de PDF Integrado:**
   - Visualización interactiva de las páginas del PDF.
   - Barra de herramientas con selector de páginas, botones de zoom y ajuste de ancho.
   - Barra de búsqueda flotante tipo Chrome con navegación anterior/siguiente y contador `$N$ de $M$`.
   - Capa de resaltado que proyecta los recuadros delimitadores (*Bounding Boxes*) de coincidencias y evidencias.
2. **Panel Derecho — Detective Chat y Hallazgos:**
   - **Hero Superior — Pydective Chat:** Asistente conversacional multi-turno con citas verificables `[Página X]`. Al hacer clic en cualquier cita, el visor izquierdo salta y resalta el elemento exacto.
   - **Inferior — Hallazgos Enriquecidos:** Tabla con parámetros extraídos, valores normalizados, scores de confianza y chips de evidencia que sincronizan el visor con un solo clic.

### Resultados parciales

Si una página falla:

- La pantalla debe mostrar los resultados exitosos.
- La página fallida debe indicar que no pudo procesarse.
- Debe evitar mensajes técnicos crudos o secretos de proveedor.
- Debe invitar a revisar el documento o reintentar más tarde si aplica.

---

## 9. Reglas de producto

1. Si un PDF tiene texto digital suficiente, el sistema usa ese texto como fuente principal.
2. La ausencia de una keyword en texto digital no obliga a usar IA.
3. La IA se usa para páginas con texto insuficiente, escaneos, ruido o contenido visual relevante.
4. Una página vacía debe resolverse sin IA.
5. Las búsquedas no distinguen mayúsculas de minúsculas.
6. Un parámetro repetido se procesa una sola vez.
7. Los hallazgos siempre conservan el número de página de origen.
8. Un error de una página no invalida el resultado de las demás.
9. El producto debe indicar que el resultado es una ayuda de extracción y requiere validación humana cuando el caso sea sensible.
10. La búsqueda repetida sobre el mismo documento debe reutilizar el conocimiento existente cuando sea válido.

---

## 10. Métricas de éxito

### Métricas de valor

| Métrica | Qué valida |
|---|---|
| Tiempo hasta primer resultado | Rapidez percibida |
| Documentos procesados por usuario | Adopción inicial |
| Consultas repetidas por documento | Valor de reutilización y caché |
| Parámetros encontrados por documento | Utilidad de búsqueda |
| Tasa de finalización de procesamiento | Confiabilidad |
| Porcentaje de resultados parciales | Calidad operativa y fallos externos |

### Métricas de negocio

| Métrica | Qué valida |
|---|---|
| Conversión prueba → uso recurrente | Ajuste problema-solución |
| Usuarios activos semanales | Frecuencia de necesidad |
| Documentos por cuenta | Intensidad de uso |
| Disposición de pago por paquete | Viabilidad comercial |
| Costo IA por documento | Margen unitario |
| Porcentaje de hits de caché | Eficiencia económica |

### Metas iniciales de producto

- Un hit de consulta previa debe sentirse instantáneo.
- Una nueva búsqueda sobre un PDF ya extraído debe responder más rápido que una primera carga.
- Un documento digital típico no debe depender de IA para encontrar texto.
- El sistema debe entregar resultados útiles incluso cuando una parte del documento no pueda analizarse.

Las metas numéricas de latencia se definen en la especificación arquitectónica y se validan con un corpus real de documentos.

---

## 11. Riesgos de producto

| Riesgo | Impacto para usuario | Mitigación de producto |
|---|---|---|
| OCR incorrecto | Hallazgos equivocados | Mostrar página de origen y advertir revisión humana |
| Documento demasiado deteriorado | Resultado incompleto | Estado claro de calidad insuficiente |
| Demora en IA | Frustración | Procesamiento selectivo, caché y resultados parciales |
| Key/proveedor agotado | Página sin resultado | Fallo aislado y mensaje no técnico |
| Parámetros ambiguos | Resultados poco útiles | Ejemplos de búsqueda y refinamiento futuro |
| Datos sensibles | Pérdida de confianza | Retención mínima y comunicación transparente |

---

## 12. Hipótesis por validar

1. Los usuarios valoran más buscar parámetros que descargar texto OCR plano.
2. Asociar cada hallazgo a una página aumenta confianza y utilidad.
3. Los documentos escaneados son un dolor por el que empresas pequeñas están dispuestas a pagar.
4. Las consultas repetidas sobre el mismo documento ocurren con suficiente frecuencia para que la caché sea visible para el usuario.
5. Una configuración por tipo de documento aumenta conversión frente a un campo libre genérico.
6. El usuario acepta resultados parciales si entiende claramente qué páginas se procesaron y cuáles no.

---

## 13. Roadmap de producto

### MVP

- Carga individual de PDF.
- Parámetros libres.
- Resultados por página.
- Texto nativo + análisis multimodal selectivo.
- Caché de consulta y extracción.
- Manejo de errores parciales.

### Siguiente etapa

- Historial limitado de documentos y consultas.
- Exportación de resultados.
- Plantillas: factura, contrato, soporte, certificado.
- Autenticación básica.
- Créditos o plan mensual.

### Evolución B2B

- Espacios de trabajo y multiusuario.
- Roles y permisos.
- Carga por lote.
- API / webhooks.
- Integraciones con ERP, CRM, correo o almacenamiento documental.
- Flujos de revisión y aprobación.

---

## 14. Criterios de éxito del MVP

El MVP se considera validado si:

- Usuarios reales logran encontrar información en documentos de prueba sin asistencia del equipo técnico.
- El sistema resuelve correctamente la mayoría de PDFs digitales sin usar IA.
- Los documentos escaneados muestran una mejora evidente frente a lectura manual sin apoyo.
- El usuario entiende de qué página proviene cada resultado.
- Las consultas repetidas evidencian una mejora perceptible de velocidad.
- Las fallas de una página no hacen perder el resultado del resto del documento.
- Al menos un segmento objetivo expresa disposición concreta de continuar usando o pagar por la solución.

---

## 15. Mensaje de producto

### Propuesta corta

> Sube un PDF, indica qué necesitas encontrar y recibe resultados organizados por página, incluso si el documento está escaneado o tiene baja calidad.

### Propuesta para equipos operativos

> Reduce el tiempo de revisar facturas, contratos y soportes. Encuentra fechas, valores, códigos, nombres y evidencias sin leer página por página.

### Declaración de límites

> La plataforma ayuda a extraer y localizar información. Los resultados deben ser verificados por una persona cuando se utilicen en decisiones importantes.
