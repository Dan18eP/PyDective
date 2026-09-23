# Épica 5: Caching, Resiliencia y Singleflight

> **Objetivo:** Implementar la estrategia de caching escalonado (L0, L1, L2), el fallback in-memory acotado con `orjson`, la protección contra estampidas concurrentes (singleflight) y la gestión dinámica de API keys con failover aislado por página.

---

### US-14: Caché L0 Instantánea

- **ID:** `US-14`
- **Requisitos asociados:** `RF-020`, `RF-021`, `RF-022`, `RNF-001`, `ADR-001`, `ADR-004 Sección 6`
- **Prioridad:** Crítica | **Estimación:** 3 pts

#### Narrativa
**Como** orquestador de trabajos (`jobs.py`),  
**Quiero** consultar la caché L0 antes de inspeccionar el PDF o ejecutar algoritmos de extracción,  
**Para** devolver respuestas HTML o JSON completas en < 20 ms ante consultas idénticas repetidas.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Hit en L0**
   - **Dado** una clave L0 `pydective:2.2:l0:{pdf_hash}:{query_hash}` almacenada en Redis o memoria,
   - **Cuando** llega una solicitud con el mismo hash binario y parámetros equivalentes,
   - **Entonces** el sistema deserializa el `JobOutput` con `orjson` y responde en < 20 ms con `nivel_cache="L0"`, sin abrir PyMuPDF ni invocar IA.

2. **Escenario: Versionado de namespace de caché**
   - **Dado** un cambio de versión de pipeline a `"2.3"` en `settings.py`,
   - **Cuando** se consulta un documento previamente procesado con la versión `"2.2"`,
   - **Entonces** ocurre un MISS natural de L0 sin requerir un comando `FLUSHALL` destructivo en Redis.

---

### US-15: Caché L1 con Cobertura y Reutilización Incremental

- **ID:** `US-15`
- **Requisitos asociados:** `RF-023`, `RF-024`, `RF-025`, `RF-026`, `RNF-002`, `ADR-004 Sección 5 y 10`
- **Prioridad:** Crítica | **Estimación:** 5 pts

#### Narrativa
**Como** servicio de caché documental (`cache_service.py`),  
**Quiero** indexar el conocimiento extraído del PDF con metadatos explícitos de cobertura (`status: complete | partial`) y un índice asociativo simple `parametro -> list[Evidence]`,  
**Para** resolver nuevas consultas sobre el mismo PDF en sub-decenas de milisegundos sin reabrir PyMuPDF y procesar únicamente páginas pendientes en documentos parciales.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Reutilización de L1 completo con nuevos parámetros**
   - **Dado** un PDF previamente procesado con `status="complete"` en L1,
   - **Cuando** un usuario consulta nuevos parámetros (`"arrendador"`, `"placa"`),
   - **Entonces** el sistema recupera las evidencias desde el índice asociativo L1 en memoria, crea un nuevo registro L0 y responde en < 50 ms sin tocar IA ni PyMuPDF.

2. **Escenario: Procesamiento incremental de L1 parcial**
   - **Dado** un documento de 20 páginas donde L1 tiene `status="partial"` con `pages_pending=[19, 20]`,
   - **Cuando** se reanuda la solicitud,
   - **Entonces** el orquestador procesa exclusivamente las páginas 19 y 20, reutilizando el 100% de las páginas 1 a 18 ya resueltas.

---

### US-16: Fallback en Memoria LRU Doblemente Acotado

- **ID:** `US-16`
- **Requisitos asociados:** `RNF-015`, `ADR-004 Sección 16`
- **Prioridad:** Alta | **Estimación:** 3 pts

#### Narrativa
**Como** arquitecto de infraestructura,  
**Quiero** un fallback `InMemoryLRUCacheService` gobernado por dos límites simples medibles (`MAX_DOCUMENTS=100` y `MAX_TOTAL_CACHE_BYTES=256MB`),  
**Para** operar transparentemente en desarrollo o ante indisponibilidad de Redis sin fugas de memoria y sin el costo de `sys.getsizeof()`.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Estimación predecible de tamaño con orjson**
   - **Dado** que se almacena un nuevo `JobOutput` en la caché en memoria,
   - **Cuando** se calcula el peso del objeto,
   - **Entonces** se evalúa `len(orjson.dumps(payload))` en microsegundos sin traversals profundos en Python.

