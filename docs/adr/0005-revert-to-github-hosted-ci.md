# ADR 0005 — Revert to GitHub-hosted Actions for platform CI

- **Status**: Accepted
- **Date**: 2026-05-28
- **Author**: isA platform infra team
- **Issue**: [xenoISA/isA_Cloud#309](https://github.com/xenoISA/isA_Cloud/issues/309) — Originating epic: [#284](https://github.com/xenoISA/isA_Cloud/issues/284)
- **Supersedes**: [ADR 0004 — Actions Runner Controller (ARC) for self-hosted CI runners](./0004-arc-self-hosted-runners.md)

## Context

[ADR 0004](./0004-arc-self-hosted-runners.md) recorded the decision to host
platform CI on an in-house ARC self-hosted runner pool, motivated by an
org-wide GitHub-hosted Actions billing failure that had been blocking merges.
Epic 14 ("Platform CI Independence") was opened to drive that work; PRs
#298, #305, #306, #307, #308 delivered the ARC controller + scale set, a
pre-baked runner image, and a `runner-status.sh` dashboard. The first
workflow migration ([xenoISA/isA_#480](https://github.com/xenoISA/isA_/pull/480),
merged 2026-05-27) flipped `isA_/.github/workflows/ci.yml` to
`runs-on: self-hosted`.

Within hours, the ARC pool went all-offline. Three runs (main + two PR
branches) sat in `queued` for over four hours and were cancelled. The
incident is captured in [xenoISA/isA_Cloud#309](https://github.com/xenoISA/isA_Cloud/issues/309).
That outage prompted a re-evaluation of the cost / benefit at platform scale.

### What changed in our cost model

The original Epic 14 motivation was a **billing failure** (failed payment /
spending-limit block on GitHub-hosted Actions), not a structural cost problem
with GitHub-hosted CI itself. That failure had already been resolved at the
billing layer when this work was kicked off; the platform-CI-independence
decision survived on the strength of "lower marginal cost per run" and
"no GitHub dependence" — both of which deserve a second look at our actual
scale.

For 19 repos at our PR volume, GitHub-hosted Pro tier (2000 free Linux
minutes / month on private repos) easily covers the typical CI load when
combined with:

- `cancel-in-progress` concurrency groups (already standard)
- `paths-ignore` filters for docs-only changes
- npm / pnpm / pip cache hits via `actions/setup-*`
- jobs that gate on the affected diff (already in place in isA_Model/ci.yml
  and isA_user/ci.yml)

Back-of-the-envelope: 5-min CI × 20 PRs/day × 22 working days ≈ 2200 min,
which falls under 2000 with normal cache hit rates. Tier upgrades or
overage charges remain available for bursts.

### What ARC actually cost us (one week in)

- **Operational tax**: image rebuild pipeline ([#306](https://github.com/xenoISA/isA_Cloud/issues/306))
  required to work around kind egress timeouts on `actions/setup-*`; runner
  pod rotation; GitHub App permission updates; org-level vars + secrets
  rollout; dind sidecar tuning ([#306](https://github.com/xenoISA/isA_Cloud/issues/306)).
- **All-pool-offline outage** within 24 hours of cutover, with no path to
  diagnose from CI alone — needed cluster-side investigation.
- **Diverts SRE attention** from product work whenever the pool blips.
- **kind cluster pressure**: 2.6 GB pre-baked runner image, `maxRunners: 2`
  (down from 4 after dind probe budget overruns), shared overlay storage.

The marginal-cost saving from "zero GitHub minutes" does not pay for that
overhead at our scale. It would pay off at much higher CI volume, with
specific hardware needs (GPU, large RAM), or under compliance constraints
that forbid US-hosted compute. None of those apply to the isA platform
today.

## Decision

**Revert to GitHub-hosted Actions (`runs-on: ubuntu-latest`) across all isA
repos.** Tear down the ARC scale set, controller, runner image build
pipeline, and supporting scripts. Keep the `isa-arc-runners` GitHub App
and its org-level credentials — they're now used to mint per-run tokens
for cross-repo private-repo checkout (a problem orthogonal to runners),
and should be renamed to drop the misleading "arc" prefix as part of a
follow-up.

### What stays

- **`isa-arc-runners` GitHub App** (subject to rename) — used for
  `actions/create-github-app-token@v1` to mint short-lived installation
  tokens for cross-repo `actions/checkout`. This avoids long-lived PATs.
  Org-level `vars.ISA_ARC_APP_ID` + `secrets.ISA_ARC_APP_PRIVATE_KEY`
  stay populated.
- **`paths-ignore` filters** added to every CI workflow during the
  reversal sweep, to control minute burn.
- **`cancel-in-progress` concurrency groups** already in place.
- **Pre-commit / pre-push local CI gates** (Epic 14 stories US1–US3) — kept
  because zero-cost local gates pay off independent of where CI runs.

### What goes

- ARC controller + runner-scale-set Helm values
- GitHub App auth Secret template, install scripts, namespaces manifest
- Pre-baked runner image Dockerfile + build script
- `runner-status.sh` dashboard
- `tests/unit/test_arc_runner_config.sh`
- ARC runbook (`docs/runbooks/arc-self-hosted-runners.md`)
- Epic 14 self-hosted-runner stories (US4–US7, US8) — see PRD update in
  the same PR
- The repo-mirror DR story (US9) — defers to a separate epic; ARC was its
  prerequisite and ARC is gone

### Reversal sweep PRs

Companion PRs in this rollout:

- [xenoISA/isA_#482](https://github.com/xenoISA/isA_/pull/482) — isA_ ci.yml revert (template)
- xenoISA/isA_App_SDK#407, xenoISA/isA_Mate#592 — single-workflow reverts
- xenoISA/isA_Model#... — ci.yml + pr-check.yml + security.yml revert
- xenoISA/isA_user#497, #498 — pr-ci/pr-check + ci.yml revert
- xenoISA/isA_Console#713, isA_MCP#721, isA_Vibe#295 — delete dead
  `deploy-kind.yml` workflows (zero successful runs in 3+ months)
- xenoISA/isA_Console#714 — delete orphaned `smoke.yml` (coupled to the
  deleted `deploy-kind.yml`)

## Alternatives considered

### Stay on ARC and harden it

Rejected. The all-pool-offline mode after one day in production is the
exact failure profile we feared from a "small ops team, complex local
infra" setup. Hardening it requires Grafana dashboards (Epic 14 US8),
alerting, capacity tuning, image rebuild on every toolchain bump, and
ongoing SRE attention. The investment exceeds the GitHub-hosted minute
budget by a wide margin at our scale.

### Cap GitHub-hosted spend via tighter workflow controls

Accepted as the *primary* control. `paths-ignore`, `cancel-in-progress`,
diff-aware job gating, and `workflow_dispatch` opt-in for heavyweight
jobs (already in place for `k8s-integration` in isA_user) bring the
typical month well under the 2000 free-minute Linux budget.

### Hybrid (ARC for deploys, GitHub-hosted for CI)

Rejected. Inspection showed all three `deploy-kind.yml` workflows
(isA_Console, isA_MCP, isA_Vibe) had no successful run in 3+ months and
were deleted in the reversal sweep. With no remaining cluster-bound CI
job, keeping ARC alive "just for deploys" leaves the operational tax in
place without a use case.

### Independent CI engine (Woodpecker / Forgejo mirror)

Out of scope. Was [#293](https://github.com/xenoISA/isA_Cloud/issues/293)'s
DR layer under Epic 14. Re-open as a standalone DR initiative if
GitHub-availability risk becomes a load-bearing concern.

## Consequences

### Positive

- **CI unblocked immediately.** ubuntu-latest runs pick up within seconds;
  the queue-forever failure mode is gone.
- **Lower operational surface.** No kind-cluster CI capacity to monitor,
  no runner image to rebuild, no App-token rotation cadence to track.
- **Cluster RAM freed** on `isa-cloud-local`. Previously the runner pool
  competed with product workloads.
- **Simpler onboarding.** New repos just write `runs-on: ubuntu-latest`
  and inherit the platform-wide caching / paths-ignore / concurrency
  conventions.
- **GitHub Actions service containers fit our needs.** isA_Model/ci.yml
  and isA_user/ci.yml's integration jobs use `services:` blocks
  (postgres / nats / redis); these run identically on ubuntu-latest.
  Kind for `k8s-integration` runs on ubuntu-latest too (kind = Docker).

### Negative / trade-offs

- **CI minute exposure.** A bad-actor PR or a stuck job could burn through
  the free tier. Mitigated by `cancel-in-progress` (already on),
  `paths-ignore`, `timeout-minutes` per job, and Actions usage alerts at
  the org level (recommend setting a 1500-min soft alert).
- **GitHub-hosted availability is now a hard dependency.** Acceptable —
  it was already a soft dependency via the Actions API even under ARC.
  A future DR story can revisit Woodpecker / Forgejo if needed.
- **Heavy jobs (kind cluster setup, large docker builds) are slower** on
  GitHub-hosted runners than on pre-baked self-hosted images. Acceptable
  for our current job mix; revisit if any single job consistently exceeds
  ~10 min wall-clock.

### Rollback plan

Rolling back to ARC would require:

1. Re-deploying the ARC controller + scale set (manifests + values are
   in git history under commits e908961, 2470efe, c26331c, a62b0f2).
2. Re-baking the runner image.
3. Restoring the runbook.
4. Per-repo workflow change: `runs-on: ubuntu-latest` → `runs-on: self-hosted`
   (~9 workflow files).

Step 4 is one-line per repo. Steps 1–3 take a day. Total rollback cost is
roughly the same as the original setup — meaningful but bounded.

## References

- Originating epic: [xenoISA/isA_Cloud#284](https://github.com/xenoISA/isA_Cloud/issues/284)
- Outage that triggered the reversal: [xenoISA/isA_Cloud#309](https://github.com/xenoISA/isA_Cloud/issues/309)
- Superseded: [ADR 0004](./0004-arc-self-hosted-runners.md)
- Template PR for the sweep: [xenoISA/isA_#482](https://github.com/xenoISA/isA_/pull/482)
