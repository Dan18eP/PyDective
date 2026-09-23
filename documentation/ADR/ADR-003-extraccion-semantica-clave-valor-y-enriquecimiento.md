# ADR-003: Extracción semántica clave-valor, ventanas de contexto y enriquecimiento de hallazgos

- **Estado:** Aceptado
- **Fecha:** 2026-09-23
- **Decisores:** Equipo de Arquitectura e Ingeniería Pydective
- **Extiende a:** [ADR-001](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/docs/ADR/ADR-001-arquitectura-hibrida-caching-y-failover.md) y [ADR-002](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/docs/ADR/ADR-002-preprocesamiento-determinista-vision-y-chat-documental.md)
- **Etiquetas:** pydective, busqueda-semantica, clave-valor, ner, normalizacion, kwic, contexto-forense, grounding

---

## 1. Contexto

En las versiones previas de la arquitectura, la búsqueda por parámetros (ej. `factura, total, fecha, NIT`) operaba predominantemente como un conteo y localización léxica de coincidencias dentro del texto extraído de cada página.

Sin embargo, para usuarios operativos reales (analistas contables, jurídicos, médicos y auditores en cualquier industria), saber que *"la palabra 'total' aparece 3 veces"* o *"la palabra 'arrendador' aparece en la página 1"* resulta insuficiente y frustrante. En flujos de negocio reales con cualquier tipo documental (contratos, pólizas, actas, expedientes o facturas), el usuario busca una etiqueta porque **desea conocer el valor, cláusula o entidad asociada a dicha etiqueta**:
- Si busca `total` o `importe`, necesita el monto económico (`$4.580.000 COP`).
- Si busca `arrendatario` o `representante legal`, necesita la entidad o nombre de la persona jurídica o natural.
- Si busca `NIT` o `cédula`, necesita el código de identificación tributaria o personal (`900.123.456-7`).
- Si busca `fecha`, `emisión` o `vencimiento`, necesita la fecha estandarizada (`2024-04-30`).
- Si busca `penalidad` o `vigencia`, necesita el fragmento o cláusula completa que estipula las condiciones, no solo la mención aislada de la palabra.
- Si el documento utiliza sinónimos como `Importe a pagar`, `Saldo neto` o `Grand Total`, o si hay variaciones de tildes (`resolución` vs `resolucion`), una búsqueda estrictamente literal arroja un falso negativo (0 resultados).

Se requiere evolucionar el motor de búsqueda de Pydective hacia un sistema de **extracción semántica enriquecida universal** que combine alta velocidad, rigor determinista y comprensión contextual para cualquier parámetro ingresado por el usuario.

---

## 2. Decisión

Adoptar un pipeline de **Extracción Clave-Valor Enriquecida, Ventana de Contexto (KWIC) y Normalización de Entidades**, gobernado por las siguientes definiciones arquitectónicas:

### 2.1 Normalización Lingüística, Tolerancia a Diacríticos (NFKD) y Fallback de Kerning Apretado

Toda comparación y búsqueda de parámetros debe ser inmune a diferencias de acentuación, mayúsculas y ligaduras tipográficas:
- **Descomposición canónica NFKD:** Mediante `unicodedata.normalize('NFKD', ...)`, términos como `"facturación"`, `"número"` o `"póliza"` coinciden de manera exacta con `"facturacion"`, `"numero"` o `"poliza"`.
- **Expansión de ligaduras:** Reemplazo determinista de caracteres especiales de fuentes PDF (`ﬁ` $\to$ `fi`, `ﬂ` $\to$ `fl`, `æ` $\to$ `ae`).
- **Estrategia de Búsqueda Escalonada (Evitar falsos negativos por kerning apretado):**
  1. *Paso 1 (Límites de palabra estrictos):* Coincidencia mediante límites de palabra regex (`r"\b" + kw + r"\b"`), evitando falsos positivos como `"IVA"` en `"PRIVADO"`.
  2. *Paso 2 (Fallback para palabras compuestas/fusionadas):* Si el Paso 1 arroja 0 resultados, se ejecuta un fallback de subcadena insensible (`casefold_substring`) y detección de CamelCase / separaciones numéricas para rescatar términos fusionados por software de maquetación (ej. `"TotalFactura"` o `"Subtotal100"`).

