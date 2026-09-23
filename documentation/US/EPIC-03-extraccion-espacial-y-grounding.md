# Épica 3: Extracción Espacial y Grounding

> **Objetivo:** Extraer pares clave-valor y entidades dinámicas asociadas a cualquier parámetro mediante geometría espacial en Cero-IA ($O(N)$), sustentando cada afirmación en evidencias trazables con identificador único (`evidence_id`) y métrica determinista (`evidence_score`).

---

### US-07: Extracción Espacial Clave-Valor Geométrica $O(N)$

- **ID:** `US-07`
- **Requisitos asociados:** `RF-096`, `RNF-003`, `ADR-003 Sección 2.2`
- **Prioridad:** Crítica | **Estimación:** 5 pts

#### Narrativa
**Como** motor de extracción semántica,  
**Quiero** localizar las palabras clave y explorar su vecindad espacial hacia la derecha y hacia abajo en una sola pasada $O(N)$ sobre `page.get_text("words")`,  
**Para** asociar de forma determinista el valor o cláusula correspondiente a cada parámetro sin invocar modelos pesados de lenguaje.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Extracción en vector horizontal derecho**
   - **Dado** una página digital donde la etiqueta `"Total a pagar:"` se ubica en el rectángulo `[120, 300, 200, 320]`,
   - **Cuando** el algoritmo busca tokens a la derecha sobre la misma línea ($|\Delta y| \le 8\text{ pt}$ y $\Delta x \le 180\text{ pt}$),
   - **Entonces** captura exitosamente el valor `"$ 9.579.500 COP"` ubicado en `[210, 300, 320, 320]`.

2. **Escenario: Extracción en vector vertical descendente (Formularios y Tablas)**
   - **Dado** un campo de formulario donde la etiqueta `"DIRECCIÓN DEL INMUEBLE"` tiene su valor debajo,
   - **Cuando** no hay contenido a la derecha pero existe texto debajo con solapamiento horizontal $\ge 60\%$ y distancia vertical $\le 35\text{ pt}$,
   - **Entonces** asocia el texto de la línea inferior como el valor del parámetro.

3. **Escenario: Tolerancia a kerning apretado (Sin límite rígido de palabra `\\b`)**
   - **Dado** un PDF generado con fuentes incrustadas donde los caracteres presentan kerning apretado (ej: `"Total:1200"` o `"NIT:900123"` sin espacio),
   - **Cuando** la expresión regular con límite de palabra estricto falla,
   - **Entonces** el motor activa automáticamente el fallback por subcadena insensible a mayúsculas (`casefold`), extrayendo el valor sin pérdida de datos.

---

### US-08: Grounding Fuerte con `Evidence` e Identidad Única

- **ID:** `US-08`
- **Requisitos asociados:** `RF-071`, `RF-072`, `RF-076`, `ADR-004 Sección 11 y 18`
- **Prioridad:** Alta | **Estimación:** 3 pts

#### Narrativa
**Como** auditor o usuario que requiere trazabilidad forense,  
**Quiero** que cada hallazgo extraído conserve una evidencia estructurada con identificador único (`evidence_id`), número de página, coordenadas exactas (`bbox`) y fuente de procedencia,  
**Para** poder auditar visualmente en el PDF la procedencia exacta de cada dato y descartar cualquier alucinación.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Generación de Evidence estructurada**
   - **Dado** un valor extraído en la página 7,
   - **Cuando** se construye el objeto `Evidence`,
   - **Entonces** se le asigna `evidence_id="ev_p7_004"`, `page=7`, `source=MetodoExtraccion.NATIVE_TEXT` y el `bbox=[x0, y0, x1, y1]` en puntos tipográficos de PyMuPDF.

2. **Escenario: Cálculo del `evidence_score` determinista**
   - **Dado** un hallazgo extraído mediante vecindad espacial de texto vectorial nativo a 45 pt de distancia y con validación regex exitosa,
   - **Cuando** se calcula la métrica de confianza:
     $$\text{evidence\_score} = \text{base\_score} \times (1 - \text{penalización\_distancia}) \times \text{score\_regex}$$
   - **Entonces** produce un score numérico determinista acotado entre $0.50$ y $1.00$ (e.g. $0.94$), evitando promesas estadísticas inventadas sin fundamento empírico.

---

### US-09: Normalización de Entidades Tipificadas

- **ID:** `US-09`
- **Requisitos asociados:** `RF-099`, `ADR-003 Sección 2.4`
- **Prioridad:** Media | **Estimación:** 3 pts

#### Narrativa
**Como** sistema integrador o consumidor de la API,  
**Quiero** que las fechas, monedas y números de identificación extraídos se transformen a un formato canónico estructurado,  
**Para** poder almacenarlos en bases de datos o sistemas contables sin tener que implementar parsers ad-hoc.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Normalización de monedas hispanas y estadounidenses**
   - **Dado** valores como `"$ 12.500.000,50 COP"`, `"USD 4,500.00"` o `"$3.200.000"`,
   - **Cuando** se procesa la normalización,
   - **Entonces** se detecta el separador decimal/miles y se emite `valor_normalizado="12500000.50"` con metadato de moneda `COP`.

2. **Escenario: Normalización de fechas mixtas**
   - **Dado** fechas en formatos `"15/04/2026"`, `"2026-04-15"` o `"22 de mayo de 2026"`,
   - **Cuando** se ejecuta el parser de fechas de `semantic_extraction_service.py`,
   - **Entonces** se normalizan de forma consistente al estándar ISO-8601 (`"2026-04-15"` y `"2026-05-22"`).

---

### US-10: Ventana Forense de Contexto (KWIC) y Resolución de Conflictos

- **ID:** `US-10`
- **Requisitos asociados:** `RF-097`, `ADR-003 Sección 2.3 y 2.6`
- **Prioridad:** Media | **Estimación:** 3 pts

#### Narrativa
**Como** analista legal o financiero,  
**Quiero** disponer de la oración completa donde se encontró la coincidencia (KWIC) y contar con una regla clara de precedencia entre el texto determinista y la IA,  
**Para** entender el sentido jurídico/financiero de la cláusula y asegurar que el texto vectorial nativo nunca sea sobrescrito por alucinaciones del modelo.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Generación de contexto KWIC**
   - **Dado** que se detectó el parámetro `"clausula penal"` en la página 3 de un contrato,
   - **Cuando** se extrae el hallazgo,
   - **Entonces** se incluye la oración completa delimitada por puntos lógicos: `"En caso de incumplimiento... la suma de TREINTA Y SIETE MILLONES QUINIENTOS MIL PESOS ($ 37.500.000 COP)..."`.

2. **Escenario: Precedencia absoluta del texto vectorial nativo**
   - **Dado** que en una página digital Fase 2 (espacial) extrae `"Total: $4.850.000"` y Gemini Fase 3 interpretó erróneamente `"$4.850.00"`,
   - **Cuando** se ejecuta la consolidación de hallazgos,
   - **Entonces** prevalece de forma estricta e inmutable el dato determinista de PyMuPDF, catalogando la respuesta de IA como redundante.
