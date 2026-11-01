"""Observe the unchanged load client; pauses remain inside measured latencies."""

import argparse
import asyncio
import gc
import json
import os
import runpy
import sys
from contextlib import suppress
from pathlib import Path
from threading import local
from time import perf_counter, thread_time

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--observation", type=Path, required=True)
    args, load_args = parser.parse_known_args()
    if args.observation.exists() or os.environ["MODEL_PROVIDER_MODE"] != "fake":
        parser.error("Preserve previous observations; explicit fake mode only")
    requests, pauses, lags = [], [], []
    gc_clock = local()
    original_send = httpx.AsyncClient.send
    original_run = asyncio.run

    async def observe_send(client, request, *args, **kwargs):
        started = perf_counter()
        try:
            return await original_send(client, request, *args, **kwargs)
        finally:
            requests.append(
                {
                    "path": request.url.path,
                    "method": request.method,
                    "started": started,
                    "ended": perf_counter(),
                }
            )

    def observe_gc(phase, info):
        if phase == "start":
            gc_clock.started = perf_counter()
        else:
            pauses.append(
                {
                    "generation": info["generation"],
                    "started": gc_clock.started,
                    "ended": perf_counter(),
                }
            )

    async def watch_loop():
        while True:
            started, cpu = perf_counter(), thread_time()
            await asyncio.sleep(0.01)
            elapsed = perf_counter() - started
            if elapsed > 0.025:
                lags.append(
                    {
                        "started": started,
                        "ended": perf_counter(),
                        "lag_ms": (elapsed - 0.01) * 1000,
                        "cpu_ms": (thread_time() - cpu) * 1000,
                    }
                )

    def observe_run(coro, *args, **kwargs):
        async def scope():
            task = asyncio.create_task(watch_loop())
            try:
                return await coro
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        return original_run(scope(), *args, **kwargs)

    httpx.AsyncClient.send = observe_send
    asyncio.run = observe_run
    gc.callbacks.append(observe_gc)
    sys.argv = [str(Path(__file__).with_name("run_v3_durable_load.py")), *load_args]
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    finally:
        gc.callbacks.remove(observe_gc)
        asyncio.run = original_run
        httpx.AsyncClient.send = original_send
        args.observation.write_text(
            json.dumps(
                {
                    "scope": "Client observation only; unmodified 10x30 workload and timing",
                    "requests": requests,
                    "gc_pauses": pauses,
                    "loop_lags": lags,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
