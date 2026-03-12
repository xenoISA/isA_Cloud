"""Unit tests for #120 — verify datetime.utcnow() is replaced with timezone-aware datetime."""
import ast
import pytest
from datetime import timezone
from pathlib import Path

# Resolve paths relative to the isa_common package root
_PKG_ROOT = Path(__file__).resolve().parents[2] / "isa_common"


class TestNoDeprecatedDatetime:
    """Ensure no file uses the deprecated datetime.utcnow()."""

    FILES_TO_CHECK = [
        _PKG_ROOT / "async_mqtt_client.py",
        _PKG_ROOT / "events" / "base_event_models.py",
        _PKG_ROOT / "events" / "billing_events.py",
    ]

    @pytest.mark.parametrize("filepath", FILES_TO_CHECK, ids=lambda p: p.name)
    def test_no_utcnow_calls(self, filepath):
        """Files must not contain datetime.utcnow() calls."""
        source = filepath.read_text()
        assert "datetime.utcnow()" not in source, (
            f"{filepath.name} still contains deprecated datetime.utcnow()"
        )

    @pytest.mark.parametrize("filepath", FILES_TO_CHECK, ids=lambda p: p.name)
    def test_no_utcnow_references(self, filepath):
        """Files must not reference datetime.utcnow as a callable (e.g. default_factory)."""
        source = filepath.read_text()
        lines = source.splitlines()
        for i, line in enumerate(lines, 1):
            if "utcnow" in line:
                pytest.fail(
                    f"{filepath.name}:{i} still references utcnow: {line.strip()}"
                )


class TestEventModelsTimezoneAware:
    """Verify event model defaults produce timezone-aware datetimes."""

    def test_base_event_metadata_has_timezone(self):
        from isa_common.events.base_event_models import EventMetadata

        meta = EventMetadata()
        assert meta.timestamp.tzinfo is not None, "EventMetadata.timestamp must be timezone-aware"

    def test_usage_event_has_timezone(self):
        from isa_common.events.billing_events import UsageEvent, UnitType
        from decimal import Decimal

        event = UsageEvent(
            user_id="u1",
            product_id="gpt-4",
            usage_amount=Decimal("100"),
            unit_type=UnitType.TOKEN,
        )
        assert event.timestamp.tzinfo is not None, "UsageEvent.timestamp must be timezone-aware"

    def test_billing_calculated_event_has_timezone(self):
        from isa_common.events.billing_events import BillingCalculatedEvent, UnitType
        from decimal import Decimal

        event = BillingCalculatedEvent(
            user_id="u1",
            billing_record_id="br1",
            usage_event_id="ue1",
            product_id="gpt-4",
            actual_usage=Decimal("100"),
            unit_type=UnitType.TOKEN,
            token_equivalent=Decimal("100"),
            cost_usd=Decimal("0.01"),
            unit_price=Decimal("0.0001"),
            token_conversion_rate=Decimal("1"),
        )
        assert event.timestamp.tzinfo is not None
