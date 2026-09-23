import asyncio
import pytest
from app.services.singleflight_service import SingleflightGroup


@pytest.mark.asyncio
async def test_us17_singleflight_concurrent_dogpile_prevention():
    # US-17: Prevención de Estampidas (Singleflight contra Dogpile)
    # Ante 5 llamadas simultáneas, solo 1 ejecuta la función real
    group = SingleflightGroup()
    execution_counter = 0

    async def worker_fn():
        nonlocal execution_counter
        execution_counter += 1
        await asyncio.sleep(0.05)
        return {"data": "processed_result", "exec_count": execution_counter}

    # Lanzar 5 llamadas simultáneas con la misma clave
    tasks = [
        group.do("shared_pdf_key", worker_fn)
        for _ in range(5)
    ]

    results = await asyncio.gather(*tasks)

    # 1. Solo se ejecutó una única vez
    assert execution_counter == 1
    # 2. Las 5 llamadas recibieron el mismo resultado
    assert len(results) == 5
    for r in results:
        assert r["data"] == "processed_result"
        assert r["exec_count"] == 1


@pytest.mark.asyncio
async def test_us17_singleflight_different_keys_execute_independently():
    group = SingleflightGroup()
    counter_a = 0
    counter_b = 0

    async def worker_a():
        nonlocal counter_a
        counter_a += 1
        return "result_a"

    async def worker_b():
        nonlocal counter_b
        counter_b += 1
        return "result_b"

    res_a, res_b = await asyncio.gather(
        group.do("key_a", worker_a),
        group.do("key_b", worker_b),
    )

    assert counter_a == 1
    assert counter_b == 1
    assert res_a == "result_a"
    assert res_b == "result_b"
