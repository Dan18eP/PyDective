# ADR-002: Preprocesamiento determinista (Otsu y Deskew), catalogación de imágenes, chat documental interactivo y resiliencia operativa

- **Estado:** Aceptado (Complementado por [ADR-003](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/docs/ADR/ADR-003-extraccion-semantica-clave-valor-y-enriquecimiento.md))
- **Fecha:** 2026-09-23
- **Decisores:** Equipo de Arquitectura e Ingeniería Pydective
- **Extiende a:** [ADR-001: Arquitectura híbrida de extracción, caché escalonada y failover por página](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/docs/ADR/ADR-001-arquitectura-hibrida-caching-y-failover.md)
- **Etiquetas:** pydective, visión-por-computadora, otsu, deskew, determinismo, catalogo-imagenes, chat-documental, sse, resiliencia, clave-valor

---

## 1. Contexto y Nuevos Requerimientos

Tras la definición de la arquitectura base en ADR-001, la dirección del proyecto ha establecido cuatro requerimientos técnicos y de negocio fundamentales para **Pydective**:

1. **Determinismo antes de IA directa:**  
   Para páginas escaneadas o con baja calidad de captura, no se debe delegar ciegamente a modelos de lenguaje multimodal la totalidad del trabajo sin antes aplicar técnicas deterministas de visión por computadora. Los documentos escaneados a menudo presentan inclinación (*skew*), manchas, sombras y contrastes deficientes que incrementan el consumo de tokens y el riesgo de alucinación o lectura errónea de caracteres.
2. **Identificación y catalogación de imágenes por página:**  
   El sistema no debe limitarse a extraer texto y buscar palabras clave; debe inventariar y catalogar explícitamente todas las imágenes y elementos gráficos presentes en el documento, indicando con precisión:
   - En qué número de página se encuentra cada imagen.
   - Su tipología y contenido semántico (sellos oficiales, firmas manuscritas, logotipos corporativos, diagramas, esquemas, fotografías o tablas rasterizadas).
3. **Módulo conversacional con el documento ("Pydective Chat"):**  
   En consonancia con la identidad del producto (*Pydective*, el detective inteligente de documentos), los usuarios deben poder no solo parametrizar palabras clave (ej. `factura, total, fecha, NIT`), sino también **conversar interactivamente con el PDF** para realizar preguntas complejas y deducciones basadas en las pistas del documento, recibiendo respuestas con citas y trazabilidad directa por página.
4. **Mitigación de riesgos operativos identificados:**  
   - Prevención de timeouts de conexión en navegadores durante el procesamiento de PDFs 100% escaneados.
   - Desacoplamiento de Redis mediante modo degradado in-memory.
   - Control de saturación de cuota en proyectos Gemini.

---

## 2. Decisiones Arquitectónicas

### 2.1 Visión por Computadora Determinista: Deskew y Binarización Otsu Optimizados

Se establece como regla obligatoria de arquitectura: **Determinismo antes de IA**.

Para evitar penalizaciones innecesarias de CPU, se aplican las siguientes reglas de diseño en `vision_service.py` con `opencv-python-headless`:

1. **Bypass configurable en páginas digitales limpias:** 
   - El umbral de legibilidad se gobierna mediante la variable de entorno configurable `OPENCV_BYPASS_WORD_THRESHOLD` (valor predeterminado: 80 palabras).
   - Si la Fase A extrae una cantidad de palabras legibles $\ge \text{OPENCV\_BYPASS\_WORD\_THRESHOLD}$ con baja ratio de caracteres basura y sin requerimiento explícito de pistas visuales, **se omite completamente el procesamiento de OpenCV**, permitiendo su calibración dinámica con datasets reales sin alterar el código fuente.
