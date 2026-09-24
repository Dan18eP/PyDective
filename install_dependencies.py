#!/usr/bin/env python3
"""
PyDective - Script de Instalacion Automatizada de Dependencias
Verifica el entorno de ejecucion, detecta gestores (uv / pip), instala las librerias
requeridas segun pyproject.toml y configura el entorno de trabajo y motores de vision.
Compatible con entornos Linux (Ubuntu, Debian, Fedora, Arch) y Windows.
"""

import sys
import os
import shutil
import platform
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
    print_step("Verificando version de Python...")
    major, minor = sys.version_info.major, sys.version_info.minor
    if major < 3 or (major == 3 and minor < 12):
        print_error(
            f"Se requiere Python 3.12 o superior. Version detectada: {major}.{minor}.{sys.version_info.micro}"
        )
        sys.exit(1)
    print_ok(f"Python {major}.{minor}.{sys.version_info.micro} detectado (compatible)")


def check_system_platform():
    print_step("Detectando sistema operativo y arquitectura...")
    os_name = platform.system()
    arch = platform.machine()
    print_ok(f"Plataforma detectada: {os_name} ({arch})")

    if sys.platform.startswith("linux"):
        print_ok("Modo Linux/POSIX activo.")
        uv_bin = find_uv_executable()
        if not uv_bin:
            print_warn("Gestor 'uv' no detectado en PATH. Puedes instalarlo con:")
            print_warn("  curl -LsSf https://astral.sh/uv/install.sh | sh")
            print_warn("O reiniciar tu terminal si ya lo instalaste previamente.")


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


def setup_environment_files():
    print_step("Configurando estructura de directorios y variables de entorno...")

    # Crear directorios de datos requeridos por el sistema
    directories = [
        ROOT_DIR / "data" / "uploads",
        ROOT_DIR / "data" / "results",
        ROOT_DIR / "data" / "cache",
        ROOT_DIR / "data" / "temp",
    ]
    for d in directories:
        d.mkdir(parents=True, exist_ok=True)
    print_ok("Directorios de almacenamiento en 'data/' verificados y listos")

    # Copiar .env si no existe
    env_file = ROOT_DIR / ".env"
    env_example = ROOT_DIR / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copy(env_example, env_file)
        print_ok("Archivo '.env' creado a partir de '.env.example'")
    elif env_file.exists():
        print_ok("Archivo '.env' ya existente")


def install_dependencies():
    print_step("Instalando dependencias de produccion, pruebas y motores de vision...")

    uv_bin = find_uv_executable()
    if uv_bin:
        print_ok(f"Gestor ultra-rapido 'uv' localizado en: {uv_bin}")
        cmd = [uv_bin, "sync"]
        print(f"Ejecutando: {' '.join(cmd)}")
        res = subprocess.run(cmd, cwd=str(ROOT_DIR))
        if res.returncode != 0:
            print_warn("'uv sync' falló, intentando con 'uv pip install -e .'...")
            res = subprocess.run([uv_bin, "pip", "install", "-e", "."], cwd=str(ROOT_DIR))
            if res.returncode != 0:
                print_error("Fallo durante la instalacion con uv.")
                sys.exit(res.returncode)
    else:
        print_warn("No se encontró 'uv'. Utilizando 'pip' estándar de Python...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], cwd=str(ROOT_DIR))
        cmd = [sys.executable, "-m", "pip", "install", "-e", "."]
        print(f"Ejecutando: {' '.join(cmd)}")
        res = subprocess.run(cmd, cwd=str(ROOT_DIR))
        if res.returncode != 0:
            print_error("Fallo durante la instalacion con pip.")
            sys.exit(res.returncode)

    print_ok("Todas las dependencias base se instalaron correctamente")


def verify_installation():
    print_step("Comprobando importacion de modulos criticos y motores de vision...")
    modules_to_test = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("pymupdf", "PyMuPDF"),
        ("docx", "python-docx"),
        ("openpyxl", "openpyxl"),
        ("PIL", "Pillow"),
        ("httpx", "HTTPX"),
        ("pydantic", "Pydantic"),
        ("rapidocr_onnxruntime", "RapidOCR ONNX Runtime"),
        ("torch", "PyTorch (CPU)"),
        ("transformers", "HuggingFace Transformers"),
        ("timm", "Timm Vision Models"),
        ("einops", "Einops Tensor Ops"),
    ]

    uv_bin = find_uv_executable()
    runner = [uv_bin, "run", "python"] if uv_bin else [sys.executable]

    for mod, name in modules_to_test:
        test_cmd = runner + ["-c", f"import {mod}; print('OK')"]
        res = subprocess.run(test_cmd, capture_output=True, text=True, cwd=str(ROOT_DIR))
        if res.returncode == 0:
            print_ok(f"Modulo '{name}' verificado.")
        else:
            print_warn(f"Modulo '{name}' no pudo ser importado directamente: {res.stderr.strip()[:100]}")


def verify_vision_engines():
    print_step("Comprobando disponibilidad de motores de vision...")

    uv_bin = find_uv_executable()
    runner = [uv_bin, "run", "python"] if uv_bin else [sys.executable]

    # 1. Comprobar RapidOCR
    check_rapid_cmd = runner + [
        "-c",
        "from app.services.ocr_service import get_ocr_engine; engine = get_ocr_engine(); print('RAPIDOCR_READY' if engine else 'RAPIDOCR_NONE')",
    ]
    res_rapid = subprocess.run(check_rapid_cmd, capture_output=True, text=True, cwd=str(ROOT_DIR))
    if "RAPIDOCR_READY" in res_rapid.stdout:
        print_ok("Motor RapidOCR ONNX: Listo (Aceleracion C++/AVX2 en CPU)")
    else:
        print_warn(f"Motor RapidOCR ONNX: Advertencia ({res_rapid.stderr.strip()[:80]})")

    # 2. Comprobar PyTorch CPU y compatibilidad con Florence-2
    check_torch_cmd = runner + [
        "-c",
        "import torch; print(f'TORCH_VERSION={torch.__version__},CUDA_AVAILABLE={torch.cuda.is_available()}')",
    ]
    res_torch = subprocess.run(check_torch_cmd, capture_output=True, text=True, cwd=str(ROOT_DIR))
    if res_torch.returncode == 0 and "TORCH_VERSION" in res_torch.stdout:
        print_ok(f"Motor PyTorch CPU: Listo ({res_torch.stdout.strip()})")
    else:
        print_warn("Motor PyTorch CPU: No detectado o requiere configuracion")


def main():
    print("=" * 70)
    print("       PyDective - Asistente de Instalacion de Dependencias       ")
    print("=" * 70)

    check_python_version()
    check_system_platform()
    setup_environment_files()
    install_dependencies()
    verify_installation()
    verify_vision_engines()

    print("\n" + "=" * 70)
    print("  [EXITO] Instalacion y verificacion completadas correctamente.")
    print("  Para iniciar el servidor y la interfaz ejecuta:")
    print("      python run.py")
    print("  O directamente con Uvicorn:")
    print("      python run_app.py")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
