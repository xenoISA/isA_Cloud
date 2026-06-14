# PRD: Platform Observability Standard

**Parent Epic**: xenoISA/isA_Cloud#453
**Status**: ready-for-design
**Affected Projects**: isA_Cloud, isA_Agent_SDK, isA_Console, isA_App_SDK
**Owner**: platform-team
**Canonical Contract**: [isA Platform Observability Contract](../observability-contract.md)

## Problem

The isA platform has the right observability components, but the contract is fragmented. `isa_common` already provides the shared Cloud observability spine for metrics, tracing, logging, resource attributes, and W3C propagation. The Agent SDK also has agent-specific metrics, custom tracing helpers, and tracker telemetry. Console has browser logging, optional tracing, Web Vitals, and trace/log views.

These pieces are not yet one coherent production stack:

1. Deployable Python services can still use per-service metrics, raw OpenTelemetry setup, or custom logging instead of `isa_common`.
2. Agent SDK tracing can behave like a competing global observability stack instead of instrumentation inside the host service context.
3. Agent tracker traces and OpenTelemetry traces are not linked by a canonical trace/span identity.
4. Logs do not consistently include OTel `trace_id` and `span_id`.
5. Console browser trace export and tracker navigation have endpoint/default mismatches.
6. Grafana dashboards and alerts do not yet cover agent GenAI RED, token, cost, model, and tool signals as a platform SLO surface.

## Goal

Make `isa_common` the required observability contract for all deployable Python services that need runtime observability, while keeping Agent SDK tracker data as product telemetry linked to the canonical OpenTelemetry trace graph.

## Target Architecture

- Backend Python services call `isa_common.observability.setup_observability()` exactly once during service startup.
- `isa_common` owns service-level OTel provider setup, resource attributes, W3C propagation, metrics middleware, Loki/log setup, Tempo export, redaction defaults, and health/preflight checks.
- Agent SDK exposes instrumentation helpers that create child spans, record domain metrics, and enrich logs within the active host service OTel context.
- Agent tracker records keep their product semantics for replay, annotation, and optimization, but store canonical OTel `trace_id` and span/run linkage.
- Console/browser uses `@xenoisa/core` as the frontend equivalent contract and exports telemetry into the same Cloud stack through configured endpoints/proxies.
- Cloud owns Collector, Tempo, Loki, Prometheus, Grafana dashboards, alerting, SLOs, sampling, retention, and migration policy.

## Requirements

### R1: `isa_common` Observability Contract (P1)

- Define the required startup pattern for deployable Python services.
- Document allowed extension points for service-specific spans, metrics, and log fields.
- Require resource attributes: `service.name`, `service.version`, `deployment.environment`.
- Require W3C trace propagation for inbound and outbound HTTP/service calls.
- Define failure behavior when Collector, Loki, Tempo, or Prometheus endpoints are unavailable.

### R2: Service Migration Enforcement (P1)

- Maintain a service-by-service migration checklist in Cloud docs.
- For migrated services, verify one `/metrics` endpoint, one OTel provider setup path, and no duplicate metric names.
- Remove raw `prometheus_client`, custom Prometheus middleware, and duplicate tracing modules where `isa_common` already provides the behavior.
- Add CI or preflight checks that detect competing observability setup in deployable services.

### R3: Agent SDK Host-Context Instrumentation (P1)

- Convert Agent SDK observability helpers to create child spans from the current OTel context.
- Avoid installing a global tracer provider from SDK helpers when running inside a service that already initialized `isa_common`.
- Keep standalone SDK behavior available for local development with explicit opt-in configuration.
- Record agent, LLM, tool, retriever, guardrail, workflow, and checkpoint spans using current GenAI/OpenInference-aligned attributes where applicable.
- Record errors with OTel span status and exception events.

### R4: Tracker and Trace Identity Unification (P1)

- Store canonical OTel `trace_id` on tracker `Trace` records.
- Store relevant OTel `span_id` or span linkage on tracker `Run` records.
- Preserve existing tracker replay, annotation, dataset export, and optimization workflows.
- Support navigation from tracker run tree to Tempo trace and from logs to tracker trace.

### R5: Log Correlation and Redaction (P1)

- Enrich structured logs with bounded correlation fields: `trace_id`, `span_id`, `request_id`, `session_id`, `service.name`, `deployment.environment`, and service version.
- Keep high-cardinality values such as user IDs, prompt IDs, and run IDs out of Loki labels unless explicitly approved.
- Redact or truncate prompt, response, token, header, and credential content before logs/spans by default.
- Make log correlation available in Agent SDK, Cloud services, and Console browser logs.

### R6: Console Telemetry Integration (P1)

