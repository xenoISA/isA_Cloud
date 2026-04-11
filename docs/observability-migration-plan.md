# isA Platform — Observability Migration Plan

> Phased migration of all isA services to shared `isa_common` observability clients.
> Last updated: 2026-04-10

## Goal

Migrate all isA services from per-service instrumentation (custom Prometheus middleware, raw OpenTelemetry SDK, ad-hoc logging) to the shared `isa_common` observability clients (`setup_observability()`, `setup_metrics()`, `setup_tracing()`).

## Current State

| Service | Metrics | Tracing | Logging | Status |
|---------|---------|---------|---------|--------|
| isA_Trade | isa_common.metrics | isa_common.observability | isa_common.logging | ✅ Done |
| isA_user | isa_common.metrics | isa_common.observability | isa_common.logging | ✅ Done |
| isA_OS | Partial (global state issues) | None | Custom | 🔶 In Progress |
| isA_Creative | Partial (global state issues) | None | Custom | 🔶 In Progress |
| isA_MCP | Duplicate core/tracing.py + PrometheusMiddleware | Custom | Custom | ❌ Not Started |
| isA_Model | prometheus-fastapi-instrumentator | Custom | Custom | ❌ Not Started |
| isA_Mate | Raw prometheus_client | None | Custom | ❌ Not Started |
| isA_Agent | None | None | Custom | ❌ Not Started |
| isA_Data | Minimal | None | Custom | ❌ Not Started |

## Migration Steps Per Service

### Phase 1: Quick Wins (services already partially migrated)

**isA_OS** (Owner: @runtime-team, Target: Q2 2026)
1. Fix global state mutation in metrics setup
2. Add `setup_observability()` call in main.py lifespan
3. Remove custom metric factories
4. Verify: `/metrics` endpoint returns isa_common format

**isA_Creative** (Owner: @creative-team, Target: Q2 2026)
1. Same pattern as isA_OS — fix global state issue
2. Add `setup_observability()` call
3. Remove custom middleware

### Phase 2: Duplicate Removal (services with competing instrumentation)

**isA_MCP** (Owner: @platform-team, Target: Q2 2026)
1. Delete `core/tracing.py` (duplicate of isa_common.tracing)
2. Delete custom `PrometheusMiddleware`
3. Add `setup_observability()` in main.py
4. Verify: no duplicate metric names in `/metrics`

**isA_Model** (Owner: @ml-team, Target: Q3 2026)
1. Remove `prometheus-fastapi-instrumentator` dependency
2. Add `isa_common[metrics,tracing]` dependency
3. Replace instrumentator with `setup_metrics()` + FastAPI middleware
4. Add `setup_tracing()` for inference span tracking
5. Verify: GPU metrics + inference metrics both export

**isA_Mate** (Owner: @platform-team, Target: Q3 2026)
1. Remove raw `prometheus_client` usage
2. Add `isa_common[metrics]` dependency
3. Replace manual Counter/Histogram with isa_common factories
4. Verify: metric names match platform convention

### Phase 3: Greenfield (services with no instrumentation)

**isA_Agent** (Owner: @agent-team, Target: Q3 2026)
1. Add `isa_common[metrics,tracing,logging]` dependency
2. Add `setup_observability()` in main.py
3. Create spans for agent execution, tool calls, LLM requests

**isA_Data** (Owner: @data-team, Target: Q3 2026)
1. Add `isa_common[metrics,tracing,logging]` dependency
2. Add `setup_observability()` in main.py
3. Create spans for pipeline stages, Delta Lake operations

## Duplicate Instrumentation Removal Checklist

For each service, verify after migration:

- [ ] No duplicate `/metrics` endpoints (only one, from isa_common)
- [ ] No raw `prometheus_client` imports (use isa_common factories)
- [ ] No custom `PrometheusMiddleware` (use isa_common middleware)
- [ ] No custom `core/tracing.py` (use isa_common.tracing)
- [ ] `setup_observability()` called exactly once in lifespan
- [ ] Service registers with Consul including metrics port
- [ ] ServiceMonitor exists in production manifests
- [ ] Grafana dashboard updated to use new metric names (if changed)

## Success Criteria

- All 9 services emit metrics via isa_common by end of Q3 2026
- At least 5 services emit traces to Tempo by end of Q3 2026
- Zero duplicate metric names across the platform
- Single Grafana dashboard template works for all services
