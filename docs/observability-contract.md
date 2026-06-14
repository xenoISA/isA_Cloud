# isA Platform Observability Contract

> Canonical runtime observability contract for deployable Python services using
> `isa_common`.
> Last updated: 2026-06-13

## Purpose

`isa_common` is the single platform entrypoint for service runtime
observability. A deployable Python service MUST NOT create a competing
Prometheus middleware, OpenTelemetry provider, Loki handler, or duplicate
`core/tracing.py` module when the same behavior is provided by `isa_common`.

This contract covers service startup, resource identity, trace propagation,
metrics, logs, redaction, degradation behavior, and approved service-specific
extensions. Service migration tracking, scanner enforcement, Collector
pipeline changes, and Grafana dashboards are handled by follow-up issues.

## Required Startup Pattern

FastAPI and Starlette services MUST initialize observability exactly once during
application startup or lifespan setup, before serving requests:

```python
from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from isa_common.observability import setup_observability


def configure_observability(app: FastAPI) -> None:
    service_name = os.environ["ISA_SERVICE_NAME"]
    service_version = os.environ["ISA_SERVICE_VERSION"]

    result = setup_observability(
        app,
        service_name=service_name,
        version=service_version,
        loki_url=os.getenv("LOKI_URL"),
        tempo_host=os.getenv("TEMPO_HOST"),
        tempo_port=int(os.getenv("TEMPO_PORT", "4317")),
        extra_labels={
            "component": "api",
        },
    )

    if not all(result.values()):
        logging.getLogger(__name__).warning(
            "observability_degraded",
            extra={"observability": result},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_observability(app)
    yield


app = FastAPI(lifespan=lifespan)
```

Rules:

- `setup_observability()` is preferred over calling `setup_metrics()`,
  `setup_loki_logging()`, or `setup_tracing()` separately.
- Calling lower-level setup functions is allowed only for non-HTTP utilities or
  tests that cannot use the full stack.
- Initialization MUST NOT run at import time.
- The `version` argument MUST NOT be `unknown` outside local development and
  tests.
- If custom metrics are created before `setup_observability()`, call
  `isa_common.metrics.set_service_name(service_name)` first. Prefer creating
  service metrics after startup when possible.

## Required Configuration

Deployments MUST provide these service identity values and pass them into
`setup_observability()`:

| Input | Required | Source | Contract |
|-------|----------|--------|----------|
| `ISA_SERVICE_NAME` | Yes | Deployment env | Stable platform service identity. Maps to OTel `service.name`. |
| `ISA_SERVICE_VERSION` | Yes | Deployment env | Build, image, package, or release version. Maps to OTel `service.version`. |
| `ISA_ENV` | Yes | Deployment env | Runtime environment. Maps to OTel `deployment.environment`. |

`isa_common` also reads these endpoint settings:

| Env var | Required | Default | Contract |
|---------|----------|---------|----------|
| `LOKI_URL` | Required when log shipping is enabled outside local dev | `http://localhost:3100` | Loki HTTP endpoint used by `setup_loki_logging()`. |
| `TEMPO_HOST` | Required when tracing is enabled outside local dev | `localhost` | Tempo or OTLP trace receiver host used by `setup_tracing()`. |
| `TEMPO_PORT` | Required when tracing is enabled outside local dev | `4317` | OTLP gRPC trace receiver port. |
| `OTEL_EXPORTER_OTLP_INSECURE` | No | `true` | Controls insecure OTLP gRPC export. Production should set this deliberately. |

Do not rely on `OTEL_SERVICE_NAME` or `OTEL_RESOURCE_ATTRIBUTES` to set Python
service identity unless `isa_common` is updated to read them. The contract
requires explicit `service_name` and `version` arguments so metrics, logs, and
traces share the same identity.

## Resource Attributes

Every trace provider configured by `isa_common.tracing.setup_tracing()` MUST
emit:

| Attribute | Source | Example |
|-----------|--------|---------|
| `service.name` | `service_name` argument | `isA_Model` |
| `service.version` | `version` argument | `2026.06.13-1a2b3c4` |
| `deployment.environment` | `ISA_ENV` | `production` |

Services MAY add low-cardinality resource attributes through
`extra_attributes` when calling `setup_tracing()` directly in approved
non-HTTP contexts. Examples: `service.namespace`, `cloud.region`,
`k8s.namespace.name`. Do not put request IDs, user IDs, prompt IDs, run IDs, or
object IDs in resource attributes.

## Trace Propagation

`isa_common.tracing` configures W3C Trace Context and W3C Baggage propagation.
Services MUST preserve one distributed trace across inbound requests, outbound
HTTP calls, worker calls, and event boundaries.

