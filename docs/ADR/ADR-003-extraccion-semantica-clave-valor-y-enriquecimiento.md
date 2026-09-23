# ADR-003: Extracción semántica clave-valor, ventanas de contexto y enriquecimiento de hallazgos

- **Estado:** Aceptado
- **Fecha:** 2026-09-23
- **Decisores:** Equipo de Arquitectura e Ingeniería Pydective
- **Extiende a:** [ADR-001](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/docs/ADR/ADR-001-arquitectura-hibrida-caching-y-failover.md) y [ADR-002](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/docs/ADR/ADR-002-preprocesamiento-determinista-vision-y-chat-documental.md)
- **Etiquetas:** pydective, busqueda-semantica, clave-valor, ner, normalizacion, kwic, contexto-forense, grounding

---

## 1. Contexto

En las versiones previas de la arquitectura, la búsqueda por parámetros (ej. `factura, total, fecha, NIT`) operaba predominantemente como un conteo y localización léxica de coincidencias dentro del texto extraído de cada página.

Sin embargo, para usuarios operativos reales (analistas contables, jurídicos y auditores), saber que *"la palabra 'total' aparece 3 veces en la página 2"* resulta insuficiente y frustrante. En flujos de negocio, el usuario busca una etiqueta porque **desea conocer el valor o entidad asociada a dicha etiqueta**:
- Si busca `total`, necesita el monto económico (`$4.580.000 COP`).
- Si busca `NIT`, necesita el código de identificación tributaria (`900.123.456-7`).
- Si busca `fecha`, necesita la fecha estandarizada de emisión o vencimiento (`2024-04-30`).
- Si busca `penalidad` o `vigencia`, necesita el fragmento o cláusula completa que estipula las condiciones, no solo la mención aislada de la palabra.
- Si el documento utiliza sinónimos como `Importe a pagar`, `Saldo neto` o `Grand Total`, una búsqueda estrictamente literal arroja un falso negativo (0 resultados).

Se requiere evolucionar el motor de búsqueda de Pydective hacia un sistema de **extracción semántica enriquecida** que combine alta velocidad, rigor determinista y comprensión contextual.

---

## 2. Decisión

Adoptar un pipeline de **Extracción Clave-Valor Enriquecida, Ventana de Contexto (KWIC) y Normalización de Entidades**, gobernado por las siguientes definiciones arquitectónicas:

### 2.1 Pipeline de Dos Etapas: Determinismo Espacial + Asistencia Semántica

El sistema implementará un enfoque escalonado para extraer el valor asociado a cada parámetro:

```text
Parámetro solicitado (ej. "total")
  │
  ▼
Etapa 1: Expansión de Sinónimos e Intención
  - Diccionario canónico de alias: "total" → ["total", "total a pagar", "importe", "saldo", "valor total", "grand total"]
  │
  ▼
Etapa 2: Análisis Determinista Espacial (PyMuPDF en C)
  - Detección de Bounding Boxes de las palabras clave candidatas.
  - Evaluación de vecindad geométrica:
    * Vector horizontal derecho (misma línea de texto, distancia ≤ umbral).
    * Vector vertical inferior (misma columna o celda de tabla adyacente).
  - Aplicación de expresiones regulares de extracción de entidades (monedas, fechas, NITs, porcentajes).
  │
  ├── [Éxito local con alta certeza] → Asignación clave-valor determinista (0 costo IA, <5 ms).
  └── [Incertidumbre / Layout complejo / Escaneo] → Delegación a Etapa 3.
  │
  ▼
Etapa 3: Extracción Semántica Asistida (Fase B / Gemini Estructurado)
  - En páginas `needs_ai` o donde la relación espacial sea ambigua, el prompt multimodal extrae parejas (clave, valor) asociadas explícitamente en el JSON Schema de la página.
```

---

### 2.2 Ventana de Contexto Forense (KWIC)

Cada hallazgo no se presentará como una palabra suelta, sino acompañado de su **oración o cláusula contextual completa** (Key Word in Context):
- Se extrae la oración delimitada por signos de puntuación (`.` `\n` `;`) que contiene la coincidencia.
- Si se trata de una cláusula contractual o viñeta de tabla, se preserva el bloque lógico completo (ej. *"Cláusula 4.1: El plazo de vigencia del presente contrato será de doce (12) meses contados a partir de la firma"*).

---

### 2.3 Tipificación y Normalización de Datos

Cada valor extraído se entrega en dos formatos:
1. **Representación textual cruda:** tal como aparece en el documento (ej. `$ 14.500.000,00`).
2. **Objeto normalizado estructurado:** tipificado para consumo programático por APIs o sistemas ERP:
   - `currency`: `{ "monto": 14500000.00, "moneda": "COP" }`
   - `date`: `{ "fecha_iso": "2024-04-30", "tipo": "vencimiento" }`
   - `tax_id`: `{ "numero": "900123456", "digito_verificacion": "7", "pais": "CO" }`
   - `percentage`: `{ "valor": 1.5, "base": "mensual" }`

---

### 2.4 Vinculación con Evidencias Visuales (Visual Grounding)

Cuando una página contenga elementos del catálogo visual (sellos, firmas manuscritas, logos) detectados por el [ADR-002](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/docs/ADR/ADR-002-preprocesamiento-determinista-vision-y-chat-documental.md), el motor cruzará la posición de la clave-valor con la imagen más cercana en la misma página:
- Permite responder preguntas de auditoría como: *"¿El valor total está respaldado por firma en la misma página?"*.

---

### 2.5 Contrato de Dominio Enriquecido

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