---

### 2.2 Pipeline de Dos Etapas: Determinismo Espacial $O(N)$ con Umbrales Métricos Concretos

El sistema implementará un enfoque escalonado para extraer el valor asociado a cualquier parámetro:

```text
Parámetro solicitado por el usuario (ej. "total", "arrendador", "vencimiento")
  │
  ▼
Etapa 1: Expansión de Sinónimos Canónicos (Opcional según catálogo base)
  - Diccionario canónico o tokenización directa del parámetro.
  │
  ▼
Etapa 2: Análisis Determinista Espacial O(N) con PyMuPDF
  - Extracción de palabras estructuradas con page.get_text("words"): (x0, y0, x1, y1, palabra, block_no, line_no, word_no).
  - Detección espacial gobernada por umbrales métricos fijos (en puntos PDF, 72 pt = 1 pulgada):
    * Vector horizontal derecho (misma línea):
      - Alineación vertical: |y0_clave - y0_valor| ≤ 4.0 pt
      - Distancia horizontal máxima: x0_valor - x1_clave ≤ 180.0 pt (o ≤ 0.30 × page_width)
    * Vector vertical inferior (tablas y formularios):
      - Distancia vertical máxima: y0_valor - y1_clave ≤ 35.0 pt (espaciado entre líneas estándar)
      - Solapamiento horizontal en X: overlap(x_clave, x_valor) ≥ 60%
  - Parser robusto de entidades y formatos:
    * Monedas: Soporte nativo para separadores hispanos ($ 4.500.000,00) y anglosajones ($4,500,000.00).
    * Fechas: DD/MM/YYYY, YYYY-MM-DD, o textuales ("30 de abril de 2024").
    * Identificaciones: NIT con dígito de verificación, cédulas, códigos alfanuméricos.
  │
  ├── [Éxito local con alta certeza] → Asignación clave-valor determinista (0 costo IA, <2 ms).
  └── [Incertidumbre / Layout complejo / Escaneo] → Delegación a Etapa 3.
  │
  ▼
Etapa 3: Extracción Semántica Asistida (Fase B / Gemini 2.0 Flash Estructurado)
  - En páginas needs_ai o escaneadas, el prompt multimodal extrae la pareja (clave, valor) guiado por el JSON Schema tipado.
```

---

### 2.3 Ventana de Contexto Forense (KWIC)

Cada hallazgo no se presentará como una palabra suelta, sino acompañado de su **oración o cláusula contextual completa** (Key Word in Context):
- Se extrae la oración delimitada por signos de puntuación (`.` `\n` `;`) que contiene la coincidencia.
- Si se trata de una cláusula contractual o viñeta de tabla, se preserva el bloque lógico completo (ej. *"Cláusula 4.1: El plazo de vigencia del presente contrato será de doce (12) meses contados a partir de la firma"*).

---

### 2.4 Tipificación y Normalización de Datos

Cada valor extraído se entrega en dos formatos:
1. **Representación textual cruda:** tal como aparece en el documento (ej. `$ 14.500.000,00`).
2. **Objeto normalizado estructurado:** tipificado para consumo programático por APIs o sistemas ERP:
   - `currency`: `{ "monto": 14500000.00, "moneda": "COP" }`
   - `date`: `{ "fecha_iso": "2024-04-30", "tipo": "vencimiento" }`
   - `tax_id`: `{ "numero": "900123456", "digito_verificacion": "7", "pais": "CO" }`
   - `percentage`: `{ "valor": 1.5, "base": "mensual" }`
   - `text`: Para nombres propios, cláusulas, descripciones o códigos alfanuméricos generales.

