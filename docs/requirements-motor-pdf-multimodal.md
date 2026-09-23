# Requisitos del Sistema
## Motor Ultra-Veloz de Extracción Multimodal Anti-Ruido

**Versión:** 1.0  
**Estado:** línea base de requisitos para MVP  
**Fecha:** 2026-09-23  
**Relacionado con:** PRD, Especificación Arquitectónica General v2.0 y ADR-001

---

## 1. Propósito

Este documento define los requisitos funcionales, no funcionales, reglas de validación y criterios verificables para el MVP del Motor Ultra-Veloz de Extracción Multimodal Anti-Ruido.

Los requisitos se redactan de forma independiente de la implementación, pero respetan las decisiones vigentes:

- extracción híbrida local + multimodal;
- Redis para caché persistente;
- caché L0, L1 y L2 opcional;
- reintento y failover por página;
- resultado parcial controlado;
- interfaz HTML SSR con FastAPI y Jinja2.

Las claves de requisito (`RF`, `RNF`, `RV`, `RC`) deben conservarse en historias de usuario, pruebas y trazabilidad futura.

---

## 2. Alcance del sistema

El sistema permite que un usuario cargue un PDF, proporcione una lista de parámetros y visualice resultados de extracción y búsqueda organizados por página.

El MVP incluye:

- un PDF por solicitud;
- PDFs de aproximadamente 20 páginas como límite inicial configurable;
- búsqueda por uno o más parámetros;
- análisis de texto nativo;
- análisis multimodal selectivo para páginas que lo requieran;
- resultados parciales;
- caché de resultados y extracción;
- visualización HTML del reporte.

El MVP excluye carga masiva, autenticación, multi-tenant, historial de usuario, flujos de aprobación, persistencia permanente del PDF original e integraciones externas de negocio.

---

## 3. Actores

| Actor | Descripción | Interacción |
|---|---|---|
| Usuario operativo | Persona que revisa PDFs y busca información | Carga PDF, indica parámetros, revisa resultados |
| Administrador técnico | Persona que configura infraestructura y keys | Define límites, Redis, API keys y observabilidad |
| Proveedor multimodal | Servicio externo de IA | Procesa únicamente páginas marcadas `needs_ai` |
| Redis | Dependencia de infraestructura | Persiste L0/L1 y punteros L2 |

---

## 4. Requisitos funcionales

### 4.1 Carga y validación de documento

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-001 | El sistema debe mostrar un formulario para cargar un PDF y registrar parámetros de búsqueda. | La ruta principal muestra selector de archivo, campo de parámetros y acción de procesar. |
| RF-002 | El sistema debe aceptar una única carga de archivo por solicitud. | El endpoint rechaza solicitudes sin archivo o con más de un archivo cuando el contrato no lo permita. |
| RF-003 | El sistema debe validar que el archivo recibido corresponda a un PDF. | Se valida MIME declarado y firma/cabecera PDF antes de procesar. |
| RF-004 | El sistema debe rechazar archivos que superen el tamaño máximo configurado. | El usuario recibe mensaje claro; no se ejecuta extracción ni IA. |
| RF-005 | El sistema debe rechazar PDFs corruptos, cifrados no soportados o imposibles de abrir. | La respuesta informa que el documento no pudo ser procesado sin exponer detalles internos. |
| RF-006 | El sistema debe aplicar un límite configurable de páginas por PDF. | Un archivo que supere el límite se rechaza o se procesa según política explícita configurada. |
| RF-007 | El sistema debe leer el PDF una única vez para iniciar el trabajo. | La ejecución usa `bytes` del archivo y no depende de persistirlo a disco. |

### 4.2 Parámetros de búsqueda

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-010 | El usuario debe poder ingresar uno o más parámetros separados por coma. | `factura, fecha, total` se convierte en tres parámetros. |
| RF-011 | El sistema debe eliminar espacios sobrantes antes y después de cada parámetro. | ` factura ` se procesa como `factura`. |
| RF-012 | La búsqueda no debe diferenciar mayúsculas y minúsculas. | `TOTAL` y `total` producen el mismo criterio de búsqueda. |
| RF-013 | El sistema debe eliminar parámetros vacíos. | `factura,, total,` no produce elementos vacíos. |
| RF-014 | El sistema debe eliminar parámetros duplicados. | `total, Total, total` genera un único criterio canónico. |
| RF-015 | El sistema debe mantener una representación canónica de parámetros para caché. | Cambiar el orden o capitalización de keywords equivalentes produce la misma clave L0. |
| RF-016 | El sistema debe informar al usuario si no se ingresó ningún parámetro válido. | No se ejecuta la búsqueda sin política explícita para consultas vacías. |

