#!/usr/bin/env python3
"""
Shared OpenTelemetry Tracing Client for isA Platform

Provides standardized distributed tracing setup targeting Tempo via OTLP:
- One-liner setup for FastAPI/Starlette apps
- Auto-instrumentation for common libraries
- Trace context propagation (W3C traceparent)
- Graceful degradation when opentelemetry is not installed

Usage:
    from isa_common.tracing import setup_tracing

    app = FastAPI()
    setup_tracing(app, service_name="isA_user")

    # Manual spans
    from isa_common.tracing import get_tracer
    tracer = get_tracer()
    with tracer.start_as_current_span("my_operation") as span:
        span.set_attribute("key", "value")
        ...
"""

import os
import logging
from typing import Optional, Dict

logger = logging.getLogger("isa_common.tracing")

# =============================================================================
# Graceful degradation: make opentelemetry optional
# =============================================================================
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.trace.propagation import TraceContextTextMapPropagator
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    logger.info("opentelemetry not installed — tracing disabled (no-op)")


# =============================================================================
# Auto-instrumentation helpers
# =============================================================================
def _instrument_fastapi(app) -> bool:
    """Auto-instrument FastAPI with OpenTelemetry."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="health,health/detailed,metrics,ready,live",
        )
        return True
    except ImportError:
        logger.debug("opentelemetry-instrumentation-fastapi not installed, skipping")
        return False


def _instrument_aiohttp() -> bool:
    """Auto-instrument aiohttp client sessions."""
    try:
        from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
        AioHttpClientInstrumentor().instrument()
        return True
    except ImportError:
        return False


def _instrument_asyncpg() -> bool:
    """Auto-instrument asyncpg (PostgreSQL)."""
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        AsyncPGInstrumentor().instrument()
        return True
    except ImportError:
        return False


def _instrument_redis() -> bool:
    """Auto-instrument redis-py."""
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
        return True
    except ImportError:
        return False


def _instrument_httpx() -> bool:
    """Auto-instrument httpx client."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        return True
    except ImportError:
        return False


# =============================================================================
# No-op tracer for when opentelemetry is not installed
# =============================================================================
class _NoOpSpan:
    """No-op span for graceful degradation."""

    def set_attribute(self, key, value):
        pass

    def set_status(self, status):
        pass

    def record_exception(self, exception):
        pass

    def add_event(self, name, attributes=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _NoOpTracer:
    """No-op tracer for graceful degradation."""

    def start_as_current_span(self, name, **kwargs):
        return _NoOpSpan()

    def start_span(self, name, **kwargs):
        return _NoOpSpan()


_noop_tracer = _NoOpTracer()

# Module-level tracer reference
_tracer: object = _noop_tracer


def get_tracer() -> object:
    """
    Get the configured tracer instance.

    Returns the OpenTelemetry tracer if configured, otherwise a no-op tracer.

    Usage:
        from isa_common.tracing import get_tracer
        tracer = get_tracer()
        with tracer.start_as_current_span("operation"):
            ...
    """
    return _tracer


# =============================================================================
# Public API: setup_tracing
# =============================================================================
def setup_tracing(
    app=None,
    service_name: str = "unknown",
    version: str = "unknown",
    tempo_host: Optional[str] = None,
    tempo_port: Optional[int] = None,
    auto_instrument: bool = True,
    extra_attributes: Optional[Dict[str, str]] = None,
) -> None:
    """
    One-liner to add OpenTelemetry distributed tracing targeting Tempo.

    Sets up:
    - TracerProvider with OTLP gRPC exporter to Tempo
    - W3C trace context propagation
    - Auto-instrumentation for FastAPI, aiohttp, asyncpg, redis (if installed)

    Args:
        app: FastAPI or Starlette app instance (optional, enables FastAPI instrumentation)
        service_name: Name of the service (e.g., "isA_user")
        version: Service version string
        tempo_host: Tempo OTLP host (default: TEMPO_HOST env or "localhost")
        tempo_port: Tempo OTLP gRPC port (default: TEMPO_PORT env or 4317)
        auto_instrument: Whether to auto-instrument common libraries
        extra_attributes: Additional resource attributes

    Example:
        from isa_common.tracing import setup_tracing
        app = FastAPI()
        setup_tracing(app, service_name="isA_user", version="1.0.0")
    """
    global _tracer

    if not _OTEL_AVAILABLE:
        logger.warning(f"Tracing disabled for {service_name} — install opentelemetry-sdk")
        return

    host = tempo_host or os.getenv("TEMPO_HOST", "localhost")
    port = tempo_port or int(os.getenv("TEMPO_PORT", "4317"))
    endpoint = f"{host}:{port}"

    # Build resource attributes
    resource_attrs = {
        SERVICE_NAME: service_name,
        SERVICE_VERSION: version,
        "deployment.environment": os.getenv("ISA_ENV", "local"),
    }
    if extra_attributes:
        resource_attrs.update(extra_attributes)

    resource = Resource.create(resource_attrs)

    # Configure OTLP exporter
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        insecure=os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true",
    )

    # Set up TracerProvider
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Set up W3C trace context propagation
    set_global_textmap(CompositePropagator([
        TraceContextTextMapPropagator(),
        W3CBaggagePropagator(),
    ]))

    # Get the tracer
    _tracer = trace.get_tracer(service_name, version)

    # Auto-instrument libraries
    if auto_instrument:
        instrumented = []
        if app is not None and _instrument_fastapi(app):
            instrumented.append("fastapi")
        if _instrument_aiohttp():
            instrumented.append("aiohttp")
        if _instrument_asyncpg():
            instrumented.append("asyncpg")
        if _instrument_redis():
            instrumented.append("redis")
        if _instrument_httpx():
            instrumented.append("httpx")
        if instrumented:
            logger.info(f"Auto-instrumented: {', '.join(instrumented)}")

    logger.info(f"Tracing initialized for {service_name} → {endpoint}")
