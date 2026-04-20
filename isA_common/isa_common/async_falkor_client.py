#!/usr/bin/env python3
"""
Async FalkorDB Native Client

High-performance async client for FalkorDB, the graph database that runs as a
Redis module. Wraps the official `falkordb-py` async driver with the isa_common
AsyncBaseClient conventions:

- Lazy connection with async context manager
- Connection pooling via redis BlockingConnectionPool
- Tenacity-based retry with exponential backoff
- OpenTelemetry tracing per query
- Vector index helpers for the new MCP hierarchical-search backend
  (see ADR-0001 in xenoISA/isA_MCP for graph schema)

Always parameterize Cypher — never string-format user input into queries.
"""

import os
import time
from typing import Any, Dict, List, Literal, Optional, Sequence

from .async_base_client import AsyncBaseClient


class AsyncFalkorClient(AsyncBaseClient):
    """
    Async FalkorDB client using the native `falkordb.asyncio` driver.

    Designed as the unified backend for hierarchical resource discovery in
    isA_MCP (epic xenoISA/isA_MCP#525). Provides:

    - Parameterized Cypher (read-only and write paths)
    - Vector index management and queries (db.idx.vector.queryNodes)
    - Bulk node creation via UNWIND
    - Health check and graph listing
    - OpenTelemetry instrumentation per operation
    """

    SERVICE_NAME = "FalkorDB"
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 6379
    ENV_PREFIX = "FALKOR"

    DEFAULT_GRAPH = "mcp_discovery"

    def __init__(
        self,
        graph: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        max_connections: int = 16,
        socket_timeout: Optional[float] = 30.0,
        ssl: bool = False,
        retry_attempts: int = 3,
        retry_min_wait: float = 0.5,
        retry_max_wait: float = 5.0,
        **kwargs,
    ):
        """
        Initialize the FalkorDB client.

        Args:
            graph: Default graph name (env: FALKOR_GRAPH, default: 'mcp_discovery')
            username: Optional auth username (env: FALKOR_USERNAME)
            password: Optional auth password (env: FALKOR_PASSWORD)
            max_connections: Pool size (default: 16)
            socket_timeout: Per-command timeout in seconds (default: 30.0)
            ssl: Use TLS (default: False)
            retry_attempts: Max retry attempts on transient failures (default: 3)
            retry_min_wait: Initial backoff seconds (default: 0.5)
            retry_max_wait: Max backoff seconds (default: 5.0)
            **kwargs: Base client args (host, port, user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        self._graph_name = graph or os.getenv("FALKOR_GRAPH", self.DEFAULT_GRAPH)
        self._username = username or os.getenv("FALKOR_USERNAME")
        self._password = password or os.getenv("FALKOR_PASSWORD")
        self._max_connections = max_connections
        self._socket_timeout = socket_timeout
        self._ssl = ssl

        self._retry_attempts = retry_attempts
        self._retry_min_wait = retry_min_wait
        self._retry_max_wait = retry_max_wait

        self._db = None
        self._pool = None
        self._tracer = None

    async def _connect(self) -> None:
        """Open a pooled connection to FalkorDB."""
        from falkordb.asyncio import FalkorDB
        from redis.asyncio import BlockingConnectionPool

        pool_kwargs: Dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "max_connections": self._max_connections,
            "decode_responses": True,
            "timeout": self._socket_timeout,
        }
        if self._username:
            pool_kwargs["username"] = self._username
        if self._password:
            pool_kwargs["password"] = self._password
        if self._ssl:
            pool_kwargs["ssl"] = True

        self._pool = BlockingConnectionPool(**pool_kwargs)
        self._db = FalkorDB(connection_pool=self._pool)
        self._logger.info(
            f"Connected to FalkorDB at {self._host}:{self._port} (graph={self._graph_name})"
        )

    async def _disconnect(self) -> None:
        """Close the connection pool."""
        if self._pool:
            try:
                await self._pool.disconnect()
            except Exception as e:
                self._logger.warning(f"FalkorDB pool disconnect raised: {e}")
        self._db = None
        self._pool = None

    def _get_tracer(self):
        """Lazily acquire an OpenTelemetry tracer; tolerate missing OTel."""
        if self._tracer is not None:
            return self._tracer
        try:
            from opentelemetry import trace

            self._tracer = trace.get_tracer("isa_common.falkor")
        except ImportError:
            self._tracer = False
        return self._tracer

    def _select_graph(self, graph: Optional[str]):
        name = graph or self._graph_name
        return self._db.select_graph(name)

    @staticmethod
    def _truncate(text: str, limit: int = 256) -> str:
        if text is None:
            return ""
        return text if len(text) <= limit else f"{text[:limit]}..."

    @staticmethod
    def _result_to_dicts(result) -> List[Dict[str, Any]]:
        """Convert a FalkorDB QueryResult into a list of dict rows."""
        if result is None:
            return []

        rows = getattr(result, "result_set", None)
        if not rows:
            return []

        header = getattr(result, "header", None) or []
        columns: List[str] = []
        for entry in header:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                columns.append(str(entry[1]))
            else:
                columns.append(str(entry))

        if not columns:
            columns = [f"col_{i}" for i in range(len(rows[0]))] if rows else []

        out: List[Dict[str, Any]] = []
        for row in rows:
            normalized: List[Any] = []
            for value in row:
                if hasattr(value, "properties"):
                    normalized.append(
                        {
                            "id": getattr(value, "id", None),
                            "labels": list(getattr(value, "labels", []) or []),
                            "properties": getattr(value, "properties", {}) or {},
                        }
                    )
                else:
                    normalized.append(value)
            out.append(dict(zip(columns, normalized)))
        return out

    async def health_check(self) -> Optional[Dict[str, Any]]:
        """Lightweight health probe using a Redis PING."""
        try:
            await self._ensure_connected()
            pong = await self._db.connection.ping()
            return {"healthy": bool(pong), "graph": self._graph_name}
        except Exception as e:
            return self.handle_error(e, "health check")

    async def list_graphs(self) -> List[str]:
        """Return the list of graphs in the FalkorDB instance."""
        try:
            await self._ensure_connected()
            graphs = await self._db.list_graphs()
            return list(graphs or [])
        except Exception as e:
            self.handle_error(e, "list graphs")
            return []

    async def query(
        self,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
        graph: Optional[str] = None,
        timeout_ms: Optional[int] = None,
        read_only: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a parameterized Cypher query.

        Args:
            cypher: Cypher statement. MUST use parameter placeholders ($name) for
                any caller-supplied value. Never f-string user input into the query.
            params: Parameter dict bound to the query.
            graph: Override the default graph name.
            timeout_ms: Per-query timeout in milliseconds.
            read_only: If True, route via ro_query for read replica friendliness.

        Returns:
            List of row dicts keyed by RETURN clause aliases, or None on error.
        """
        try:
            await self._ensure_connected()
            g = self._select_graph(graph)

            attempt = 0
            last_error: Optional[Exception] = None
            while attempt < self._retry_attempts:
                attempt += 1
                start = time.monotonic()
                tracer = self._get_tracer()
                span_cm = (
                    tracer.start_as_current_span("falkor.query") if tracer else None
                )
                try:
                    if span_cm:
                        with span_cm as span:
                            span.set_attribute("db.system", "falkordb")
                            span.set_attribute("db.name", graph or self._graph_name)
                            span.set_attribute(
                                "db.operation", "ro_query" if read_only else "query"
                            )
                            span.set_attribute(
                                "db.statement", self._truncate(cypher)
                            )
                            result = await self._run_query(
                                g, cypher, params, timeout_ms, read_only
                            )
                            span.set_attribute(
                                "db.rows", len(getattr(result, "result_set", []) or [])
                            )
                            return self._result_to_dicts(result)
                    else:
                        result = await self._run_query(
                            g, cypher, params, timeout_ms, read_only
                        )
                        return self._result_to_dicts(result)
                except Exception as e:
                    last_error = e
                    if not self._is_retriable(e) or attempt >= self._retry_attempts:
                        raise
                    backoff = min(
                        self._retry_max_wait,
                        self._retry_min_wait * (2 ** (attempt - 1)),
                    )
                    self._logger.warning(
                        f"FalkorDB query failed (attempt {attempt}/{self._retry_attempts}): "
                        f"{e}; retrying in {backoff:.2f}s"
                    )
                    import asyncio

                    await asyncio.sleep(backoff)
                finally:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    self._logger.debug(
                        f"FalkorDB query took {elapsed_ms:.1f}ms (attempt {attempt})"
                    )

            if last_error:
                raise last_error
            return []
        except Exception as e:
            return self.handle_error(e, "query")

    async def _run_query(
        self,
        g,
        cypher: str,
        params: Optional[Dict[str, Any]],
        timeout_ms: Optional[int],
        read_only: bool,
    ):
        kwargs: Dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if timeout_ms is not None:
            kwargs["timeout"] = timeout_ms
        if read_only:
            return await g.ro_query(cypher, **kwargs)
        return await g.query(cypher, **kwargs)

    @staticmethod
    def _is_retriable(error: Exception) -> bool:
        """Decide whether to retry — only transient connection errors."""
        message = str(error).lower()
        retriable_hints = (
            "connection",
            "timeout",
            "timed out",
            "reset by peer",
            "broken pipe",
            "loading dataset",
            "max number of clients",
        )
        return any(hint in message for hint in retriable_hints)

    async def query_vector(
        self,
        label: str,
        attribute: str,
        vector: Sequence[float],
        k: int = 10,
        graph: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Vector similarity search via db.idx.vector.queryNodes.

        Args:
            label: Node label that has a vector index on `attribute`.
            attribute: Property name carrying the embedding.
            vector: Query embedding (must match index dimension).
            k: Top-K nearest neighbors.
            graph: Override default graph.

        Returns:
            Rows of {node, score} where node is {id, labels, properties}.
        """
        cypher = (
            "CALL db.idx.vector.queryNodes($label, $attribute, $k, vecf32($vector)) "
            "YIELD node, score RETURN node, score"
        )
        return await self.query(
            cypher,
            params={
                "label": label,
                "attribute": attribute,
                "k": int(k),
                "vector": list(vector),
            },
            graph=graph,
            read_only=True,
        )

    async def bulk_create_nodes(
        self,
        label: str,
        rows: List[Dict[str, Any]],
        merge_on: Optional[str] = None,
        graph: Optional[str] = None,
        batch_size: int = 500,
        vector_props: Optional[List[str]] = None,
    ) -> Optional[int]:
        """
        Insert or upsert nodes in batches via UNWIND.

        Args:
            label: Node label.
            rows: List of property dicts. Each row becomes one node.
            merge_on: If provided, MERGE on this property and SET the rest;
                otherwise CREATE.
            graph: Override default graph.
            batch_size: Rows per Cypher call (default: 500).
            vector_props: Property names that hold embedding vectors. These
                are written via ``vecf32(row.<prop>)`` so the vector index
                can use them. Defaults to ``["embedding"]`` — the canonical
                name across the platform — pass ``[]`` to disable wrapping.

        Returns:
            Total rows written, or None on error.

        Note on vector properties:
            FalkorDB's vector index only sees properties stored via
            ``vecf32(...)``. If you write a list of floats directly with
            ``SET n += row``, the value is stored as a generic array and
            ``db.idx.vector.queryNodes`` returns no matches. This method
            handles the wrap automatically for the names listed in
            ``vector_props``.
        """
        if not rows:
            return 0

        if not label.isidentifier():
            raise ValueError(f"Invalid label: {label!r}")

        if merge_on and not merge_on.isidentifier():
            raise ValueError(f"Invalid merge_on property: {merge_on!r}")

        # Default vector property is `embedding` — the convention used
        # everywhere in the isA platform.
        if vector_props is None:
            vector_props = ["embedding"]
        for vp in vector_props:
            if not vp.isidentifier():
                raise ValueError(f"Invalid vector_prop: {vp!r}")

        # Build a "SET" clause that strips the vector props out of the
        # per-row dict and writes them via vecf32() so the vector index
        # picks them up. Other properties go through the bulk `n += row`.
        scrub = ", ".join(f"{vp}: null" for vp in vector_props)
        if scrub:
            base_set = f"SET n += apoc.map.removeKeys(row, $vec_keys)"
        else:
            base_set = "SET n += row"

        # FalkorDB doesn't ship apoc; use a portable manual approach via
        # WITH and per-property removal. The portable form: store the
        # whole row, then overwrite each vector prop via vecf32().
        per_vec_sets = " ".join(
            f"SET n.{vp} = CASE WHEN row.{vp} IS NULL THEN n.{vp} "
            f"ELSE vecf32(row.{vp}) END"
            for vp in vector_props
        )

        try:
            await self._ensure_connected()

            if merge_on:
                cypher = (
                    f"UNWIND $rows AS row "
                    f"MERGE (n:{label} {{ {merge_on}: row.{merge_on} }}) "
                    f"SET n += row "
                    f"{per_vec_sets}"
                )
            else:
                cypher = (
                    f"UNWIND $rows AS row "
                    f"CREATE (n:{label}) "
                    f"SET n += row "
                    f"{per_vec_sets}"
                )

            total = 0
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                result = await self.query(
                    cypher, params={"rows": batch}, graph=graph
                )
                if result is None:
                    return None
                total += len(batch)
            return total
        except Exception as e:
            return self.handle_error(e, "bulk create nodes")

    async def create_index(
        self,
        label: str,
        prop: str,
        kind: Literal["range", "vector"] = "range",
        dim: Optional[int] = None,
        metric: Literal["cosine", "euclidean"] = "cosine",
        graph: Optional[str] = None,
    ) -> Optional[bool]:
        """
        Create a node index.

        Args:
            label: Node label.
            prop: Property name to index.
            kind: 'range' (B-tree-like) or 'vector'.
            dim: Required for kind='vector' — embedding dimension.
            metric: For kind='vector' — 'cosine' or 'euclidean'.
            graph: Override default graph.

        Returns:
            True on success, None on error.
        """
        if not label.isidentifier():
            raise ValueError(f"Invalid label: {label!r}")
        if not prop.isidentifier():
            raise ValueError(f"Invalid prop: {prop!r}")

        try:
            if kind == "vector":
                if dim is None or dim <= 0:
                    raise ValueError("Vector index requires dim > 0")
                if metric not in ("cosine", "euclidean"):
                    raise ValueError(f"Invalid metric: {metric!r}")
                cypher = (
                    f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.{prop}) "
                    f"OPTIONS {{dimension: {int(dim)}, similarityFunction: '{metric}'}}"
                )
            elif kind == "range":
                cypher = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
            else:
                raise ValueError(f"Unknown index kind: {kind!r}")

            await self.query(cypher, graph=graph)
            return True
        except Exception as e:
            return self.handle_error(e, "create index")

    async def drop_graph(self, graph: Optional[str] = None) -> Optional[bool]:
        """Drop a graph (DESTRUCTIVE). Use only in tests / migrations."""
        try:
            await self._ensure_connected()
            g = self._select_graph(graph)
            await g.delete()
            return True
        except Exception as e:
            return self.handle_error(e, "drop graph")