### 4.3 Identidad y caché

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-020 | El sistema debe calcular una huella SHA-256 del contenido binario del PDF. | El mismo archivo binario genera el mismo hash. |
| RF-021 | El sistema debe consultar caché L0 antes de abrir el PDF con el motor de extracción. | Un hit L0 no ejecuta clasificación, render ni IA. |
| RF-022 | La caché L0 debe indexarse por hash del PDF y parámetros normalizados. | El mismo PDF con parámetros distintos no devuelve resultados de una consulta anterior. |
| RF-023 | El sistema debe consultar caché L1 cuando no exista resultado L0. | Mismo PDF con nuevos parámetros puede refiltrarse sin IA. |
| RF-024 | L1 debe guardar conocimiento reusable por página. | Incluye texto limpio, descripción visual si existe, origen y estado. |
| RF-025 | El sistema debe crear un nuevo resultado L0 tras refiltrar L1 con una nueva consulta. | La segunda consulta equivalente se resuelve desde L0. |
| RF-026 | El sistema no debe almacenar como resultado reutilizable una página con extracción fallida. | Una página `exito=false` no se guarda como contenido válido en L1. |
| RF-027 | La caché de producción debe sobrevivir al reinicio de la aplicación. | Al reiniciar la app con Redis disponible, L0/L1 continúan consultables. |
| RF-028 | El sistema debe soportar invalidación de entradas L0 y L1 por TTL. | Una entrada vencida no se utiliza como hit válido. |

### 4.4 Clasificación y extracción local

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-030 | El sistema debe abrir el PDF desde memoria para analizar sus páginas. | El pipeline opera sobre `bytes`; no necesita archivo temporal para el flujo normal. |
| RF-031 | El sistema debe extraer texto nativo de cada página antes de decidir el uso de IA. | La clasificación local obtiene texto y señales por página. |
| RF-032 | El sistema debe clasificar cada página como `local`, `empty` o `needs_ai`. | Toda página termina con uno de esos estados antes de consolidación. |
| RF-033 | Una página con texto digital suficiente y sin análisis visual requerido debe resolverse localmente. | No genera pixmap ni solicitud de IA. |
| RF-034 | Una página digital sin coincidencias debe resolverse localmente con lista vacía de parámetros. | La ausencia de keyword no desencadena IA. |
| RF-035 | Una página vacía sin contenido útil debe devolverse como resultado vacío. | No se llama a IA para una página vacía. |
| RF-036 | Una página con texto insuficiente, escaneo o ruido debe marcarse `needs_ai`. | Se envía a Fase B solo si corresponde. |
| RF-037 | Una página con contenido visual relevante debe marcarse `needs_ai` cuando la solicitud requiera descripción visual. | La política se aplica de forma consistente. |

### 4.5 Extracción multimodal

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-040 | El sistema debe renderizar únicamente páginas `needs_ai`. | En un PDF mixto, las páginas locales no generan WebP. |
| RF-041 | El sistema debe convertir la página pendiente a un formato de imagen optimizado antes de enviarla a IA. | Se genera WebP con tamaño controlado. |
| RF-042 | El sistema debe enviar una instrucción que solicite texto limpio, parámetros encontrados y descripciones visuales relevantes. | La respuesta se valida contra el contrato de página. |
| RF-043 | El sistema debe solicitar salida JSON estructurada cuando el SDK/modelo seleccionado lo permita. | La respuesta se parsea y valida contra el esquema. |
| RF-044 | El sistema debe conservar el número de página asociado a cada respuesta IA. | Cada resultado IA contiene el índice de página original. |
| RF-045 | El sistema debe reutilizar el mismo buffer WebP durante reintentos de una página. | Un retry no vuelve a renderizar ni a comprimir esa página. |
| RF-046 | El sistema debe convertir una respuesta inválida de IA en error aislado de página. | No cancela otras páginas ni rompe el formato del resultado global. |
| RF-047 | El sistema debe describir únicamente imágenes, logos, ilustraciones u objetos relevantes, no manchas o ruido visual. | Las descripciones deben seguir la regla de producto definida. |

