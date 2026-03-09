"""Unified observability setup unit tests — no infrastructure required."""
import pytest
from unittest.mock import MagicMock, patch


# ============================================================================
# setup_observability() — all pillars enabled
# ============================================================================


class TestSetupObservabilityAllEnabled:
    def test_all_pillars_attempted_by_default(self):
        """All three pillars should be attempted when all flags are True (default)."""
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(app, service_name="test_svc", version="1.0.0")

        # All three keys present — each is True or False depending on available libs
        assert "metrics" in result
        assert "logging" in result
        assert "tracing" in result
        assert all(isinstance(v, bool) for v in result.values())

    def test_returns_dict_with_three_keys(self):
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(app, service_name="test_svc")

        assert "metrics" in result
        assert "logging" in result
        assert "tracing" in result


# ============================================================================
# Individual enable/disable flags
# ============================================================================


class TestSetupObservabilityFlags:
    def test_disable_metrics(self):
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(app, service_name="test", enable_metrics=False)
        assert result["metrics"] is False

    def test_disable_logging(self):
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(app, service_name="test", enable_logging=False)
        assert result["logging"] is False

    def test_disable_tracing(self):
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(app, service_name="test", enable_tracing=False)
        assert result["tracing"] is False

    def test_all_disabled(self):
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(
            app,
            service_name="test",
            enable_metrics=False,
            enable_logging=False,
            enable_tracing=False,
        )
        assert result == {"metrics": False, "logging": False, "tracing": False}


# ============================================================================
# Partial failure resilience
# ============================================================================


class TestPartialFailure:
    def test_never_raises_even_with_all_pillars(self):
        """setup_observability should never propagate exceptions from individual pillars."""
        from isa_common.observability import setup_observability

        app = MagicMock()
        # The function has try/except for each pillar; just verify it doesn't raise
        result = setup_observability(app, service_name="test")
        assert isinstance(result, dict)

    def test_disabled_metrics_still_enables_others(self):
        """Disabling metrics should not affect logging/tracing attempts."""
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(app, service_name="test", enable_metrics=False)
        assert result["metrics"] is False
        # Other pillars were still attempted (may be True or False based on libs)
        assert "logging" in result
        assert "tracing" in result

    def test_disabled_logging_still_enables_others(self):
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(app, service_name="test", enable_logging=False)
        assert result["logging"] is False
        assert "metrics" in result
        assert "tracing" in result

    def test_disabled_tracing_still_enables_others(self):
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(app, service_name="test", enable_tracing=False)
        assert result["tracing"] is False
        assert "metrics" in result
        assert "logging" in result


# ============================================================================
# Return value accuracy
# ============================================================================


class TestReturnValue:
    def test_return_value_reflects_actual_state(self):
        """Return dict should accurately reflect which pillars initialized."""
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(app, service_name="test")

        # Each value must be a bool
        for key in ("metrics", "logging", "tracing"):
            assert isinstance(result[key], bool), f"{key} should be bool, got {type(result[key])}"

    def test_extra_labels_passed_through(self):
        """extra_labels param should not cause errors."""
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(
            app,
            service_name="test",
            extra_labels={"team": "platform", "region": "us-east-1"},
        )
        assert isinstance(result, dict)

    def test_custom_loki_url(self):
        """Custom loki_url should not cause errors."""
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(
            app,
            service_name="test",
            loki_url="http://custom-loki:3100",
        )
        assert isinstance(result, dict)

    def test_custom_tempo_config(self):
        """Custom tempo host/port should not cause errors."""
        from isa_common.observability import setup_observability

        app = MagicMock()
        result = setup_observability(
            app,
            service_name="test",
            tempo_host="custom-tempo",
            tempo_port=4318,
        )
        assert isinstance(result, dict)
