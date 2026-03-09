#!/usr/bin/env python3
"""
Shared Prometheus Metrics Client for isA Platform

Provides standardized Prometheus metrics setup for all isA services:
- Auto-instrumentation for FastAPI (request count, latency, error rate)
- Standard metric naming convention: isa_{service}_{metric}_{unit}
- Custom metric registration helpers
- Graceful degradation when prometheus_client is not installed

Usage:
    from isa_common.metrics import setup_metrics

    app = FastAPI()
    setup_metrics(app, service_name="isA_user")

    # Custom metrics
    from isa_common.metrics import create_counter, create_histogram
    my_counter = create_counter("orders_total", "Total orders processed", ["status"])
    my_counter.labels(status="success").inc()
"""

import os
import time
import logging
from typing import Optional, List, Dict, Sequence

logger = logging.getLogger("isa_common.metrics")

# =============================================================================
# Graceful degradation: make prometheus_client optional
# =============================================================================
try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        Info,
        CollectorRegistry,
        REGISTRY as DEFAULT_REGISTRY,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    DEFAULT_REGISTRY = None
    CONTENT_TYPE_LATEST = "text/plain"
    logger.info("prometheus_client not installed — metrics disabled (no-op)")


# =============================================================================
# Standard bucket configurations
# =============================================================================
FAST_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
"""For fast operations: cache lookups, simple DB queries."""

DEFAULT_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
"""For typical HTTP request latencies."""

SLOW_BUCKETS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)
"""For long-running operations: agent execution, model inference."""


# =============================================================================
# Naming convention helpers
# =============================================================================
_PREFIX = "isa"


def _metric_name(service: str, name: str) -> str:
    """Build a standardized metric name: isa_{service}_{name}."""
    service_clean = service.lower().replace("-", "_").replace(" ", "_")
    # Remove isa_ prefix if already present to avoid isa_isa_
    if service_clean.startswith("isa_"):
        service_clean = service_clean[4:]
    return f"{_PREFIX}_{service_clean}_{name}"


# =============================================================================
# Metric factory functions (with no-op fallback)
# =============================================================================
_service_name: str = "unknown"
_registry: Optional[object] = None


def _effective_registry():
    """Return the registry to use — custom if set, otherwise the default."""
    return _registry if _registry is not None else DEFAULT_REGISTRY


class _NoOpMetric:
    """No-op metric for when prometheus_client is not installed."""

    def labels(self, **kwargs):
        return self

    def inc(self, amount=1):
        pass

    def dec(self, amount=1):
        pass

    def set(self, value):
        pass

    def observe(self, amount):
        pass

    def time(self):
        return _NoOpTimer()

    def info(self, val):
        pass


