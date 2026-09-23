# Documento de Negocio
## Pydective: Motor Inteligente, Visión Forense y Detective Documental B2B

**Versión:** 2.0 — definición de negocio y producto  
**Estado:** propuesta de producto aprobada  
**Tipo de solución:** SaaS web B2B para extracción asistida, catalogación visual y chat interactivo sobre PDFs

---

## 1. Resumen ejecutivo

**Pydective** es una plataforma web inteligente de extracción asistida, catalogación visual forense y análisis conversacional de documentos PDF. Permite a empresas y equipos operativos (contabilidad, finanzas, jurídico, auditoría y operaciones) interrogar a sus documentos, extraer campos clave y auditar evidencias gráficas con rapidez absoluta, incluso ante escaneos de baja calidad, inclinados (*skewed*), manchados o con tipografía deteriorada.

El producto combina visión por computadora determinista (corrección de inclinación *Deskew* y binarización *Otsu*), extracción nativa de alta velocidad, catalogación de elementos gráficos (sellos, firmas manuscritas, logos) y un **módulo conversacional ("Pydective Chat")** que permite al usuario formular preguntas complejas en lenguaje natural y obtener respuestas fundamentadas con citas exactas por página.

La ventaja competitiva se concentra en cuatro atributos:

1. **Determinismo antes de IA directa:** Se corrigen las imperfecciones visuales (Deskew acotado + Otsu) con visión por computadora clásica, reduciendo el gasto innecesario de tokens de IA y disparando la precisión.
2. **Identificación forense de imágenes:** Cada firma manuscrita, sello oficial y logotipo queda catalogado con su número de página y descripción semántica.
3. **Interrogatorio conversacional (Pydective Chat):** No solo busca parámetros; permite conversar con el PDF para deducciones y análisis complejos fundamentados con citas obligatorias por página.
4. **Velocidad y economía unitaria:** Triple caché (L0/L1/L2) con serialización ultra-rápida en `orjson` que permite reconsultas instantáneas (<20 ms) y costos marginales mínimos.

---

## 2. Problema de mercado

Muchas organizaciones siguen trabajando con documentos PDF como formato principal para facturas, contratos, expedientes, informes técnicos, certificados, órdenes de compra, reportes operativos, documentos académicos y archivos históricos digitalizados.

El problema aparece cuando la información dentro de esos archivos no es fácilmente utilizable:

- El PDF es un escaneo y no contiene texto seleccionable.
- La calidad del escaneo es baja: sombras, manchas, inclinación, compresión o tipografía débil.
- La información clave está distribuida en muchas páginas.
- Hay logos, sellos, fotos, diagramas o imágenes que aportan contexto.
- El usuario necesita encontrar campos concretos, no leer el documento completo.
- Cada nueva búsqueda obliga a revisar el archivo otra vez.
- Las herramientas tradicionales son lentas, exigen trabajo manual o devuelven texto poco confiable.

El coste real no es solo técnico. Se traduce en tiempo operativo, errores humanos, demoras de atención, dificultad para auditar y pérdida de oportunidades de automatización.

---

## 3. Oportunidad

Existe una necesidad clara de convertir PDF no estructurado en información consultable, especialmente en organizaciones con alto volumen documental y procesos repetitivos.

La oportunidad no está en competir como un lector de PDF generalista. Está en resolver un trabajo específico:

> “Sube un documento, indica qué necesitas encontrar y recibe resultados estructurados por página, aunque el archivo esté sucio o sea visual.”

El producto puede entrar inicialmente como una herramienta de productividad para equipos operativos y crecer hacia integraciones con procesos empresariales, sistemas de gestión documental, CRMs, ERPs o flujos de validación.

---

## 4. Propuesta de valor

### Para el usuario final