2. **Deskew Selectivo y Acelerado:**
   - La búsqueda de ángulo de inclinación se acota estrictamente a un rango de **$\pm 15^\circ$** (un documento escaneado raramente supera los $10^\circ$; buscar a $90^\circ$ o $360^\circ$ multiplica por 6 el coste de CPU y arriesga rotar verticalmente texto horizontal).
   - El cálculo de la Transformada de Hough / momentos se realiza sobre una miniatura reducida a **500 px de ancho**; luego, el ángulo obtenido se aplica a la matriz de rotación de la imagen en alta resolución. Esto ahorra hasta un 75% del tiempo de CPU.
3. **Binarización de Otsu Adaptativa:**
   - Solo se aplica ante bajo contraste o detección de ruido de fondo.
   - Si la página limpia resultante permite extracción determinista con alta certeza, se resuelve localmente. Si contiene sellos, firmas o ambigüedad visual, pasa a Fase B optimizada.

```text
Página escaneada o con texto deficiente (needs_ai)
  │
  ▼
1. Estimación de Deskew (miniatura 500px, ángulo ∈ [-15°, +15°])
2. Rotación inversa de alineación
3. Binarización de Otsu (remoción de sombras y artefactos)
  │
  ▼
Evaluación de señal:
  ├── [Texto limpio resoluble] → Extracción determinista (0 costo IA)
  └── [Requiere OCR profundo / Sellos / Firmas] → Envío a Fase B (Gemini 2.0 Flash)
```

**Beneficios:**
- La imagen enviada al modelo multimodal en Fase B tiene un ratio señal/ruido drásticamente superior, reduciendo tokens de atención y errores de transcripción en un 30-50%.
- El preprocesamiento determinista añade menos de 25-40 ms de CPU gracias al cálculo en miniatura y rango acotado.

---

### 2.2 Subsistema de Catalogación de Elementos Visuales

Cada página analizada producirá un inventario estructurado de elementos visuales dentro del contrato de datos:

```json
{
  "pagina": 3,
  "exito": true,
  "origen": "ia",
  "imagenes_detectadas": [
    {
      "id_imagen": "img_p3_1",
      "tipo": "sello_oficial",
      "descripcion": "Sello circular de la Notaría Primera con fecha legible del 15 de marzo de 2024",
      "ubicacion_aproximada": "inferior_derecha"
    },
    {
      "id_imagen": "img_p3_2",
      "tipo": "firma_manuscrita",
      "descripcion": "Firma del representante legal sobre la línea de aceptación de contrato",
      "ubicacion_aproximada": "inferior_centro"
    },
    {
      "id_imagen": "img_p3_3",
      "tipo": "logotipo",
      "descripcion": "Logotipo corporativo de la empresa contratista",
      "ubicacion_aproximada": "superior_izquierda"
    }
  ]
}
```

- PyMuPDF inspecciona metadatos nativos (`page.get_images()`) para detectar la presencia física de objetos gráficos.
- Cuando la página contiene imágenes o es un escaneo completo, el prompt multimodal exige la catalogación tipificada (`sello_oficial`, `firma_manuscrita`, `logotipo`, `grafico_diagrama`, `fotografia`, `tabla_grafica`) y su descripción detallada.

---

### 2.3 Arquitectura del Chat Documental ("Pydective Q&A")

El chat conversacional opera como una extensión del conocimiento estructurado persistido en la caché:

```text
Usuario envía pregunta: "¿Quién aprobó el desembolso y en qué fecha?"
  │
  ▼
POST /chat/{pdf_hash}
  │
  ▼
jobs.py / chat_service.py recupera:
  ├─ Caché L1 (Redis): Texto estructurado, parámetros y catálogo de imágenes de TODAS las páginas.
  └─ Puntero L2 (Google Context Cache): Si el documento requirió análisis visual y L2 está activo.
  │
  ▼
Gemini Chat Engine (Prompt de Detective Documental con Grounding Estricto):
  - Rol: "Pydective", asistente forense y detective de documentos.
  - Regla: Toda afirmación debe citar explícitamente [Página X].
  - Si un dato no existe en el documento, debe declarar explícitamente su ausencia sin alucinar.
  - Configuración de Latencia: thinking_budget=0 (sin espera de CoT) y temperature=0.0.
  - Streaming de Respuesta: Emite tokens en streaming para lograr un Time-To-First-Token (TTFT) <600 ms.
  │
  ▼
Respuesta estructurada al usuario:
  - Explicación en lenguaje natural.
  - Lista de referencias/páginas citadas.
  - Pistas visuales asociadas (si la respuesta involucra una firma o sello de la página citada).
```

