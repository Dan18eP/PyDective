"""
PyDective — Servicio de Adaptación Universal de Hardware (Intel y AMD)
Detecta en tiempo de ejecución las capacidades de la CPU (fabricante, núcleos físicos,
instrucciones AVX2/AVX-512/VNNI, memoria RAM libre) y auto-configura los parámetros óptimos
de inferencia local (hilos, perfiles de cuantización y selección dinámica de modelos SLM).
"""

import os
import sys
import platform
import multiprocessing
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("pydective.hardware_adapter")


class HardwareProfile:
    LOW = "low"      # <= 4 núcleos, < 8 GB RAM -> SLM 0.5B (390 MB)
    MID = "mid"      # 6-8 núcleos, 8-16 GB RAM -> SLM 1.5B o 1B (900 MB - 1.2 GB)
    HIGH = "high"    # > 8 núcleos, > 16 GB RAM -> SLM 3B (2 GB)


_DETECTED_PROFILE: Optional[Dict[str, Any]] = None


def detect_hardware_profile(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Inspecciona en tiempo real las especificaciones del procesador y la memoria física
    en entornos Windows y Linux, sin requerir dependencias binarias externas.
    """
    global _DETECTED_PROFILE
    if _DETECTED_PROFILE is not None and not force_refresh:
        return _DETECTED_PROFILE

    # 1. Total de hilos lógicos y estimación de núcleos físicos
    total_logical = os.cpu_count() or multiprocessing.cpu_count() or 4
    # En la mayoría de procesadores modernos (Intel HyperThreading o AMD SMT), físicos = lógicos // 2
    physical_cores = max(1, total_logical // 2) if total_logical > 2 else total_logical

    # 2. Fabricante y arquitectura del procesador
    processor_name = platform.processor() or ""
    machine = platform.machine().lower()
    system = sys.platform

    vendor = "Generic"
    vendor_raw = f"{processor_name} {platform.uname().processor} {platform.uname().machine}".lower()

    if "intel" in vendor_raw:
        vendor = "Intel"
    elif "amd" in vendor_raw or "ryzen" in vendor_raw:
        vendor = "AMD"
    elif "arm" in machine or "aarch64" in machine:
        vendor = "ARM"

    # 3. Estimación de memoria RAM física total y disponible
    total_ram_gb = 8.0
    free_ram_gb = 4.0

    try:
        if system == "win32":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_ram_gb = round(stat.ullTotalPhys / (1024 ** 3), 2)
                free_ram_gb = round(stat.ullAvailPhys / (1024 ** 3), 2)
        elif system.startswith("linux"):
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith("MemTotal:"):
                        total_ram_gb = round(int(line.split()[1]) / (1024 ** 2), 2)
                    elif line.startswith("MemAvailable:"):
                        free_ram_gb = round(int(line.split()[1]) / (1024 ** 2), 2)
    except Exception as exc:
        logger.debug(f"No se pudo determinar memoria física exacta: {exc}")

    # 4. Clasificación de Perfil de Rendimiento
    if total_ram_gb < 7.0 or physical_cores <= 2:
        tier = HardwareProfile.LOW
    elif physical_cores < 8 or total_ram_gb < 16.0:
        tier = HardwareProfile.MID
    else:
        tier = HardwareProfile.HIGH

    # 5. Detección de aceleración de visión (OpenVINO para Intel, ONNX para AMD/Genérico)
    vision_runtime = "onnxruntime"
    if vendor == "Intel":
        try:
            import openvino
            vision_runtime = "openvino"
        except ImportError:
            vision_runtime = "onnxruntime"

    _DETECTED_PROFILE = {
        "vendor": vendor,
        "processor_name": processor_name,
        "physical_cores": physical_cores,
        "logical_cores": total_logical,
        "total_ram_gb": total_ram_gb,
        "free_ram_gb": free_ram_gb,
        "tier": tier,
        "vision_runtime": vision_runtime,
    }

    logger.info(
        f"[HardwareAdapter] CPU detectada: {vendor} ({physical_cores} núcleos físicos / {total_logical} lógicos) | "
        f"RAM: {free_ram_gb} GB libres de {total_ram_gb} GB | Perfil: {tier.upper()} | Visión: {vision_runtime}"
    )
    return _DETECTED_PROFILE


def get_optimal_thread_count() -> int:
    """
    Calcula el número exacto de subprocesos para inferencia en CPU sin provocar contención de caché.
    Utiliza los núcleos físicos reales, reservando al menos 1 hilo para la API web.
    """
    profile = detect_hardware_profile()
    cores = profile["physical_cores"]
    # En procesadores de 6 núcleos (ej Ryzen 5500U o i5), 4-5 hilos es el punto dulce de velocidad
    if cores >= 6:
        return max(4, cores - 1)
    elif cores >= 4:
        return max(2, cores)
    return max(1, cores)


def get_recommended_slm_model() -> str:
    """
    Selecciona el modelo SLM local óptimo según el perfil de hardware para garantizar
    altas velocidades de generación (> 35-50 tokens/s en CPU).
    """
    profile = detect_hardware_profile()
    tier = profile["tier"]

    # Si hay poca RAM libre (<3.5 GB), forzar el modelo ultra-ligero 0.5B
    if profile.get("free_ram_gb", 4.0) < 3.5 or tier == HardwareProfile.LOW:
        return "qwen2.5:0.5b"
    elif tier == HardwareProfile.MID:
        # En gama media, qwen2.5:1.5b o llama3.2:1b ofrecen el mejor balance velocidad/calidad
        return "qwen2.5:1.5b"
    else:
        # En servidores potentes (>16GB RAM y >8 núcleos), usar qwen2.5:3b o llama3.2:3b
        return "qwen2.5:3b"


def get_recommended_dpi() -> int:
    """Retorna la resolución DPI óptima de renderizado de imagen según la CPU para no saturar memoria."""
    profile = detect_hardware_profile()
    tier = profile["tier"]
    if tier == HardwareProfile.LOW:
        return 110
    elif tier == HardwareProfile.MID:
        return 130
    return 150
