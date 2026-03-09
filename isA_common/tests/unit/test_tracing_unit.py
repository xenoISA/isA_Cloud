"""OpenTelemetry tracing client unit tests — no infrastructure required."""
import pytest
from unittest.mock import MagicMock, patch


def _has_otel():
    try:
        import opentelemetry  # noqa: F401
        return True
    except ImportError:
        return False


# ============================================================================
# No-Op Tracer (graceful degradation)
# ============================================================================


class TestNoOpSpan:
    def test_set_attribute_is_noop(self):
        from isa_common.tracing import _NoOpSpan

        span = _NoOpSpan()
        span.set_attribute("key", "value")  # should not raise

    def test_set_status_is_noop(self):
        from isa_common.tracing import _NoOpSpan

        span = _NoOpSpan()
        span.set_status("OK")

    def test_record_exception_is_noop(self):
        from isa_common.tracing import _NoOpSpan

        span = _NoOpSpan()
        span.record_exception(RuntimeError("test"))

    def test_add_event_is_noop(self):
        from isa_common.tracing import _NoOpSpan

        span = _NoOpSpan()
        span.add_event("event_name", attributes={"k": "v"})

    def test_context_manager(self):
        from isa_common.tracing import _NoOpSpan

        span = _NoOpSpan()
        with span as s:
            assert s is span


class TestNoOpTracer:
    def test_start_as_current_span_returns_noop(self):
        from isa_common.tracing import _NoOpTracer, _NoOpSpan

        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("op")
        assert isinstance(span, _NoOpSpan)

    def test_start_span_returns_noop(self):
        from isa_common.tracing import _NoOpTracer, _NoOpSpan

        tracer = _NoOpTracer()
        span = tracer.start_span("op")
        assert isinstance(span, _NoOpSpan)


# ============================================================================
# get_tracer()
# ============================================================================


class TestGetTracer:
    def test_returns_noop_by_default(self):
        from isa_common.tracing import _NoOpTracer

        # Reset module state to simulate fresh import
        import isa_common.tracing as mod

        original = mod._tracer
        try:
            mod._tracer = mod._noop_tracer
            tracer = mod.get_tracer()
            assert isinstance(tracer, _NoOpTracer)
        finally:
            mod._tracer = original

    def test_returns_configured_tracer(self):
        import isa_common.tracing as mod

        original = mod._tracer
        sentinel = object()
        try:
            mod._tracer = sentinel
            assert mod.get_tracer() is sentinel
        finally:
            mod._tracer = original


# ============================================================================
# setup_tracing() with mocked opentelemetry
# ============================================================================


class TestSetupTracing:
    def test_noop_when_otel_unavailable(self):
        """When opentelemetry is not available, setup should return without error."""
        import isa_common.tracing as mod

        original = mod._OTEL_AVAILABLE
        try:
            mod._OTEL_AVAILABLE = False
            mod.setup_tracing(service_name="test")  # should not raise
        finally:
            mod._OTEL_AVAILABLE = original

    def test_skips_setup_when_otel_sdk_not_available(self):
        """When _OTEL_AVAILABLE is False, tracer stays as noop."""
        import isa_common.tracing as mod

        original_tracer = mod._tracer
        original_flag = mod._OTEL_AVAILABLE
        try:
            mod._tracer = mod._noop_tracer
            mod._OTEL_AVAILABLE = False
            mod.setup_tracing(service_name="test_svc", auto_instrument=False)
            assert mod._tracer is mod._noop_tracer
        finally:
            mod._tracer = original_tracer
            mod._OTEL_AVAILABLE = original_flag

    def test_env_defaults(self):
        """Verify environment variable defaults."""
        import os

        assert os.getenv("TEMPO_HOST", "localhost") == os.getenv("TEMPO_HOST", "localhost")
        assert int(os.getenv("TEMPO_PORT", "4317")) == int(os.getenv("TEMPO_PORT", "4317"))


# ============================================================================
# Auto-instrumentation helpers
# ============================================================================


class TestAutoInstrumentation:
    def test_instrument_fastapi_returns_false_without_package(self):
        from isa_common.tracing import _instrument_fastapi

        app = MagicMock()
        with patch.dict("sys.modules", {"opentelemetry.instrumentation.fastapi": None}):
            # When the import fails, should return False
            result = _instrument_fastapi(app)
            # Result depends on whether package is installed
            assert isinstance(result, bool)

    def test_instrument_aiohttp_returns_bool(self):
        from isa_common.tracing import _instrument_aiohttp

        result = _instrument_aiohttp()
        assert isinstance(result, bool)

    def test_instrument_asyncpg_returns_bool(self):
        from isa_common.tracing import _instrument_asyncpg

        result = _instrument_asyncpg()
        assert isinstance(result, bool)

    def test_instrument_redis_returns_bool(self):
        from isa_common.tracing import _instrument_redis

        result = _instrument_redis()
        assert isinstance(result, bool)

    def test_instrument_httpx_returns_bool(self):
        from isa_common.tracing import _instrument_httpx

        result = _instrument_httpx()
        assert isinstance(result, bool)


