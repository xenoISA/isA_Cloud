from pathlib import Path

from scripts.observability_contract_scan import (
    collect_service_monitor_refs,
    scan,
    service_monitor_findings,
)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def rules(summary):
    return {finding.rule for finding in summary.findings}


def test_scan_detects_competing_observability_stacks(tmp_path):
    service_root = tmp_path / "services" / "isa_agent"
    write(
        service_root / "main.py",
        """
from prometheus_client import Counter
from opentelemetry.sdk.trace import TracerProvider

def setup_observability(app): ...

class PrometheusMiddleware: ...

app.add_middleware(PrometheusMiddleware)
app.get("/metrics")(lambda: "metrics")
setup_observability("app")
setup_observability("app")
""",
    )

    summary = scan(
        [service_root],
        tmp_path,
        services=(),
        check_service_monitors=False,
    )

    assert summary.scanned_files == 1
    assert {
        "raw-prometheus-client",
        "raw-tracer-provider",
        "custom-prometheus-middleware",
        "custom-metrics-route",
        "multiple-setup-observability",
    }.issubset(rules(summary))


def test_scan_skips_docs_tests_and_allowed_isa_common_paths(tmp_path):
    write(tmp_path / "docs" / "example.py", "from prometheus_client import Counter\n")
    write(tmp_path / "tests" / "test_metrics.py", "from prometheus_client import Counter\n")
    write(tmp_path / "isA_common" / "isa_common" / "metrics.py", "from prometheus_client import Counter\n")

    summary = scan(
        [tmp_path],
        tmp_path,
        services=(),
        check_service_monitors=False,
    )

    assert summary.scanned_files == 0
    assert summary.findings == []


def test_service_monitor_check_reports_missing_services(tmp_path):
    monitor = write(
        tmp_path / "deployments" / "service-monitors.yaml",
        """
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: isa-agent
spec:
  selector:
    matchLabels:
      app: isa-agent
""",
    )

    refs = collect_service_monitor_refs([monitor])
    assert "isa-agent" in refs

    findings = service_monitor_findings(
        ["isa-agent", "isa-model"],
        [monitor],
        tmp_path,
    )

    assert [finding.service for finding in findings] == ["isa-model"]
    assert findings[0].rule == "missing-service-monitor"
