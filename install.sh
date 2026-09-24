#!/usr/bin/env bash
set -e

# PyDective - Instalador de dependencias para Linux / POSIX
echo "======================================================================"
echo "       PyDective - Instalador de Dependencias (Linux / POSIX)         "
echo "======================================================================"

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "[ERROR] Python no encontrado en el sistema. Instala Python 3.12 o superior."
    exit 1
fi

$PYTHON_BIN install_dependencies.py "$@"
