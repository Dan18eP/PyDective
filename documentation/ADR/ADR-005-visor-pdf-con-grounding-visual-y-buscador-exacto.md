# ADR-005: Visor de PDF interactivo con buscador de texto exacto tipo Chrome, grounding visual bidireccional y eliminación total de mocks

- **Estado:** Aceptado
- **Fecha:** 2026-09-23
- **Decisores:** Equipo de Arquitectura e Ingeniería Pydective
- **Extiende a:** [ADR-001](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/documentation/ADR/ADR-001-arquitectura-hibrida-caching-y-failover.md), [ADR-002](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/documentation/ADR/ADR-002-preprocesamiento-determinista-vision-y-chat-documental.md), [ADR-003](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/documentation/ADR/ADR-003-extraccion-semantica-clave-valor-y-enriquecimiento.md) y [ADR-004](file:///c:/Users/LENOVO/Documents/DANI%20DOCS/RIWI/IA%20FOR%20DEVS/PyDective/documentation/ADR/ADR-004-optimizacion-rendimiento-precision-y-reutilizacion-documental.md)
- **Relacionado con:** PRD, Requisitos del Sistema (RF-100 a RF-103) y Especificación Arquitectónica General
- **Etiquetas:** pydective, visor-pdf, pdfjs, buscador-chrome, bounding-boxes, visual-grounding, cero-mocks, trazabilidad-100

---

## 1. Contexto

Hasta la versión 2.2, Pydective extrae información textual y visual, cataloga sellos y firmas, y responde preguntas mediante un chat fundamentado en el índice L1. Sin embargo, en la pantalla de dictamen (`resultados.html`), el usuario ve tablas y textos extraídos pero **no visualiza el documento PDF original en su contexto espacial**, lo que genera dos limitaciones operativas críticas:

1. **Falta de inspección directa del PDF:** El usuario necesita verificar con sus propios ojos el formato original del documento (factura, contrato, escritura o informe técnico) en paralelo con los hallazgos y el chat.
2. **Ausencia de un buscador visual interactivo:** Al buscar términos concretos, el usuario espera una experiencia idéntica a la del visor de PDFs de Google Chrome (`Ctrl+F`): navegación rápida entre ocurrencias ($N$ de $M$), resaltado simultáneo en amarillo de todas las coincidencias y resaltado en naranja de la coincidencia activa con desplazamiento automático (*auto-scroll*).
3. **Pérdida del puente visual entre respuesta y documento (*Visual Grounding*):** Cuando el asistente conversacional o la tabla de hallazgos cita `[Página 4]`, el usuario debe buscar manualmente el párrafo, sello o firma en cuestión.
4. **Mandato de Cero Mocks (*100% Real Production Execution*):** Para certificar la viabilidad del aplicativo, no debe existir ningún dato simulado, ficticio o hardcodeado. Todas las coordenadas, textos, recuadros y descripciones deben provenir directamente del binario del PDF analizado mediante PyMuPDF y Gemini multimodal.

---

## 2. Decisión

Implementar un **Visor de PDF Interactivo Integrado en la Vista de Resultados**, complementado con un **Buscador de Coincidencias Exactas estilo Chrome** y un motor de **Visual Grounding Bidireccional** gobernado por las siguientes definiciones arquitectónicas:

### 2.1 Arquitectura del Visor en Layout Split-View

La vista `resultados.html` se rediseña como un espacio de trabajo forense de dos columnas (*Split-View* interactivo):
- **Panel Izquierdo (Visor de PDF):** Contenedor interactivo alimentado por `PDF.js` que renderiza las páginas en canvas con capas de texto y anotaciones (*Highlight Layer*). Incluye barra de controles (Página anterior/siguiente, selector de página, zoom dinámico y ajuste de ancho).
- **Panel Derecho (Pydective Chat + Hallazgos):** Panel conversacional en la parte superior y tabla de hallazgos enriquecidos en la parte inferior, sincronizados bidireccionalmente con el visor.
- **Servicio seguro del binario PDF:** Endpoint backend `GET /documentos/{pdf_hash}/raw` que sirve el archivo PDF con tipo MIME `application/pdf` y cabeceras de caché eficientes, recuperándolo desde el almacenamiento persistente (`data/uploads/{pdf_hash}.pdf`).

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Resultados Forenses                             │
├───────────────────────────────────┬────────────────────────────────────┤
│           VISOR DE PDF            │          PYDECTIVE CHAT            │
│  ┌─────────────────────────────┐  │  ┌──────────────────────────────┐  │
│  │ [🔍 Buscador Chrome: 3 de 12]│  │  │ User: ¿Tiene código de barra?│  │
│  ├─────────────────────────────┤  │  │ Pydective: Sí, en [Pág 7] 👈  │  │
│  │                             │  │  └──────────────────────────────┘  │
│  │   [Página 7 del PDF]        │  ├────────────────────────────────────┤
│  │                             │  │       HALLAZGOS ENRIQUECIDOS       │
│  │    ┌──────────────────┐     │  │  ┌──────┬──────────┬───────────┐  │
│  │    │ 🔲 Highlight Box │     │  │  │Total │$ 3.250.00│[Pág 1] 👈 │  │
│  │    │  (Código Barras) │     │  │  └──────┴──────────┴───────────┘  │
│  │    └──────────────────┘     │  │                                    │
│  └─────────────────────────────┘  └────────────────────────────────────┘
└────────────────────────────────────────────────────────────────────────┘
```

---

### 2.2 Buscador de Coincidencias Exactas (Experiencia Chrome PDF)

El buscador del visor emula con fidelidad el comportamiento nativo del buscador de Chrome:

1. **Endpoint Backend de Coordenadas (`GET /documentos/{pdf_hash}/search?q=...`):**
   - Utiliza `page.search_for(query, quads=False)` de PyMuPDF en el servidor.
   - Retorna una lista estructurada de todas las instancias encontradas en el PDF con sus coordenadas exactas en puntos tipográficos (`[x0, y0, x1, y1]`), número de página y texto del contexto inmediato.
2. **Interfaz de Búsqueda Flotante en el Visor:**
   - Campo de entrada de texto reactivo con evento *debounce*.
   - Contador dinámico de coincidencias: `$N$ de $M$` (ej: `1 de 8`).
   - Botones de navegación: `Anterior (<)` y `Siguiente (>)`.
   - Atajos de teclado universales: `Enter` para avanzar a la siguiente coincidencia, `Shift+Enter` para retroceder, y `Esc` para limpiar.
3. **Resaltado y Auto-Scroll:**
   - **Todas las coincidencias pasivas:** Se colorean con un recuadro amarillo semitransparente (`rgba(255, 235, 59, 0.4)`).
   - **Coincidencia activa actual:** Se destaca en color naranja/ámbar brillante (`rgba(255, 152, 0, 0.7)`) con borde acentuado.
   - El visor ejecuta un desplazamiento suave (*smooth scroll*) para centrar la coincidencia activa en el campo visual del usuario.

---

### 2.3 Visual Grounding 100% Confiable para Preguntas y Hallazgos

Para garantizar una trazabilidad inmutable sin margen de error ni alucinación:

1. **Vínculo Cita $\rightarrow$ Visor:**
   - Cada respuesta del chat y cada fila de la tabla de hallazgos contiene citas y badges con atributos de datos: `data-page="X"` y `data-bbox="[x0, y0, x1, y1]"`.
2. **Interacción con un solo clic:**
   - Al hacer clic en un chip de cita (ej. `[Página 7 - Código de Barras]` o `[Página 1 - Total Factura]`), el visor:
     1. Salta inmediatamente a la página indicada.
     2. Dibuja una capa de resaltado forense (*Forensic Highlight Box*) con borde verde/cian brillante pulsante sobre las coordenadas `[x0, y0, x1, y1]` de la evidencia.
     3. Muestra una etiqueta flotante temporal (*tooltip*) indicando el concepto (ej. *"Firma del Representante Legal"* o *"Monto Total"*).
3. **Soporte Universal de Tipos de Evidencia:**
   - Funciona idénticamente para:
     - **Texto:** Líneas de contrato, montos, fechas, NITs y cláusulas.
     - **Imágenes y Gráficos:** Códigos de barras, códigos QR, firmas manuscritas, sellos notariales circulares, diagramas de arquitectura y logotipos.

---

### 2.4 Cero Datos Mock y Validación Forense Robusta

Se elimina categóricamente cualquier simulación o dato estático:
1. El archivo `documento_completo_20_paginas.pdf` y cualquier PDF cargado por el usuario se analizan de punta a punta con el pipeline real de PyDective.
2. Todas las coordenadas de evidencias provienen directamente de los diccionarios de PyMuPDF (`page.get_text("words")`, `page.get_images()`, `page.search_for()`) o de la detección multimodal.
3. Las respuestas de Pydective Chat se fundamentan exclusivamente en las evidencias persistidas en L1 (`Evidence.bbox`).

---

## 3. Consecuencias y Criterios de Aceptación

### Consecuencias Positivas:
1. **Auditoría visual instantánea:** El usuario valida en menos de 2 segundos si el número, firma o sello extraído corresponde con la realidad física del documento.
2. **Experiencia de usuario familiar:** El buscador de texto reproduce el estándar de Chrome, reduciendo la curva de aprendizaje a cero.
3. **Confiabilidad total (100% Truthfulness):** Cero dependencia de datos mock; cada recuadro dibujado en pantalla responde a coordenadas matemáticas reales del archivo PDF.

### Criterios de Aceptación:
- [ ] `GET /documentos/{pdf_hash}/raw` entrega el archivo PDF binario correctamente para su consumo por `PDF.js`.
- [ ] El buscador integrado resalta todas las ocurrencias en amarillo y la activa en naranja, indicando `$N$ de $M$`.
- [ ] Al pulsar `Enter` en el buscador, el visor navega hacia la siguiente coincidencia con desplazamiento automático.
- [ ] Al hacer clic en una cita del chat o en una evidencia de la tabla, el visor salta a la página y resalta el recuadro exacto (texto, sello, firma o código de barras).
- [ ] La validación automatizada sobre `documento_completo_20_paginas.pdf` verifica que las búsquedas de términos y la ubicación de imágenes coincidan con las coordenadas del documento real.
