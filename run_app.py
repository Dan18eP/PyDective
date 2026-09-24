#!/usr/bin/env python
"""
PyDective — Script de Arranque del Servidor y Aplicación
Inicia la API FastAPI con Uvicorn, verifica la configuración del entorno,
resuelve el proveedor de LLM activo y muestra las rutas de acceso principales.
"""

import sys
import shutil
import subprocess
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

    host = settings.HOST or "0.0.0.0"
    port = settings.PORT or 8000
    debug_mode = settings.DEBUG

    # Determinar información del proveedor de LLM
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
            # Ejecutar a través de 'uv run' para garantizar el entorno virtual gestionado
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
        print("\n\n[PyDective] Servidor detenido por el usuario. ¡Hasta pronto!\n")


if __name__ == "__main__":
    main()
