#!/usr/bin/env python
"""
PyDective — Script de Instalación Automatizada de Dependencias
Verifica el entorno de ejecución, detecta gestores (uv / pip), instala las librerías
requeridas según pyproject.toml y configura el entorno de trabajo.
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent


def print_step(msg: str):
    print(f"\n[PyDective Setup] ===> {msg}")


def print_ok(msg: str):
    print(f"  [OK] {msg}")


def print_warn(msg: str):
    print(f"  [WARN] {msg}")


def print_error(msg: str):
    print(f"  [ERROR] {msg}")


def check_python_version():
    print_step("Verificando versión de Python...")
    major, minor = sys.version_info.major, sys.version_info.minor
    if major < 3 or (major == 3 and minor < 12):
        print_error(
            f"Se requiere Python 3.12 o superior. Versión detectada: {major}.{minor}.{sys.version_info.micro}"
        )
        sys.exit(1)
    print_ok(f"Python {major}.{minor}.{sys.version_info.micro} detectado (compatible)")


def find_uv_executable() -> str | None:
    # 1. En PATH
    uv_path = shutil.which("uv")
    if uv_path:
        return uv_path

    # 2. Rutas comunes en Windows
    user_home = Path.home()
    cand_windows = user_home / ".local" / "bin" / "uv.exe"
    if cand_windows.exists():
        return str(cand_windows)

    cand_cargo = user_home / ".cargo" / "bin" / "uv.exe"
    if cand_cargo.exists():
        return str(cand_cargo)

    return None


def setup_environment_files():
    print_step("Configurando estructura de directorios y variables de entorno...")

    # Crear directorios de datos
    uploads_dir = ROOT_DIR / "data" / "uploads"
    results_dir = ROOT_DIR / "data" / "results"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    print_ok("Directorios 'data/uploads' y 'data/results' listos")

    # Copiar .env si no existe
    env_file = ROOT_DIR / ".env"
    env_example = ROOT_DIR / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copy(env_example, env_file)
        print_ok("Archivo '.env' creado a partir de '.env.example'")
    elif env_file.exists():
        print_ok("Archivo '.env' ya existente")


def install_dependencies():
    print_step("Instalando dependencias de producción y pruebas...")

    uv_bin = find_uv_executable()
    if uv_bin:
        print_ok(f"Gestor ultra-rápido 'uv' localizado en: {uv_bin}")
        cmd = [uv_bin, "sync"]
        print(f"Ejecutando: {' '.join(cmd)}")
        res = subprocess.run(cmd, cwd=str(ROOT_DIR))
        if res.returncode != 0:
            print_warn("'uv sync' falló, intentando con 'uv pip install -e .'...")
            res = subprocess.run([uv_bin, "pip", "install", "-e", "."], cwd=str(ROOT_DIR))
            if res.returncode != 0:
                print_error("Fallo durante la instalación con uv.")
                sys.exit(res.returncode)
    else:
        print_warn("No se encontró 'uv'. Utilizando 'pip' estándar de Python...")
        # Actualizar pip primero
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], cwd=str(ROOT_DIR))
        # Instalar dependencias en modo editable
        cmd = [sys.executable, "-m", "pip", "install", "-e", "."]
        print(f"Ejecutando: {' '.join(cmd)}")
        res = subprocess.run(cmd, cwd=str(ROOT_DIR))
        if res.returncode != 0:
            print_error("Fallo durante la instalación con pip.")
            sys.exit(res.returncode)

    print_ok("Todas las dependencias se instalaron correctamente")


def verify_installation():
    print_step("Comprobando importación de módulos críticos...")
    modules_to_test = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("pymupdf", "PyMuPDF"),
        ("docx", "python-docx"),
        ("openpyxl", "openpyxl"),
        ("PIL", "Pillow"),
        ("httpx", "HTTPX"),
        ("pydantic", "Pydantic"),
    ]

    uv_bin = find_uv_executable()
    runner = [uv_bin, "run", "python"] if uv_bin else [sys.executable]

    for mod, name in modules_to_test:
        test_cmd = runner + ["-c", f"import {mod}; print('OK')"]
        res = subprocess.run(test_cmd, capture_output=True, text=True, cwd=str(ROOT_DIR))
        if res.returncode == 0:
            print_ok(f"Módulo '{name}' verificado.")
        else:
            print_warn(f"Módulo '{name}' no pudo ser importado directamente: {res.stderr.strip()[:100]}")


def main():
    print("=" * 65)
    print("       PyDective — Asistente de Instalación de Dependencias       ")
    print("=" * 65)

    check_python_version()
    setup_environment_files()
    install_dependencies()
    verify_installation()

    print("\n" + "=" * 65)
    print("  ¡Instalación completada con éxito!")
    print("  Ahora puedes iniciar el programa ejecutando:")
    print("      python run_app.py")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