### 4.6 Concurrencia y failover

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-050 | El sistema debe limitar la cantidad de renderizados WebP concurrentes. | La configuración aplica un máximo de workers de render. |
| RF-051 | El sistema debe limitar globalmente las solicitudes Gemini en vuelo. | Existe semáforo compartido con límite configurable. |
| RF-052 | El sistema debe procesar tareas IA pendientes de manera concurrente dentro del límite. | Páginas pendientes no se procesan necesariamente en serie. |
| RF-053 | Un fallo de una tarea IA no debe cancelar las demás tareas de páginas. | El resultado conserva páginas exitosas. |
| RF-054 | El pool de keys debe distinguir estados `healthy`, `cooldown`, `exhausted` e `invalid`. | El estado de cada key se consulta y actualiza. |
| RF-055 | Ante 429 temporal, el sistema debe poner la key en cooldown y reintentar solo la página afectada con otra key sana si existe. | No se repite el documento ni las páginas exitosas. |
| RF-056 | Ante cuota dura, el sistema debe excluir la key para el job o TTL definido. | La key no vuelve a seleccionarse mientras siga agotada. |
| RF-057 | Ante 401 o 403, el sistema debe marcar la key como inválida. | La key no se usa hasta intervención/recarga permitida. |
| RF-058 | Ante 400 atribuible a contenido, schema o solicitud inválida, el sistema no debe rotar keys automáticamente. | La página devuelve error aislado. |
| RF-059 | Si todas las keys válidas están en cooldown, el sistema debe esperar de forma acotada o devolver parcial según deadline. | No relanza todo el documento. |
| RF-060 | Si no quedan keys utilizables, el sistema debe devolver las páginas exitosas y reportar errores de las pendientes. | `partial_result=true` cuando corresponda. |

### 4.7 Context Cache del proveedor

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-065 | El sistema puede crear una caché de contexto explícita para documentos con contenido multimodal reutilizable. | Se crea solo cuando existen páginas IA y la funcionalidad está habilitada. |
| RF-066 | El sistema debe almacenar el identificador del Context Cache junto con `pdf_hash`, `key_id` y vencimiento. | No se reutiliza un `cache_name` de key ajena. |
| RF-067 | El sistema debe respetar el TTL del Context Cache. | Un puntero vencido no se envía como caché válida. |
| RF-068 | Si el Context Cache no existe, vence o falla, el sistema debe continuar sin devolver error global. | Reenvía contenido o procesa sin L2 según corresponda. |
| RF-069 | El sistema no debe asumir que una propiedad no verificada del SDK activa Context Cache. | La implementación usa la API vigente del SDK fijado. |

### 4.8 Resultados y presentación

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-070 | El sistema debe devolver resultados ordenados de forma ascendente por número de página. | Página 1 aparece antes de página 2 independientemente del orden de finalización. |
| RF-071 | Cada resultado de página debe incluir estado de éxito. | `exito` existe y es booleano. |
| RF-072 | Cada página exitosa debe incluir texto limpio, parámetros encontrados y descripción visual. | Las listas pueden estar vacías, pero los campos siguen existiendo. |
| RF-073 | Cada página con error debe incluir una descripción segura del error. | No expone API key, stack trace ni secretos. |
| RF-074 | El resultado global debe indicar si es parcial. | `partial_result=true` si una o más páginas no finalizan con éxito. |
| RF-075 | La interfaz debe mostrar los parámetros buscados. | El usuario puede verificar qué consulta ejecutó. |
| RF-076 | La interfaz debe mostrar el estado y hallazgos de cada página. | Se distinguen encontrada, sin coincidencia, vacía y error. |
| RF-077 | La interfaz debe comunicar que los resultados requieren revisión humana en usos sensibles. | El aviso aparece en resultados o contexto de uso. |

