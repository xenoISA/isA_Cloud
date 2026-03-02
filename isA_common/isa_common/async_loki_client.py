#!/usr/bin/env python3
"""
Async Loki Native Client
High-performance async Loki client using aiohttp for HTTP API.

This client connects directly to Loki's HTTP API, providing:
- Log push (single and batch) via /loki/api/v1/push
- Log query via /loki/api/v1/query_range
- Label discovery via /loki/api/v1/labels
- Built-in batching with configurable flush interval
"""

import os
import json
import time
import asyncio
from typing import List, Dict, Optional, Any

import aiohttp

from .async_base_client import AsyncBaseClient


class AsyncLokiClient(AsyncBaseClient):
    """
    Async Loki client using native HTTP API.

    Provides direct connection to Loki for log ingestion and querying.
    Supports built-in batching for efficient log push operations.
    """

    SERVICE_NAME = "Loki"
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 3100
    ENV_PREFIX = "LOKI"
    TENANT_SEPARATOR = "/"

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        batch_size: int = 100,
        flush_interval: float = 1.0,
        default_labels: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """
        Initialize async Loki client.

        Args:
            tenant_id: Loki tenant ID for multi-tenancy (X-Scope-OrgID header)
            batch_size: Max entries before auto-flush (default: 100)
            flush_interval: Seconds between auto-flushes (default: 1.0)
            default_labels: Labels applied to all log entries
            **kwargs: Base client args (host, port, user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        self._tenant_id = tenant_id or os.getenv('LOKI_TENANT_ID', '')
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._default_labels = default_labels or {}

        self._session: Optional[aiohttp.ClientSession] = None
        self._batch: List[Dict[str, Any]] = []
        self._flush_task: Optional[asyncio.Task] = None

    @property
    def _base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._tenant_id:
            headers["X-Scope-OrgID"] = self._tenant_id
        return headers

    # ============================================
    # Connection Management
    # ============================================

    async def _connect(self) -> None:
        """Establish HTTP session."""
        self._session = aiohttp.ClientSession(
            base_url=self._base_url,
            headers=self._headers(),
        )
        self._logger.info(f"Connected to Loki at {self._host}:{self._port}")

    async def _disconnect(self) -> None:
        """Close HTTP session and flush remaining batch."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        if self._batch:
            await self._flush_batch()
        if self._session:
            await self._session.close()
            self._session = None

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self) -> Optional[Dict]:
        """Check Loki service health via /ready endpoint."""
        try:
            await self._ensure_connected()
            async with self._session.get("/ready") as resp:
                is_ready = resp.status == 200
                return {
                    'healthy': is_ready,
                    'loki_status': 'ready' if is_ready else 'not_ready',
                    'status_code': resp.status,
                }
        except Exception as e:
            return self.handle_error(e, "health check")

    # ============================================
    # Log Push Operations
    # ============================================

    async def push_log(
        self,
        message: str,
        labels: Optional[Dict[str, str]] = None,
        timestamp_ns: Optional[int] = None,
    ) -> bool:
        """
        Push a single log entry to Loki.

        Args:
            message: Log message string
            labels: Labels for this entry (merged with default_labels)
            timestamp_ns: Timestamp in nanoseconds (default: now)

        Returns:
            True if pushed/batched successfully
        """
        try:
            merged_labels = {**self._default_labels, **(labels or {})}
            ts = timestamp_ns or int(time.time() * 1e9)

            entry = {
                "labels": merged_labels,
                "values": [[str(ts), message]],
            }
            self._batch.append(entry)

            if len(self._batch) >= self._batch_size:
                return await self._flush_batch()

            return True
        except Exception as e:
            self.handle_error(e, "push_log")
            return False

    async def push_batch(
        self,
        entries: List[Dict[str, Any]],
    ) -> bool:
        """
        Push a batch of log entries to Loki immediately.

        Each entry should have:
            - labels: Dict[str, str]
            - message: str
            - timestamp_ns: Optional[int] (nanoseconds)

        Args:
            entries: List of log entry dicts

        Returns:
            True if pushed successfully
        """
        try:
            await self._ensure_connected()

            # Group entries by label set
            streams: Dict[str, Dict] = {}
            for entry in entries:
                labels = {**self._default_labels, **entry.get("labels", {})}
                label_key = self._labels_to_str(labels)
                ts = entry.get("timestamp_ns") or int(time.time() * 1e9)
                message = entry.get("message", "")

                if label_key not in streams:
                    streams[label_key] = {
                        "stream": labels,
                        "values": [],
                    }
                streams[label_key]["values"].append([str(ts), message])

            payload = {"streams": list(streams.values())}

            async with self._session.post(
                "/loki/api/v1/push",
                json=payload,
            ) as resp:
                if resp.status == 204:
                    return True
                text = await resp.text()
                self._logger.warning(f"Loki push returned {resp.status}: {text}")
                return False

        except Exception as e:
            self.handle_error(e, "push_batch")
            return False

    async def _flush_batch(self) -> bool:
        """Flush accumulated batch to Loki."""
        if not self._batch:
            return True

        batch = self._batch
        self._batch = []

        try:
            await self._ensure_connected()

            # Group by label set
            streams: Dict[str, Dict] = {}
            for entry in batch:
                labels = entry["labels"]
                label_key = self._labels_to_str(labels)
                if label_key not in streams:
                    streams[label_key] = {
                        "stream": labels,
                        "values": [],
                    }
                streams[label_key]["values"].extend(entry["values"])

            payload = {"streams": list(streams.values())}

            async with self._session.post(
                "/loki/api/v1/push",
                json=payload,
            ) as resp:
                if resp.status == 204:
                    return True
                text = await resp.text()
                self._logger.warning(f"Loki flush returned {resp.status}: {text}")
                return False

        except Exception as e:
            self.handle_error(e, "flush_batch")
            return False

    async def flush(self) -> bool:
        """Manually flush the current batch."""
        return await self._flush_batch()

    # ============================================
    # Auto-flush Background Task
    # ============================================

    def start_auto_flush(self) -> None:
        """Start background auto-flush task."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._auto_flush_loop())

    async def _auto_flush_loop(self) -> None:
        """Periodically flush batch."""
        while True:
            await asyncio.sleep(self._flush_interval)
            if self._batch:
                await self._flush_batch()

    # ============================================
    # Query Operations
    # ============================================

    async def query(
        self,
        logql: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 100,
        direction: str = "backward",
    ) -> Optional[Dict]:
        """
        Query logs via LogQL.

        Args:
            logql: LogQL query string (e.g., '{app="isa-agent"}')
            start: Start time (RFC3339 or Unix nanoseconds, default: 1h ago)
            end: End time (RFC3339 or Unix nanoseconds, default: now)
            limit: Max entries to return (default: 100)
            direction: Sort order — "forward" or "backward" (default: backward)

        Returns:
            Query result dict or None on error
        """
        try:
            await self._ensure_connected()

            params = {
                "query": logql,
                "limit": str(limit),
                "direction": direction,
            }
            if start:
                params["start"] = start
            if end:
                params["end"] = end

            async with self._session.get(
                "/loki/api/v1/query_range",
                params=params,
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                text = await resp.text()
                self._logger.warning(f"Loki query returned {resp.status}: {text}")
                return None

        except Exception as e:
            return self.handle_error(e, "query")

    # ============================================
    # Label Discovery
    # ============================================

    async def get_labels(self) -> Optional[List[str]]:
        """Get all label names from Loki."""
        try:
            await self._ensure_connected()
            async with self._session.get("/loki/api/v1/labels") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
                return None
        except Exception as e:
            return self.handle_error(e, "get_labels")

    async def get_label_values(self, label: str) -> Optional[List[str]]:
        """Get values for a specific label."""
        try:
            await self._ensure_connected()
            async with self._session.get(f"/loki/api/v1/label/{label}/values") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
                return None
        except Exception as e:
            return self.handle_error(e, "get_label_values")

    # ============================================
    # Helpers
    # ============================================

    @staticmethod
    def _labels_to_str(labels: Dict[str, str]) -> str:
        """Convert labels dict to a sorted, deterministic string key."""
        return json.dumps(labels, sort_keys=True)
