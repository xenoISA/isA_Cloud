"""L2 Component tests for isa_common.tracing — verify span creation and no-op behavior."""

import pytest
from unittest.mock import MagicMock

try:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

    _OTEL_SDK_AVAILABLE = True
except ImportError:
    _OTEL_SDK_AVAILABLE = False

pytestmark = [
    pytest.mark.component,
]


class TestNoOpTracer:
    """Test no-op tracer behavior (always available, no deps required)."""

    def test_get_tracer_returns_noop_without_setup(self):
        from isa_common.tracing import _NoOpTracer, _noop_tracer
        import isa_common.tracing as t

        old_tracer = t._tracer
        t._tracer = _noop_tracer
        try:
            tracer = t.get_tracer()
            assert isinstance(tracer, _NoOpTracer)
        finally:
            t._tracer = old_tracer

    def test_noop_span_context_manager(self):
        from isa_common.tracing import _NoOpTracer

        tracer = _NoOpTracer()
        with tracer.start_as_current_span("test") as span:
            span.set_attribute("key", "value")
            span.add_event("test_event")

    def test_noop_span_start_span(self):
        from isa_common.tracing import _NoOpTracer, _NoOpSpan

        tracer = _NoOpTracer()
        span = tracer.start_span("test")
        assert isinstance(span, _NoOpSpan)

    def test_noop_span_set_status(self):
        from isa_common.tracing import _NoOpSpan

        span = _NoOpSpan()
        span.set_status("OK")
        span.record_exception(ValueError("test"))


@pytest.mark.skipif(not _OTEL_SDK_AVAILABLE, reason="opentelemetry-sdk not installed")
class TestSpanCreation:
    """Test that spans are created and exported correctly with real SDK."""

    class _CollectingExporter(SpanExporter):
        def __init__(self):
            self.spans = []

        def export(self, spans):
            self.spans.extend(spans)
            return SpanExportResult.SUCCESS

        def shutdown(self):
            pass

        def force_flush(self, timeout_millis=None):
            return True

    @pytest.fixture
    def tracer_with_exporter(self):
        """Create an isolated TracerProvider — no global override needed."""
        exporter = self._CollectingExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        yield provider, exporter
        provider.shutdown()

    def test_span_recorded(self, tracer_with_exporter):
        provider, exporter = tracer_with_exporter

        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("test_operation") as span:
            span.set_attribute("test.key", "test_value")

        assert len(exporter.spans) == 1
        assert exporter.spans[0].name == "test_operation"
        assert exporter.spans[0].attributes["test.key"] == "test_value"

    def test_nested_spans_have_parent(self, tracer_with_exporter):
        provider, exporter = tracer_with_exporter

        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("parent"):
            with tracer.start_as_current_span("child"):
                pass

        assert len(exporter.spans) == 2

        child = next(s for s in exporter.spans if s.name == "child")
        parent = next(s for s in exporter.spans if s.name == "parent")
        assert child.parent.span_id == parent.context.span_id

    def test_span_records_exception(self, tracer_with_exporter):
        provider, exporter = tracer_with_exporter

        tracer = provider.get_tracer("test")
        try:
            with tracer.start_as_current_span("failing") as span:
                raise ValueError("test error")
        except ValueError:
            pass

        assert len(exporter.spans) == 1
        events = exporter.spans[0].events
        assert any(e.name == "exception" for e in events)


class TestSetupTracingDegradation:
    """Test setup_tracing behavior when dependencies are missing."""

    def test_setup_is_noop_when_otel_unavailable(self):
        import isa_common.tracing as t

        old_flag = t._OTEL_AVAILABLE
        old_tracer = t._tracer
        t._OTEL_AVAILABLE = False
        try:
            t.setup_tracing(service_name="test_svc", auto_instrument=False)
            # _tracer should remain unchanged
            assert t._tracer is old_tracer
        finally:
            t._OTEL_AVAILABLE = old_flag
            t._tracer = old_tracer
