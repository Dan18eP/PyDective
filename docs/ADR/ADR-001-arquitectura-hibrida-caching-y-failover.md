# ADR-001: Arquitectura híbrida de extracción, caché escalonada y failover por página

- **Estado:** Aceptado
- **Fecha:** 2026-09-23
- **Decisores:** Equipo del proyecto `app_pdf_veloz`
- **Etiquetas:** arquitectura, pdf, OCR, IA multimodal, rendimiento, caché, resiliencia

---

## Contexto

El producto necesita procesar PDFs de aproximadamente 20 páginas desde una aplicación web. Los documentos pueden ser:

- PDFs digitales con texto nativo seleccionable.
- PDFs mixtos con texto, gráficos, logos o imágenes embebidas.
- Escaneos sin texto nativo.
- Escaneos de baja calidad con ruido, sombras, manchas o compresión.

El usuario proporciona parámetros de búsqueda, por ejemplo: `factura`, `fecha`, `total`, `NIT`, `vigencia` o códigos de operación. El sistema debe responder con hallazgos estructurados por página, incluyendo texto limpio, coincidencias y descripciones visuales relevantes cuando aplique.

Una arquitectura simple que envíe todas las páginas a una IA multimodal tiene problemas de velocidad, costo, cuota y resiliencia:

- Renderiza páginas que podrían resolverse localmente.
- Envía imágenes innecesarias a red.
- Repite trabajo cuando se vuelve a cargar el mismo PDF.
- Reprocesa el documento cuando cambian únicamente los parámetros de búsqueda.
- Puede superar límites de tasa y recibir `429 RESOURCE_EXHAUSTED`.
- Puede cancelar todo el lote si falla una key o una página individual.

Se requiere un diseño que haga el mínimo trabajo posible y que aísle fallos por página.

---

## Decisión

Adoptar una arquitectura de procesamiento híbrido con tres niveles de caché, clasificación local previa y failover de API keys por página.

El orden obligatorio de procesamiento será:

```text
PDF bytes en RAM
  → SHA-256
  → Caché L0: hash + keywords
  → Caché L1: extracción completa por hash
  → Fase A: clasificación local con PyMuPDF
  → Fase B: render WebP + Gemini únicamente para páginas pendientes
  → Consolidación ordenada por página
  → Escritura L1 / L0 y registro opcional L2
  → Renderizado Jinja2
```

### 1. Procesamiento en RAM

El archivo se recibe y procesa como `bytes` en memoria. La versión inicial no persiste el PDF original por defecto.

### 2. Caché L0: respuesta por consulta

La primera caché usa una clave formada por:

```text
(pdf_hash, keywords_normalizadas)
```

Las keywords se normalizan con trim, `casefold`, eliminación de vacíos, deduplicación y orden canónico.

Un hit L0 devuelve el resultado de inmediato sin abrir el PDF, extraer texto, renderizar imagen ni llamar a la IA.

### 3. Caché L1: conocimiento reusable del documento

La segunda caché se indexa solo por hash:

```text
pdf_hash
```

Almacena por página:

- texto nativo u OCR limpio;
- descripción de imágenes cuando exista;
- origen del resultado: local o IA;
- estado de extracción;
- metadatos de TTL.

Un hit L1 permite refiltrar nuevos parámetros de búsqueda localmente y generar un nuevo L0 sin usar IA.

### 4. Fase A: clasificación local

Antes de generar cualquier imagen, PyMuPDF inspecciona cada página:

- extrae texto nativo;
- mide calidad y densidad de texto;
- detecta imágenes;
- clasifica la página como `local`, `empty` o `needs_ai`.

Las páginas con texto digital suficiente se resuelven localmente, incluso si no contienen los parámetros solicitados. La ausencia de una keyword no es razón para llamar a IA cuando el PDF ya tiene texto nativo confiable.

La Fase A no permite pixmaps, Pillow ni red.

### 5. Fase B: IA selectiva