Required behavior:

- Accept and extract inbound `traceparent` and `tracestate` headers.
- Inject `traceparent` and `tracestate` on outbound HTTP calls through
  instrumented clients such as `httpx` and `aiohttp`.
- Preserve `traceparent` and `tracestate` in event envelopes when work crosses
  NATS, queues, task runners, or scheduler boundaries.
- Use Baggage only for low-cardinality, non-sensitive routing context.
- Do not invent service-specific trace headers as the primary propagation path.
  Legacy headers may be mirrored temporarily only during migration.
- Health, readiness, liveness, and metrics endpoints are excluded from automatic
  HTTP tracing and metrics by default.

Manual spans MUST be children of the active request or worker span:

```python
from isa_common.tracing import get_tracer

tracer = get_tracer()

with tracer.start_as_current_span("model.inference") as span:
    span.set_attribute("gen_ai.system", "openai")
    span.set_attribute("gen_ai.request.model", normalized_model_name)
    span.set_attribute("isa.operation", "chat_completion")
```

## Metrics Contract

Services MUST use `isa_common.metrics` factories and middleware for Prometheus
metrics unless an exporter is explicitly approved by the platform team.

Metric naming:

- Names use `isa_{service}_{metric}_{unit}`.
- `service` is the service name lowercased with `isA_` removed and separators
  normalized to underscores.
- Counters end in `_total`.
- Durations use seconds and end in `_seconds`.
- Byte sizes end in `_bytes`.
- Use `FAST_BUCKETS`, `DEFAULT_BUCKETS`, or `SLOW_BUCKETS` unless a service has
  a documented SLO-driven bucket requirement.

Default HTTP metrics:

| Metric suffix | Labels | Notes |
|---------------|--------|-------|
| `http_requests_total` | `method`, `path`, `status_code` | `path` is normalized to collapse IDs. |
| `http_request_duration_seconds` | `method`, `path` | Uses default latency buckets. |
| `http_request_size_bytes` | `method`, `path` | Body size when available. |
| `http_response_size_bytes` | `method`, `path` | Response size when available. |
| `http_requests_in_progress` | `method` | Active request gauge. |
| `service` info metric | `name`, `version` values | Service identity, not a high-cardinality label set. |

Allowed labels are bounded, enumerable dimensions such as `method`,
`status_code`, `operation`, `component`, `queue`, `model_family`,
`tool_family`, and `outcome`.

Forbidden metric labels include `user_id`, `org_id`, `session_id`,
`request_id`, `trace_id`, `span_id`, `run_id`, `prompt_id`, raw URL, raw path,
email, IP address, file path, object key, SQL text, prompt text, and response
text.

## Log Contract

Services MUST send application logs through `isa_common` Loki integration when
log shipping is enabled.

Loki stream labels MUST stay low cardinality:

| Label | Required | Notes |
|-------|----------|-------|
| `app` | Yes | Current `isa_common` label for service name. |
| `env` | Yes | Current `isa_common` label for deployment environment. |
| `level` | Yes | Logging level name. |
| `logger` | Yes | Python logger name. Keep logger names stable. |
| `component` | Optional | Static service component, such as `api`, `worker`, or `scheduler`. |

`app` and `env` are the current Loki label names emitted by
`setup_loki_logging()`. Query layers and dashboards MAY alias them to
`service.name` and `deployment.environment`, but services should not emit both
sets as separate labels until the platform changes the handler.

Structured log bodies SHOULD include these fields when available:

- `trace_id`
- `span_id`
- `request_id`
- `session_id`
- `service.name`
- `service.version`
- `deployment.environment`
- `operation`
- `outcome`

High-cardinality correlation fields belong in the log body, not Loki labels.
Sensitive fields MUST be redacted before the record is emitted.

## Redaction Defaults

Telemetry MUST be safe by default. Redaction applies before values are attached
to logs, spans, metrics, events, tracker metadata, or exception messages.

Always redact:

- Credentials: `authorization`, `cookie`, `set-cookie`, `api_key`, `token`,
  `secret`, `password`, `private_key`, `session_token`, `refresh_token`.
- Prompt and generation content: `prompt`, `messages`, `input`, `output`,
  `response`, `completion`, `tool_result`, `retrieved_context`.
- Personal data unless explicitly approved for a product telemetry store:
  emails, phone numbers, addresses, payment data, and government IDs.
- Raw SQL text, raw vector payloads, full file paths, object keys, and headers
  outside an allowlist.

Default transformations:

