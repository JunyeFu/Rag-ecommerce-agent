"""Static startup graphs need not be scanned in every runtime collection."""

import json
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration


def test_startup_static_graph_does_not_disable_runtime_cycle_collection():
    if not os.environ.get("API_DATABASE_URL") or not os.environ.get("MINIO_ENDPOINT"):
        pytest.skip("API_DATABASE_URL and MINIO_ENDPOINT are required")
    script = """
import asyncio, gc, json, weakref
from ragcommerce_api.persistent_demo import app

class Cycle: pass

async def check():
    threshold = gc.get_threshold()
    original_frozen = gc.get_freeze_count()
    async with app.router.lifespan_context(app):
        frozen = gc.get_freeze_count()
        value = Cycle()
        value.link = value
        reference = weakref.ref(value)
        del value
        gc.collect()
        result = dict(static_frozen=frozen > original_frozen,
                      runtime_cycle_collected=reference() is None,
                      gc_enabled=gc.isenabled(),
                      thresholds_unchanged=gc.get_threshold() == threshold)
    result['existing_frozen_policy_preserved'] = gc.get_freeze_count() >= original_frozen
    return result
print(json.dumps(asyncio.run(check())))
"""
    env = {
        **os.environ,
        "MODEL_PROVIDER_MODE": "fake",
        "MIMO_API_KEY": "",
        "OPENAI_COMPATIBLE_API_KEY": "",
        "PYTHONPATH": os.pathsep.join(sys.path),
    }
    process = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )
    result = json.loads(process.stdout)
    assert result == {
        "static_frozen": True,
        "runtime_cycle_collected": True,
        "gc_enabled": True,
        "thresholds_unchanged": True,
        "existing_frozen_policy_preserved": True,
    }
