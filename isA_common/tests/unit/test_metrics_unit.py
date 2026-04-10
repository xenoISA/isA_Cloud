"""Prometheus metrics client unit tests — no infrastructure required."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

try:
    from prometheus_client import CollectorRegistry
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False

pytestmark = pytest.mark.skipif(
    not _HAS_PROMETHEUS, reason="prometheus_client not installed"
)


# ============================================================================
# Naming Convention
# ============================================================================


class TestMetricName:
    def test_standard_naming(self):
        from isa_common.metrics import _metric_name

        assert _metric_name("user", "requests_total") == "isa_user_requests_total"

    def test_service_with_dashes(self):
        from isa_common.metrics import _metric_name

        assert _metric_name("my-service", "errors_total") == "isa_my_service_errors_total"

    def test_service_with_spaces(self):
        from isa_common.metrics import _metric_name

        assert _metric_name("my service", "count") == "isa_my_service_count"

    def test_deduplicates_isa_prefix(self):
        from isa_common.metrics import _metric_name

        assert _metric_name("isA_user", "requests_total") == "isa_user_requests_total"

    def test_isa_prefix_case_insensitive(self):
        from isa_common.metrics import _metric_name

        # "isA_" lowered becomes "isa_" which triggers dedup
        assert _metric_name("ISA_Model", "latency") == "isa_model_latency"

    def test_no_prefix_when_not_isa(self):
        from isa_common.metrics import _metric_name

        assert _metric_name("gateway", "bytes_total") == "isa_gateway_bytes_total"


# ============================================================================
# Path Normalization
# ============================================================================


class TestNormalizePath:
    def test_uuid_replaced(self):
        from isa_common.metrics import _normalize_path

        path = "/api/users/550e8400-e29b-41d4-a716-446655440000"
        assert _normalize_path(path) == "/api/users/{id}"

    def test_numeric_id_replaced(self):
        from isa_common.metrics import _normalize_path

        assert _normalize_path("/api/orders/12345") == "/api/orders/{id}"

    def test_multiple_numeric_segments(self):
        from isa_common.metrics import _normalize_path

        assert _normalize_path("/api/users/42/orders/99") == "/api/users/{id}/orders/{id}"

    def test_no_replacement_for_named_segments(self):
        from isa_common.metrics import _normalize_path

        assert _normalize_path("/api/users/search") == "/api/users/search"

    def test_uuid_mid_path(self):
        from isa_common.metrics import _normalize_path

        path = "/api/orgs/550e8400-e29b-41d4-a716-446655440000/members"
        assert _normalize_path(path) == "/api/orgs/{id}/members"

    def test_root_path_unchanged(self):
        from isa_common.metrics import _normalize_path

        assert _normalize_path("/") == "/"

    def test_trailing_numeric_segment(self):
        from isa_common.metrics import _normalize_path

        assert _normalize_path("/items/7") == "/items/{id}"


# ============================================================================
# NoOp Metric
# ============================================================================


class TestNoOpMetric:
    def test_labels_returns_self(self):
        from isa_common.metrics import _NoOpMetric

        noop = _NoOpMetric()
        result = noop.labels(method="GET", path="/test")
        assert result is noop

    def test_inc_dec_set_observe_are_safe(self):
        from isa_common.metrics import _NoOpMetric

        noop = _NoOpMetric()
        # These should not raise
        noop.inc()
        noop.inc(5)
        noop.dec()
        noop.dec(3)
        noop.set(42)
        noop.observe(0.5)
        noop.info({"key": "val"})

    def test_chaining_labels_then_inc(self):
        from isa_common.metrics import _NoOpMetric

        noop = _NoOpMetric()
        # Should not raise — common usage pattern
        noop.labels(status="ok").inc()

    def test_time_context_manager(self):
        from isa_common.metrics import _NoOpMetric

        noop = _NoOpMetric()
        with noop.time():
            pass  # Should not raise


# ============================================================================
# Bucket Configurations
# ============================================================================


class TestBucketConfigs:
    def test_fast_buckets_ascending(self):
        from isa_common.metrics import FAST_BUCKETS

        assert list(FAST_BUCKETS) == sorted(FAST_BUCKETS)
        assert FAST_BUCKETS[0] > 0

    def test_default_buckets_ascending(self):
        from isa_common.metrics import DEFAULT_BUCKETS

        assert list(DEFAULT_BUCKETS) == sorted(DEFAULT_BUCKETS)

    def test_slow_buckets_ascending(self):
        from isa_common.metrics import SLOW_BUCKETS

        assert list(SLOW_BUCKETS) == sorted(SLOW_BUCKETS)
        assert SLOW_BUCKETS[-1] >= 60  # Should cover long operations

    def test_fast_smaller_than_default(self):
        from isa_common.metrics import FAST_BUCKETS, DEFAULT_BUCKETS

        assert FAST_BUCKETS[-1] <= DEFAULT_BUCKETS[-1]

    def test_default_smaller_than_slow(self):
        from isa_common.metrics import DEFAULT_BUCKETS, SLOW_BUCKETS

        assert DEFAULT_BUCKETS[-1] <= SLOW_BUCKETS[-1]


# ============================================================================
# Factory Functions (with isolated registry)
# ============================================================================


class TestCreateCounter:
    def test_creates_counter_with_correct_name(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        old_svc, old_reg = m._service_name, m._registry
        m._service_name, m._registry = "test_svc", registry
        try:
            counter = m.create_counter("events_total", "Total events")
            # prometheus_client Counter strips _total suffix from _name
            assert "isa_test_svc_events" in counter._name
        finally:
            m._service_name, m._registry = old_svc, old_reg

    def test_creates_counter_with_labels(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        old_svc, old_reg = m._service_name, m._registry
        m._service_name, m._registry = "test_svc", registry
        try:
            counter = m.create_counter("req_total", "Requests", ["method", "status"])
            counter.labels(method="GET", status="200").inc()
            # Should not raise
        finally:
            m._service_name, m._registry = old_svc, old_reg


class TestCreateHistogram:
    def test_creates_histogram_with_correct_name(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        old_svc, old_reg = m._service_name, m._registry
        m._service_name, m._registry = "test_svc", registry
        try:
            hist = m.create_histogram("duration_seconds", "Duration")
            assert hist._name == "isa_test_svc_duration_seconds"
        finally:
            m._service_name, m._registry = old_svc, old_reg

    def test_custom_buckets(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        old_svc, old_reg = m._service_name, m._registry
        m._service_name, m._registry = "test_svc", registry
        try:
            buckets = (0.1, 0.5, 1.0)
            hist = m.create_histogram("latency", "Latency", buckets=buckets)
            # Upper bounds include +Inf
            assert list(hist._upper_bounds) == [0.1, 0.5, 1.0, float("inf")]
        finally:
            m._service_name, m._registry = old_svc, old_reg


class TestCreateGauge:
    def test_creates_gauge_with_correct_name(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        old_svc, old_reg = m._service_name, m._registry
        m._service_name, m._registry = "test_svc", registry
        try:
            gauge = m.create_gauge("connections", "Active connections")
            assert gauge._name == "isa_test_svc_connections"
        finally:
            m._service_name, m._registry = old_svc, old_reg

    def test_gauge_set_and_read(self):
        import isa_common.metrics as m
        from prometheus_client import REGISTRY

        registry = CollectorRegistry()
        old_svc, old_reg = m._service_name, m._registry
        m._service_name, m._registry = "test_svc", registry
        try:
            gauge = m.create_gauge("temp", "Temperature")
            gauge.set(42)
            assert gauge._value.get() == 42.0
        finally:
            m._service_name, m._registry = old_svc, old_reg


# ============================================================================
# Graceful Degradation (prometheus_client absent)
# ============================================================================


class TestGracefulDegradation:
    def test_create_counter_returns_noop_when_unavailable(self):
        import isa_common.metrics as m

        old_flag = m._PROMETHEUS_AVAILABLE
        m._PROMETHEUS_AVAILABLE = False
        try:
            result = m.create_counter("test", "desc")
            assert isinstance(result, m._NoOpMetric)
        finally:
            m._PROMETHEUS_AVAILABLE = old_flag

    def test_create_histogram_returns_noop_when_unavailable(self):
        import isa_common.metrics as m

        old_flag = m._PROMETHEUS_AVAILABLE
        m._PROMETHEUS_AVAILABLE = False
        try:
            result = m.create_histogram("test", "desc")
            assert isinstance(result, m._NoOpMetric)
        finally:
            m._PROMETHEUS_AVAILABLE = old_flag

    def test_create_gauge_returns_noop_when_unavailable(self):
        import isa_common.metrics as m

        old_flag = m._PROMETHEUS_AVAILABLE
        m._PROMETHEUS_AVAILABLE = False
        try:
            result = m.create_gauge("test", "desc")
            assert isinstance(result, m._NoOpMetric)
        finally:
            m._PROMETHEUS_AVAILABLE = old_flag

    def test_metrics_text_returns_empty_when_unavailable(self):
        import isa_common.metrics as m

        old_flag = m._PROMETHEUS_AVAILABLE
        m._PROMETHEUS_AVAILABLE = False
        try:
            assert m.metrics_text() == b""
        finally:
            m._PROMETHEUS_AVAILABLE = old_flag


# ============================================================================
# setup_metrics
# ============================================================================


class TestSetupMetrics:
    def test_sets_service_name_and_registry(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        app = MagicMock()
        app.routes = []

        old_svc, old_reg = m._service_name, m._registry
        try:
            result = m.setup_metrics(app, service_name="isA_test", registry=registry)
            assert result is True
            assert m._service_name == "isA_test"
            assert m._registry is registry
        finally:
            m._service_name, m._registry = old_svc, old_reg

    def test_adds_middleware_and_metrics_route(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        app = MagicMock()
        app.routes = []

        old_svc, old_reg = m._service_name, m._registry
        try:
            m.setup_metrics(app, service_name="isA_test", registry=registry)
            app.add_middleware.assert_called_once()
            assert len(app.routes) == 1
            assert app.routes[0].path == "/metrics"
        finally:
            m._service_name, m._registry = old_svc, old_reg

    def test_initializes_common_metrics(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        app = MagicMock()
        app.routes = []

        old_svc, old_reg = m._service_name, m._registry
        old_total = m.HTTP_REQUESTS_TOTAL
        try:
            m.setup_metrics(app, service_name="isA_test", registry=registry)
            # Common metrics should no longer be the initial _NOOP
            assert not isinstance(m.HTTP_REQUESTS_TOTAL, m._NoOpMetric)
            assert not isinstance(m.HTTP_REQUEST_DURATION, m._NoOpMetric)
            assert not isinstance(m.HTTP_REQUESTS_IN_PROGRESS, m._NoOpMetric)
        finally:
            m._service_name, m._registry = old_svc, old_reg
            m.HTTP_REQUESTS_TOTAL = old_total

    def test_skips_when_prometheus_unavailable(self):
        import isa_common.metrics as m

        old_flag = m._PROMETHEUS_AVAILABLE
        m._PROMETHEUS_AVAILABLE = False
        try:
            app = MagicMock()
            app.routes = []
            result = m.setup_metrics(app, service_name="isA_test")
            assert result is False
            # Should not add middleware or routes
            app.add_middleware.assert_not_called()
            assert len(app.routes) == 0
        finally:
            m._PROMETHEUS_AVAILABLE = old_flag

    def test_custom_excluded_paths(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        app = MagicMock()
        app.routes = []

        old_svc, old_reg = m._service_name, m._registry
        old_excluded = m._EXCLUDED_PATHS.copy()
        try:
            m.setup_metrics(
                app,
                service_name="isA_test",
                registry=registry,
                excluded_paths={"/custom-health"},
            )
            assert "/custom-health" in m._EXCLUDED_PATHS
        finally:
            m._service_name, m._registry = old_svc, old_reg
            m._EXCLUDED_PATHS.clear()
            m._EXCLUDED_PATHS.update(old_excluded)


# ============================================================================
# metrics_text
# ============================================================================


class TestMetricsText:
    def test_returns_bytes(self):
        import isa_common.metrics as m

        registry = CollectorRegistry()
        old_reg = m._registry
        m._registry = registry
        try:
            result = m.metrics_text()
            assert isinstance(result, bytes)
        finally:
            m._registry = old_reg

    def test_contains_registered_metric(self):
        import isa_common.metrics as m
        from prometheus_client import Counter

        registry = CollectorRegistry()
        old_svc, old_reg = m._service_name, m._registry
        m._service_name, m._registry = "txt_test", registry
        try:
            counter = m.create_counter("check_total", "A check metric")
            counter.inc()
            text = m.metrics_text()
            assert b"isa_txt_test_check_total" in text
        finally:
            m._service_name, m._registry = old_svc, old_reg


# ============================================================================
# Excluded Paths
# ============================================================================


class TestExcludedPaths:
    def test_default_excluded_paths(self):
        from isa_common.metrics import _EXCLUDED_PATHS

        assert "/health" in _EXCLUDED_PATHS
        assert "/metrics" in _EXCLUDED_PATHS
        assert "/ready" in _EXCLUDED_PATHS
        assert "/live" in _EXCLUDED_PATHS
