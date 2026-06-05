# ADR 0007 — Artifact Delivery Pipeline (platform release → SN)

> Status: Proposed (2026-06-05)
> Story: #320 (artifact delivery), epic #332 (delivery follow-up to #328).
> Grounded in a 3-part investigation of the current image/chart/SN-delivery state.
> Sibling: ADR 0003 (helm chart layout), `deployments/editions/`,
> `sn_cloud/docs/implementation-delivery/production/assets/offline-bundle/`.

## Context

The editions/profile model (#328) is built: one codebase deploys as
SaaS / on-prem-full / on-prem-lite via Helm value overlays, brand+edition as
runtime config. **But there is no mechanism to ship it to SN.** Today:

- **Images**: each repo's CI builds + pushes its own image to `ghcr.io/xenoisa/*`
  independently; no platform-wide version; `promote-to-production.yml` is a stub.
  Images are already **runtime edition-agnostic** (brand/edition via env) — good.
- **Charts**: one `isa-service` chart + `deployments/editions/` overlays + a
  separate `isa-bigdata` umbrella; all at placeholder `0.1.0`; **no `helm package`,
  no chart repo** — applied straight from Git via ArgoCD.
- **SN target**: customer Harbor `harbor.prod.sn.local`; **~20M international
  egress** → offline-bundle-first; **no public registry pulls post-deploy**
  (firewall FW-OUT-001); **immutable digests required** (no `:latest`). An
  offline-bundle mechanism already exists: `mirror-to-harbor.sh` +
  `offline-bundle-manifest.csv` (supports direct registry→Harbor and
  `MODE=archive` sneakernet).

The gap: nothing ties a coherent set of edition-agnostic images + the editions
chart into a **versioned, digest-pinned bundle** that SN's existing mirror can
seed into Harbor and `helm install` with edition+brand values.

## Decision

A **platform release** = one version (`platform-vX.Y.Z`) that pins a coherent set
of artifacts and produces a delivery bundle SN can consume offline. Reuse what
exists (GHCR source registry, SN's mirror-to-harbor, the editions chart); add the
missing release/packaging/manifest layer.

### 1. Source registry + image policy
- **GHCR `ghcr.io/xenoisa/<service>` is the single source-of-truth registry.**
  Fix the two outliers (isA_MCP, isA_user) that reference un-built Harbor base
  images — build their base images in CI to GHCR too.
- Images stay **runtime edition-agnostic** (no brand/edition baked at build).
  → the SAME image serves isA SaaS and SN; only env (`BRAND_*`, `ISA_EDITION`)
  differs. No per-customer image rebuild.

### 2. Platform release version + manifest (the keystone)
- A platform release pins every platform service to an **immutable digest**.
- Output: a **release manifest** `releases/platform-vX.Y.Z.json`:
  ```json
  { "platform_version": "1.0.0",
    "services": { "isa-agent": "ghcr.io/xenoisa/isa-agent@sha256:…", … },
    "charts":   { "isa-service": "1.0.0", "isa-bigdata": "1.0.0" } }
  ```
  This is the single source of truth for "what is platform v1.0.0" — drives
  the bundle, the SN mirror, and ArgoCD image tags.

### 3. Chart packaging + versioning
- Move charts off placeholder `0.1.0`: **chart version = platform version** at
  release (`helm package` with `--version $PLATFORM_VERSION`).
- Publish charts as **OCI artifacts to `oci://ghcr.io/xenoisa/charts/*`**
  (Helm-native OCI; no separate ChartMuseum/Pages to operate). Resolve the
  umbrella's `file://` deps + commit Chart.lock so it packages cleanly.
- Editions stay **value overlays** (not separate charts) — the bundle ships the
  `deployments/editions/*.yaml` alongside the chart.

### 4. SN delivery bundle (fits the 20M-egress / no-public-pull reality)
- A release generates a **versioned offline bundle** = the existing
  `offline-bundle-manifest.csv` populated from the release manifest (image
  digests) + the packaged charts + the edition/brand values.
- SN's existing `mirror-to-harbor.sh` (direct or `MODE=archive`) seeds
  `harbor.prod.sn.local`; then `helm install isa-<edition> oci://…/isa-service
  --version X -f values-base -f values-<edition> -f values-brand-sn`.
- **Update** = new platform release → new manifest → mirror the **delta** images
  → `helm upgrade` / ArgoCD sync → rollback via `helm rollback`.

### 5. Brand/edition at delivery, not in the artifact
- One bundle per platform version (edition-agnostic images + one chart). The
  customer's **edition + brand are chosen at `helm install`** via the
  `values-<edition>` + `values-brand-<customer>` overlays — no per-customer
  artifact. (SN = on-prem-full + brand-sn.)

## Phased plan (stories under #332)

1. **Release manifest generator** (MVP keystone): a script that, given a
   platform version, collects platform services → image refs (resolve to
   digests) + chart versions → writes `releases/platform-vX.Y.Z.json` and a
   populated `offline-bundle-manifest.csv`. Smallest unblocking piece.
2. **Chart packaging + OCI publish** workflow: `helm package` (version=platform
   version) + push `oci://ghcr.io/xenoisa/charts/{isa-service,isa-bigdata}`;
   resolve umbrella deps; `helm lint` gate.
3. **Platform-release workflow**: on `platform-v*` tag → ensure all service
   images exist at the release digests (build/verify) → emit manifest (1) →
   package+publish charts (2) → attach bundle to a GitHub Release.
4. **SN mirror integration**: point `mirror-to-harbor.sh` at the release
   manifest; document the SN install/upgrade runbook using OCI chart + edition
   overlays.
5. **Fix base-image outliers** (isA_MCP/isA_user Harbor base → build to GHCR).
6. **ArgoCD image-tag sync** from the release manifest (replace manual edits;
   `promote-to-production.yml` stub → real).

## Consequences
- **Positive**: SN deploys/updates from a single digest-pinned, offline-capable
  bundle; one edition-agnostic image set serves all editions/customers; reuses
  SN's existing mirror + the editions chart; immutable + auditable.
- **Negative/risk**: needs a coordinated release across ~12 repos (the manifest
  decouples this — it pins existing per-repo images rather than forcing a
  monorepo build); chart version bump touches many Chart.yaml; OCI chart hosting
  is new (low ops, but a new path).
- **Out of scope here**: model-weight delivery (the ~27GB LLM weights have their
  own bundle path in the SN docs); GPU/Triton specifics.

## Open questions
- Release granularity: pin **current latest per repo** at release time, or
  require each repo to cut a matching `v*` first? (Lean: pin current GHCR digests
  — the manifest records exactly what shipped.)
- OCI charts in GHCR vs an air-gap-friendlier packaged `.tgz` in the bundle for
  SN (likely **both**: OCI for connected installs, `.tgz` in the offline bundle).