### 4.9 Observabilidad

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-080 | El sistema debe asignar un `request_id` a cada procesamiento. | El ID aparece en logs del mismo flujo. |
| RF-081 | El sistema debe registrar hash, número de páginas, nivel de caché y duración total. | Logs estructurados contienen esos campos. |
| RF-082 | El sistema debe registrar número de páginas locales, IA, fallidas, retries y failovers. | Métricas/logs permiten calcularlos. |
| RF-083 | El sistema debe permitir identificar la causa de un resultado parcial. | Existe evento o campo de razón agregada. |
| RF-084 | El sistema debe exponer endpoint de salud. | `GET /health` responde según estado de aplicación y dependencias esenciales. |

### 4.10 Visión determinista, catalogación de imágenes y chat interactivo

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-090 | El sistema debe corregir la inclinación (*deskew*) de páginas escaneadas mediante técnicas deterministas antes de invocar IA. | Se detecta el ángulo dominante y se rota la imagen para horizontalizar el texto antes de evaluar legibilidad o llamar a Gemini. |
| RF-091 | El sistema debe aplicar binarización de Otsu a páginas escaneadas o con ruido visual para maximizar el contraste texto/fondo. | Se genera máscara binarizada minimizando varianza intraclasal previo a OCR/análisis visual. |
| RF-092 | El sistema debe inventariar y catalogar todas las imágenes por página, indicando número de página, tipo (sello, firma, logo, diagrama, foto) y descripción de contenido. | El JSON de salida y la UI presentan la lista estructurada `imagenes_detectadas` por cada página. |
| RF-093 | El sistema debe permitir al usuario conversar en lenguaje natural con el documento analizado mediante un endpoint de chat. | `POST /chat/{pdf_hash}` recibe pregunta y responde contextualmente fundamentado en L1/L2. |
| RF-094 | Toda respuesta del chat debe incluir obligatoriamente citas y referencias al número de página de procedencia de cada evidencia. | La respuesta estructurada lista las páginas citadas y declina responder si el dato no figura en el documento. |
| RF-095 | El sistema debe ofrecer un endpoint de streaming reactivo (SSE) para emitir el progreso página a página en tiempo real. | `GET /procesar/stream` emite eventos `page_completed` y `job_completed` mitigando timeouts HTTP en el cliente. |

### 4.11 Extracción semántica enriquecida y clave-valor

| ID | Requisito | Criterio verificable |
|---|---|---|
| RF-096 | El sistema debe extraer la entidad o valor asociado a cada parámetro buscado mediante análisis de proximidad geométrica espacial y expresiones regulares. | Se captura el valor numérico, código o nombre adyacente a la derecha o debajo de la etiqueta en la misma página o tabla. |
| RF-097 | El sistema debe suministrar una ventana de contexto forense (KWIC) con la oración o cláusula completa que contiene la coincidencia. | El campo `contexto_oracion` entrega la oración completa delimitada por puntuación lógica. |
| RF-098 | El sistema debe soportar expansión semántica mediante diccionario de sinónimos canónicos para parámetros clave comunes. | Búsquedas como `total` recuperan automáticamente `importe`, `saldo`, `valor total` y `grand total`. |
| RF-099 | El sistema debe tipificar y normalizar valores extraídos de monedas, fechas y números de identificación. | Se genera el sub-objeto `valor_normalizado` con tipos (`currency`, `date`, `tax_id`, `percentage`) estructurados para integración. |

---

## 5. Requisitos no funcionales

### 5.1 Rendimiento

| ID | Requisito | Meta / criterio |
|---|---|---|
| RNF-001 | El hit L0 debe evitar todas las etapas de extracción. | Objetivo de diseño: < 20 ms, sin considerar red de cliente. |
| RNF-002 | Una nueva búsqueda resuelta desde L1 debe evitar IA y render. | Objetivo de diseño: < 50 ms, sin considerar red de cliente. |
| RNF-003 | Un PDF digital de ~20 páginas con caché fría debe resolverse localmente si contiene texto utilizable. | Objetivo p95: < 150 ms más render HTML, sujeto a hardware. |
| RNF-004 | El sistema debe limitar CPU/RAM durante render. | Render workers configurable, valor inicial 2–4. |
| RNF-005 | El sistema debe limitar solicitudes IA en vuelo. | Semáforo configurable, valor inicial 4–8. |
| RNF-006 | El sistema no debe re-renderizar una página por retry de key. | Un WebP por página pendiente y job. |
| RNF-007 | El sistema no debe reabrir el PDF por cada página. | Una apertura lógica por job para clasificación. |

