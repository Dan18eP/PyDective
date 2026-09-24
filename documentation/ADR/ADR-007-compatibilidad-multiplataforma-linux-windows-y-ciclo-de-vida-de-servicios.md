# ADR-007: Compatibilidad Universal Multiplataforma (Linux / Windows), Gestión Desacoplada de Procesos Daemon y Resiliencia en Portapapeles

- **Estado:** Aceptado
- **Fecha:** 2026-09-24
- **Decisores:** Brandon Carranza (Arquitecto de Software y Lead Engineer)
- **Extiende a:** [ADR-001](file:///C:/Users/Usuario/Desktop/Github/PyDective/documentation/ADR/ADR-001-arquitectura-hibrida-caching-y-failover.md), [ADR-004](file:///C:/Users/Usuario/Desktop/Github/PyDective/documentation/ADR/ADR-004-optimizacion-rendimiento-precision-y-reutilizacion-documental.md) y [ADR-006](file:///C:/Users/Usuario/Desktop/Github/PyDective/documentation/ADR/ADR-006-arquitectura-dual-de-motores-de-vision-y-grounding-espacial-exacto.md)
- **Relacionado con:** PRD, Requisitos del Sistema (RF-106, RNF-052) y Especificación Arquitectónica General
- **Etiquetas:** pydective, cross-platform, linux, windows, posix, daemon-lifecycle, ollama, clipboard-fallback

---

## 1. Contexto

La arquitectura inicial de PyDective fue validada primordialmente sobre estaciones de trabajo Windows. Sin embargo, los entornos corporativos de despliegue, servidores CI/CD, instancias en la nube (AWS EC2, Google Cloud Compute Engine) y estaciones de desarrollo forense operan preponderantemente sobre distribuciones Linux (Ubuntu Server, Debian, Fedora, Arch Linux).

Durante la transición hacia la portabilidad multiplataforma, se detectaron las siguientes fricciones críticas:

1. **Rutas Rígidas y Extensiones de Binarios:** El código dependía de ejecutables con extensión `.exe` (`uv.exe`, `ollama.exe`) y directorios fijos bajo `%LOCALAPPDATA%`, provocando que en distribuciones POSIX los gestores de paquetes no fueran detectados a pesar de estar instalados en `~/.local/bin`, `/usr/local/bin` o `/snap/bin`.
2. **Incompatibilidad en Creación de Procesos Hijos:** La bandera `subprocess.CREATE_NEW_PROCESS_GROUP` es exclusiva de la API Win32. Al intentar iniciar el servidor daemon de Ollama en Linux, el intérprete Python levantaba excepciones `AttributeError` o `ValueError`.
3. **Bloqueo de Señales de Terminación (SIGINT / SIGTERM):** Procesos en segundo plano lanzados sin desacoplamiento de grupo de procesos quedaban como procesos huérfanos (*zombies*) tras cerrar el servidor principal.
4. **Excepciones de Portapapeles en Navegadores Linux (Wayland / X11):** En navegadores modernos ejecutados bajo sesiones Wayland o en servidores locales accedidos vía red sin certificado TLS (`http://`), la API `navigator.clipboard.writeText()` es bloqueada por las políticas de seguridad del navegador (`NotAllowedError`), impidiendo copiar las coordenadas de bounding boxes generadas por los motores de visión.

---

## 2. Decisión Arquitectónica

Estructurar un **Sistema Universal Multiplataforma** para el ciclo de vida del aplicativo, compuesto por:

1. **Script Autónomo de Instalación de Recursos (`install_dependencies.py`):**
   - Detección dinámica de sistema operativo y arquitectura mediante `platform.system()` y `platform.machine()`.
   - Inspección exhaustiva de binarios de `uv` en rutas estándar POSIX y Windows.
   - Generación de estructura de directorios de trabajo (`uploads/`, `cache/`, `runs/`) con permisos adecuados.
   - Creación de archivos de entorno `.env` a partir de `.env.example` preservando configuraciones existentes.
2. **Lanzador Resiliente de Aplicación (`run_app.py` / `run.py`):**
   - Resolución desacoplada de `uvicorn` y `ollama`.
   - Invocación de procesos demonio con discriminación de plataforma:
     - En **Windows**: `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP`.
     - En **Linux / POSIX**: `start_new_session=True` para crear una nueva sesión de proceso desacoplada y limpiar la sesión ante señales de apagado.
3. **Lanzadores Nativos Shell (`install.sh` / `run.sh`):**
   - Scripts Bash con directiva `set -e` y detección progresiva de intérpretes (`python3` -> `python`) para terminales Linux.
4. **Abstracción de Portapapeles en Frontend con Fallback Automático:**
   - Implementación de `copyToClipboard()` con verificación previa de `window.isSecureContext` y fallback mediante elemento `<textarea>` temporal oculto con `document.execCommand('copy')`.

```text
                                  ┌───────────────────────────────┐
                                  │   Lanzador del Sistema        │
                                  │   (run.py / run.sh)           │
                                  └──────────────┬────────────────┘
                                                 │
                                                 ▼
                                  ┌───────────────────────────────┐
                                  │ Detección de Plataforma       │
                                  │ sys.platform / platform       │
                                  └──────┬─────────────────┬──────┘
                                         │                 │
                 ┌───────────────────────┘                 └───────────────────────┐
                 │ sys.platform == "win32"                                         │ sys.platform.startswith("linux")
                 ▼                                                                 ▼
┌──────────────────────────────────────────────┐                  ┌──────────────────────────────────────────────┐
│ Windows Execution Strategy                   │                  │ Linux / POSIX Execution Strategy             │
│ - Rutas: %LOCALAPPDATA%\Programs\Ollama      │                  │ - Rutas: /usr/local/bin, ~/.local/bin, /snap │
│ - Rutas: %USERPROFILE%\.local\bin\uv.exe     │                  │ - Rutas: /usr/bin/uv, ~/.cargo/bin/uv        │
│ - creationflags: CREATE_NEW_PROCESS_GROUP    │                  │ - start_new_session: True                    │
│ - Señal: CTRL_BREAK_EVENT / TerminateProcess │                  │ - Señal: SIGTERM / SIGKILL                   │
└──────────────────────────────────────────────┘                  └──────────────────────────────────────────────┘
```

---

## 3. Matriz Comparativa de Estrategias de Aislamiento de Procesos

| Estrategia de Aislamiento | Compatibilidad OS | Comportamiento Señal SIGTERM | Prevención de Procesos Zombies | Overhead de Creación | Nivel de Seguridad |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`start_new_session=True` (POSIX)** | Linux / macOS / BSD | Aislado en nuevo SID / PGID | Alta (limpieza total con killpg) | $<1\text{ ms}$ | Alto (desacoplado de tty) |
| **`CREATE_NEW_PROCESS_GROUP` (Win32)** | Exclusivo Windows | Ignora Ctrl+C principal; recibe Break | Alta (controlado por Windows OS) | $<2\text{ ms}$ | Alto (aislado de consola) |
| **`subprocess.Popen` sin flags** | Universal | Se propaga señal a hijos directamente | Nula (potencial cuelgue o zombie) | $<1\text{ ms}$ | Bajo |
| **Servicio de Sistema (`systemd`)** | Exclusivo Linux | Administrado por init del sistema | Absoluta | Requiere `sudo` | Máximo (nivel demonio) |
| **Contenedor Docker / OCI** | Universal con runtime | Aislamiento por cgroups y namespaces | Absoluta | $200 - 600\text{ ms}$ | Máximo |

> [!NOTE]
> La combinación de `start_new_session=True` en Linux y `CREATE_NEW_PROCESS_GROUP` en Windows permite que PyDective orqueste el servidor de inferencia local Ollama sin requerir privilegios de superusuario (`sudo`) ni alterar los servicios del sistema operativo anfitrión.

---

## 4. Cuota de Recomendaciones Técnicas

Siguiendo el protocolo estricto de ingeniería, se establecen las siguientes directivas de evolución:

1. **CRÍTICO - Manejador de Salida Limpia (`atexit` y señales POSIX):**
   - Registrar `signal.signal(signal.SIGTERM, handler)` y `signal.signal(signal.SIGINT, handler)` en `run_app.py` para asegurar que el proceso de Ollama reciba `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` antes de que la aplicación finalice.
   - *Fundamento:* Evita que instancias huérfanas de Ollama continúen consumiendo núcleos de CPU tras un reinicio de la aplicación.
2. **RECOMENDADO - Empaquetado de Instalación mediante Makefile / Taskfile:**
   - Crear un `Makefile` universal con targets limpios (`make install`, `make run`, `make test`) compatible con desarrolladores en Linux, WSL y Windows (usando Make o `task`).
   - *Fundamento:* Estandariza la experiencia de desarrollo sin importar el shell predilecto del desarrollador.
3. **RECOMENDADO - Verificación de Soporte AVX/AVX2 en CPU:**
   - Incorporar en `install_dependencies.py` una rutina de sondeo de banderas de CPU (`/proc/cpuinfo` en Linux y registro CPUID en Windows) para advertir al usuario si su hardware carece de extensiones vectoriales AVX2 antes de compilar o ejecutar modelos locales.
   - *Fundamento:* Previene fallos de tipo *Illegal Instruction* al cargar bibliotecas de inferencia profunda en servidores virtuales antiguos.
4. **OPCIONAL - Servicio Systemd de Usuario para Despliegues Linux:**
   - Proveer una plantilla `pydective.service` en `scripts/linux/` para que los administradores de sistemas puedan instalar PyDective como un servicio persistente administrado por `systemctl --user`.
   - *Fundamento:* Facilita despliegues productivos desatendidos en servidores dedicados.
5. **FUTURO - Contenedorización OCI Multi-Arquitectura (AMD64 / ARM64):**
   - Publicar una definición de `Dockerfile` multi-etapa basada en `cgr.dev/chainguard/python` que incluya `uv`, compilación optimizada de OpenCV y Ollama preconfigurado para CPU.
   - *Fundamento:* Asegura reproducibilidad bit a bit en clústeres Kubernetes y entornos cloud soberanos.

---

## 5. Siguientes Pasos

1. Validar la suite completa de pruebas en contenedores Linux Ubuntu 22.04 LTS y 24.04 LTS.
2. Actualizar el archivo `README.md` principal con la guía paso a paso de ejecución en Linux y Windows.
3. Incorporar los requisitos funcionales de portabilidad en la especificación arquitectónica del sistema.
