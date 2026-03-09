"""L3 Integration tests for observability modules — real app, real metrics."""

import pytest

try:
    from prometheus_client import CollectorRegistry
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    _STARLETTE_AVAILABLE = True
except ImportError:
    _STARLETTE_AVAILABLE = False

try:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

    _OTEL_SDK_AVAILABLE = True
except ImportError:
    _OTEL_SDK_AVAILABLE = False

pytestmark = [
    pytest.mark.integration,
]


@pytest.fixture
def metrics_app():
    """Create an app with metrics instrumented on an isolated registry."""
    pytest.importorskip("starlette")
    pytest.importorskip("prometheus_client")

    import isa_common.metrics as m

    registry = CollectorRegistry()
    old_svc, old_reg = m._service_name, m._registry

    async def api_endpoint(request):
        return JSONResponse({"status": "ok"})

    async def items_endpoint(request):
        return JSONResponse({"items": [1, 2, 3]})

    app = Starlette(routes=[
        Route("/api/status", api_endpoint),
        Route("/api/items", items_endpoint),
    ])

    m.setup_metrics(app, service_name="test_integration", registry=registry)

    yield app, registry

    m._service_name, m._registry = old_svc, old_reg


@pytest.mark.skipif(not _STARLETTE_AVAILABLE, reason="starlette not installed")
class TestMetricsIntegration:
    """Test metrics collection through real HTTP requests."""

    def test_full_request_lifecycle_metrics(self, metrics_app):
        app, registry = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/api/status")
        client.get("/api/items")
        client.get("/api/status")

        status_count = registry.get_sample_value(
            "isa_test_integration_http_requests_total",
            {"method": "GET", "path": "/api/status", "status_code": "200"},
        )
        assert status_count == 2.0

        items_count = registry.get_sample_value(
            "isa_test_integration_http_requests_total",
            {"method": "GET", "path": "/api/items", "status_code": "200"},
        )
        assert items_count == 1.0

    def test_duration_histogram_has_observations(self, metrics_app):
        app, registry = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/api/status")

        duration_count = registry.get_sample_value(
            "isa_test_integration_http_request_duration_seconds_count",
            {"method": "GET", "path": "/api/status"},
        )
        assert duration_count == 1.0

        duration_sum = registry.get_sample_value(
            "isa_test_integration_http_request_duration_seconds_sum",
            {"method": "GET", "path": "/api/status"},
        )
        assert duration_sum > 0

    def test_metrics_endpoint_serves_all_recorded_data(self, metrics_app):
        app, _ = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/api/status")
        client.get("/api/items")

        response = client.get("/metrics")
        assert response.status_code == 200
        body = response.text

        assert "isa_test_integration_http_requests_total" in body
        assert "isa_test_integration_http_request_duration_seconds" in body
        assert "# HELP" in body
        assert "# TYPE" in body


@pytest.mark.skipif(not _STARLETTE_AVAILABLE, reason="starlette not installed")
class TestSetServiceNameIntegration:
    """Test that set_service_name works correctly for module-level metric creation."""

    def test_set_service_name_before_metric_creation(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        old_svc, old_reg = m._service_name, m._registry

        try:
            m.set_service_name("integration_test_svc")
            m._registry = registry

            counter = m.create_counter("events_total", "Test events", ["type"])
            counter.labels(type="click").inc()

            val = registry.get_sample_value(
                "isa_integration_test_svc_events_total",
                {"type": "click"},
            )
            assert val == 1.0
        finally:
            m._service_name, m._registry = old_svc, old_reg

    def test_set_service_name_does_not_require_app(self):
        import isa_common.metrics as m

        old_svc = m._service_name
        try:
            m.set_service_name("no_app_svc")
            assert m._service_name == "no_app_svc"
        finally:
            m._service_name = old_svc


@pytest.mark.skipif(not _OTEL_SDK_AVAILABLE, reason="opentelemetry-sdk required")
class TestTracingIntegration:
    """Test tracing with in-memory exporter captures spans correctly."""

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
    def tracing_provider(self):
        """Create an isolated TracerProvider — no global override needed."""
        exporter = self._CollectingExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        yield provider, exporter
        provider.shutdown()

    def test_manual_span_creation_and_export(self, tracing_provider):
        provider, exporter = tracing_provider

        tracer = provider.get_tracer("integration_test")
        with tracer.start_as_current_span("integration_operation") as span:
            span.set_attribute("test.integration", True)

        op_spans = [s for s in exporter.spans if s.name == "integration_operation"]
        assert len(op_spans) == 1
        assert op_spans[0].attributes["test.integration"] is True

    def test_nested_spans_maintain_context(self, tracing_provider):
        provider, exporter = tracing_provider

        tracer = provider.get_tracer("integration_test")
        with tracer.start_as_current_span("parent_op"):
            with tracer.start_as_current_span("child_op"):
                pass

        child = next(s for s in exporter.spans if s.name == "child_op")
        parent = next(s for s in exporter.spans if s.name == "parent_op")
        assert child.parent.span_id == parent.context.span_id