### 5.2 Disponibilidad y resiliencia

| ID | Requisito | Criterio verificable |
|---|---|---|
| RNF-010 | El sistema debe tolerar fallo aislado de página IA. | Devuelve resultado parcial y no error global cuando sea posible. |
| RNF-011 | El sistema debe tolerar una API key agotada. | Failover por página o parcial controlado. |
| RNF-012 | El sistema debe evitar que una excepción individual cancele el lote de tareas. | Gather/colección de resultados contiene manejo individual de fallos. |
| RNF-013 | El sistema debe manejar indisponibilidad temporal de Redis con política explícita. | Fallback controlado o error claro; nunca corrupción de respuesta. |
| RNF-014 | La caché no debe ser requisito para que el pipeline básico pueda procesar un PDF en modo degradado. | Si Redis falla, se puede procesar sin hits/escrituras según configuración. |
| RNF-015 | El sistema debe ofrecer fallback automático a caché in-memory (`InMemoryLRUCacheService`) si Redis no está disponible o está deshabilitado. | Se conmuta de forma transparente manteniendo el contrato `BaseCacheService` sin interrumpir el servicio. |

### 5.3 Seguridad y privacidad

| ID | Requisito | Criterio verificable |
|---|---|---|
| RNF-020 | Las API keys deben provenir de entorno o gestor de secretos. | No se encuentran hardcodeadas ni en repositorio. |
| RNF-021 | La aplicación no debe exponer secretos en HTML, logs o respuestas de error. | Pruebas de error no contienen patrones de secrets. |
| RNF-022 | El PDF original no debe persistirse por defecto tras procesar. | No existen archivos de upload permanentes en flujo MVP. |
| RNF-023 | Los resultados cacheados deben tener TTL configurable. | Redis expira o elimina registros conforme a política. |
| RNF-024 | La comunicación debe usar HTTPS en producción. | Configuración de despliegue fuerza/termina TLS. |
| RNF-025 | El sistema debe validar límites de entrada para reducir abuso y agotamiento de recursos. | Tamaño, páginas, timeout y concurrencia son configurables. |

### 5.4 Mantenibilidad y calidad

| ID | Requisito | Criterio verificable |
|---|---|---|
| RNF-030 | La lógica debe organizarse por responsabilidad. | HTTP, orquestación, caché, PDF, render, IA y keys están separados. |
| RNF-031 | `jobs.py` debe ser el único escritor de L0/L1/L2. | No hay escrituras de caché desde servicios de bajo nivel. |
| RNF-032 | Los contratos internos deben validarse con modelos tipados. | Entradas/salidas principales usan Pydantic o equivalente. |
| RNF-033 | Las versiones de dependencias deben fijarse. | `requirements.txt` contiene restricciones/versiones acordadas. |
| RNF-034 | Los cambios de arquitectura relevantes deben documentarse mediante ADR. | ADRs versionados en repositorio. |
| RNF-035 | El sistema debe contar con pruebas unitarias e integración para los caminos críticos. | Suite cubre caché, clasificación, retry y resultados parciales. |

### 5.5 Observabilidad

| ID | Requisito | Criterio verificable |
|---|---|---|
| RNF-040 | Los logs deben ser estructurados y correlacionables. | Incluyen `request_id` y metadatos operativos. |
| RNF-041 | Las métricas no deben incluir texto completo de documentos ni secretos. | Revisión de telemetría confirma datos mínimos. |
| RNF-042 | Deben poder medirse p50/p95/p99 de duración total y por fase. | Instrumentación diferencia caché, clasificación, render e IA. |
| RNF-043 | Debe poder alertarse sobre 429, tasa de fallo y todas las keys no saludables. | Métricas/eventos cubren estos estados. |

---

