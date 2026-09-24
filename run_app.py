#!/usr/bin/env python
"""
PyDective — Script de Arranque del Servidor y Aplicación
Inicia la API FastAPI con Uvicorn, verifica la configuración del entorno,
gestiona el ciclo de vida del modelo LLM local (Ollama) y muestra las rutas de acceso.
"""

import sys
import os
import time
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent


def find_uv_executable() -> str | None:
    uv_path = shutil.which("uv")
    if uv_path:
        return uv_path

    user_home = Path.home()
    cand_windows = user_home / ".local" / "bin" / "uv.exe"
    if cand_windows.exists():
        return str(cand_windows)

    cand_cargo = user_home / ".cargo" / "bin" / "uv.exe"
    if cand_cargo.exists():
        return str(cand_cargo)

    return None


def find_ollama_executable() -> str | None:
    """Busca el ejecutable de Ollama en el PATH o en rutas estándar de Windows/Linux."""
    bin_path = shutil.which("ollama")
    if bin_path:
        return bin_path

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
    """Comprueba si el servidor local de Ollama está respondiendo peticiones HTTP."""
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
    Verifica si el servidor de inferencia local está activo.
    Si no está corriendo, intenta iniciarlo automáticamente en segundo plano.
    Retorna el proceso Popen si fue creado por este script, o None si ya existía.
    """
    print("\n[PyDective LLM] Verificando estado del motor de inferencia local...")

    if is_ollama_running():
        print("  • Servidor Ollama:     Activo en http://localhost:11434 ✅")
        _check_and_warm_model(model_name)
        return None

    ollama_bin = find_ollama_executable()
    if not ollama_bin:
        print("  • Servidor Ollama:     No encontrado en el sistema ⚠️")
        print("                         (El sistema operará en modo Cero-IA o con Gemini Cloud)")
        return None

    print(f"  • Servidor Ollama:     Iniciando daemon local ({ollama_bin} serve)...")
    try:
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
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
            print("  • Servidor Ollama:     Conexión establecida con éxito en localhost:11434 ✅")
            _check_and_warm_model(model_name, ollama_bin=ollama_bin)
            return proc
        else:
            print("  • Servidor Ollama:     Iniciado, esperando estabilización en background ⏳")
            return proc
    except Exception as exc:
        print(f"  • Servidor Ollama:     No se pudo iniciar automáticamente ({exc}) ⚠️")
        return None


def _check_and_warm_model(model_name: str, ollama_bin: str | None = None):
    """Verifica si el modelo especificado se encuentra descargado en el catálogo local."""
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
                print(f"  • Modelo Local:        '{model_name}' disponible en catálogo ✅")
            else:
                print(f"  • Modelo Local:        '{model_name}' no detectado en catálogo local ⚠️")
                bin_to_use = ollama_bin or find_ollama_executable()
                if bin_to_use:
                    print(f"  [LLM] Descargando modelo '{model_name}' vía Ollama...")
                    subprocess.run([bin_to_use, "pull", model_name], check=False)
                else:
                    print(f"  [LLM] Para descargarlo manualmente ejecuta: ollama pull {model_name}")
    except Exception:
        pass


def show_banner(host: str, port: int, provider_desc: str):
    print("\n" + "=" * 70)
    print("               🔍  PyDective — Motor Forense Documental  🔍            ")
    print("=" * 70)
    print(f"  • Servidor API:        http://{host}:{port}")
    print(f"  • Visor Interactivo:   http://{host}:{port}/visor")
    print(f"  • Documentación OpenAPI: http://{host}:{port}/docs")
    print(f"  • Proveedor LLM:       {provider_desc}")
    print("=" * 70)
    print("  [INFO] Presiona CTRL + C en cualquier momento para detener el servidor.\n")


def main():
    # Asegurar que el directorio raíz del proyecto esté en el PYTHONPATH
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

    # Cargar configuración del proyecto
    try:
        from app.settings import settings
        from app.services.providers import get_llm_provider
    except ImportError as e:
        print("\n[ERROR] No se pudieron importar las dependencias del proyecto:")
        print(f"        {e}")
        print("\nPor favor, ejecuta primero el instalador:")
        print("        python install_dependencies.py\n")
        sys.exit(1)

    # 1. Gestión del ciclo de vida del modelo LLM local (Ollama)
    ollama_process = None
    target_provider = settings.LLM_PROVIDER.lower()
    if target_provider in ("auto", "local"):
        ollama_process = ensure_local_llm_service(model_name=settings.LOCAL_LLM_MODEL)

    host = settings.HOST or "0.0.0.0"
    port = settings.PORT or 8000
    debug_mode = settings.DEBUG

    # Determinar información del proveedor de LLM activo
    try:
        prov = get_llm_provider()
        prov_status = "En línea ✅" if prov.is_available() else "No detectado (Modo local estricto Cero-IA activo) ⚠️"
        prov_desc = f"{prov.name} ({prov_status})"
    except Exception:
        prov_desc = "Modo heurístico nativo (Cero-IA)"

    show_banner(host=host if host != "0.0.0.0" else "localhost", port=port, provider_desc=prov_desc)

    uv_bin = find_uv_executable()

    try:
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
            import uvicorn
            uvicorn.run(
                "app.main:app",
                host=host,
                port=port,
                reload=debug_mode,
            )
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
        print("[PyDective] ¡Servidor detenido! Hasta pronto.\n")


if __name__ == "__main__":
    main()
