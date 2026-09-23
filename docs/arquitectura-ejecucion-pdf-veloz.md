# Arquitectura de ejecución
## Encaje de capas para máxima velocidad

Este documento **alinea** módulos, caché, CPU y red para que cada etapa haga el mínimo trabajo y el camino feliz sea el más corto. Complementa la especificación; si hay conflicto, **gana este orden de ejecución**.

---

## 1. Regla de oro

> No se abre el PDF, no se pinta pixmap, no se llama a Gemini, hasta que la capa anterior demuestre que hace falta.

Velocidad = **evitar trabajo**, no paralelizar trabajo inútil.

Orden fijo:

1. Bytes en RAM  
2. SHA-256  
3. Caché L0 `(hash, keywords)` y L1 `(hash)`  
4. Clasificación local con PyMuPDF + Visión Determinista (Deskew Hough + Binarización Otsu con OpenCV)  
5. Catalogación forense de imágenes (firmas, sellos, logotipos, diagramas) por página  
6. Carril IA multimodal **solo** para páginas que persistan ilegibles o requieran descripción visual, con semáforo acotado  
7. Merge estable por número de página  
8. Escritura de caché L1 y L0 en `jobs.py` (con fallback in-memory ante fallo de Redis)  
9. HTML / SSE streaming de progreso + Interfaz conversacional (Pydective Chat)  

---

## 2. Por qué encaja (mapa de dependencias)

```
main.py          borde HTTP: tamaño, timeout, form
    │
    ▼
hash SHA-256     CPU barato, una pasada sobre bytes
    │
    ▼
cache.py         HIT → return (0 PyMuPDF, 0 Gemini)
    │ MISS
    ▼
pipeline.fase_A  fitz.open en RAM → texto nativo + has_images
                 │
                 ├── páginas ESCANEADAS/SUCIAS → preprocess_service (Deskew + Otsu)
                 │                                │
                 │                                ├── limpias deterministas → RESUELTAS local
                 │                                └── persisten sucias      → PENDIENTES IA
                 │
                 ├── catálogo visual            → image_service (firmas, sellos, logos)
                 ├── páginas RESUELTAS           → lista resultados (0 I/O red)
                 └── páginas PENDIENTES          → fase_B
                           │
                           ▼
                      WebP optimizado (150 DPI, q70, una vez por página pendiente)
              │
              ▼
         Gemini async + semáforo = f(keys sanas, RPM)
              │ 429 → otra key, mismo WebP
              ▼
cache.py write  Redis + (opcional) puntero Context Cache
    │
    ▼
Jinja2          no espera I/O extra
```

Ningún módulo llama a Gemini por su cuenta. `config.py` solo entrega clientes sanos. `cache.py` no renderiza. `main.py` no conoce páginas.

---

## 3. Fase A — clasificar barato (el acelerador real)

Una sola apertura `fitz.open(stream=bytes)`. Para cada página, **solo** operaciones C:

| Señal | Umbral de diseño | Destino |
|---|---|---|
| Texto nativo largo y keywords presentes, sin imágenes | éxito local | no pixmap |
| Texto nativo largo, keywords ausentes, sin imágenes | éxito local con lista vacía | no pixmap (no alucinar con IA si el PDF es digital) |
| Página inclinada o fondo con sombras/ruido | Preprocesamiento determinista: Deskew + Otsu | Limpieza antes de evaluar |
| Post-Otsu: texto legible alcanzado | éxito local | no pixmap, 0 costo IA |
| Poco texto / texto basura persistente / escaneo complejo | pendiente IA | pixmap 150 DPI |
| Hay sellos, firmas, logos o imágenes a describir | catalogación image_service + pendiente IA | pixmap 150 DPI |

Heurística de “texto basura” (producto, no magia):

- pocos caracteres alfanuméricos por página, o  
- alta ratio de reemplazos/control chars, o  
- `get_images()` cubre casi todo el rect de la página.

**Prohibido en fase A:** `get_pixmap`, Pillow, red.

Concurrencia fase A: `asyncio.to_thread` / pool acotado al número de CPU, no a 20 ciegas. PyMuPDF no es siempre thread-safe sobre el **mismo** `Document`: o se itera en un hilo, o se abre un doc por worker. Decisión de implementación: **un hilo, loop de 20 páginas de texto es ~ms**; no vale la pena pelear el GIL aquí. El win es no pintar. [web:35]

