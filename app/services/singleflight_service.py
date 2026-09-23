import asyncio
from typing import Dict, Any, Callable, Coroutine, Optional
import time
import logging

logger = logging.getLogger("pydective.singleflight")


class InFlightCall:
    def __init__(self, future: asyncio.Future):
        self.future = future
        self.created_at = time.time()
        self.waiters_count = 0


class SingleflightGroup:
    """
    Prevención de estampidas concurrentes (Dogpile / Cache Stampede) (US-17).
    Garantiza que ante múltiples peticiones simultáneas para el mismo (pdf_hash, query_hash),
    solo una ejecute el trabajo real mientras las demás esperan el resultado de forma no bloqueante.
    """
    _instance: Optional["SingleflightGroup"] = None
    _class_lock = asyncio.Lock()

    def __init__(self):
        self._calls: Dict[str, InFlightCall] = {}
        self._lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "SingleflightGroup":
        if cls._instance is None:
            async with cls._class_lock:
                if cls._instance is None:
                    cls._instance = SingleflightGroup()
        return cls._instance

    async def do(
        self,
        key: str,
        fn: Callable[[], Coroutine[Any, Any, Any]],
        timeout_seconds: float = 60.0,
    ) -> Any:
        """
        Ejecuta `fn` de forma exclusiva para la `key` dada.
        Cualquier llamada concurrente que ingrese con la misma `key` esperará
        la finalización de la primera llamada y compartirá su resultado.
        """
        loop = asyncio.get_running_loop()
        is_leader = False
        call: InFlightCall

        async with self._lock:
            if key in self._calls:
                call = self._calls[key]
                call.waiters_count += 1
            else:
                fut = loop.create_future()
                call = InFlightCall(future=fut)
                self._calls[key] = call
                is_leader = True

        if not is_leader:
            logger.info(f"Singleflight: uniendo petición concurrente a la clave en vuelo {key}")
            try:
                # Esperar el resultado del líder con timeout seguro de lease
                return await asyncio.wait_for(asyncio.shield(call.future), timeout=timeout_seconds)
            except Exception as e:
                logger.warning(f"Singleflight waiter error para clave {key}: {e}")
                raise e

        # Ejecución del líder
        try:
            result = await fn()
            if not call.future.done():
                call.future.set_result(result)
            return result
        except BaseException as exc:
            if not call.future.done():
                call.future.set_exception(exc)
            raise exc
        finally:
            async with self._lock:
                self._calls.pop(key, None)


singleflight_group = SingleflightGroup()
