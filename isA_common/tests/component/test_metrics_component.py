"""L2 Component tests for isa_common.metrics — real middleware with TestClient."""

import pytest
from unittest.mock import MagicMock

try:
    from prometheus_client import CollectorRegistry
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False

pytestmark = [
    pytest.mark.component,
    pytest.mark.skipif(not _DEPS_AVAILABLE, reason="starlette or prometheus_client not installed"),
]


@pytest.fixture
def metrics_app():
    """Create a Starlette app instrumented with isa_common metrics."""
    import isa_common.metrics as m

    registry = CollectorRegistry()
    old_svc, old_reg = m._service_name, m._registry
    m._service_name, m._registry = "test_component", registry

    async def homepage(request):
        return PlainTextResponse("ok")

    async def users(request):
        return PlainTextResponse("users")

    async def health(request):
        return PlainTextResponse("healthy")

    app = Starlette(routes=[
        Route("/", homepage),
        Route("/api/users", users),
        Route("/health", health),
    ])

    m.setup_metrics(app, service_name="test_component", registry=registry)

    yield app, registry

    m._service_name, m._registry = old_svc, old_reg


class TestMetricsMiddleware:
    """Test that metrics middleware records request data correctly."""

    def test_request_increments_counter(self, metrics_app):
        app, registry = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/")

        text = registry.get_sample_value(
            "isa_test_component_http_requests_total",
            {"method": "GET", "path": "/", "status_code": "200"},
        )
        assert text is not None
        assert text >= 1.0

    def test_request_records_duration(self, metrics_app):
        app, registry = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/api/users")

        count = registry.get_sample_value(
            "isa_test_component_http_request_duration_seconds_count",
            {"method": "GET", "path": "/api/users"},
        )
        assert count is not None
        assert count >= 1.0

    def test_excluded_path_not_recorded(self, metrics_app):
        app, registry = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/health")

        text = registry.get_sample_value(
            "isa_test_component_http_requests_total",
            {"method": "GET", "path": "/health", "status_code": "200"},
        )
        assert text is None

    def test_multiple_requests_accumulate(self, metrics_app):
        app, registry = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/")
        client.get("/")
        client.get("/")

        text = registry.get_sample_value(
            "isa_test_component_http_requests_total",
            {"method": "GET", "path": "/", "status_code": "200"},
        )
        assert text is not None
        assert text >= 3.0

    def test_in_progress_gauge_returns_to_zero(self, metrics_app):
        app, registry = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/")

        in_progress = registry.get_sample_value(
            "isa_test_component_http_requests_in_progress",
            {"method": "GET"},
        )
        assert in_progress is not None
        assert in_progress == 0.0


class TestMetricsEndpoint:
    """Test the /metrics endpoint serves Prometheus exposition format."""

    def test_metrics_endpoint_returns_200(self, metrics_app):
        app, _ = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_endpoint_contains_help_text(self, metrics_app):
        app, _ = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/metrics")
        assert "# HELP" in response.text

    def test_metrics_endpoint_contains_recorded_metrics(self, metrics_app):
        app, _ = metrics_app
        client = TestClient(app, raise_server_exceptions=False)

        # Generate some metrics first
        client.get("/")

        response = client.get("/metrics")
        assert "isa_test_component_http_requests_total" in response.text
