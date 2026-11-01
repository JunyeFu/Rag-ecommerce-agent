"""Diagnose real PG submit costs; this is not an HTTP capacity acceptance test."""

import argparse
import asyncio
import gc
import json
import os
import sys
from pathlib import Path
from threading import get_ident, local
from time import perf_counter
from uuid import uuid4


async def diagnose(http_port=None, server_log_level="info", batches=1):
    if os.environ.get("MODEL_PROVIDER_MODE") != "fake":
        raise ValueError("Profiling is only authorized for explicit fake mode")
    from ragcommerce_api.persistent_demo import app

    service = app.state.turn_service
    original = service._submit
    original_submit = service.submit
    awaited_samples = []
    samples = []
    timing = local()
    index_originals = {name: getattr(service.index, name) for name in ("get_thread", "reserve")}

    def timed(name, call):
        def execute(*args, **kwargs):
            started = perf_counter()
            try:
                return call(*args, **kwargs)
            finally:
                if hasattr(timing, "stages"):
                    timing.stages.append(
                        {"stage": name, "elapsed_ms": (perf_counter() - started) * 1000}
                    )

        return execute

    for name, call in index_originals.items():
        setattr(service.index, name, timed(name, call))

    def profiled(*args):
        timing.stages = []
        started = perf_counter()
        try:
            return original(*args)
        finally:
            samples.append(
                {
                    "diagnostic_id": str(args[0]),
                    "work_ms": (perf_counter() - started) * 1000,
                    "stages": timing.stages,
                }
            )
            del timing.stages

    service._submit = profiled

    async def timed_submit(*args, **kwargs):
        started = perf_counter()
        try:
            return await original_submit(*args, **kwargs)
        finally:
            awaited_samples.append(
                {
                    "diagnostic_id": str(args[0]),
                    "awaited_server_ms": (perf_counter() - started) * 1000,
                }
            )

    service.submit = timed_submit

    gc_samples = []
    gc_started = {}

    def observe_gc(phase, info):
        key = (get_ident(), info["generation"])
        if phase == "start":
            gc_started[key] = perf_counter()
        elif key in gc_started:
            gc_samples.append(
                {
                    "generation": info["generation"],
                    "pause_ms": (perf_counter() - gc_started.pop(key)) * 1000,
                    "collected": info["collected"],
                }
            )

    gc.callbacks.append(observe_gc)

    server = None
    server_task = None

    async def submit_one():
        owner = uuid4()
        thread = await asyncio.to_thread(service.create_thread, owner, "预算1000元的通勤降噪耳机")
        started = perf_counter()
        record, _ = await service.submit(owner, thread.id, str(uuid4()), thread.goal, ())
        return {
            "diagnostic_id": str(owner),
            "run_id": str(record.run_id),
            "awaited_ms": (perf_counter() - started) * 1000,
        }

    try:
        if http_port is None:
            results = await asyncio.gather(*(submit_one() for _ in range(30)))
            load = None
        else:
            import uvicorn

            server = uvicorn.Server(
                uvicorn.Config(app, host="127.0.0.1", port=http_port, log_level=server_log_level)
            )
            server_task = asyncio.create_task(server.serve())
            while not server.started:
                if server_task.done():
                    await server_task
                    raise RuntimeError("Diagnostic server did not start")
                await asyncio.sleep(0.1)
            code = (
                "import asyncio,json,os,sys;sys.path.insert(0,sys.argv[2])\n"
                "from run_v3_durable_load import measure,percentile\n"
                "async def execute():\n"
                " reports=[]\n"
                " for index in range(int(sys.argv[3])):\n"
                "  report=await measure(sys.argv[1],os.environ['DATABASE_URL']);report['batch']=index+1;reports.append(report)\n"
                " if len(reports)==1:return reports[0]\n"
                " rows=[row for report in reports for row in report['results']]\n"
                " return {'batch_count':len(reports),'completed':sum(r['completed'] for r in reports),'passed':all(r['passed'] for r in reports),'batches':reports,'results':rows,'turn_accept_p95_ms':percentile([r['accepted_ms'] for r in rows],0.95),'first_state_p95_ms':percentile([r['first_state_ms'] for r in rows],0.95)}\n"
                "print(json.dumps(asyncio.run(execute())))"
            )
            client = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                code,
                f"http://127.0.0.1:{http_port}",
                str(Path(__file__).resolve().parent),
                str(batches),
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await client.communicate()
            if client.returncode:
                raise RuntimeError(f"Diagnostic client exited {client.returncode}")
            load = json.loads(stdout)
            results = load["results"]
    finally:
        gc.callbacks.remove(observe_gc)
        if server is not None:
            server.should_exit = True
            await server_task
        service._submit = original
        service.submit = original_submit
        for name, call in index_originals.items():
            setattr(service.index, name, call)
    return {
        "scope": "Real PG TurnService thread profile; not HTTP/SSE acceptance",
        "provider": "fake",
        "requests": 30 * batches,
        "batch_count": batches,
        "samples": samples,
        "awaited_server_samples": awaited_samples,
        "gc_pauses": gc_samples,
        "client_process_separate": http_port is not None,
        "server_log_level": server_log_level,
        "event_loop": type(asyncio.get_running_loop()).__name__,
        "results": results,
        "http_diagnostic": load,
        "limitations": [
            "Stage timers wrap actual methods in this diagnostic process only; no production mutation",
            "HTTP client runs in a separate process; stage instrumentation may affect timing",
            "No attribution to connection pool, thread pool or SQL without separate-process corroboration",
        ],
        "paid_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--http-port", type=int)
    parser.add_argument("--server-log-level", choices=["info", "warning"], default="info")
    parser.add_argument("--batches", type=int, choices=[1, 10], default=1)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve existing diagnostic output")
    if args.batches != 1 and args.http_port is None:
        parser.error("Ten-batch profiling requires the real HTTP path")
    report = asyncio.run(diagnose(args.http_port, args.server_log_level, args.batches))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Profiled {report['requests']} persistent submissions; no automatic signoff")


if __name__ == "__main__":
    main()
