# SN Delivery Runbook — platform release → `harbor.prod.sn.local`

> Implements **ADR 0007 — Artifact Delivery Pipeline** ([`../../docs/adr/0007-artifact-delivery.md`](../../docs/adr/0007-artifact-delivery.md)),
> phase 4 (story #320, epic #332). Pairs with the phase-3
> [`platform-release.yml`](../../.github/workflows/platform-release.yml) workflow
> and the phase-1+2 release tooling in this directory ([`README.md`](README.md)).

This is the end-to-end runbook **SN operations** follows to install or update the
isA platform on the customer's air-gapped cluster from a single, digest-pinned
**platform release** bundle.

## Audience + where this runs

- **Run by:** SN ops, on an SN-internal host that can reach **`harbor.prod.sn.local`**
  (the customer Harbor) and, for the seeding step only, the public GHCR mirror —
  OR fully offline via `MODE=archive` sneakernet (see below).
- **isA side** (this repo) only *produces* the bundle via `platform-release.yml`;
  it never touches the SN cluster.

## Hard constraints (why this is offline-first)

From ADR 0007 §Context and the SN production network policy:

- **~20M international egress budget.** Pull each image **once** into Harbor, then
  never again — plan the seed around this number (`approx_size` column in the CSV).
- **No public registry pulls post-deploy** (firewall **FW-OUT-001**). Everything
  the cluster runs MUST already live in `harbor.prod.sn.local`. The chart's images
  are re-tagged to the Harbor host before `helm install`.
- **Immutable digests required** — no `:latest`. The release manifest pins every
  service to `@sha256:…`; the offline bundle carries those digests as `source_ref`.

---

## What you receive (the platform release bundle)

A `platform-vX.Y.Z` GitHub Release (cut by `platform-release.yml`) attaches:

| Asset | Role |
|---|---|
| `platform-vX.Y.Z.json` | **Release manifest** — single source of truth: `services` (digest-pinned GHCR refs) + `charts` versions. |
| `platform-vX.Y.Z.offline-bundle.csv` | **Mirror input** — same column shape as SN's `offline-bundle-manifest.csv`; one `MIRROR` row per image → `harbor.prod.sn.local/isa/<image>:X.Y.Z`. |
| `isa-service-X.Y.Z.tgz` | Packaged base service chart (version = platform version). |
| `isa-bigdata-X.Y.Z.tgz` | Packaged big-data umbrella (on-prem-full only). |

> The edition + brand value overlays (`values-base.yaml`, `values-on-prem-full.yaml`,
> `values-brand-sn.example.yaml`) ship in this repo under
> [`../editions/`](../editions/) and are also bundled under `releases/charts/editions/`
> by `package-charts.sh`. SN keeps its real (non-example) `values-brand-sn.yaml` in
> the `sn_*` fork — it carries customer domains / support email the sanitizer can't infer.

---

## Step 0 — Download + verify the release

```bash
export PLATFORM_VERSION=1.0.0     # the X.Y.Z you are deploying
export REL="platform-v${PLATFORM_VERSION}"

# Pull the release assets (from the isA GitHub Release, on a connected host).
gh release download "$REL" --repo xenoISA/isA_Cloud --dir "$REL"
cd "$REL"
ls   # platform-vX.Y.Z.json  platform-vX.Y.Z.offline-bundle.csv  isa-service-*.tgz  isa-bigdata-*.tgz

# Sanity-check the manifest: every service MUST be @sha256-pinned (no :tag).
python3 - <<'PY'
import json, glob, sys
m = json.load(open(glob.glob("platform-v*.json")[0]))
bad = [k for k, v in m["services"].items() if "@sha256:" not in v]
print("platform_version:", m["platform_version"], "| services:", len(m["services"]))
assert not bad, f"NOT digest-pinned: {bad}"
print("OK — all services digest-pinned")
PY
```

## Step 1 — Seed Harbor (mirror images)

Use SN's existing **`mirror-to-harbor.sh`** (lives in the `sn_cloud` fork under
`docs/implementation-delivery/production/assets/offline-bundle/`). It reads the
offline-bundle CSV via `csv.DictReader` on the standard columns
(`category,component,source_ref,harbor_target,approx_size,action,notes`) and acts
on `MIRROR` rows — which is exactly the shape our generator emits, so **no
transformation is needed**.

**Connected seed** (host can reach GHCR + Harbor — pulls each image once, ~20M budget):

```bash
export HARBOR=harbor.prod.sn.local
# CSV points at the release's offline bundle; mirror copies source_ref -> harbor_target.
CSV=platform-v${PLATFORM_VERSION}.offline-bundle.csv ./mirror-to-harbor.sh images
```

**True air-gap seed** (sneakernet — no SN-side egress at all):

```bash
# On a connected host: tar every image referenced by the CSV.
MODE=archive CSV=platform-v${PLATFORM_VERSION}.offline-bundle.csv ./mirror-to-harbor.sh images
# Carry the tarball in; on an SN-internal host load it into Harbor:
MODE=archive ARCHIVE_DIR=./bundle-archive ./mirror-to-harbor.sh load
```

After this step every `services.*` digest from the manifest exists in Harbor as
`harbor.prod.sn.local/isa/<image>:X.Y.Z`. **No further public pulls occur.**

## Step 2 — Install (first deployment)

SN runs **on-prem-full + brand-sn**. Install the base service chart with the
edition overlay then the brand overlay (brand last so its env wins, per
[`../editions/README.md`](../editions/README.md)):