## 6. Reglas de validación

| ID | Regla | Acción esperada |
|---|---|---|
| RV-001 | Archivo ausente | Rechazar con mensaje de validación |
| RV-002 | Tipo distinto de PDF | Rechazar antes de extracción |
| RV-003 | Cabecera no compatible con PDF | Rechazar como archivo inválido |
| RV-004 | Tamaño excedido | Rechazar antes de pipeline |
| RV-005 | PDF corrupto o cifrado no soportado | Informar imposibilidad de procesamiento |
| RV-006 | Más páginas que el máximo | Rechazar o aplicar política configurada |
| RV-007 | Parámetros vacíos tras normalización | Rechazar y solicitar al menos uno |
| RV-008 | Redis no disponible | Conmutar a modo degradado in-memory sin interrumpir ejecución |
| RV-009 | Todas las keys inválidas o agotadas | Entregar páginas locales y marcar pendientes IA con error parcial |
| RV-010 | Respuesta IA no cumple schema | Marcar error de página; no persistir L1 inválida |
| RV-011 | Deadline global expirado | Cancelar solo pendientes seguras; consolidar parcial |

---

## 7. Restricciones técnicas de diseño

| ID | Restricción |
|---|---|
| RC-001 | FastAPI sirve la aplicación web y Jinja2 renderiza vistas SSR en el MVP. |
| RC-002 | PyMuPDF es el motor principal de extracción y render local en v1. |
| RC-003 | Pillow procesa/consolida imagen y WebP para páginas multimodales. |
| RC-004 | `google-genai` es el SDK previsto para el proveedor multimodal inicial. |
| RC-005 | Redis es la fuente de caché de producción para L0 y L1. |
| RC-006 | Batch API no se utiliza para el endpoint interactivo `/procesar`; está orientada a procesamiento asíncrono masivo. [web:31][web:32] |
| RC-007 | Context Cache se debe usar solo con API y campos verificados en la versión fijada del SDK. [web:16][web:18][web:24] |
| RC-008 | No se usa un diccionario local como única caché de producción, pero sí como fallback de resiliencia in-memory. |
| RC-009 | La concurrencia IA se controla antes de enviar solicitudes para reducir errores de cuota. [web:31] |
| RC-010 | `opencv-python-headless` y `numpy` constituyen la suite obligatoria para operaciones deterministas de visión (Deskew y Otsu). |

---

## 8. Trazabilidad inicial

| Artefacto | Relación |
|---|---|
| PRD | Define problema, alcance, usuarios y éxito del producto Pydective |
| Requisitos | Define comportamiento verificable del MVP |
| ADR-001 | Define arquitectura híbrida, caché y failover |
| ADR-002 | Define preprocesamiento determinista (Otsu, Deskew), catálogo de imágenes, chat documental y streaming SSE |
| ADR-003 | Define extracción semántica clave-valor, ventanas de contexto (KWIC) y normalización de entidades |
| Especificación arquitectónica general | Define módulos, flujos y contratos |
| Estrategia de pruebas | Debe mapear cada caso crítico a RF/RNF/RV |
| Historias de usuario | Deben referenciar requisitos aplicables |

---

## 9. Criterios de aceptación globales

El MVP cumple esta línea base si se verifica que:

- [ ] El sistema acepta un PDF válido y parámetros normalizados.
- [ ] El mismo PDF y misma consulta se resuelven desde L0 sin abrir el documento.
- [ ] El mismo PDF y nueva consulta se resuelven desde L1 sin IA, cuando la extracción existe.
- [ ] Un PDF digital se resuelve localmente sin generar imágenes innecesarias.
- [ ] Un PDF mixto envía exclusivamente las páginas `needs_ai` a IA.
- [ ] La IA devuelve o valida una estructura uniforme por página.
- [ ] Un 429 de una key provoca failover o error aislado, no reinicio del job.
- [ ] La respuesta conserva páginas exitosas, incluso ante errores parciales.
- [ ] Redis conserva las cachés después de reiniciar la aplicación.
- [ ] La respuesta no expone secretos ni detalles internos.
- [ ] Las métricas permiten saber si el resultado vino de L0, L1, procesamiento local o IA.
