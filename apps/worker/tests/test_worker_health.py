import asyncio

from ragcommerce_worker import TurnWorker, health


def test_worker_health_is_side_effect_free() -> None:
    assert health() == {"status": "ok", "component": "worker"}


def test_worker_claims_and_executes_one_durable_turn() -> None:
    record = object()

    class Index:
        def claim_next(self):
            return record

    class Service:
        def __init__(self):
            self.executed = []

        async def execute_claimed(self, value):
            self.executed.append(value)

    service = Service()

    assert asyncio.run(TurnWorker(Index(), service).run_once()) is True
    assert service.executed == [record]