Cierre de iteración: cada resultado local se construye con `pagina=i+1` y un dict **ya copiado**, no un lambda que cierra sobre `i`.

---

## 4. Fase B — pintar y ver solo lo sucio

### 4.1 Pixmap y WebP (CPU)

- Solo páginas pendientes.  
- DPI **150** como default de velocidad; 200 solo si la heurística marca texto minúsculo. 300+ está fuera de v1 (RAM nativa enorme). [web:35][web:43]
- Liberar pixmap en cuanto existe el buffer WebP (`pix = None`).  
- Thumbnail 1024 y WebP q70: el cuello pasa a ser **RTT de Gemini**, no el PNG.  
- CPU en thread pool pequeño (2–4). Pintar 20 páginas a 150 DPI en serie en C suele ser más estable que 20 hilos peleando RAM.

### 4.2 Ráfaga Gemini (I/O)

- `asyncio.gather` **solo** de pendientes, no de las 20.  
- Semáforo: `min(pendientes, keys_sanas, MAX_INFLIGHT)`.  
  - `MAX_INFLIGHT` arranca en 4–8. Subir no linealiza: 429 serializa peor que un semáforo. [web:40]
- Un WebP, N reintentos de key.  
- `thinking` mínimo, JSON schema, `temperature` 0.1.  
- Batch API de Google **no** entra: es cola de horas, no request web. [web:31][web:32]

### 4.3 Keys y cuota

Varias keys **del mismo proyecto de Google no multiplican RPM**. El pool sirve para keys **de proyectos distintos** o para aislar keys muertas, no para 20 disparos simultáneos contra un solo cupo. [web:40]

Encaje: semáforo global del **proyecto** + rotación solo al ver 429/401 en esa key.

---

## 5. Caché que acelera de verdad

Tres lecturas, una escritura, sin pisa-pisas:

| Capa | Clave | Se consulta | Ahorra |
|---|---|---|---|
| L0 Redis aplicación | `(sha256, keywords_canónicas)` | **antes** de fitz | 100% CPU+red |
| L1 Redis OCR | `sha256` → texto/descripciones por página | miss de L0, mismo PDF otras keywords | Gemini + pixmap |
| L2 Google Context Cache | `sha256 + key_id` → `cache_name` + `expire_at` | miss L1, misma key, páginas imagen | tokens de imagen |

Camino más rápido posible:

1. Hit L0 → HTML.  
2. Hit L1 → refiltrar keywords en CPU → escribir L0 → HTML.  
3. Miss L1, hit L2 y key sana = la del cache → Gemini **sin** reenviar WebP.  
4. Else → fase A/B.

Escritura:

- L1 se llena con OCR/descripciones de páginas `exito: true` (independiente de keywords).  
- L0 se llena con el JSON **ya filtrado** de esta request.  
- L2 se crea **una vez por (pdf, key)** tras la primera ráfaga de imágenes, TTL ~60 min; no se crea si todas las páginas fueron locales. [web:16]

Invalidación: hash distinto; TTL; key `invalid`; no mezclar `cache_name` entre keys.

---

## 6. Presupuesto de latencia (20 páginas, diseño)

Escenario A — PDF digital, keywords en texto, hit frío L0:

- hash ~5–15 ms  
- fitz texto ~10–40 ms  
- 0 red  
- **objetivo p95 < 150 ms** más HTML  

Escenario B — mismo PDF, otras keywords, hit L1:

- hash + Redis + filtro  
- **objetivo p95 < 50 ms**

Escenario C — 20 escaneos sucios, 4 keys/proyectos, semáforo 4:

- fase A + 20 WebP (CPU)  
- 5 olas de 4 RTT Flash-Lite  
- failover no reinicia olas ya OK  
- **objetivo: 1–3 RTT efectivos**, no 20 RTT en serie y no 20 en paralelo que se 429  

Escenario D — hit L0:

- **objetivo < 20 ms**

Estos números son **presupuestos de diseño**, no promesas de SLA.

---

## 7. Encaje HTTP ↔ pipeline