2. **Escenario: Desalojo LRU ante saturación de bytes o documentos**
   - **Dado** que el gestor acumula 100 documentos o supera 256 MB serializados,
   - **Cuando** se inserta una nueva entrada,
   - **Entonces** desaloja las entradas menos recientemente utilizadas (LRU) hasta restablecer el presupuesto.

---

### US-17: Prevención de Estampidas (Singleflight contra Dogpile)

- **ID:** `US-17`
- **Requisitos asociados:** `RNF-016`, `ADR-004 Sección 17`
- **Prioridad:** Alta | **Estimación:** 5 pts

#### Narrativa
**Como** orquestador de concurrencia (`jobs.py`),  
**Quiero** adquirir un candado distribuido (`lock:pdf:{pdf_hash}`) con renovación de lease antes de iniciar la extracción de un documento nuevo,  
**Para** asegurar que ante 5 solicitudes simultáneas para el mismo PDF solo 1 ejecute el trabajo y las otras 4 resuelvan desde la caché cuando termine.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Una sola ejecución real ante peticiones concurrentes**
   - **Dado** 5 peticiones simultáneas con el mismo `pdf_hash` en un miss frío de caché,
   - **Cuando** el primer worker adquiere el candado distribuido con `SETNX` y lease de 60s,
   - **Entonces** los otros 4 esperan mediante polling no bloqueante (100 ms) y resuelven inmediatamente desde L0 una vez el primero publica el resultado.

---

### US-18: Gestión de Salud de API Keys y Failover Aislado por Página

- **ID:** `US-18`
- **Requisitos asociados:** `RF-054`, `RF-055`, `RF-056`, `RF-057`, `RF-058`, `RF-059`, `RF-060`, `RNF-011`, `ADR-001 Sección 7`
- **Prioridad:** Crítica | **Estimación:** 5 pts

#### Narrativa
**Como** gestor de claves de API (`key_pool.py`),  
**Quiero** monitorear el estado de salud de cada clave (`healthy`, `cooldown`, `exhausted`, `invalid`) y rotarlas a nivel de página individual,  
**Para** garantizar resiliencia ante errores 429 transitorios sin reiniciar el procesamiento de páginas exitosas.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Cooldown automático ante HTTP 429**
   - **Dado** que la clave `KeyA` recibe un error `429 RESOURCE_EXHAUSTED` al procesar la página 3,
   - **Cuando** se captura el error,
   - **Entonces** `KeyA` pasa a estado `cooldown` (e.g. 60s) y la página 3 se reintenta inmediatamente con `KeyB` en estado `healthy`.

2. **Escenario: Cuota diaria agotada (Exhausted)**
   - **Dado** un error de cuota permanente diaria (`quota exceeded`),
   - **Cuando** se detecta la condición,
   - **Entonces** la clave pasa a `exhausted` y queda excluida del pool durante todo el ciclo de vida del job.

---

### US-19: Caché Contextual de Proveedor L2 (Google Context Cache)

- **ID:** `US-19`
- **Requisitos asociados:** `RF-065`, `RF-066`, `RF-067`, `RF-068`, `ADR-001`, `ADR-004 Sección 15`
- **Prioridad:** Baja | **Estimación:** 3 pts

#### Narrativa
**Como** optimizador de costos de IA,  
**Quiero** crear un Context Cache de Google solo cuando el PDF supere el umbral mínimo de 32.768 tokens,  
**Para** ahorrar costo de entrada en consultas repetidas de documentos extensos y borrar de inmediato el puntero si L1 se invalida.

#### Criterios de Aceptación (Gherkin)
1. **Escenario: Salvaguarda de umbral mínimo de tokens**
   - **Dado** un PDF cuyas páginas multimodales suman 8.000 tokens (inferior a 32.768),
   - **Cuando** se evalúa la creación de L2,
   - **Entonces** el sistema omite la llamada a `client.caches.create()`, evitando errores del proveedor.

2. **Escenario: Invalidación automática en cascada**
   - **Dado** que se reescribe o actualiza la caché L1 de un documento,
   - **Cuando** `jobs.py` guarda la nueva versión,
   - **Entonces** elimina de inmediato el puntero L2 en Redis para evitar desincronización con Google.
