# PRD — Motor Ultra-Veloz de Extracción Multimodal Anti-Ruido

**Versión:** 1.0  
**Estado:** definición de producto para MVP  
**Fecha:** 2026-09-23  
**Producto:** aplicación web B2B de búsqueda y extracción asistida sobre PDFs

---

## 1. Resumen

El Motor Ultra-Veloz de Extracción Multimodal Anti-Ruido permite a un usuario cargar un PDF, indicar los datos que necesita encontrar y recibir resultados estructurados por página. El producto funciona tanto con PDFs digitales como con escaneos o documentos mixtos que contienen texto no seleccionable, imágenes, logos, diagramas o baja calidad visual.

La promesa del MVP es:

> Encuentra y verifica información importante en PDFs digitales o escaneados sin revisar manualmente cada página.

El producto no se posiciona como un lector de PDF genérico ni como una plataforma documental completa. Se posiciona como una herramienta de productividad para extraer y localizar información específica de forma rápida, verificable y reutilizable.

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

1. El usuario abre la página principal.
2. Carga un archivo PDF válido.
3. Escribe uno o más parámetros separados por coma.
4. Envía el formulario.
5. El sistema procesa el documento o reutiliza información ya extraída.
6. El usuario visualiza resultados ordenados por página.
7. El usuario puede cargar el mismo PDF y consultar otros parámetros.

### Funciones incluidas

- Carga de un PDF por operación.
- Parámetros de búsqueda libres, separados por coma.
- Normalización de parámetros: espacios, mayúsculas/minúsculas y duplicados.
- Detección de coincidencias en texto nativo.
- Análisis de páginas escaneadas o visuales cuando sea necesario.
- Extracción de texto limpio por página.
- Descripción de imágenes, logos u objetos relevantes cuando aplique.
- Resultados por página con estado de éxito o error.
- Reutilización de resultados para el mismo documento.
- Vista HTML renderizada en servidor.

### Tipos de PDF soportados

| Tipo de documento | Expectativa MVP |
|---|---|
| PDF digital con texto | Resolución local rápida |
| PDF mixto texto + imágenes | Texto local; IA solo si se requiere análisis visual |
| Escaneo sin capa de texto | Análisis multimodal por página necesaria |
| Escaneo con ruido moderado | Intento de extracción multimodal y advertencia si la calidad limita el resultado |
| Página vacía | Resultado vacío sin llamar a IA |

---

## 8. Experiencia de usuario

### Pantalla inicial

Debe incluir:

- Área de carga de PDF.
- Indicador claro de tipo y tamaño permitido.
- Campo de parámetros de búsqueda.
- Ejemplo visible de uso: `factura, fecha, total, NIT`.
- Botón de procesamiento.
- Mensajes de validación antes de enviar.

### Estado de procesamiento

En el MVP puede ser una transición simple hacia la pantalla de resultados. Debe comunicar que el documento está siendo analizado y no debe inducir al usuario a reenviar el formulario mientras está en curso.

### Pantalla de resultados

Debe mostrar:

- Hash o identificador técnico no sensible del procesamiento, si es útil para soporte.
- Parámetros buscados.
- Resumen: páginas analizadas, páginas resueltas localmente, páginas analizadas con IA, páginas con advertencia.
- Lista ordenada de páginas.
- Por cada página:
  - número de página;
  - estado: encontrada, sin coincidencias, procesada, advertencia/error;
  - texto extraído o fragmento útil;
  - parámetros encontrados;
  - descripciones visuales cuando existan;
  - origen informativo: local, IA o caché.

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