- Replace secret-like values with `[REDACTED]`.
- Record content lengths, token counts, hashes, or normalized categories instead
  of raw prompt/response text.
- Truncate free-form error messages and exception strings before exporting.
- Use allowlists for headers and structured fields that may be exported.

Services that need richer product telemetry, such as agent tracker replay data,
MUST store it in the product telemetry path and link it to OTel by trace/span
identity. They MUST NOT put raw prompt or response content into Loki labels,
metric labels, or OTel resource attributes.

## Degradation Behavior

Observability failure MUST NOT break the request path.

Expected behavior:

| Failure | Required service behavior |
|---------|---------------------------|
| Optional Python dependency missing | `isa_common` returns no-op metrics/tracing behavior and logs a warning. |
| Prometheus unavailable | Service continues exposing `/metrics`; missed scrapes are handled by Prometheus. |
| Loki unavailable | Request path continues; log shipping MUST avoid blocking request handling and surface queue/drop failures through warnings or counters. |
| Tempo or OTLP receiver unavailable | Spans are dropped by the exporter queue; requests continue. |
| Collector unavailable | Same as Tempo/OTLP unavailable until #454 changes the pipeline. |
| Partial setup failure | `setup_observability()` returns a per-pillar result dict and service logs degraded state. |

Readiness probes SHOULD remain focused on serving capability, not external
telemetry reachability. Separate preflight or health detail endpoints SHOULD
surface telemetry degradation for operators.

## Service-Specific Extensions

Extensions are allowed when they use `isa_common` helpers and follow the
cardinality and redaction rules above.

### Model Service

```python
from isa_common.metrics import SLOW_BUCKETS, create_counter, create_histogram
from isa_common.tracing import get_tracer

model_requests = create_counter(
    "model_requests_total",
    "Model inference requests",
    ["model_family", "outcome"],
)
model_latency = create_histogram(
    "model_request_duration_seconds",
    "Model inference latency",
    ["model_family"],
    buckets=SLOW_BUCKETS,
)

tracer = get_tracer()

with tracer.start_as_current_span("model.inference") as span:
    span.set_attribute("gen_ai.request.model", model_family)
    span.set_attribute("isa.model.provider", provider)
```

Do not label metrics with the full user-supplied model name when it is
unbounded. Normalize to `model_family` or an allowlisted deployment name.

### Agent Runtime

```python
from isa_common.metrics import DEFAULT_BUCKETS, create_counter, create_histogram
from isa_common.tracing import get_tracer

tool_calls = create_counter(
    "tool_calls_total",
    "Agent tool calls",
    ["tool_family", "outcome"],
)
tool_latency = create_histogram(
    "tool_call_duration_seconds",
    "Agent tool call latency",
    ["tool_family"],
    buckets=DEFAULT_BUCKETS,
)

with get_tracer().start_as_current_span("agent.tool_call") as span:
    span.set_attribute("isa.agent.tool_family", tool_family)
    span.set_attribute("isa.agent.workflow", workflow_name)
```

Agent tracker trace IDs and run IDs may be logged as body fields for
navigation, but they MUST NOT become Loki or metric labels.

### Data Pipeline Worker

```python
from isa_common.metrics import SLOW_BUCKETS, create_histogram
from isa_common.tracing import get_tracer

stage_latency = create_histogram(
    "pipeline_stage_duration_seconds",
    "Pipeline stage latency",
    ["stage", "outcome"],
    buckets=SLOW_BUCKETS,
)

with get_tracer().start_as_current_span("pipeline.stage") as span:
    span.set_attribute("isa.pipeline.stage", stage)
    span.set_attribute("isa.dataset.kind", dataset_kind)
```

Dataset IDs, object keys, file paths, and row-level values stay out of labels
and resource attributes.

## Migration Gate

A service is compliant when:

- It calls `setup_observability()` exactly once in startup/lifespan.
- It passes service name, version, and deployment environment into the shared
  stack.
- It has one `/metrics` endpoint and no duplicate Prometheus middleware.
- It does not create a second OpenTelemetry provider.
- It propagates W3C trace context across inbound, outbound, and async
  boundaries.
- Its metrics and Loki labels pass the low-cardinality rules.
- Its logs and spans apply redaction defaults before export.
- Its degraded telemetry state is observable without failing serving readiness.

## Related Work

- Migration checklist and scanner enforcement: #457.
- Collector health, sampling, and cross-signal correlation: #454.
- Agent GenAI dashboards and alerts: #455.
- Product scope: [Platform Observability Standard PRD](prd/platform_observability_standard.md).
- Migration plan: [Observability Migration Plan](observability-migration-plan.md).