Solo las páginas `needs_ai` se renderizan y envían al proveedor multimodal.

Configuración de referencia:

```text
Pixmap: 150 DPI
Thumbnail: máximo 1024 px
Formato: WebP
Calidad WebP: ~70
Salida: JSON estructurado validado por esquema
```

El WebP se produce una sola vez por página y se reutiliza en reintentos de red o rotaciones de key.

### 6. Control de concurrencia

Se separan recursos CPU y red:

| Recurso | Límite inicial |
|---|---:|
| Render WebP | 2–4 workers |
| Gemini concurrente | 4–8 solicitudes, semáforo global |
| Páginas por PDF | ~20 en v1 |

El semáforo Gemini es global al proceso/proyecto; no se lanza una ráfaga ilimitada por cada request. Los límites del proveedor pueden provocar `429 RESOURCE_EXHAUSTED`, por lo que controlar la concurrencia es parte de la latencia y de la confiabilidad. [web:31]

### 7. Pool de API keys con salud

El sistema no usa un round-robin ciego. Cada API key tiene estado:

| Estado | Uso |
|---|---|
| `healthy` | Disponible para solicitudes |
| `cooldown` | Temporalmente excluida tras 429 transitorio o sobrecarga |
| `exhausted` | Excluida tras cuota diaria o límite persistente |
| `invalid` | Excluida tras 401/403 o error de configuración |

La unidad de retry es la **página**, no el documento.

- Ante 429 temporal: poner la key en cooldown y reintentar la misma página con otra key sana.
- Ante cuota diaria: marcar `exhausted` y no reutilizar en el job.
- Ante 401/403: marcar `invalid`.
- Ante 400 de request/schema: no rotar keys; retornar error aislado de página.
- Si no queda key utilizable: preservar páginas exitosas y devolver resultado parcial.

Las API keys del mismo proyecto no se consideran multiplicadores automáticos de cuota. El límite de concurrencia se configura por cuota efectiva/proyecto, no por número de keys.

### 8. Context Cache explícito de Google (L2)

L2 es una optimización opcional para reutilizar contenido multimodal en nuevas consultas del mismo PDF.

- Se almacena un puntero `cache_name` junto con `pdf_hash`, `key_id` y `expire_at`.
- Solo se usa con la misma key/proyecto que creó el recurso.
- Se crea mediante la API oficial de caché y se referencia como contenido cacheado en solicitudes posteriores.
- Su TTL se respeta; si vence, se recrea u omite sin bloquear el trabajo.
- L2 no reemplaza Redis L0/L1.

El Context Cache se crea y usa con interfaces de caché del SDK, no mediante campos no verificados añadidos a la configuración de generación. [web:16][web:18][web:24]

### 9. Persistencia de caché

Redis (o equivalente) será el almacén de producción para L0 y L1. Un diccionario en RAM solo puede usarse en desarrollo local porque desaparece al reiniciar el proceso y no se comparte entre instancias.

TTL inicial propuesto:

| Capa | TTL |
|---|---:|
| L0 | 24 horas o evicción LRU |
| L1 | 24 horas o política de retención configurable |
| L2 | TTL definido por proveedor, inicialmente ~60 minutos |

### 10. Estructura de módulos

La implementación se separará según responsabilidad y costo:

```text
app/
├── main.py                 # HTTP, middleware y Jinja2
├── domain/                 # contratos, enums y errores
├── services/
│   ├── jobs.py             # orquestador y único escritor de caché
│   ├── classifier.py       # Fase A: PyMuPDF
│   ├── renderer.py         # Fase B CPU: pixmap → WebP
│   ├── gemini_service.py   # Fase B I/O: generación y retry por página
│   ├── key_pool.py         # salud de keys y semáforo
│   ├── cache_service.py    # L0/L1/L2
│   └── keyword_service.py  # normalización y filtrado
└── infrastructure/         # Redis, clientes Gemini, observabilidad
```