- Encuentra datos importantes en segundos en lugar de leer manualmente páginas completas.
- Puede trabajar con PDFs digitales y escaneados desde una interfaz sencilla.
- Define parámetros de búsqueda adaptados a su tarea: nombres, fechas, montos, códigos, cláusulas, números de factura o términos técnicos.
- Cataloga e inspecciona sellos, firmas y logos con su página correspondiente.
- **Interroga al PDF mediante un chat interactivo** con citas obligatorias de página para resolver dudas específicas.
- Puede repetir búsquedas sobre el mismo documento con respuesta prácticamente inmediata (<20 ms en L0, <50 ms en L1).

### Para la organización

- Reduce tiempo de digitación, revisión y búsqueda documental.
- Disminuye errores derivados de la lectura manual.
- Acelera procesos de atención, validación, auditoría y clasificación.
- Permite estandarizar la extracción de campos relevantes.
- Crea una base para automatizaciones futuras sin reemplazar todos los sistemas existentes.

### Diferenciador central

La plataforma usa una lógica de procesamiento selectivo: el texto digital se resuelve de forma local y rápida; la IA se utiliza solo donde aporta valor, como escaneos ruidosos o contenido visual. Esto permite competir por velocidad, eficiencia de costo y capacidad de interpretar documentos imperfectos.

---

## 5. Cliente objetivo

### Segmento inicial: pymes y equipos operativos

Empresas o áreas que manejan PDFs con frecuencia, pero no tienen una solución avanzada de automatización documental.

Características:

- Alto uso de correo, carpetas compartidas y archivos PDF.
- Procesos con revisión manual repetitiva.
- Necesidad de encontrar datos puntuales rápidamente.
- Presupuesto moderado y preferencia por herramientas SaaS simples.
- Interés en pagar por ahorro de tiempo, no por infraestructura compleja.

### Segmentos prioritarios

| Segmento | Documentos frecuentes | Caso de uso |
|---|---|---|
| Contabilidad y finanzas | Facturas, recibos, órdenes de compra | Buscar montos, fechas, NIT, proveedores y referencias |
| Jurídico y cumplimiento | Contratos, anexos, certificados | Detectar cláusulas, fechas, partes, vigencias y documentos faltantes |
| Logística y operaciones | Guías, manifiestos, órdenes, reportes | Ubicar códigos, destinos, cantidades y responsables |
| Salud administrativa | Autorizaciones, soportes, formularios | Identificar datos administrativos y campos requeridos |
| Educación | Certificados, documentos académicos, formularios | Consultar datos de estudiantes, cursos, fechas y soportes |
| Inmobiliario | Contratos, avalúos, certificados | Extraer datos de inmuebles, partes, valores y fechas |
| Consultoría y auditoría | Informes, evidencias y soportes | Buscar hallazgos, requisitos y referencias documentales |

### Usuario comprador

- Coordinador administrativo.
- Líder de operaciones.
- Jefe de contabilidad.
- Responsable de cumplimiento.
- Director de transformación digital.
- Dueño o gerente de pyme.

### Usuario operativo

- Auxiliar administrativo.
- Analista contable.
- Revisor documental.
- Auditor.
- Asistente jurídico.
- Personal de back-office.

---

## 6. Casos de uso comerciales

### Facturas y soportes contables

Una empresa carga un lote o documento de factura y consulta: proveedor, NIT, total, IVA, fecha, número de factura y orden de compra. El resultado permite validar rápidamente si el soporte cumple los criterios internos.

### Revisión de contratos

Un usuario carga un contrato escaneado y busca términos como “vigencia”, “penalidad”, “renovación”, “objeto”, “valor” y nombres de las partes. La plataforma muestra las páginas relevantes y el contexto encontrado.

### Validación de documentos para trámites

Una institución verifica que un PDF contenga campos o evidencias obligatorias: firma, sello, código, fecha, identificación o certificado asociado.

### Auditoría documental

Un auditor aplica un conjunto de keywords a documentos de soporte para localizar evidencia, inconsistencias o referencias requeridas sin revisar cada página manualmente.

### Búsqueda sobre expedientes históricos

Una organización digitaliza archivos antiguos y necesita convertirlos en una fuente consultable, aun si los escaneos presentan baja calidad.

---

## 7. Producto mínimo viable

