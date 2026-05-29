"""Observability wiring: tracing + metrics.

Tracing uses OpenTelemetry (OTLP exporter when an endpoint is configured,
otherwise a no-op so local runs need no collector). Metrics are exposed at
/metrics via prometheus-fastapi-instrumentator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dataforge.core.config import get_settings
from dataforge.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)


def setup_tracing(app: FastAPI) -> None:
    """Configure OpenTelemetry tracing for the app, if enabled."""
    settings = get_settings()
    if not settings.tracing_enabled:
        logger.info("tracing.disabled")
        return

    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": settings.service_name})
    provider = TracerProvider(resource=resource)

    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
        )
        logger.info(
            "tracing.otlp_enabled",
            endpoint=settings.otel_exporter_otlp_endpoint,
        )
    else:
        logger.info("tracing.local_noop")

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


def setup_metrics(app: FastAPI) -> None:
    """Expose Prometheus metrics at /metrics, if enabled."""
    settings = get_settings()
    if not settings.metrics_enabled:
        logger.info("metrics.disabled")
        return

    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/metrics", "/health", "/health/live", "/health/ready"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("metrics.enabled")
