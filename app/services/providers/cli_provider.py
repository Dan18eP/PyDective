import logging
import os
import shutil
import subprocess
from typing import Optional, List
from pathlib import Path

from app.services.providers.base_provider import BaseLLMProvider
from app.settings import settings

logger = logging.getLogger("pydective.providers.cli")


def _find_executable(cmd: str, extra_paths: Optional[List[str]] = None) -> Optional[str]:
    """Busca el comando en el PATH y en rutas adicionales especificadas."""
    if not cmd:
        return None

    # Si es ruta absoluta o relativa existente
    p = Path(cmd)
    if p.is_file() and os.access(p, os.X_OK):
        return str(p.resolve())

    # Búsqueda en PATH estándar
    found = shutil.which(cmd)
    if found:
        return found

    # Búsqueda en rutas extra
    if extra_paths:
        for ep in extra_paths:
            candidate = Path(ep)
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate.resolve())
            if candidate.is_dir():
                sub = candidate / cmd
                if sub.is_file() and os.access(sub, os.X_OK):
                    return str(sub.resolve())

    return None


class AgyCLIProvider(BaseLLMProvider):
    """
    Proveedor que ejecuta el asistente agy vía terminal CLI (`agy -p '<prompt>'`).
    Aprovecha el modelo de razonamiento y herramientas de Antigravity CLI.
    """

    def __init__(self, bin_path: Optional[str] = None, timeout: Optional[float] = None):
        self._bin_path = bin_path or settings.AGY_BIN_PATH
        self._timeout = timeout or settings.CLI_SUBPROCESS_TIMEOUT_SECONDS
        self._resolved_bin: Optional[str] = None

    @property
    def name(self) -> str:
        return "cli:agy"

    def is_available(self) -> bool:
        extra_search = [
            "/snap/antigravity-cli/22/bin/agy",
            "/snap/bin/agy",
            "/usr/local/bin/agy",
            "/usr/bin/agy",
            str(Path.home() / "bin" / "agy"),
        ]
        resolved = _find_executable(self._bin_path, extra_search)
        if resolved:
            self._resolved_bin = resolved
            return True
        return False

    def generate_chat_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        image_bytes: Optional[bytes] = None,
        image_path: Optional[str] = None,
    ) -> Optional[str]:
        if not self.is_available():
            logger.warning("agy CLI no disponible en el sistema")
            return None

        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"

        # Si hay una imagen provista para análisis detallado, se añade al prompt para agy
        if image_path:
            full_prompt += f"\n\n[IMAGEN ADJUNTA PARA INSPECCIÓN VISUAL DIRECTA]: {image_path}"
        elif image_bytes:
            try:
                import tempfile
                tmp_img = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp_img.write(image_bytes)
                tmp_img.flush()
                tmp_img.close()
                full_prompt += f"\n\n[IMAGEN ADJUNTA PARA INSPECCIÓN VISUAL DIRECTA]: {tmp_img.name}"
            except Exception as e:
                logger.debug(f"No se pudo guardar temporal de imagen para agy: {e}")

        cmd = [
            self._resolved_bin or "agy",
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
            "-p",
            full_prompt,
        ]
        logger.info(f"Ejecutando agy CLI: {self._resolved_bin} con prompt de {len(full_prompt)} caracteres")

        try:
            import tempfile
            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                cwd=tempfile.gettempdir(),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                output = result.stdout.strip()
                if "Authentication required" in output:
                    logger.warning("agy CLI requiere autenticación en terminal. Activando fallback...")
                    return None
                return output
            else:
                stderr_msg = result.stderr.strip() if result.stderr else (result.stdout.strip() if result.stdout else "")
                logger.warning(
                    f"agy terminó con código {result.returncode}. Mensaje: {stderr_msg[:200]}"
                )
                return None
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout al ejecutar agy CLI tras {self._timeout}s")
            return None
        except Exception as exc:
            logger.warning(f"Excepción al invocar agy CLI: {exc}")
            return None


class OpenCodeCLIProvider(BaseLLMProvider):
    """
    Proveedor que ejecuta opencode vía terminal CLI.
    Soporta rutas del sistema y fallback a la carpeta local bin/ del proyecto.
    """

    def __init__(self, bin_path: Optional[str] = None, timeout: Optional[float] = None):
        self._bin_path = bin_path or settings.OPENCODE_BIN_PATH
        self._timeout = timeout or settings.CLI_SUBPROCESS_TIMEOUT_SECONDS
        self._resolved_bin: Optional[str] = None

    @property
    def name(self) -> str:
        return "cli:opencode"

    def is_available(self) -> bool:
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        extra_search = [
            str(project_root / "bin" / "opencode"),
            str(project_root / "opencode"),
            "/home/cohorte5/.opencode/bin/opencode",
            "/usr/local/bin/opencode",
            "/usr/bin/opencode",
            str(Path.home() / ".opencode" / "bin" / "opencode"),
        ]
        resolved = _find_executable(self._bin_path, extra_search)
        if resolved:
            self._resolved_bin = resolved
            return True
        return False

    def generate_chat_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        image_bytes: Optional[bytes] = None,
        image_path: Optional[str] = None,
    ) -> Optional[str]:
        if not self.is_available():
            logger.warning("opencode CLI no disponible en el sistema")
            return None

        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"

        if image_path:
            full_prompt += f"\n\n[IMAGEN ADJUNTA PARA INSPECCIÓN VISUAL]: {image_path}"
        elif image_bytes:
            try:
                import tempfile
                tmp_img = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp_img.write(image_bytes)
                tmp_img.flush()
                tmp_img.close()
                full_prompt += f"\n\n[IMAGEN ADJUNTA PARA INSPECCIÓN VISUAL]: {tmp_img.name}"
            except Exception as e:
                logger.debug(f"No se pudo guardar temporal para opencode: {e}")

        # Sintaxis oficial no interactiva de OpenCode: `opencode run "<prompt>"`
        cmd = [self._resolved_bin or "opencode", "run", full_prompt]
        logger.info(f"Ejecutando opencode CLI: {self._resolved_bin}")

        try:
            import tempfile
            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                cwd=tempfile.gettempdir(),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                raw_output = result.stdout.strip()
                # Filtrar encabezados de sesión de terminal como '> build · model-name'
                lines = raw_output.splitlines()
                clean_lines = [
                    l for l in lines 
                    if not (l.startswith("> ") and ("build" in l or "run" in l))
                ]
                output = "\n".join(clean_lines).strip()
                return output or raw_output
            
            # Reintento alternativo con flag '-p' por si se usa un wrapper shim
            cmd_alt = [self._resolved_bin or "opencode", "-p", full_prompt]
            result_alt = subprocess.run(
                cmd_alt,
                stdin=subprocess.DEVNULL,
                cwd=tempfile.gettempdir(),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
            if result_alt.returncode == 0 and result_alt.stdout:
                return result_alt.stdout.strip()

            logger.warning(
                f"opencode falló con código {result.returncode}. Stderr: {result.stderr.strip()[:200]}"
            )
            return None
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout al ejecutar opencode CLI tras {self._timeout}s")
            return None
        except Exception as exc:
            logger.warning(f"Excepción al invocar opencode CLI: {exc}")
            return None
