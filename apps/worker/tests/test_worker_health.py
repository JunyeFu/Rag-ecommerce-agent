from ragcommerce_worker import health


def test_worker_health_is_side_effect_free() -> None:
    assert health() == {"status": "ok", "component": "worker"}
