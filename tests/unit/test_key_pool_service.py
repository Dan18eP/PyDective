import time
import pytest
from app.domain.enums import EstadoKey
from app.services.key_pool_service import KeyPoolManager


def test_us18_automatic_cooldown_on_429_and_failover():
    # US-18 Escenario 1: Cooldown automático ante HTTP 429
    pool = KeyPoolManager(api_keys=["KeyA", "KeyB"])

    calls_made = []

    def mock_worker(key: str):
        calls_made.append(key)
        if key == "KeyA":
            raise RuntimeError("HTTP 429 RESOURCE_EXHAUSTED: Rate limit exceeded")
        return f"result_from_{key}"

    # Ejecutar con failover en la página 3
    result, used_key = pool.execute_with_failover(page_number=3, fn=mock_worker)

    # 1. KeyA fue llamada y falló con 429
    assert calls_made[0] == "KeyA"
    # 2. KeyA pasa inmediatamente a estado COOLDOWN
    assert pool.get_key_status("KeyA") == EstadoKey.COOLDOWN
    # 3. La página 3 se resolvió exitosamente con KeyB
    assert calls_made[1] == "KeyB"
    assert used_key == "KeyB"
    assert result == "result_from_KeyB"


def test_us18_permanent_exhausted_on_quota_exceeded():
    # US-18 Escenario 2: Cuota diaria agotada (Exhausted)
    pool = KeyPoolManager(api_keys=["KeyA", "KeyB"])

    def mock_quota_worker(key: str):
        if key == "KeyA":
            raise RuntimeError("403 Quota exceeded: Daily limit reached")
        return f"result_from_{key}"

    result, used_key = pool.execute_with_failover(page_number=1, fn=mock_quota_worker)

    # KeyA queda excluida permanentemente en EXHAUSTED
    assert pool.get_key_status("KeyA") == EstadoKey.EXHAUSTED
    assert used_key == "KeyB"
    assert result == "result_from_KeyB"

    # Una siguiente petición nunca volverá a recibir KeyA
    healthy = pool.get_healthy_key()
    assert healthy == "KeyB"


def test_us18_cooldown_recovery_after_expiration():
    pool = KeyPoolManager(api_keys=["KeyOnly"])
    # Cooldown breve de 0.05s
    pool.mark_cooldown("KeyOnly", cooldown_seconds=0.05)
    assert pool.get_key_status("KeyOnly") == EstadoKey.COOLDOWN
    assert pool.get_healthy_key() is None

    time.sleep(0.06)
    # Tras expirar el tiempo, se recupera a HEALTHY automáticamente
    assert pool.get_healthy_key() == "KeyOnly"
    assert pool.get_key_status("KeyOnly") == EstadoKey.HEALTHY
