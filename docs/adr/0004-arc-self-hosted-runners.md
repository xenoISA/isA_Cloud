# ADR 0004 — Actions Runner Controller (ARC) for self-hosted CI runners

- **Status**: Superseded by [ADR 0005](./0005-revert-to-github-hosted-ci.md) on 2026-05-28
- **Date**: 2026-05-21
- **Author**: isA platform infra team
- **Issue**: [xenoISA/isA_Cloud#288](https://github.com/xenoISA/isA_Cloud/issues/288) — Parent epic: [#284](https://github.com/xenoISA/isA_Cloud/issues/284)
- **Supersedes**: n/a
- **Superseded by**: [ADR 0005 — Revert to GitHub-hosted Actions](./0005-revert-to-github-hosted-ci.md)

> **Note (2026-05-28)**: After one week in production, ARC was withdrawn. The
> operational overhead (image rebuilds, runner registration, App-token
> rotation, all-pool-offline outages) exceeded the cost of GitHub-hosted
> minutes at platform scale. See [ADR 0005](./0005-revert-to-github-hosted-ci.md)
> for the rationale and the reversal plan. The rest of this document is kept
> for historical context.

## Context

GitHub-hosted Actions billing failed org-wide for `xenoISA` (failed payments /
spending limit), blocking CI across the isA repos and forcing local-test +
admin-override merges. Epic [#284](https://github.com/xenoISA/isA_Cloud/issues/284)
moves CI compute onto the platform's own `isa-cloud-local` kind cluster so
test / lint / build no longer consume GitHub-hosted minutes.

The discovery pass found the platform is already partway there: four repos run
self-hosted runners for `deploy-kind` jobs (`runs-on: self-hosted`), and the
kind cluster is fully configured. The gap is *how* to run those runners
reliably for the full 19-repo rollout.

Two implementation options were considered for #288:

1. A plain Kubernetes **StatefulSet** of long-lived runner pods.
2. **Actions Runner Controller (ARC)** — the modern scale-set model
   (`gha-runner-scale-set-controller` + `gha-runner-scale-set` Helm charts).

## Decision

Use **ARC with the scale-set model** and **GitHub App authentication**.

- ARC controller in namespace `arc-systems`; the runner scale set, its
  listener, and ephemeral runner pods in `arc-runners`.
- Auth via a **GitHub App** registered on the `xenoISA` org — not a PAT.
- The scale set is assigned to an org runner group named `isA CI`, scoped to
  the repos allowed to consume local-kind CI capacity.
- The scale set is installed as `self-hosted` (`runnerScaleSetName`) so the
  four repos already on `runs-on: self-hosted` route to ARC unchanged.
- Runner pods use `dind` container mode so `docker build` CI jobs work.
- `minRunners: 0`, `maxRunners: 4` on the local cluster.

## Alternatives considered

### Plain StatefulSet of runner pods

Rejected:

- **State leak.** Long-lived runners carry workspace, Docker layer cache, and
  tool state between jobs — a recipe for flaky, non-reproducible CI.
- **Token fragility.** Runner registration tokens expire after one hour;
  a StatefulSet would need an external refresh loop or pod restarts.
- **No scale-to-zero.** Fixed replicas burn idle RAM on the kind cluster even
  when no CI is running; over-provisioning to absorb bursts wastes more.
- **Does not scale to 19 repos.** Manual replica tuning per load does not fit
  the rollout target ([#291](https://github.com/xenoISA/isA_Cloud/issues/291)).

### ARC with PAT auth

Rejected in favour of a GitHub App: a PAT needs periodic manual rotation, is
tied to one user account, and carries a lower API rate limit. A GitHub App has
scoped permissions, a higher rate limit, and zero-downtime key rotation.

### Independent CI engine (Woodpecker / Forgejo mirror)

Out of scope for #284 by design — kept as the DR layer
([#293](https://github.com/xenoISA/isA_Cloud/issues/293)). ARC still depends on
the GitHub Actions API; see Consequences.

## Consequences

### Positive

- **Ephemeral pod-per-job** — clean, reproducible CI; no state leak.
- **Scale 0 → N → 0** — zero idle RAM on the kind cluster between jobs.
- **GitHub App auth** — no PAT rotation chore; scoped org permissions.
- **One-line workflow change** — keeping the `self-hosted` label means the
  pilot repos need no `runs-on` edit; the rest migrate in
  [#289](https://github.com/xenoISA/isA_Cloud/issues/289).
- **Autoscaling** fits the 19-repo rollout.

### Negative / trade-offs

- **`dind` mode needs a privileged sidecar.** Acceptable on a local kind
  cluster; the `arc-runners` namespace runs at PSA `privileged`. Revisit
  (rootless Docker / buildkit) before any shared environment.
- **Still depends on the GitHub Actions API.** ARC fixes the compute *cost*,
  not GitHub *availability*. A full account suspension stops the Actions API;
  surviving that is [#293](https://github.com/xenoISA/isA_Cloud/issues/293)'s
  scope (repo mirror + independent CI), not #288.
- **Org-admin prerequisite.** The live deploy needs a GitHub App and an `isA CI`
  runner group registered on `xenoISA` (org-admin actions) — #288's config
  artifacts cannot self-deploy.

## References

- Runbook: [`docs/runbooks/arc-self-hosted-runners.md`](../runbooks/arc-self-hosted-runners.md)
- Config: [`deployments/kubernetes/local/arc/`](../../deployments/kubernetes/local/arc/)
- ARC docs: <https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners-with-actions-runner-controller>
