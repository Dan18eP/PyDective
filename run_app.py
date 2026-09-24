#!/usr/bin/env python3
"""
PyDective - Script de Arranque del Servidor y Aplicacion
Inicia la API FastAPI con Uvicorn, verifica la configuracion del entorno,
gestiona el ciclo de vida del modelo LLM local (Ollama), comprueba los motores
de vision (RapidOCR / Florence-2) y muestra las rutas de acceso del sistema.
Compatible con entornos Linux (Ubuntu, Debian, Fedora, Arch) y Windows.
"""

import sys
import os
import time
import json
import shutil
import platform
import subprocess
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def find_uv_executable() -> str | None:
    # 1. Busqueda en PATH del sistema
    for name in ("uv", "uv.exe"):
        uv_path = shutil.which(name)
        if uv_path:
            return uv_path

    # 2. Rutas estandar en Linux / macOS / Windows
    user_home = Path.home()
    is_windows = sys.platform == "win32"
    candidates = [
        user_home / ".local" / "bin" / ("uv.exe" if is_windows else "uv"),
        user_home / ".cargo" / "bin" / ("uv.exe" if is_windows else "uv"),
        user_home / ".local" / "bin" / "uv",
        user_home / ".cargo" / "bin" / "uv",
        Path("/usr/local/bin/uv"),
        Path("/usr/bin/uv"),
        Path("/snap/bin/uv"),
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)

    return None


def find_ollama_executable() -> str | None:
    """Busca el ejecutable de Ollama en el PATH o en rutas estandar de Windows/Linux."""
    for name in ("ollama", "ollama.exe"):
        bin_path = shutil.which(name)
        if bin_path:
            return bin_path

    # Rutas estandar en Linux
    for linux_path in ("/usr/local/bin/ollama", "/usr/bin/ollama", "/bin/ollama", "/snap/bin/ollama"):
        cand_linux = Path(linux_path)
        if cand_linux.exists():
            return str(cand_linux)

    # Rutas estandar en Windows
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        cand = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if cand.exists():
            return str(cand)

    for env_var in ("ProgramFiles", "ProgramFiles(x86)"):
        pf = os.environ.get(env_var)
        if pf:
            cand = Path(pf) / "Ollama" / "ollama.exe"
            if cand.exists():
                return str(cand)

    return None


def is_ollama_running(base_url: str = "http://localhost:11434") -> bool:
    """Comprueba si el servidor local de Ollama esta respondiendo peticiones HTTP."""
    try:
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/tags",
            headers={"User-Agent": "PyDective-Healthcheck"},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_local_llm_service(model_name: str = "qwen2.5:3b") -> subprocess.Popen | None:
    """
    Verifica si el servidor de inferencia local esta activo.
    Si no esta corriendo, intenta iniciarlo automaticamente en segundo plano.
    Retorna el proceso Popen si fue creado por este script, o None si ya existia.
    """
    print("\n[PyDective LLM] Verificando estado del motor de inferencia local...")

    if is_ollama_running():
        print("  [ONLINE]  Servidor Ollama:     Activo en http://localhost:11434")
        _check_and_warm_model(model_name)
        return None

    ollama_bin = find_ollama_executable()
    if not ollama_bin:
        print("  [AVISO]   Servidor Ollama:     No encontrado en el sistema")
        print("                                 (El sistema operará en modo Cero-IA o con Gemini Cloud)")
        return None

    print(f"  [INICIO]  Servidor Ollama:     Iniciando daemon local ({ollama_bin} serve)...")
    try:
        creation_flags = 0
        start_new_session = False
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            start_new_session = True

        proc = subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
            start_new_session=start_new_session,
        )

        # Esperar hasta 6.0 segundos a que el servidor comience a responder
        t_start = time.perf_counter()
        ready = False
        while time.perf_counter() - t_start < 6.0:
            time.sleep(0.3)
            if is_ollama_running():
                ready = True
                break

        if ready:
            print("  [ONLINE]  Servidor Ollama:     Conexion establecida con exito en localhost:11434")
            _check_and_warm_model(model_name, ollama_bin=ollama_bin)
            return proc
        else:
            print("  [AVISO]   Servidor Ollama:     Iniciado, esperando estabilizacion en segundo plano")
            return proc
    except Exception as exc:
        print(f"  [ERROR]   Servidor Ollama:     No se pudo iniciar automaticamente ({exc})")
        return None


