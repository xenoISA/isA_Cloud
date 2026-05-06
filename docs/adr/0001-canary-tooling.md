# ADR 0001 — Canary Deploy Tooling: Argo Rollouts

> Status: Accepted (2026-05-04)
> Origin: ported from xenoISA/isA_user PR #361 (issue
> [#350](https://github.com/xenoISA/isA_user/issues/350), parent epic
> [#345](https://github.com/xenoISA/isA_user/issues/345))
> Sibling docs: `deployments/charts/isa-service/templates/rollout.yaml`,
> `deployments/charts/isa-service/templates/analysis-template.yaml`,
> `docs/runbooks/canary-deploy.md`

## Context

isA_user epic #345 (K8s HPA Readiness) requires a canary deploy strategy
for platform microservices so a bad release does not reach 100% of
traffic before metrics catch up. Issue #350 specifies:

- Stage 1 replica → ≥60s health gate → 10% → 25% → 50% → 100% traffic ramp
- Auto-rollback on error rate >1% OR p95 latency >1.5× baseline
- Configurable Prometheus analysis queries
- Helm-native integration with the existing deploy pipelines

The platform already runs:

- Kubernetes (KIND for local, managed clusters for staging/prod)
- Helm 3 charts under `isA_Cloud/deployments/charts/`
- Consul + APISIX (no service mesh required)
- Prometheus for metrics (assumed present in the cluster)
- GitHub Actions CI (per-repo `deploy.yml`)

The shared `isa-service` chart in this repo is the natural home for
the new template — it is already the chart that owns each service's
`Deployment`, `Service`, `HorizontalPodAutoscaler`, and
`PodDisruptionBudget`.

## Options considered

### Option A — Argo Rollouts (CHOSEN)

CRD-driven progressive delivery controller. Replaces `Deployment` with
`Rollout`. Native support for canary stages with traffic weights,
per-stage pauses, and analysis runs that hit Prometheus / Datadog /
New Relic / etc. Works without a service mesh by using the built-in
"basic canary" mode (replica-count-based traffic split), and gains
true L7 split when Istio / Linkerd / SMI / Gateway API / Nginx / ALB
are present.

Pros
- First-class Kubernetes object — `kubectl argo rollouts get rollout X`
  and a UI dashboard ship out of the box.
- Per-stage `pause` + `setWeight` directives match the issue spec verbatim.
- Inline `AnalysisTemplate` runs Prometheus queries during each step and
  aborts the rollout on threshold breach (== auto-rollback).
- Wide ecosystem adoption (CNCF Incubating). Documented for ArgoCD users
  who likely run the rest of the platform.
- Replicas-based canary works on a vanilla cluster — no mesh required to
  ship the first version.

Cons
- Adds a controller dependency in every cluster (one Deployment + CRDs).
- Replacing the existing `Deployment` shape touches the chart. We
  mitigate by making rollout opt-in via `rollout.enabled` and gating
  the existing `Deployment` template off when the flag is on so two
  controllers cannot reconcile the same Pods.

### Option B — Flagger

Operator that drives canary rollouts using Istio / Linkerd / Contour /
Gloo / NGINX / Skipper / Traefik / ALB. Uses the same primitives (steps,
analysis, metric queries).

Pros
- Production-grade, similar feature set.
- Tighter integration with service meshes when one exists.

Cons
- **Hard requirement on a service mesh or supported ingress for traffic
  splitting.** isA_user fronts traffic with APISIX, which Flagger does
  not list as a first-class provider — we'd need to migrate to a
  supported mesh first.
- Pause/promote workflow is less visible (no dedicated dashboard /
  `kubectl` plugin equivalent to Argo's).

### Option C — Custom (kubectl + Bash + Prometheus queries in CI)

Bake the canary loop into the workflow itself: scale a canary Deployment,
sleep 60s, query Prometheus, scale up, repeat.

Pros
- No new cluster dependencies.
- Logic is auditable in the workflow file.

Cons
- Reinvents Argo Rollouts poorly. State lives in the runner, so a CI cancel
  abandons the canary mid-stage. No UI, no `kubectl` introspection, no
  experiments / blue-green / preview environments later. Operators who want
  to "pause" or "promote" manually have nothing to drive.
- Multiplies code in the workflow per service.

## Decision

**Adopt Argo Rollouts.** It is the only option that satisfies the issue
acceptance criteria with reasonable operational effort and zero forced
dependencies on a service mesh. The basic canary mode is sufficient for
the first cut; we keep the door open to plug in APISIX or a mesh later
purely by editing the `Rollout` `strategy.canary.trafficRouting` block.

## Consequences

### Positive

- Stages and analysis are declarative inside the chart — diffs in git
  show the full canary policy.
- `kubectl argo rollouts get rollout user-auth-service -n isa-cloud-prod`
  gives operators a live tree view during every deploy.
- Re-uses the existing migration-job hook order: Alembic Job (pre-upgrade
  hook) runs to completion → service `Rollout` reconciles → analysis
  template promotes or aborts.
- Production stays on canary; staging keeps the simpler kubectl-driven
  rollout (faster feedback for developers) by toggling
  `rollout.enabled=false` per environment.
- The chart now owns BOTH the `Deployment` (rollout disabled) and the
  `Rollout` (rollout enabled) — flipping a single value handles the
  cutover instead of needing two charts in two repos.

### Negative / Follow-ups

- Cluster admins MUST install the Argo Rollouts controller before this
  chart's `Rollout` resource can reconcile. See the runbook for the
  install command and link to the upstream guide.
- We do not yet have a service mesh; traffic-splitting fidelity is
  approximate (replica-count weighted). For the spec's 10/25/50/100
  thresholds this is acceptable because we are still gating each step on
  a Prometheus analysis run.
- The `setCanaryScale.matchTrafficWeight: true` step is only rendered
  when `rollout.trafficRouting` is non-empty (it is a no-op without
  L7 routing).
- The AnalysisTemplate's Prometheus queries assume metrics carry an
  `app_kubernetes_io_name` label (Prometheus's auto-conversion of
  the pod label `app.kubernetes.io/name`). If the chart adds new
  pod labels, keep that one or update the analysis template to match.
- The default metric names (`http_requests_total`,
  `http_request_duration_seconds_bucket`) match the unprefixed names
  some services emit. `isa_common.metrics` adds an `isa_<service>_`
  prefix; operators flipping `rollout.enabled` MUST set
  `rollout.analysis.metricNames.*` to the actual emitted name. See
  the TODO in the AnalysisTemplate.

## Links

- Argo Rollouts docs: https://argo-rollouts.readthedocs.io/
- Install: `kubectl create namespace argo-rollouts && kubectl apply -n argo-rollouts -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml`
- Flagger comparison: https://argo-rollouts.readthedocs.io/en/stable/FAQ/#how-does-argo-rollouts-differ-from-flagger
- Originating PR (closed in favor of this chart change): https://github.com/xenoISA/isA_user/pull/361