El MVP debe resolver una necesidad completa, no intentar abarcar toda la gestión documental.

### Alcance del MVP

- Carga de un PDF por operación (hasta ~20 páginas).
- Búsqueda por parámetros definidos por el usuario con normalización canónica.
- **Extracción semántica clave-valor y contexto forense (KWIC):**
  - Captura del valor asociado (montos, fechas, NITs) más allá del simple conteo de palabras.
  - Normalización tipificada de monedas, fechas y documentos de identidad.
  - Ventanas contextuales de cláusulas u oraciones completas.
  - Expansión semántica de sinónimos comunes (ej. `total`, `importe`, `saldo`).
  - Vinculación de hallazgos con sellos y firmas cercanas.
- **Preprocesamiento determinista de imagen:** Corrección de inclinación (*Deskew*) y binarización (*Otsu*) para documentos escaneados.
- **Inventario y catalogación de imágenes:** Detección y descripción de firmas, sellos, logos y diagramas por página.
- Extracción de texto nativo sin coste de IA para páginas digitales.
- Análisis multimodal selectivo (Gemini Flash) restringido únicamente a páginas `needs_ai`.
- **Módulo Pydective Chat:** Interfaz para conversar con el PDF con grounding estricto y citas por página.
- Resultado por página con estado, hallazgos, catálogo visual y procedencia (`local`, `ia`, `cache_l1`, `empty`).
- Streaming reactivo SSE del progreso para mitigar timeouts en el navegador.
- Resiliencia operativa con fallback automático a memoria local si Redis no está disponible.

### Promesa de producto MVP

> “Encuentra información específica dentro de PDFs digitales o escaneados, con resultados organizados por página y sin repetir procesamiento innecesario.”

### Fuera del MVP

- Gestión masiva de miles de documentos.
- Workflow de aprobación complejo.
- Firma electrónica.
- Repositorio documental corporativo completo.
- Integraciones ERP/CRM profundas.
- Entrenamiento de modelos propios.
- Clasificación legal definitiva o decisiones automáticas de alto impacto.

---

## 8. Modelo de negocio

### Modelo principal: SaaS por uso y capacidad

La solución debe ofrecer una entrada sencilla y cobrar en función del valor generado: documentos procesados, páginas analizadas o capacidad mensual.

| Plan | Cliente | Propuesta | Cobro sugerido |
|---|---|---|---|
| Prueba | Prospectos | Uso limitado para validar calidad | Gratis con límite estricto |
| Starter | Profesional / microempresa | Documentos ocasionales, búsquedas manuales | Suscripción mensual baja + límite de páginas |
| Business | Pyme / equipo | Mayor volumen, historial y usuarios | Suscripción mensual por capacidad |
| Pro / Enterprise | Organización | SLA, integración, seguridad y volumen | Contrato mensual o anual personalizado |

### Unidad de valor recomendada

La unidad más clara para el cliente es el **documento procesado** o el **paquete mensual de páginas analizadas**.

Internamente se debe medir también:

- Páginas resueltas localmente.
- Páginas que requirieron IA.
- Reconsultas atendidas por caché.
- Coste medio de IA por documento.

Esto permite mantener un margen saludable: no todos los documentos deben tener el mismo coste, pero el cliente debe entender el precio de forma simple.

### Posible estrategia de precios

- Créditos por páginas que pasan por procesamiento multimodal.
- Búsquedas repetidas sobre documentos ya procesados incluidas o muy económicas.
- Planes con cuota mensual y sobreuso por bloques.
- Precio empresarial basado en volumen, usuarios, retención y soporte.

---

## 9. Ventaja competitiva

La ventaja no depende únicamente de usar IA. Depende de convertir IA en una experiencia de negocio rápida, confiable y costeable.

### Diferenciadores