---

### 2.5 Vinculación con Evidencias Visuales (Visual Grounding)

Cuando una página contenga elementos del catálogo visual (sellos, firmas manuscritas, logos) detectados por el [ADR-002](file:///home/dypok/Projects/PyDective/documentation/ADR/ADR-002-preprocesamiento-determinista-vision-y-chat-documental.md), el motor cruzará la posición de la clave-valor con la imagen más cercana en la misma página:
- Permite responder preguntas de auditoría como: *"¿El valor total está respaldado por firma en la misma página?"*.

---

### 2.6 Regla de Autoridad y Resolución de Conflictos (Determinismo vs IA)

Cuando tanto la Fase 2 (espacial determinista) como la Fase 3 (Gemini multimodal) extraigan un valor para el mismo parámetro en una página:
1. **Autoridad del texto vectorial nativo:** Si la coincidencia proviene de texto digital nativo con alta certeza geométrica (distancia $\le$ umbrales y formato regex válido), **el dato determinista de PyMuPDF tiene precedencia absoluta**. Esto previene que alucinaciones visuales o artefactos de OCR del LLM alteren cifras o códigos literales exactos.
2. **Autoridad multimodal en páginas visuales:** Si la página es escaneada, tiene bajo contraste o la relación espacial local presentó ambigüedad de layout, **prevalece el valor de Gemini Fase 3**.
3. **Trazabilidad:** Cada resultado consigna `metodo_extraccion` (`espacial_determinista` | `multimodal_ia`) y su índice de `confianza` numérico.

---

### 2.7 Contrato de Dominio Enriquecido

Se define la estructura `HallazgoEnriquecido`:

```json
{
  "parametro_solicitado": "total",
  "termino_encontrado": "Total Factura",
  "valor_extraido": "$ 3.250.000 COP",
  "valor_normalizado": {
    "tipo": "currency",
    "monto": 3250000.0,
    "moneda": "COP"
  },
  "contexto_oracion": "El Total Factura a cancelar antes de la fecha límite es de $ 3.250.000 COP.",
  "confianza": 0.96,
  "metodo_extraccion": "espacial_determinista",
  "evidencia_visual_asociada": "firma_representante_p1"
}
```

---

## 3. Integración con la Caché L1 y el Chat Documental

- Toda la información enriquecida (clave, valor normalizado, contexto) se persiste dentro de la **Caché L1 en Redis**.
- Cuando el usuario utiliza **Pydective Chat** (`POST /chat/{pdf_hash}`), el asistente conversacional accede de inmediato a los valores normalizados sin tener que recalcular ni volver a consultar a la IA para preguntas como *"¿A cuánto asciende el total con IVA?"* o *"¿Cuándo vence la factura?"*.

---

## 4. Consecuencias y Criterios de Aceptación

### Consecuencias Positivas:
1. Valor de negocio inmediato: los usuarios obtienen datos concretos listos para digitar, auditar o integrar.
2. Tolerancia a sinónimos y variaciones lingüísticas en documentos reales.
3. Respaldo de auditoría gracias a las ventanas de contexto completas.
4. Mantenimiento del rendimiento: el 80% de las asociaciones clave-valor en PDFs digitales se resuelven en microsegundos mediante la vecindad espacial de PyMuPDF.

### Criterios de Aceptación:
- [ ] La búsqueda de `total` extrae el monto numérico asociado cuando está presente en la línea o tabla adyacente.
- [ ] Cada hallazgo incluye la oración completa en la que se encuentra la palabra clave.
- [ ] La búsqueda de términos comunes reconoce sinónimos canónicos preconfigurados.
- [ ] Los montos y fechas se normalizan a formatos estandarizados (`float`, `ISO 8601`).
- [ ] El chat de Pydective utiliza los valores extraídos en L1 para responder de forma inmediata.