`jobs.py` es el único módulo autorizado para encadenar las fases y escribir caché. Los demás servicios no deben invadir responsabilidades de otras capas.

---

## Justificación

La arquitectura se adopta por las siguientes razones:

1. **El trabajo evitado es más rápido que el trabajo paralelizado.** L0 evita todo el pipeline; L1 evita nueva extracción; Fase A evita renderizado e IA para PDFs digitales.
2. **El costo de IA es variable y debe reservarse para páginas que lo requieren.** Esto protege el margen del producto y mejora la velocidad percibida.
3. **Los documentos repetidos y las nuevas búsquedas son un caso esperado.** Indexar solo por hash no basta; por eso se separa L0 (consulta) de L1 (conocimiento del documento).
4. **El proveedor externo puede fallar o limitar solicitudes.** El semáforo global y el failover por página evitan que una falla aislada destruya el resultado completo.
5. **La separación de módulos permite medir y optimizar.** Si render, lógica PDF y red viven en un único archivo, es difícil atribuir latencia y ajustar correctamente.
6. **Redis permite confiabilidad real.** La caché en memoria no sobrevive reinicios ni funciona bien al escalar horizontalmente.

---

## Consecuencias

### Positivas

- Los hits L0 pueden responder sin tocar PDF ni IA.
- Cambiar keywords sobre el mismo PDF puede responder desde L1 en milisegundos.
- Los PDFs digitales pueden resolverse sin coste de IA.
- Los PDFs mixtos envían a IA solo sus páginas relevantes o sucias.
- Un 429 o key agotada no obliga a reiniciar el documento.
- La aplicación puede entregar resultados parciales en vez de fallar por completo.
- La estructura soporta evolución hacia multiusuario, colas o integraciones sin reescribir el núcleo.
- Las métricas pueden separar tiempo de hash, extracción, renderizado, Gemini, caché y failover.

### Negativas / costos

- Aumenta el número de módulos y contratos internos respecto a un único `pipeline.py`.
- Redis se vuelve una dependencia operativa para rendimiento y persistencia de caché.
- Se debe administrar TTL, invalidación y serialización de datos de caché.
- El pool de keys requiere pruebas rigurosas de concurrencia, cooldown y reintentos.
- Context Cache L2 agrega complejidad y debe manejarse por key/proyecto.
- Se necesita observabilidad desde el inicio para ajustar DPI, semáforo y reglas de clasificación.

### Riesgos aceptados

- La heurística de clasificación local puede necesitar ajuste con documentos reales.
- Algunos documentos visuales requerirán IA aunque haya texto nativo.
- Una respuesta parcial puede ser menos cómoda que una respuesta completa, pero es preferible a perder resultados correctos ya obtenidos.
- Las metas de latencia dependen de tamaño de PDF, calidad del escaneo, red y cuota disponible; se tratan como objetivos de diseño, no como SLA.

---

## Alternativas consideradas

### Alternativa A: Enviar todas las páginas a Gemini

**Descripción:** renderizar todas las páginas y enviar una llamada IA por página.

**Rechazada porque:**

- Genera alto coste y más latencia.
- Desperdicia extracción nativa rápida en PDFs digitales.
- Aumenta presión de cuota y errores 429.
- Repite trabajo en consultas posteriores.
- Hace que un PDF de 20 páginas use 20 solicitudes incluso cuando no son necesarias.

### Alternativa B: Solo PyMuPDF / OCR local

**Descripción:** extraer texto nativo y no usar IA multimodal.

**Rechazada porque:**

- No resuelve bien escaneos de baja calidad.
- No describe logos, imágenes, diagramas u objetos.
- Reduce la utilidad en documentos visuales o sin capa de texto.

Puede incorporarse OCR clásico como tercer carril en una versión posterior, pero no forma parte de v1.

### Alternativa C: Caché única por SHA-256

**Descripción:** guardar un único resultado por documento.

**Rechazada porque:**