| Pieza | Rol de velocidad |
|---|---|
| `file.read()` directo a RAM | cero disco |
| Límite 20–25 MB | rechazar antes del hash |
| Timeout HTTP > (olas_IA × RTT + cooldown corto) | no matar jobs casi listos |
| Un job por request | sin cola en v1; simplicidad > throughput multi-usuario |
| Jinja2 al final | no serializar JSON extra al browser como API |

Si el timeout pisa el failover, se **devuelve parcial** (páginas OK + errores), nunca se relanza el documento.

---

## 8. Módulos y contratos (para que no se pisen)

```
pydective/
├── main.py               # Borde HTTP: SSE streaming (/procesar/stream), Chat (/chat), Jinja2
├── jobs.py               # Orquestador único: hash → L0/L1 → Fase A → Fase B → persistencia
├── classify.py           # Fase A: extracción nativa con PyMuPDF
├── preprocess_service.py # Visión determinista: Deskew (Hough) + Binarización Otsu con OpenCV
├── image_service.py      # Detección y catalogación forense de imágenes (firmas, sellos, logos)
├── chat_service.py       # Pydective Chat: Grounding sobre L1 + Context Cache L2 con citas
├── render.py             # Pixmap 150 DPI → WebP q70 en CPU
├── gemini_io.py          # Llamada a Gemini Flash estructurado + retry y failover por página
├── keys.py               # Pool con estados healthy/cooldown/exhausted/invalid + semáforo por proyecto
├── cache.py              # Redis L0/L1/L2 + Fallback transparente InMemoryLRUCache
├── models.py             # Modelos Pydantic (JobInput, JobOutput, ChatInput, ChatOutput)
├── templates/            # UI Pydective con panel de hallazgos y chat interactivo
└── static/
```

`pipeline.py` único del borrador se **parte**: clasificación, render y red tienen costos distintos; mezclarlos impide medir y acelera peor.

Contrato interno:

```text
JobInput  = { bytes, keywords[] }
JobOutput = { hash, resultados[página], cache_hit: l0|l1|l2|none }
```

`jobs.py` es el único que escribe caché. Así no hay doble write ni condiciones de carrera.

---

## 9. Paralelismo permitido vs prohibido

**Permitido**

- Redis get/set async mientras no hay CPU pesada.  
- Gather de llamadas Gemini ≤ semáforo.  
- Thread pool chico para WebP de pendientes.

**Prohibido (ralentiza)**

- 20 pixmaps simultáneos.  
- Gather de 20 Gemini contra un solo proyecto.  
- Reabrir el PDF por cada página.  
- Recomprimir WebP en cada retry de key.  
- Relanzar fase A porque falló la página 19.  
- Context Cache en el primer hit local (no hay imágenes que cachear).  
- Batch API para el POST `/procesar`.

---

## 10. Checklist de encaje (aceptación de velocidad)

- [ ] Hit L0 no importa `fitz` ni crea clientes Gemini extra.  
- [ ] PDF digital de 20 páginas no genera ningún WebP.  
- [ ] PDF mixto (3 sucias / 17 limpias) = 3 llamadas IA máximo.  
- [ ] Retry de key reutiliza el mismo `bytes` WebP.  
- [ ] Semáforo ≤ keys/proyectos útiles, no ≤ número de páginas.  
- [ ] L1 permite cambiar keywords sin visión.  
- [ ] L2 no se consulta con una key distinta a la que lo creó.  
- [ ] Reinicio de Uvicorn no borra L0/L1 (Redis).  
- [ ] Respuesta parcial si el tiempo se acaba; páginas hechas se cachean.

---

## 11. Qué se implementa primero (cuando haya código)

1. `keys.py` + semáforo (sin esto, más paralelismo = más 429).  
2. `classify.py` + `jobs.py` fase A (el mayor win de velocidad).  
3. `cache.py` L0/L1 (el mayor win de repetición).  
4. `render.py` + `gemini_io.py` fase B.  
5. L2 Context Cache.  
6. Ajuste de `MAX_INFLIGHT` y DPI con un PDF real de 20 páginas.

No se escribe HTML ni se pulen plantillas hasta que el job devuelva el contrato `JobOutput` estable.
