"""Observe the standard Uvicorn lifecycle without disabling logs or GC."""

import argparse
import asyncio
import gc
import importlib
import json
import logging
import os
import sys
from pathlib import Path
from threading import local
from time import perf_counter, thread_time

import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lifecycle", choices=["cli", "server"], default="cli")
    args = parser.parse_args()
    raw_output = args.output.with_name(args.output.stem + "-load.json")
    if args.output.exists() or raw_output.exists():
        parser.error("Preserve existing observations")
    if os.environ["MODEL_PROVIDER_MODE"] != "fake":
        parser.error("Only explicit fake mode is authorized")
    samples = []
    log_samples = []
    gc_samples = []
    requests = []
    loop_lags = []
    gc_clock = local()
    original_emit = logging.StreamHandler.emit

    def observe_emit(handler, record):
        started = perf_counter()
        cpu_started = thread_time()
        try:
            return original_emit(handler, record)
        finally:
            log_samples.append(
                {
                    "logger": record.name,
                    "started": started,
                    "ended": perf_counter(),
                    "cpu_ms": (thread_time() - cpu_started) * 1000,
                    "emit_ms": (perf_counter() - started) * 1000,
                }
            )

    def observe_gc(phase, info):
        if phase == "start":
            gc_clock.started = perf_counter()
        else:
            gc_samples.append(
                {
                    "generation": info["generation"],
                    "started": gc_clock.started,
                    "ended": perf_counter(),
                    "pause_ms": (perf_counter() - gc_clock.started) * 1000,
                }
            )

    class ObservedServer(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            from ragcommerce_api.persistent_demo import app

            service = app.state.turn_service
            original_submit = service.submit
            original_work = service._submit

            original_app = self.config.loaded_app

            async def observe_request(scope, receive, send):
                if scope["type"] != "http":
                    return await original_app(scope, receive, send)
                sample = {"path": scope["path"], "started": perf_counter()}

                async def observe_send(message):
                    if message["type"] == "http.response.start":
                        sample["response_started"] = perf_counter()
                    await send(message)

                try:
                    await original_app(scope, receive, observe_send)
                finally:
                    sample["ended"] = perf_counter()
                    requests.append(sample)

            self.config.loaded_app = observe_request

            def observe_work(*call_args):
                started = perf_counter()
                try:
                    return original_work(*call_args)
                finally:
                    samples.append(
                        {
                            "stage": "work",
                            "thread_id": str(call_args[1]),
                            "started": started,
                            "ended": perf_counter(),
                            "ms": (perf_counter() - started) * 1000,
                        }
                    )

            async def observe_submit(*call_args, **kwargs):
                started = perf_counter()
                try:
                    return await original_submit(*call_args, **kwargs)
                finally:
                    samples.append(
                        {
                            "stage": "awaited_submit",
                            "thread_id": str(call_args[1]),
                            "started": started,
                            "ended": perf_counter(),
                            "ms": (perf_counter() - started) * 1000,
                        }
                    )

            service._submit = observe_work
            service.submit = observe_submit
            self.event_loop = type(asyncio.get_running_loop()).__name__

            async def observe_loop():
                while not self.should_exit:
                    started = perf_counter()
                    cpu = thread_time()
                    await asyncio.sleep(0.01)
                    elapsed = perf_counter() - started
                    if elapsed > 0.025:
                        loop_lags.append(
                            {
                                "started": started,
                                "ended": perf_counter(),
                                "lag_ms": (elapsed - 0.01) * 1000,
                                "cpu_ms": (thread_time() - cpu) * 1000,
                            }
                        )

            self.observation_task = asyncio.create_task(observe_loop())

            async def client():
                try:
                    process = await asyncio.create_subprocess_exec(
                        sys.executable,
                        str(Path(__file__).with_name("profile_durable_client.py")),
                        "--observation",
                        str(args.output.with_name(args.output.stem + "-client.json")),
                        "--base-url",
                        f"http://127.0.0.1:{args.port}",
                        "--batches",
                        "10",
                        "--output",
                        str(raw_output),
                        stdout=asyncio.subprocess.PIPE,
                    )
                    await process.communicate()
                    return process.returncode
                finally:
                    self.should_exit = True

            self.client_task = asyncio.create_task(client())

    servers = []
    original_server = importlib.import_module("uvicorn.main").Server

    def observed_server(*args, **kwargs):
        server = ObservedServer(*args, **kwargs)
        servers.append(server)
        return server

    logging.StreamHandler.emit = observe_emit
    gc.callbacks.append(observe_gc)
    try:
        if args.lifecycle == "cli":
            importlib.import_module("uvicorn.main").Server = observed_server
            uvicorn.run("ragcommerce_api.persistent_demo:app", host="127.0.0.1", port=args.port)
            server = servers[0]
        else:
            server = observed_server(
                uvicorn.Config(
                    "ragcommerce_api.persistent_demo:app", host="127.0.0.1", port=args.port
                )
            )
            server.run()
        client_exit = server.client_task.result()
    finally:
        importlib.import_module("uvicorn.main").Server = original_server
        logging.StreamHandler.emit = original_emit
        gc.callbacks.remove(observe_gc)
    report = {
        "scope": "Read-only observations; not final capacity signoff",
        "lifecycle": args.lifecycle,
        "event_loop": server.event_loop,
        "client_exit": client_exit,
        "load": json.loads(raw_output.read_text(encoding="utf-8")),
        "samples": samples,
        "log_emits": log_samples,
        "gc_pauses": gc_samples,
        "requests": requests,
        "loop_lags": loop_lags,
        "paid_calls": 0,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Standard lifecycle observation complete; paid calls=0")


if __name__ == "__main__":
    main()