| Diferenciador | Valor para el cliente | Valor para el negocio |
|---|---|---|
| Procesamiento híbrido | Más rapidez en documentos digitales | Menor coste variable de IA |
| IA solo en páginas necesarias | Mejor respuesta para escaneos y visuales | Mayor margen por documento |
| Búsquedas repetidas rápidas | Mejor experiencia de usuario | Más uso sin coste proporcional |
| Resultados por página | Revisión y verificación sencilla | Menos ambigüedad comercial |
| Tolerancia a fallos de proveedor | Menos interrupciones | Mayor confiabilidad percibida |
| Arquitectura extensible | Integraciones futuras | Camino hacia clientes enterprise |

### Barrera defensible progresiva

Al inicio, la barrera es la experiencia y la velocidad. Con el tiempo se fortalece mediante:

- Plantillas de extracción por industria.
- Flujos de validación configurables.
- Historial de documentos y resultados.
- Integraciones con sistemas de clientes.
- Datos anonimizados de calidad de documentos y rendimiento, con consentimiento y controles adecuados.

---

## 10. Estrategia de salida al mercado

### Fase 1: validación dirigida

Objetivo: comprobar disposición de pago y calidad de resultados con un nicho específico.

Recomendación inicial: enfocarse en **facturas, soportes administrativos y documentos operativos de pymes**. Son casos repetitivos, fáciles de explicar y con retorno de tiempo visible.

Canales:

- Contacto directo con pymes locales.
- Redes de contadores, asesores empresariales y consultores.
- Demostraciones con documentos reales anonimizados.
- Landing page con prueba limitada.
- LinkedIn y comunidades de emprendimiento / transformación digital.

### Fase 2: venta consultiva ligera

Ofrecer una configuración inicial de parámetros de búsqueda por tipo de documento.

Ejemplo:

> “Configuramos una plantilla de revisión de facturas: NIT, proveedor, fecha, subtotal, IVA, total, orden de compra y número de factura.”

Esto transforma una herramienta genérica en una solución directamente aplicable.

### Fase 3: expansión vertical

Después de validar un caso, crear versiones o paquetes por industria:

- Extractor de facturas.
- Revisor de contratos.
- Verificador de expedientes.
- Auditor documental.
- Clasificador de soportes logísticos.

---

## 11. Métricas de negocio

### Adquisición y activación

- Visitantes a prueba registrada.
- Porcentaje de usuarios que cargan su primer PDF.
- Tiempo hasta primer resultado útil.
- Porcentaje de usuarios que realiza una segunda consulta.

### Valor y retención

- Documentos procesados por cuenta por semana.
- Reconsultas sobre el mismo documento.
- Porcentaje de resultados usados o exportados.
- Usuarios activos semanales y mensuales.
- Retención a 30, 60 y 90 días.

### Calidad

- Porcentaje de parámetros correctamente encontrados.
- Porcentaje de documentos resueltos sin intervención manual adicional.
- Tasa de páginas con error.
- Tasa de resultados parciales.
- Tiempo medio de procesamiento por tipo de documento.

### Economía unitaria

- Ingreso mensual por cliente.
- Coste de IA por cliente.
- Coste de infraestructura por documento.
- Margen bruto por plan.
- Porcentaje de respuestas resueltas desde caché.
- Costo de adquisición de cliente y tiempo de recuperación.

La métrica técnica más importante para el margen es el **porcentaje de páginas resueltas localmente o desde caché**. Cada hit reduce el coste de IA sin reducir valor para el cliente.

---

## 12. Riesgos de negocio y mitigación

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Resultados incorrectos en documentos críticos | Pérdida de confianza | Mostrar página de origen, estados de confianza y revisión humana |
| Coste de IA demasiado alto | Margen bajo | Procesamiento híbrido, caché, límites y precios por uso |
| PDFs de mala calidad extrema | Calidad inconsistente | Mensajes claros, reintentos controlados y mejora progresiva de preprocesamiento |
| Dependencia de un proveedor de IA | Riesgo operativo | Abstracción de proveedor y capacidad futura de fallback |
| Usuarios esperan automatización total | Riesgo de expectativas | Posicionar como asistente de extracción y revisión, no como autoridad final |
| Datos sensibles | Riesgo legal y reputacional | Cifrado, retención mínima, controles de acceso y términos transparentes |
| Competencia de grandes plataformas | Diferenciación insuficiente | Enfocar nichos, velocidad, simplicidad y configuraciones verticales |

