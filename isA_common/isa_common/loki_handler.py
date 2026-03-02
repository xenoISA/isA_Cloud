#!/usr/bin/env python3
"""
Loki Logging Handler
Python logging.Handler that ships structured logs to Loki via AsyncLokiClient.

Non-blocking: uses a background thread with an async event loop to push logs
without slowing down the application.

Usage:
    from isa_common.loki_handler import setup_loki_logging

    setup_loki_logging(service_name="isA_Agent_SDK", loki_url="http://localhost:3100")
"""

import asyncio
import atexit
import logging
import threading
import time
from typing import Dict, Optional

from .async_loki_client import AsyncLokiClient


class LokiHandler(logging.Handler):
    """
    Logging handler that ships log records to Loki.

    Uses a background thread with an async event loop to batch and push logs
    without blocking the calling application.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3100,
        tenant_id: str = "",
        default_labels: Optional[Dict[str, str]] = None,
        batch_size: int = 100,
        flush_interval: float = 2.0,
        level: int = logging.NOTSET,
    ):
        super().__init__(level)

        self._default_labels = default_labels or {}
        self._batch_size = batch_size
        self._flush_interval = flush_interval

        self._client = AsyncLokiClient(
            host=host,
            port=port,
            tenant_id=tenant_id,
            batch_size=batch_size,
            flush_interval=flush_interval,
            default_labels=self._default_labels,
        )

        self._queue: list = []
        self._lock = threading.Lock()

        # Background thread with its own event loop
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="loki-handler"
        )
        self._thread.start()

        # Schedule periodic flush
        asyncio.run_coroutine_threadsafe(self._periodic_flush(), self._loop)

        atexit.register(self.close)

    def _run_loop(self) -> None:
        """Run the background event loop."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def emit(self, record: logging.LogRecord) -> None:
        """Queue a log record for async push to Loki."""
        try:
            labels = {
                **self._default_labels,
                "level": record.levelname,
                "logger": record.name,
            }

            message = self.format(record) if self.formatter else record.getMessage()

            entry = {
                "labels": labels,
                "message": message,
                "timestamp_ns": int(record.created * 1_000_000_000),
            }

            with self._lock:
                self._queue.append(entry)
                if len(self._queue) >= self._batch_size:
                    batch = self._queue
                    self._queue = []
                    asyncio.run_coroutine_threadsafe(
                        self._client.push_batch(batch), self._loop
                    )
        except Exception:
            self.handleError(record)

    async def _periodic_flush(self) -> None:
        """Periodically flush queued entries."""
        while True:
            await asyncio.sleep(self._flush_interval)
            self._do_flush()

    def _do_flush(self) -> None:
        """Flush current queue."""
        with self._lock:
            if not self._queue:
                return
            batch = self._queue
            self._queue = []
        asyncio.run_coroutine_threadsafe(
            self._client.push_batch(batch), self._loop
        )

    def close(self) -> None:
        """Flush remaining entries and shut down."""
        # Drain the queue and wait for the flush to complete
        with self._lock:
            batch = self._queue
            self._queue = []
        if batch:
            flush_future = asyncio.run_coroutine_threadsafe(
                self._client.push_batch(batch), self._loop
            )
            try:
                flush_future.result(timeout=5)
            except Exception:
                pass

        # Now close the client session
        close_future = asyncio.run_coroutine_threadsafe(
            self._client.close(), self._loop
        )
        try:
            close_future.result(timeout=5)
        except Exception:
            pass

        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)
        super().close()


def setup_loki_logging(
    service_name: str,
    loki_url: str = "http://localhost:3100",
    level: int = logging.INFO,
    tenant_id: str = "",
    extra_labels: Optional[Dict[str, str]] = None,
) -> LokiHandler:
    """
    One-liner to add Loki log shipping to any isA project.

    Args:
        service_name: Name of the service (used as 'app' label)
        loki_url: Loki push URL (e.g., "http://localhost:3100")
        level: Minimum log level to ship (default: INFO)
        tenant_id: Loki tenant ID for multi-tenancy
        extra_labels: Additional static labels

    Returns:
        The LokiHandler instance (attached to root logger)

    Example:
        from isa_common.loki_handler import setup_loki_logging
        setup_loki_logging(service_name="isA_Agent_SDK")
    """
    # Parse host/port from URL
    url = loki_url.rstrip("/")
    if "://" in url:
        url = url.split("://", 1)[1]
    parts = url.split(":")
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else 3100

    labels = {"app": service_name}
    if extra_labels:
        labels.update(extra_labels)

    handler = LokiHandler(
        host=host,
        port=port,
        tenant_id=tenant_id,
        default_labels=labels,
        level=level,
    )

    logging.getLogger().addHandler(handler)
    return handler
