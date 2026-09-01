"""Structured request logs and optional OTLP traces for the local V3 stack."""

from __future__ import annotations

import json
import logging
import os
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

LOGGER = logging.getLogger("ragcommerce.api")


def configure_observability(app: FastAPI) -> None:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        provider = TracerProvider(resource=Resource.create({"service.name": "ragcommerce-api"}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    @app.middleware("http")
    async def structured_request_log(request: Request, call_next):
        started = perf_counter()
        trace_id = request.headers.get("X-Trace-ID", "").strip() or uuid4().hex
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        LOGGER.info(
            json.dumps(
                {
                    "event": "http_request",
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                },
                separators=(",", ":"),
            )
        )
        return response


__all__ = ["configure_observability"]