---

## 13. Privacidad y confianza

El producto procesa documentos que pueden contener información financiera, contractual, personal o empresarial. La confianza debe ser parte de la oferta comercial desde el primer día.

Principios:

- Minimizar persistencia del archivo original.
- Definir claramente cuánto tiempo se guardan resultados y metadatos.
- Permitir eliminación de documentos y resultados.
- Cifrar datos en tránsito y en reposo.
- Separar cuentas y documentos por organización.
- Informar al cliente cuando contenido se procesa mediante un proveedor de IA externo.
- No prometer precisión absoluta ni usar resultados como decisión automática en ámbitos de alto impacto sin revisión humana.

Para una primera operación en Colombia, el producto debe considerar desde diseño el tratamiento adecuado de datos personales y la autorización aplicable de los titulares. Antes de comercializar a sectores regulados, conviene una revisión legal específica.

---

## 14. Hoja de ruta de producto

### Etapa 0 — Descubrimiento

- Entrevistar 10–20 usuarios del nicho elegido.
- Conseguir ejemplos anonimizados de documentos reales.
- Medir tiempo actual de revisión manual.
- Validar qué campos buscan y cuánto vale automatizarlos.

### Etapa 1 — MVP funcional

- Upload de PDF.
- Parámetros de búsqueda.
- Resultados por página.
- Procesamiento híbrido.
- Reconsulta rápida.
- Métricas básicas de uso y rendimiento.

### Etapa 2 — Producto vendible

- Cuentas de usuario.
- Historial limitado de documentos.
- Paquetes de crédito o suscripción.
- Exportación de resultados.
- Plantillas reutilizables por tipo de documento.
- Soporte y panel básico de administración.

### Etapa 3 — Expansión B2B

- Multiusuario y espacios de trabajo.
- Roles y permisos.
- Integraciones API / webhook.
- Carga por lote.
- Auditoría de actividad.
- Planes empresariales con retención configurable.

---

## 15. Hipótesis a validar

El proyecto debe validar estas hipótesis antes de invertir en características enterprise:

1. Los equipos operativos pierden suficiente tiempo revisando PDFs como para pagar por reducir esa tarea.
2. La búsqueda por parámetros es más valiosa que entregar OCR plano.
3. Los usuarios confían más cuando el resultado indica la página de origen.
4. Los documentos mixtos o escaneados son el dolor con mayor disposición de pago.
5. Una experiencia de carga y resultado rápido genera más adopción que herramientas complejas de gestión documental.
6. Las plantillas por tipo de documento aumentan conversión y retención.
7. El coste de IA se mantiene por debajo de una fracción sostenible del ingreso gracias a caché y procesamiento selectivo.

---

## 16. Mensaje comercial inicial

### Versión corta

> Encuentra datos importantes en PDFs digitales o escaneados en segundos. Sube el documento, indica qué buscas y recibe resultados organizados por página.

### Versión para pymes

> Reduce el tiempo de revisar facturas, contratos y soportes. Nuestra plataforma identifica los datos que necesitas incluso en documentos escaneados, sin obligarte a leer página por página.

### Versión para operaciones

> Convierte PDFs difíciles de revisar en información consultable. Localiza códigos, fechas, valores, nombres y evidencias de forma rápida, verificable y organizada.

---

## 17. Decisión estratégica inicial

La primera versión debe venderse como una herramienta de **búsqueda y extracción asistida**, no como un sistema de OCR ni como una plataforma documental completa.

La oferta inicial recomendada es:

> Una aplicación web para equipos administrativos y operativos que necesitan encontrar y verificar información dentro de PDFs rápidamente, incluso cuando están escaneados o tienen baja calidad.

El foco de ejecución debe ser validar un caso de uso repetitivo, demostrar ahorro de tiempo con documentos reales y construir una economía unitaria sostenible antes de ampliar funcionalidades.