**Eficiencia:** No se vuelve a subir ni a transferir el archivo binario del PDF. El chat consume el conocimiento ya indexado en L1 o la sesión L2 existente.

---

### 2.4 Mitigación de Riesgos Operativos

#### A. Timeout en Navegadores y Arquitectura Unificada de Streaming (SSE)
- Para evitar duplicación de lógica y condiciones de carrera, el orquestador principal (`jobs.process_pdf()`) se diseña como un **generador asíncrono (`AsyncGenerator`)** que emite eventos atómicos (`JobEvent`).
- **Endpoint SSE:** `GET /procesar/stream?session_id=...` retransmite los eventos en vivo mediante Server-Sent Events:
  - `event: page_completed` con el estado y hallazgos de cada página a medida que finaliza en paralelo.
  - `event: job_completed` con la consolidación final y escritura de caché L0/L1.
- **Endpoint Sincrónico:** `POST /procesar` consume internamente el mismo generador hasta agotar los eventos y renderiza `resultados.html` para clientes estándar.

#### B. Desacoplamiento y Modo Degradado de Redis
- Se implementa una interfaz abstracta `BaseCacheService`.
- Se dispone de dos implementaciones:
  1. `RedisCacheService` (producción por defecto con serialización `orjson`).
  2. `InMemoryLRUCacheService` (fallback automático si `REDIS_ENABLED=false` o si Redis no responde en el arranque, acotado con límite LRU de 100 documentos para prevenir saturación de RAM).
- El sistema nunca aborta la inicialización si Redis está caído; entra en modo degradado informando en logs estructurados.

#### C. Control de Cuota Multiproducto en Gemini
- La configuración de `key_pool.py` agrupa las claves por `(project_id, api_key)`.
- El semáforo de concurrencia se asigna a nivel de `project_id`, impidiendo que múltiples claves del mismo proyecto lancen más de $N$ peticiones en vuelo que sobrepasen el RPM contratado.

---

## 3. Consecuencias y Criterios de Aceptación

### Consecuencias Positivas:
1. Mayor fidelidad en la extracción de texto escaneado gracias a Otsu y corrección de inclinación.
2. Identificación forense de firmas, sellos y logos con su ubicación por página.
3. Capacidad de interacción conversacional profunda sin costo de reprocesamiento.
4. Experiencia de usuario en tiempo real sin pantallas congeladas ni caídas por timeout.
5. Tolerancia total a entornos sin Redis para despliegue local o CI/CD.

### Dependencias Nuevas:
- `opencv-python-headless` (para Deskew y Otsu de alta velocidad en C++).
- `numpy` (para manipulación eficiente de matrices de imagen).

### Criterios de Aceptación del ADR-002:
- [ ] Todo PDF escaneado con inclinación es enderezado antes de evaluación de texto.
- [ ] La binarización de Otsu se aplica a páginas con bajo contraste o fondos ruidosos.
- [ ] Las imágenes detectadas incluyen número de página, tipo y descripción semántica.
- [ ] El endpoint `/chat/{pdf_hash}` responde preguntas usando el contexto L1 sin reenviar el archivo PDF original.
- [ ] Las respuestas del chat citan obligatoriamente la página de origen de cada dato.
- [ ] Si Redis no está disponible, la aplicación inicia y procesa usando la caché in-memory.