```bash
helm upgrade --install isa-on-prem ./isa-service-${PLATFORM_VERSION}.tgz \
  --namespace isa --create-namespace \
  -f editions/values-base.yaml \
  -f editions/values-on-prem-full.yaml \
  -f editions/values-brand-sn.yaml \
  --set global.imageRegistry=harbor.prod.sn.local/isa \
  --wait --timeout 15m
```

> `--set global.imageRegistry` repoints the chart's images at Harbor (the images
> were re-tagged there in Step 1). Confirm the exact value key against the chart
> `values.yaml`; if the chart pins per-service image refs, override those instead.

Once OCI chart publish is enabled on the isA side (`PUBLISH_CHARTS=true`) and the
charts are mirrored into Harbor's OCI registry, you may install from OCI instead
of the local `.tgz`:

```bash
helm upgrade --install isa-on-prem \
  oci://harbor.prod.sn.local/charts/isa-service --version ${PLATFORM_VERSION} \
  --namespace isa --create-namespace \
  -f editions/values-base.yaml \
  -f editions/values-on-prem-full.yaml \
  -f editions/values-brand-sn.yaml \
  --wait --timeout 15m
```

### Big-data umbrella (on-prem-full only)

`values-on-prem-full.yaml` sets `bigdata.enabled: true`. The umbrella is a
**separate Helm release** — install it too (its images are in the same bundle):

```bash
helm upgrade --install isa-bigdata ./isa-bigdata-${PLATFORM_VERSION}.tgz \
  --namespace isa \
  --set global.imageRegistry=harbor.prod.sn.local/isa \
  --wait --timeout 20m
```

## Step 3 — Verify

```bash
helm status isa-on-prem -n isa
kubectl get pods -n isa            # all Running / Ready
kubectl get deploy -n isa -o wide  # IMAGE column shows harbor.prod.sn.local/isa/... (NOT ghcr.io)

# Confirm no pod is pulling from a public registry (FW-OUT-001 compliance).
kubectl get pods -n isa -o jsonpath='{range .items[*]}{.spec.containers[*].image}{"\n"}{end}' \
  | grep -v '^harbor.prod.sn.local/' && echo "WARN: non-Harbor image above" || echo "OK — all images Harbor-local"
```

## Step 4 — Rollback on failure

`helm upgrade --install` records a revision history, so rollback is a one-liner —
**no re-mirror needed** (the previous revision's images are already in Harbor):

```bash
helm history isa-on-prem -n isa
helm rollback isa-on-prem <PREVIOUS_REVISION> -n isa --wait --timeout 15m
# Same for the umbrella if it was upgraded:
helm rollback isa-bigdata <PREVIOUS_REVISION> -n isa --wait --timeout 20m
```

---

## Update flow (new platform release)

A platform update = a **new** `platform-vX.Y.Z` release. Mirror only the **delta**
images, then `helm upgrade` (or let ArgoCD sync).

```bash
export PLATFORM_VERSION=1.1.0          # the NEW version
export REL="platform-v${PLATFORM_VERSION}"
gh release download "$REL" --repo xenoISA/isA_Cloud --dir "$REL" && cd "$REL"

# 1. Mirror the DELTA. mirror-to-harbor.sh skips digests already present in Harbor,
#    so re-running against the new CSV pulls only changed images (keeps egress low).
export HARBOR=harbor.prod.sn.local
CSV=platform-v${PLATFORM_VERSION}.offline-bundle.csv ./mirror-to-harbor.sh images

# 2a. Imperative upgrade (same overlays as install).
helm upgrade isa-on-prem ./isa-service-${PLATFORM_VERSION}.tgz \
  -n isa \
  -f editions/values-base.yaml \
  -f editions/values-on-prem-full.yaml \
  -f editions/values-brand-sn.yaml \
  --set global.imageRegistry=harbor.prod.sn.local/isa \
  --wait --timeout 15m

# 2b. OR GitOps: bump the chart/app version in the SN ArgoCD Application to
#     X.Y.Z (the manifest is the source of truth for image digests) and sync:
#       argocd app sync isa-on-prem --revision <git-ref-or-chart-version>
```

If the upgrade is unhealthy, roll back with **Step 4** — the prior revision's
images remain in Harbor, so rollback never re-pulls from a public registry.

---

## Quick reference

| Action | Command |
|---|---|
| Download release | `gh release download platform-vX.Y.Z --repo xenoISA/isA_Cloud` |
| Seed Harbor (connected) | `CSV=...offline-bundle.csv ./mirror-to-harbor.sh images` |
| Seed Harbor (air-gap) | `MODE=archive ... ./mirror-to-harbor.sh images` → carry in → `... load` |
| Install / upgrade | `helm upgrade --install isa-on-prem ./isa-service-X.Y.Z.tgz -f values-base -f values-on-prem-full -f values-brand-sn` |
| Big-data umbrella | `helm upgrade --install isa-bigdata ./isa-bigdata-X.Y.Z.tgz` |
| Verify | `kubectl get pods -n isa` + image-origin grep |
| Rollback | `helm rollback isa-on-prem <rev> -n isa` |

## References

- [`README.md`](README.md) — release tooling (manifest generator + chart packaging).
- [`../../.github/workflows/platform-release.yml`](../../.github/workflows/platform-release.yml) — phase-3 release workflow.
- [`../editions/README.md`](../editions/README.md) — edition + brand overlay model.
- [`../../docs/adr/0007-artifact-delivery.md`](../../docs/adr/0007-artifact-delivery.md) — the ADR (§4 SN bundle, §5 brand/edition at delivery).
- `sn_cloud` fork: `docs/implementation-delivery/production/assets/offline-bundle/`
  (`mirror-to-harbor.sh` + `offline-bundle-manifest.csv`).
