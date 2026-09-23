# Épica 2: Clasificación y Preprocesamiento

> **Objetivo:** Categorizar de forma determinista y ultrarrápida cada página del documento en el carril correspondiente (`local`, `empty` o `needs_ai`), aplicando preprocesamiento de visión en C/OpenCV únicamente sobre páginas escaneadas o degradadas para maximizar la señal de texto.

---

### US-04: Clasificación Determinista en Cero-IA con PyMuPDF

- **ID:** `US-04`
- **Requisitos asociados:** `RF-030`, `RF-031`, `RF-032`, `RF-033`, `RF-034`, `RF-035`, `RNF-003`, `RNF-007`, `ADR-001`, `ADR-004`
- **Prioridad:** Crítica | **Estimación:** 5 pts

#### Narrativa
**Como** motor documental de alto rendimiento,  
**Quiero** clasificar cada página inspeccionando su texto vectorial nativo y recuento de palabras en C con PyMuPDF,  
**Para** resolver páginas digitales limpias en milisegundos (`LOCAL`) sin generar imágenes WebP ni invocar IA multimodal.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Página digital con texto nativo suficiente (Bypass de OpenCV e IA)**
   - **Dado** que una página contiene más de `OPENCV_BYPASS_WORD_THRESHOLD` (por defecto 80 palabras) de texto estructurado y elementos gráficos decorativos pequeños (<15% del área total),
   - **Cuando** se ejecuta `classifier.py`,
   - **Entonces** se marca como `tipo=TipoPagina.LOCAL`, se extrae el texto vectorial nativo y nunca se llama a OpenCV ni a Gemini para esa página.

2. **Escenario: Página vacía**
   - **Dado** una página en blanco o sin caracteres legibles ni imágenes vectoriales,
   - **Cuando** se analiza la página,
   - **Entonces** se marca como `tipo=TipoPagina.EMPTY` con duración < 5 ms, sin desencadenar inferencia IA.

3. **Escenario: Página digital sin coincidencias para la consulta**
   - **Dado** una página con texto digital nativo abundante pero donde ninguna de las palabras coincide con los parámetros solicitados,
   - **Cuando** concluye la Fase A,
   - **Entonces** la página se resuelve exitosamente como `LOCAL` con lista vacía de hallazgos (la ausencia de una keyword nunca forzará llamada a IA).

---

### US-05: Score Compuesto de Legibilidad Anti-Ruido

- **ID:** `US-05`
- **Requisitos asociados:** `RF-036`, `RNF-003`, `ADR-004 Sección 7`
- **Prioridad:** Alta | **Estimación:** 3 pts

#### Narrativa
**Como** arquitecto del motor de extracción,  
**Quiero** calcular un índice compuesto de legibilidad (`readability_score`),  
**Para** evitar que capas de OCR corruptas (con caracteres `\ufffd` o palabras de 50 caracteres pegadas sin espacios) se clasifiquen falsamente como texto local válido.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Detección de capa OCR corrupta y desvío a IA**
   - **Dado** una página con 120 palabras reportadas por PyMuPDF, pero con alta concentración de caracteres de reemplazo Unicode `\ufffd` (>5%) o longitud promedio anormal (>30 caracteres sin espacios),
   - **Cuando** se calcula el `readability_score`,
   - **Entonces** el score cae por debajo del umbral mínimo de legibilidad y la página se desvía forzosamente a `TipoPagina.NEEDS_AI` para ser leída por visión con Gemini.

2. **Escenario: Texto breve pero limpio**
   - **Dado** una página con 40 palabras (por debajo del umbral simple de 80) pero con sintaxis limpia, mayúsculas/minúsculas coherentes y sin caracteres de control,
   - **Cuando** se evalúa el score de legibilidad,
   - **Entonces** el sistema la reconoce como página estructurada limpia y la mantiene en el carril `LOCAL`.

---

### US-06: Preprocesamiento Determinista con OpenCV (Deskew y Otsu)

- **ID:** `US-06`
- **Requisitos asociados:** `RF-090`, `RF-091`, `ADR-002`, `ADR-004 Sección 8`
- **Prioridad:** Media | **Estimación:** 5 pts

#### Narrativa
**Como** componente de preprocesamiento visual,  
**Quiero** enderezar páginas escaneadas inclinadas (Deskew) y optimizar el contraste de imágenes de baja calidad (Otsu),  
**Para** entregar a Gemini una imagen de alta relación señal/ruido que maximice la precisión de extracción y reduzca alucinaciones.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Deskew sobre miniatura acotado a $\pm 15^\circ$**
   - **Dado** una página escaneada marcada como `needs_ai` con una inclinación física de $8.5^\circ$,
   - **Cuando** `preprocess_service.py` ejecuta la transformada de Hough o detección de líneas sobre una miniatura reducida a 500 px,
   - **Entonces** detecta el ángulo dominante en < 30 ms y rota la imagen en sentido inverso, limitando la corrección al rango de $[-15^\circ, +15^\circ]$.

2. **Escenario: Binarización adaptativa de Otsu selectiva**
   - **Dado** una página con sombras o fondo grisáceo que dificulta la lectura visual,
   - **Cuando** la varianza del histograma de grises indica bajo contraste,
   - **Entonces** se aplica la binarización de Otsu preservando el trazo del texto sobre fondo blanco.

3. **Escenario: Trazabilidad determinista (Preprocesamiento ≠ OCR)**
   - **Dado** que OpenCV limpia y endereza una página escaneada,
   - **Cuando** se registra el resultado de la página,
   - **Entonces** se marca `preprocesado=True` pero `textually_resolved=False`, garantizando que la página continúe hacia la Fase B para su transcripción multimodal.