- No distingue búsquedas con parámetros distintos.
- Podría devolver coincidencias incorrectas o incompletas.
- No permite modelar claramente la diferencia entre resultado de consulta y conocimiento reusable.

Se adopta L0 + L1 en su lugar.

### Alternativa D: Reintentar el endpoint o documento completo ante 429

**Descripción:** si una llamada IA falla, ejecutar nuevamente todo el pipeline.

**Rechazada porque:**

- Reabre el PDF y vuelve a renderizar páginas resueltas.
- Duplica coste y latencia.
- Puede repetir el mismo fallo de cuota.
- Destruye la experiencia si la falla ocurre al final del procesamiento.

Se adopta retry por página con reutilización del WebP.

### Alternativa E: Round-robin ciego de keys

**Descripción:** seleccionar la siguiente key de un `itertools.cycle` sin estado de salud.

**Rechazada porque:**

- Una key agotada sigue siendo seleccionada.
- No diferencia cooldown, cuota diaria e invalidez.
- No permite hacer backoff ni failover controlado.

Se adopta un pool de keys con estados explícitos.

### Alternativa F: Context Cache como única caché

**Descripción:** depender exclusivamente del Context Cache del proveedor de IA.

**Rechazada porque:**

- No responde L0/L1 sin contactar proveedor.
- No sustituye el refiltrado local de nuevas keywords.
- Tiene TTL, vínculo de key/proyecto y costes propios.
- No sobrevive como fuente universal de verdad del producto.

Se adopta como L2 opcional y complementario.

### Alternativa G: Batch API para la carga web

**Descripción:** enviar documentos al Batch API del proveedor.

**Rechazada porque:**

- Está pensado para procesamiento asíncrono masivo, no para respuesta interactiva de un formulario web.
- No satisface el objetivo de resultados inmediatos.

Puede considerarse en un producto futuro de procesamiento masivo. [web:31][web:32]

---

## Criterios de aceptación

La implementación se considerará alineada con este ADR cuando:

- [ ] Un hit L0 no abre el PDF ni llama servicios de IA.
- [ ] Una consulta distinta sobre el mismo PDF puede refiltrarse desde L1.
- [ ] Un PDF digital suficiente no genera WebP ni llamadas IA.
- [ ] Un PDF mixto solo envía páginas `needs_ai` a la Fase B.
- [ ] El WebP se genera una vez por página pendiente y se reutiliza en retries.
- [ ] La concurrencia Gemini se limita mediante semáforo global.
- [ ] Una key agotada no provoca reinicio ni cancelación de páginas exitosas.
- [ ] Los resultados se mantienen ordenados por página y soportan estado parcial.
- [ ] Redis conserva L0/L1 tras reinicio de la aplicación.
- [ ] L2 respeta TTL y no cruza cache entre keys distintas.
- [ ] `main.py` no contiene lógica de extracción, caché, prompts o failover.

---

## Notas de implementación

Este ADR define decisiones arquitectónicas; no fija una versión concreta de librerías ni APIs del SDK. Durante implementación se deben fijar las versiones en `requirements.txt` y validar contra documentación vigente:

- Creación y uso de Context Cache.
- Nombres de modelos disponibles.
- Soporte de `thinking_level` y esquema JSON estructurado.
- Tipos de excepción, códigos y headers para `Retry-After`.
- Cuotas efectivas por proyecto, modelo y nivel de cuenta.

Los objetivos iniciales de rendimiento son:

| Escenario | Objetivo de diseño |
|---|---:|
| Hit L0 | < 20 ms |
| Hit L1 con nuevas keywords | < 50 ms |
| PDF digital de ~20 páginas, caché fría | p95 < 150 ms + HTML |
| PDF mixto | IA solo para páginas pendientes |
| Falla de una key | Sin reprocesar páginas ya exitosas |

Estos objetivos se validarán con documentos de prueba representativos antes de optimizar DPI, límite de render workers o `MAX_INFLIGHT_GEMINI`.