class _NoOpTimer:
    """No-op context manager timer."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


_NOOP = _NoOpMetric()


def create_counter(
    name: str,
    description: str,
    labelnames: Optional[List[str]] = None,
) -> object:
    """
    Create a Counter metric with standardized naming.

    Args:
        name: Metric name suffix (e.g., "requests_total")
        description: Human-readable description
        labelnames: Label names for dimensional data

    Returns:
        prometheus_client.Counter or no-op
    """
    if not _PROMETHEUS_AVAILABLE:
        return _NOOP
    return Counter(
        _metric_name(_service_name, name),
        description,
        labelnames=labelnames or [],
        registry=_effective_registry(),
    )


def create_histogram(
    name: str,
    description: str,
    labelnames: Optional[List[str]] = None,
    buckets: Sequence[float] = DEFAULT_BUCKETS,
) -> object:
    """
    Create a Histogram metric with standardized naming.

    Args:
        name: Metric name suffix (e.g., "request_duration_seconds")
        description: Human-readable description
        labelnames: Label names for dimensional data
        buckets: Histogram bucket boundaries

    Returns:
        prometheus_client.Histogram or no-op
    """
    if not _PROMETHEUS_AVAILABLE:
        return _NOOP
    return Histogram(
        _metric_name(_service_name, name),
        description,
        labelnames=labelnames or [],
        buckets=buckets,
        registry=_effective_registry(),
    )


def create_gauge(
    name: str,
    description: str,
    labelnames: Optional[List[str]] = None,
) -> object:
    """
    Create a Gauge metric with standardized naming.

    Args:
        name: Metric name suffix (e.g., "active_connections")
        description: Human-readable description
        labelnames: Label names for dimensional data

    Returns:
        prometheus_client.Gauge or no-op
    """
    if not _PROMETHEUS_AVAILABLE:
        return _NOOP
    return Gauge(
        _metric_name(_service_name, name),
        description,
        labelnames=labelnames or [],
        registry=_effective_registry(),
    )


# =============================================================================
# Common metrics (created during setup_metrics)
# =============================================================================
HTTP_REQUESTS_TOTAL = _NOOP
HTTP_REQUEST_DURATION = _NOOP
HTTP_REQUEST_SIZE = _NOOP
HTTP_RESPONSE_SIZE = _NOOP
HTTP_REQUESTS_IN_PROGRESS = _NOOP
SERVICE_INFO = _NOOP

# Paths to exclude from HTTP metrics
_EXCLUDED_PATHS = {"/health", "/health/detailed", "/metrics", "/ready", "/live"}


def _init_common_metrics() -> None:
    """Initialize the standard HTTP and service metrics."""
    global HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION, HTTP_REQUEST_SIZE
    global HTTP_RESPONSE_SIZE, HTTP_REQUESTS_IN_PROGRESS, SERVICE_INFO

    HTTP_REQUESTS_TOTAL = create_counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status_code"],
    )
    HTTP_REQUEST_DURATION = create_histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path"],
        DEFAULT_BUCKETS,
    )
    HTTP_REQUEST_SIZE = create_histogram(
        "http_request_size_bytes",
        "HTTP request body size in bytes",
        ["method", "path"],
        (100, 1_000, 10_000, 100_000, 1_000_000),
    )
    HTTP_RESPONSE_SIZE = create_histogram(
        "http_response_size_bytes",
        "HTTP response body size in bytes",
        ["method", "path"],
        (100, 1_000, 10_000, 100_000, 1_000_000),
    )
    HTTP_REQUESTS_IN_PROGRESS = create_gauge(
        "http_requests_in_progress",
        "Number of HTTP requests currently being processed",
        ["method"],
    )
    if _PROMETHEUS_AVAILABLE:
        SERVICE_INFO = Info(
            _metric_name(_service_name, "service"),
            "Service information",
            registry=_effective_registry(),
        )


def _normalize_path(path: str) -> str:
    """
    Collapse high-cardinality path segments (UUIDs, IDs) to reduce label explosion.

    /api/users/550e8400-e29b-41d4-a716-446655440000 -> /api/users/{id}
    /api/orders/12345 -> /api/orders/{id}
    """
    import re
    # UUID pattern
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
    )
    # Pure numeric segments
    path = re.sub(r"/\d+(?=/|$)", "/{id}", path)
    return path


# =============================================================================
# FastAPI middleware
# =============================================================================
def _create_metrics_middleware(app):
    """Create ASGI middleware that records standard HTTP metrics."""

    async def metrics_middleware(request, call_next):
        path = request.url.path
        if path in _EXCLUDED_PATHS:
            return await call_next(request)

        method = request.method
        normalized = _normalize_path(path)

        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            HTTP_REQUESTS_TOTAL.labels(
                method=method, path=normalized, status_code="500"
            ).inc()
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            raise

        duration = time.perf_counter() - start
        status = str(response.status_code)

        HTTP_REQUESTS_TOTAL.labels(
            method=method, path=normalized, status_code=status
        ).inc()
        HTTP_REQUEST_DURATION.labels(method=method, path=normalized).observe(duration)
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()

        # Response size (if available)
        content_length = response.headers.get("content-length")
        if content_length:
            HTTP_RESPONSE_SIZE.labels(method=method, path=normalized).observe(
                int(content_length)
            )

        return response

    return metrics_middleware


def _create_metrics_endpoint():
    """Create the /metrics endpoint handler."""

    async def metrics_endpoint(request):
        from starlette.responses import Response

        data = generate_latest(_effective_registry())
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    return metrics_endpoint


# =============================================================================
# Public API: setup_metrics
# =============================================================================
def setup_metrics(
    app,
    service_name: str,
    version: str = "unknown",
    registry: Optional[object] = None,
    excluded_paths: Optional[set] = None,
) -> None:
    """
    One-liner to add Prometheus metrics to any FastAPI/Starlette app.

    Sets up:
    - Standard HTTP request metrics (count, duration, size)
    - /metrics endpoint for Prometheus scraping
    - Service info metric with version

    Args:
        app: FastAPI or Starlette application instance
        service_name: Name of the service (e.g., "isA_user", "isA_Agent_SDK")
        version: Service version string
        registry: Custom CollectorRegistry (default: prometheus default)
        excluded_paths: Paths to exclude from metrics (default: /health, /metrics, etc.)

    Example:
        from isa_common.metrics import setup_metrics
        app = FastAPI()
        setup_metrics(app, service_name="isA_user", version="1.0.0")
    """
    global _service_name, _registry

    _service_name = service_name
    _registry = registry

    if excluded_paths:
        _EXCLUDED_PATHS.update(excluded_paths)

    if not _PROMETHEUS_AVAILABLE:
        logger.warning(f"Metrics disabled for {service_name} — install prometheus_client")
        return

    # Initialize standard metrics
    _init_common_metrics()

    # Set service info
    try:
        SERVICE_INFO.info({"name": service_name, "version": version})
    except Exception:
        pass

    # Add middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=_create_metrics_middleware(app))

    # Add /metrics endpoint
    from starlette.routing import Route
    app.routes.append(Route("/metrics", _create_metrics_endpoint()))

    logger.info(f"Prometheus metrics initialized for {service_name}")


def metrics_text() -> bytes:
    """
    Generate Prometheus text exposition format.

    Useful for custom /metrics endpoints or testing.
    """
    if not _PROMETHEUS_AVAILABLE:
        return b""
    return generate_latest(_effective_registry())
