from typing import List, Optional, Dict, Any, Callable, TypeVar, Tuple
import time
import threading
import logging
from pydantic import BaseModel, Field

from app.domain.enums import EstadoKey
from app.settings import settings

logger = logging.getLogger("pydective.key_pool")
T = TypeVar("T")


class KeyStatus(BaseModel):
    key: str
    status: EstadoKey = EstadoKey.HEALTHY
    cooldown_until: float = 0.0
    last_used: float = 0.0
    error_count: int = 0


class KeyPoolManager:
    """
    Gestión de salud de API keys y failover aislado por página (US-18).
    - Estados: HEALTHY, COOLDOWN, EXHAUSTED, INVALID.
    - Cooldown transitorio (60s) ante HTTP 429 / RESOURCE_EXHAUSTED.
    - Exclusión permanente ante quota exceeded (EXHAUSTED).
    - Rotación y reintento inmediato por página individual.
    """
    def __init__(self, api_keys: Optional[List[str]] = None):
        self._lock = threading.Lock()
        keys_list = api_keys if api_keys is not None else settings.api_keys_list
        self._keys: Dict[str, KeyStatus] = {
            k: KeyStatus(key=k) for k in keys_list
        }

    def add_key(self, key: str) -> None:
        with self._lock:
            if key not in self._keys:
                self._keys[key] = KeyStatus(key=key)

    def get_healthy_key(self) -> Optional[str]:
        """
        Retorna la siguiente clave disponible en estado HEALTHY.
        Restaura claves en COOLDOWN cuyo tiempo haya expirado.
        """
        now = time.time()
        with self._lock:
            if not self._keys and settings.api_keys_list:
                for k in settings.api_keys_list:
                    self._keys[k] = KeyStatus(key=k)

            for k, entry in self._keys.items():
                if entry.status == EstadoKey.COOLDOWN and now >= entry.cooldown_until:
                    entry.status = EstadoKey.HEALTHY
                    entry.cooldown_until = 0.0
                    logger.info(f"API Key {k[:6]}... restaurada a HEALTHY tras finalizar cooldown")

                if entry.status == EstadoKey.HEALTHY:
                    entry.last_used = now
                    return k
        return None

    def mark_cooldown(self, key: str, cooldown_seconds: float = 60.0) -> None:
        """
        Pasa la clave a estado COOLDOWN por un tiempo determinado ante errores 429 (US-18 Escenario 1).
        """
        with self._lock:
            if key in self._keys:
                entry = self._keys[key]
                entry.status = EstadoKey.COOLDOWN
                entry.cooldown_until = time.time() + cooldown_seconds
                entry.error_count += 1
                logger.warning(f"API Key {key[:6]}... puesta en COOLDOWN por {cooldown_seconds}s (HTTP 429)")

    def mark_exhausted(self, key: str) -> None:
        """
        Pasa la clave a estado EXHAUSTED permanentemente ante cuota diaria agotada (US-18 Escenario 2).
        """
        with self._lock:
            if key in self._keys:
                entry = self._keys[key]
                entry.status = EstadoKey.EXHAUSTED
                entry.error_count += 1
                logger.error(f"API Key {key[:6]}... marcada como EXHAUSTED por cuota agotada")

    def mark_invalid(self, key: str) -> None:
        """
        Pasa la clave a INVALID ante credencial mal formada o rechazada permanentemente.
        """
        with self._lock:
            if key in self._keys:
                entry = self._keys[key]
                entry.status = EstadoKey.INVALID
                logger.error(f"API Key {key[:6]}... marcada como INVALID")

    def mark_success(self, key: str) -> None:
        with self._lock:
            if key in self._keys:
                entry = self._keys[key]
                entry.status = EstadoKey.HEALTHY
                entry.last_used = time.time()

    def get_key_status(self, key: str) -> Optional[EstadoKey]:
        with self._lock:
            entry = self._keys.get(key)
            if entry:
                # Comprobar si el cooldown ya expiró
                if entry.status == EstadoKey.COOLDOWN and time.time() >= entry.cooldown_until:
                    entry.status = EstadoKey.HEALTHY
                    entry.cooldown_until = 0.0
                return entry.status
            return None

    def execute_with_failover(
        self,
        page_number: int,
        fn: Callable[[str], T],
        max_attempts: int = 3,
    ) -> Tuple[T, Optional[str]]:
        """
        Ejecuta la función `fn(active_key)` intentando claves sanas.
        Si la clave falla con 429 o cuota, conmuta a la siguiente clave sana sin reiniciar el documento.
        """
        attempts = 0
        last_error = None

        while attempts < max_attempts:
            key = self.get_healthy_key()
            if not key:
                break

            attempts += 1
            try:
                result = fn(key)
                self.mark_success(key)
                return result, key
            except Exception as exc:
                err_msg = str(exc).lower()
                last_error = exc

                if "429" in err_msg or "resource_exhausted" in err_msg or "rate limit" in err_msg:
                    self.mark_cooldown(key, cooldown_seconds=60.0)
                    logger.warning(f"Reintentando página {page_number} con siguiente clave sana tras 429...")
                elif "quota exceeded" in err_msg or "daily quota" in err_msg:
                    self.mark_exhausted(key)
                    logger.warning(f"Reintentando página {page_number} tras cuota agotada...")
                else:
                    # Error no relacionado a cuotas
                    raise exc

        if last_error:
            raise last_error
        raise RuntimeError("No hay API keys disponibles en estado HEALTHY en el pool")


key_pool = KeyPoolManager()
