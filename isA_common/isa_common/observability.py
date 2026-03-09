#!/usr/bin/env python3
"""
Unified Observability Setup for isA Platform

One-liner to wire up all three observability pillars:
- Prometheus metrics (scraping via /metrics endpoint)
- Loki log shipping (structured logs)
- Tempo distributed tracing (OpenTelemetry → OTLP)

Usage:
    from isa_common.observability import setup_observability

    app = FastAPI()
    setup_observability(app, service_name="isA_user", version="1.0.0")
    # That's it — metrics, logs, and traces are all configured.
"""

import os
import logging
from typing import Optional, Dict

logger = logging.getLogger("isa_common.observability")


def setup_observability(
    app,
    service_name: str,
    version: str = "unknown",
    *,
    # Metrics config
    enable_metrics: bool = True,
    metrics_registry: Optional[object] = None,
    # Logging config
    enable_logging: bool = True,
    loki_url: Optional[str] = None,
    log_level: int = logging.INFO,
    # Tracing config
    enable_tracing: bool = True,
    tempo_host: Optional[str] = None,
    tempo_port: Optional[int] = None,
    # Shared
    extra_labels: Optional[Dict[str, str]] = None,
) -> Dict[str, bool]:
    """
    One-liner to set up all three observability pillars for an isA service.

    Args:
        app: FastAPI or Starlette application instance
        service_name: Service name (e.g., "isA_user", "isA_MCP")
        version: Service version string

    Keyword Args:
        enable_metrics: Enable Prometheus metrics (default: True)
        metrics_registry: Custom Prometheus CollectorRegistry
        enable_logging: Enable Loki log shipping (default: True)
        loki_url: Loki URL (default: LOKI_URL env or "http://localhost:3100")
        log_level: Minimum log level to ship (default: INFO)
        enable_tracing: Enable distributed tracing (default: True)
        tempo_host: Tempo OTLP host (default: TEMPO_HOST env or "localhost")
        tempo_port: Tempo OTLP gRPC port (default: TEMPO_PORT env or 4317)
        extra_labels: Additional labels for all pillars

    Returns:
        Dict indicating which pillars were successfully enabled:
        {"metrics": True, "logging": True, "tracing": False}

    Example:
        from isa_common.observability import setup_observability
        app = FastAPI()
        result = setup_observability(app, service_name="isA_user", version="1.0.0")
        # result: {"metrics": True, "logging": True, "tracing": True}
    """
    result = {"metrics": False, "logging": False, "tracing": False}
    env = os.getenv("ISA_ENV", "local")

    # -------------------------------------------------------------------------
    # 1. Prometheus Metrics
    # -------------------------------------------------------------------------
    if enable_metrics:
        try:
            from .metrics import setup_metrics
            setup_metrics(
                app,
                service_name=service_name,
                version=version,
                registry=metrics_registry,
            )
            result["metrics"] = True
        except Exception as e:
            logger.warning(f"Failed to setup metrics: {e}")

    # -------------------------------------------------------------------------
    # 2. Loki Log Shipping
    # -------------------------------------------------------------------------
    if enable_logging:
        try:
            from .loki_handler import setup_loki_logging
            url = loki_url or os.getenv("LOKI_URL", "http://localhost:3100")
            labels = {"env": env}
            if extra_labels:
                labels.update(extra_labels)
            setup_loki_logging(
                service_name=service_name,
                loki_url=url,
                level=log_level,
                extra_labels=labels,
            )
            result["logging"] = True
        except Exception as e:
            logger.warning(f"Failed to setup Loki logging: {e}")

    # -------------------------------------------------------------------------
    # 3. Distributed Tracing (Tempo via OTLP)
    # -------------------------------------------------------------------------
    if enable_tracing:
        try:
            from .tracing import setup_tracing
            setup_tracing(
                app=app,
                service_name=service_name,
                version=version,
                tempo_host=tempo_host,
                tempo_port=tempo_port,
                extra_attributes={"deployment.environment": env},
            )
            result["tracing"] = True
        except Exception as e:
            logger.warning(f"Failed to setup tracing: {e}")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    enabled = [k for k, v in result.items() if v]
    disabled = [k for k, v in result.items() if not v]

    if enabled:
        logger.info(f"Observability for {service_name}: {', '.join(enabled)} enabled")
    if disabled:
        logger.warning(f"Observability for {service_name}: {', '.join(disabled)} disabled")

    return result
