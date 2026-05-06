# Canary Deploy Runbook

> Sibling docs: `deployments/charts/isa-service/templates/rollout.yaml`,
> `deployments/charts/isa-service/templates/analysis-template.yaml`,
> `docs/adr/0001-canary-tooling.md`.
>
> Origin: ported from xenoISA/isA_user PR #361 (issue
> [#350](https://github.com/xenoISA/isA_user/issues/350) — parent epic
> [#345](https://github.com/xenoISA/isA_user/issues/345)).
> Tooling: Argo Rollouts.

## What this covers

The shared `isa-service` chart renders an Argo Rollouts `Rollout` CR
(instead of the standard `Deployment`) when `rollout.enabled: true`.
Every service that consumes this chart can opt in per environment.
This runbook explains how to:

1. Verify the controller is installed in the target cluster.
2. Watch a canary in flight.
3. Manually promote, pause, abort, or roll back.
4. Read the AnalysisRun output when auto-rollback fires.
5. Migrate a service from the legacy `Deployment` to the new `Rollout`.

If you are looking for the migration-Job pre-deploy gate, see the
consuming repo's runbook (e.g. `xenoISA/isA_user/docs/runbooks/migration-rollback.md`)
— that runs FIRST, before any canary starts.

## 0. Prerequisites — install the controller

The chart renders `Rollout` and `AnalysisTemplate` CRs but does NOT
install the Argo Rollouts controller itself. Install it once per
cluster, **pinned to a specific release** so the cluster admin can
reproduce the install on a fresh cluster and roll back deterministically
if a controller release introduces a regression. Track the upgrade
cadence as a normal cluster-admin chore, not via `latest`.

```bash
# Pin to the same version we exercise in CI (the kubectl-argo-rollouts
# plugin step in xenoISA/isA_user/.github/workflows/deploy.yml uses
# the same tag — bump both at once).
ARGO_ROLLOUTS_VERSION=v1.7.2

kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts \
  -f "https://github.com/argoproj/argo-rollouts/releases/download/${ARGO_ROLLOUTS_VERSION}/install.yaml"

# Optional but strongly recommended — kubectl plugin for live tree views.
brew install argoproj/tap/kubectl-argo-rollouts   # macOS
# or download the pinned binary from
#   https://github.com/argoproj/argo-rollouts/releases/tag/${ARGO_ROLLOUTS_VERSION}
```

Upstream install guide:
<https://argo-rollouts.readthedocs.io/en/stable/installation/>.

Verify:

```bash
kubectl get crd rollouts.argoproj.io analysistemplates.argoproj.io
kubectl get pods -n argo-rollouts
kubectl argo rollouts version
```

## 1. Trigger a canary deploy

The CI workflow that ships images (e.g. `xenoISA/isA_user/.github/workflows/deploy.yml`)
handles this once it has been wired to use `rollout.enabled=true`.
Until then, push a new image tag and let `helm upgrade` reconcile the
`Rollout` — Argo takes over from there.

Sequence (per service):

1. CI runs the schema migration Job (helm pre-upgrade hook). Existing
   replicas keep serving until this Job exits 0.
2. CI runs `helm upgrade --install <release> deployments/charts/isa-service`
   with a values file that sets `rollout.enabled=true` and the new
   image tag. Argo's controller reconciles the `Rollout`.

Manual trigger for a single service (debugging):

```bash
NAMESPACE=isa-cloud-prod
SERVICE=user-auth-service
VERSION=v1.4.2

kubectl argo rollouts set image "${SERVICE}" \
  "${SERVICE}=ghcr.io/xenoisa/isa_user/${SERVICE#user-}:${VERSION}" \
  -n "${NAMESPACE}"
```

Note: `kubectl argo rollouts set image` only fires if the new tag
differs from the current one. CI workflows that always tag `latest`
will not re-trigger a canary — bake a content-addressed tag (commit
SHA) into the deploy step instead.

## 2. Watch a canary in flight

```bash
NAMESPACE=isa-cloud-prod
SERVICE=user-auth-service

# Live tree view — best single command for situational awareness.
kubectl argo rollouts get rollout "${SERVICE}" -n "${NAMESPACE}" --watch

# Just the current step / weight / status:
kubectl argo rollouts status "${SERVICE}" -n "${NAMESPACE}"

# Inspect AnalysisRuns triggered during the canary. Argo Rollouts emits
# the `rollout.argoproj.io/name=<rollout-name>` label on every
# AnalysisRun it spawns — there is no plain `rollout=` label.
kubectl get analysisrun -n "${NAMESPACE}" \
  -l "rollout.argoproj.io/name=${SERVICE}" \
  --sort-by=.metadata.creationTimestamp
```

The tree view shows:

- The stable + canary ReplicaSets (with hashes).
- Current step index and target weight.
- Analysis pass/fail per metric.
- Time spent paused.

Default ramp from issue #350 (rendered by `templates/rollout.yaml`):

| Step | Action            | Notes                              |
|------|-------------------|------------------------------------|
| 0    | setCanaryScale=1  | Pin canary at exactly one replica. |
| 1    | pause 60s         | Health gate.                       |
| 2*   | matchTrafficWeight| Only when `trafficRouting` is set. |
| 3    | setWeight 10      |                                    |
| 4    | analysis          | error-rate + p95 ratio.            |
| 5    | pause 30s         | Drain analysis window.             |
| 6    | setWeight 25      |                                    |
| 7    | analysis          |                                    |
| 8    | pause 30s         |                                    |
| 9    | setWeight 50      |                                    |
| 10   | analysis          |                                    |
| 11   | pause 30s         |                                    |
| —    | implicit 100%     | Argo promotes after final step.    |

## 3. Manual gates — promote, pause, abort, retry

```bash
NAMESPACE=isa-cloud-prod
SERVICE=user-auth-service

# Promote past the current step (skips remaining time on a pause).
kubectl argo rollouts promote "${SERVICE}" -n "${NAMESPACE}"

# Promote past ALL remaining steps (jump straight to 100%). Use with care.
kubectl argo rollouts promote "${SERVICE}" -n "${NAMESPACE}" --full

# Abort — Argo halts the canary and routes 100% back to the stable RS.
# Stable pods continue serving; canary RS is scaled down per
# scaleDownDelaySeconds (default 30 in this chart).
kubectl argo rollouts abort "${SERVICE}" -n "${NAMESPACE}"

# Retry an aborted rollout (re-runs from step 0).
kubectl argo rollouts retry rollout "${SERVICE}" -n "${NAMESPACE}"
```

Pausing with no time bound:

```bash
# Indefinite pause (no duration). Use to investigate before promoting.
kubectl argo rollouts pause "${SERVICE}" -n "${NAMESPACE}"
```

## 4. Auto-rollback — what just happened?

When a Prometheus metric breaches threshold (or returns no data — the
template treats empty results as failure), the AnalysisRun fails and
Argo aborts the rollout automatically. Symptoms:

```bash
$ kubectl argo rollouts status user-auth-service -n isa-cloud-prod
Status: Degraded
Message: RolloutAborted: Rollout aborted update to revision 12: ...
```

Investigate:

```bash
NAMESPACE=isa-cloud-prod
SERVICE=user-auth-service

# Latest AnalysisRun for this service. The selector below matches the
# `rollout.argoproj.io/name` label Argo Rollouts attaches to every
# AnalysisRun (a plain `rollout=<name>` selector would match nothing).
RUN=$(kubectl get analysisrun -n "${NAMESPACE}" \
  -l "rollout.argoproj.io/name=${SERVICE}" \
  --sort-by=.metadata.creationTimestamp \
  -o jsonpath='{.items[-1:].metadata.name}')

kubectl describe analysisrun "${RUN}" -n "${NAMESPACE}" | sed -n '/Status:/,$p'

# Per-metric measurements (the actual Prometheus values that failed).
kubectl get analysisrun "${RUN}" -n "${NAMESPACE}" \
  -o jsonpath='{.status.metricResults}' | jq .
```

Common causes:

| Symptom                                  | Likely root cause                              |
|------------------------------------------|------------------------------------------------|
| `error-rate` failed, `result[0]` ≈ 1.0   | Misconfig, exception loop, bad migration tail. |
| `latency-p95-ratio` > 1.5                | Cold cache, GC churn, downstream slowdown.     |
| `query did not return any results`       | Metric-name mismatch (see "Tweaking" §5).      |
| Both metrics passing but rollout stuck   | A `pause` step with no duration — promote it.  |

After triage, redeploy the previous good version (auto-rollback only
halts traffic; image rollback is manual):

```bash
# Show recent revisions (image SHAs).
kubectl argo rollouts history rollout "${SERVICE}" -n "${NAMESPACE}"

# Roll back to the previous revision (re-runs the canary ladder).
kubectl argo rollouts undo "${SERVICE}" -n "${NAMESPACE}"
```

## 5. Tweaking thresholds for one service

Set the values at the CLI or in a per-service / per-environment values
file:

```yaml
rollout:
  enabled: true
  healthGateSeconds: 120        # bake the canary longer
  analysis:
    errorRateThreshold: "0.005" # tighter — 0.5% triggers rollback
    latencyRatioThreshold: "1.3"
    metricNames:
      # Override when the service uses isa_common.metrics with the
      # `isa_<service>_` prefix.
      requests: "isa_user_auth_service_http_requests_total"
      duration: "isa_user_auth_service_http_request_duration_seconds_bucket"
      statusLabel: "status_code"
```

CLI override:

```bash
helm upgrade --install user-auth-service \
  ~/Documents/Fun/isA/isA_Cloud/deployments/charts/isa-service \
  --set rollout.enabled=true \
  --set rollout.analysis.errorRateThreshold="0.005" \
  -n isa-cloud-prod
```

## 6. Migration path from Deployment to Rollout

The chart renders EITHER a `Deployment` OR a `Rollout` (gated on
`rollout.enabled`), so a single helm upgrade flips ownership. Two
controllers cannot own the same Pods, so the steps below must run in
order:

```bash
NAMESPACE=isa-cloud-prod
SERVICE=user-auth-service

# 1. Confirm the controller is installed.
kubectl get crd rollouts.argoproj.io >/dev/null
kubectl get deploy -n argo-rollouts argo-rollouts >/dev/null

# 2. Apply with rollout enabled. Helm deletes the existing Deployment
#    and creates the Rollout in the same release.
helm upgrade --install "${SERVICE}" \
  ~/Documents/Fun/isA/isA_Cloud/deployments/charts/isa-service \
  --set rollout.enabled=true \
  -n "${NAMESPACE}"

# 3. Watch the Rollout converge.
kubectl argo rollouts get rollout "${SERVICE}" -n "${NAMESPACE}" --watch

# 4. Verify Service endpoints flipped to the Rollout-owned pods.
kubectl get endpoints "${SERVICE}" -n "${NAMESPACE}" -o yaml | head -40
```

To revert (controller down, canary tooling broken, etc.):

```bash
helm upgrade --install "${SERVICE}" \
  ~/Documents/Fun/isA/isA_Cloud/deployments/charts/isa-service \
  --set rollout.enabled=false \
  -n "${NAMESPACE}"
```

## 7. CI follow-up (deferred)

The `xenoISA/isA_user/.github/workflows/deploy.yml` workflow currently
performs a Blue-Green Deployment step. Switching it to a Canary
Rollout step needs:

- `kubectl argo rollouts set image …` against each service per ramp,
  with content-addressed image tags (commit SHA) so each deploy
  actually triggers a new revision.
- `kubectl argo rollouts status --watch --timeout=…` to block on
  promotion / abort.
- A workflow-level timeout that fits the new serial ramp (the original
  45m budget against 30m per-service ramps × N services will not
  serialize). Recommend parallelizing per service via a matrix job.

Tracked in the cross-repo follow-up issue (linked from the isA_Cloud
PR description). Until that is wired in, operators canary-deploy via
the `kubectl argo rollouts` commands in §1 / §6.