def _check_and_warm_model(model_name: str, ollama_bin: str | None = None) -> str:
    """Verifica si el modelo especificado se encuentra descargado en el catalogo local."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode())
            installed = [m.get("name", "") for m in data.get("models", [])]

            has_model = any(
                model_name in m or m.startswith(model_name.split(":")[0])
                for m in installed
            )

            if has_model:
                print(f"  [ONLINE]  Modelo Local:        '{model_name}' disponible en catalogo")
                return model_name
            else:
                # Usar modelo instalado existente para evitar bloqueo de descarga en arranque
                usable_models = [m for m in installed if not m.startswith("bge")]
                if usable_models:
                    fallback_model = usable_models[0]
                    print(f"  [ONLINE]  Modelo Local:        '{fallback_model}' (auto-seleccionado de modelos instalados)")
                    from app.settings import settings
                    settings.LOCAL_LLM_MODEL = fallback_model
                    return fallback_model
                else:
                    print(f"  [AVISO]   Modelo Local:        '{model_name}' no detectado en catalogo local")
                    print(f"  [LLM] Para descargarlo ejecuta: ollama pull {model_name}")
    except Exception:
        pass
    return model_name


def check_vision_engines():
    """Comprueba el estado de los motores de vision configurados en PyDective."""
    print("\n[PyDective Vision] Verificando motores de extraccion y vision...")

    # 1. RapidOCR ONNX
    try:
        from app.services.ocr_service import get_ocr_engine
        engine = get_ocr_engine()
        if engine:
            print("  [ONLINE]  RapidOCR ONNX:       Listo (Aceleracion C++/AVX2 ~120ms)")
        else:
            print("  [AVISO]   RapidOCR ONNX:       No inicializado")
    except Exception as exc:
        print(f"  [AVISO]   RapidOCR ONNX:       Error al comprobar ({exc})")

    # 2. Microsoft Florence-2
    try:
        import torch
        import transformers
        print(f"  [ONLINE]  Florence-2 VLM:      Listo (PyTorch {torch.__version__} en CPU, Transformers {transformers.__version__})")
    except Exception as exc:
        print(f"  [AVISO]   Florence-2 VLM:      Dependencias de vision no detectadas ({exc})")


def show_banner(host: str, port: int, provider_desc: str):
    print("\n" + "=" * 70)
    print("               PyDective - Motor Forense Documental               ")
    print("=" * 70)
    print(f"  * Servidor API:        http://{host}:{port}")
    print(f"  * Interfaz Web:        http://{host}:{port}/")
    print(f"  * Documentacion API:   http://{host}:{port}/docs")
    print(f"  * Motor OCR:           RapidOCR ONNX (C++/AVX2 ~120 ms)")
    print(f"  * Motor VLM:           Microsoft Florence-2 (230M en CPU)")
    print(f"  * Proveedor Chat/LLM:  {provider_desc}")
    print(f"  * Modos Disponibles:   RapidOCR | Florence-2 | Benchmark Dual (A/B)")
    print("=" * 70)
    print("  [INFO] Presiona CTRL + C en cualquier momento para detener el servidor.\n")


def main():
    # Asegurar que el directorio raiz del proyecto este en el PYTHONPATH
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

    # Cargar configuracion del proyecto
    try:
        from app.settings import settings
        from app.services.providers import get_llm_provider
    except ImportError as e:
        print("\n[ERROR] No se pudieron importar las dependencias del proyecto:")
        print(f"        {e}")
        print("\nPor favor, ejecuta primero el instalador:")
        print("        python install_dependencies.py\n")
        sys.exit(1)

    # 1. Gestion del ciclo de vida del modelo LLM local (Ollama)
    ollama_process = None
    target_provider = settings.LLM_PROVIDER.lower()
    if target_provider in ("auto", "local"):
        ollama_process = ensure_local_llm_service(model_name=settings.LOCAL_LLM_MODEL)

    # 2. Verificacion de motores de vision
    check_vision_engines()

    host = settings.HOST or "0.0.0.0"
    port = settings.PORT or 8000
    debug_mode = settings.DEBUG

    # Determinar informacion del proveedor de LLM activo
    try:
        prov = get_llm_provider()
        prov_status = "[ONLINE]" if prov.is_available() else "[MODO CERO-IA]"
        prov_desc = f"{prov.name} {prov_status}"
    except Exception:
        prov_desc = "Modo heuristico nativo (Cero-IA)"

    show_banner(host=host if host != "0.0.0.0" else "localhost", port=port, provider_desc=prov_desc)

    uv_bin = find_uv_executable()

    try:
        import uvicorn
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=debug_mode,
        )
    except ImportError:
        if uv_bin:
            cmd = [
                uv_bin,
                "run",
                "uvicorn",
                "app.main:app",
                "--host",
                host,
                "--port",
                str(port),
            ]
            if debug_mode:
                cmd.append("--reload")
            subprocess.run(cmd, cwd=str(ROOT_DIR))
        else:
            print("[PyDective] Error: uvicorn no encontrado.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n[PyDective] Deteniendo el servidor por solicitud del usuario...")
    finally:
        if ollama_process is not None:
            print("[PyDective] Liberando recursos del proceso Ollama iniciado...")
            try:
                ollama_process.terminate()
                ollama_process.wait(timeout=3.0)
            except Exception:
                ollama_process.kill()
        print("[PyDective] Servidor detenido. Hasta pronto.\n")


if __name__ == "__main__":
    main()