- Fix or replace the Console browser trace export endpoint so enabled browser tracing has a real target.
- Remove localhost tracker defaults from production trace detail and replay paths.
- Align Console dashboards with emitted Loki labels and OTel attributes.
- Provide click-through navigation among Console logs, backend traces, tracker traces, and Tempo.

### R7: Agent GenAI Dashboards and Alerts (P1)

- Add dashboards for agent RED metrics: request rate, error rate, latency, and saturation.
- Add GenAI-specific panels for model latency, tool latency, token usage, cost, fallback rate, circuit breaker state, tracker write failures, and dropped spans/logs.
- Add Prometheus rules for agent SLO burn rate, p95/p99 latency, model/tool error spikes, collector drop rate, and missing telemetry targets.
- Extend SLO docs to include Agent Runtime service-level targets.

### R8: Collector Pipeline Maturity (P2)

- Add Collector health, dropped telemetry, queue, retry, and sampling visibility.
- Evaluate tail sampling for high-volume traces while preserving error and slow-trace retention.
- Evaluate metrics/logs through OTel Collector only where it improves correlation, governance, or deployment simplicity.
- Document retention and sampling policies for production, staging, local, and on-prem editions.

## Acceptance Criteria

| ID | Criteria |
|----|----------|
| AC-1 | Every migrated deployable Python service initializes observability through `isa_common` exactly once. |
| AC-2 | Browser-to-agent requests preserve one W3C trace context across Console, backend, Agent SDK, LLM calls, and tool calls. |
| AC-3 | Agent tracker traces/runs store canonical OTel trace/span linkage without breaking replay or annotation flows. |
| AC-4 | Structured logs from services and Console include `trace_id` and `span_id` when an active span exists. |
| AC-5 | Console trace/log/tracker links resolve in deployed environments without localhost defaults or missing telemetry routes. |
| AC-6 | Grafana contains Agent Runtime dashboards for RED, GenAI model/tool latency, token/cost, tracker health, and telemetry pipeline health. |
| AC-7 | Prometheus rules cover Agent Runtime SLOs and telemetry pipeline degradation. |
| AC-8 | Preflight/CI checks fail or warn when a service introduces duplicate metrics, duplicate OTel provider setup, or raw observability stacks outside approved wrappers. |

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| Collector unavailable | Service continues; spans are dropped through bounded queues; health/preflight surfaces degraded telemetry. |
| Loki unavailable | Request path does not block; log shipping failure is observable through counters/log warnings. |
| Tempo unavailable | Traces fail closed from the telemetry path, not the request path; local tracker product telemetry still records if configured. |
| Browser tracing disabled | Console still logs errors/Web Vitals according to configured logging policy. |
| On-prem edition disables observability | Console and preflight report observability disabled explicitly instead of showing broken dashboards. |
| High-cardinality tool/model names | Names are normalized, allowlisted, or moved to trace attributes instead of metric labels. |
| Prompt/response contains sensitive content | Content is redacted/truncated before logs, spans, and tracker metadata by default. |

## Stories

| # | Story | Priority | Project | Layer | Issue |
|---|-------|----------|---------|-------|-------|
| 1 | Define the platform observability contract in `isa_common` | P1 | isA_Cloud | infra, api | xenoISA/isA_Cloud#456 |
| 2 | Complete service-by-service `isa_common` migration checklist | P1 | isA_Cloud | infra | xenoISA/isA_Cloud#457 |
| 3 | Expand Collector health, sampling, and cross-signal correlation | P2 | isA_Cloud | infra | xenoISA/isA_Cloud#454 |
| 4 | Add Agent GenAI RED, token, cost dashboards and alerts | P1 | isA_Cloud | infra | xenoISA/isA_Cloud#455 |
| 5 | Convert Agent SDK observability to host-context instrumentation helpers | P1 | isA_Agent_SDK | sdk, core | xenoISA/isA_Agent_SDK#911 |
| 6 | Link Agent tracker runs to canonical OTel trace and span IDs | P1 | isA_Agent_SDK | sdk, data | xenoISA/isA_Agent_SDK#910 |
| 7 | Fix Console browser trace export endpoint and tracker defaults | P1 | isA_Console | ui, api | xenoISA/isA_Console#794 |
| 8 | Correlate Console logs, traces, and tracker navigation by trace ID | P1 | isA_Console | ui, api | xenoISA/isA_Console#795 |

## Out of Scope

- Replacing the Agent tracker with Tempo.
- Introducing a third-party SaaS observability vendor.
- Full browser session replay or source-map upload.
- Rewriting all service dashboards in one release.

## References

- `docs/observability-contract.md`
- `docs/observability-migration-plan.md`
- `docs/slo-sla-targets.md`
- `isA_common/isa_common/observability.py`
- `isA_common/isa_common/tracing.py`
- `isA_Agent_SDK/docs/prd/production_resilience_observability.md`
- `isA_Console/docs/product/PRD.md`
