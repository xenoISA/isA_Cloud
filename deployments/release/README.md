# Platform release tooling

> Implements **ADR 0007 — Artifact Delivery Pipeline** ([`../../docs/adr/0007-artifact-delivery.md`](../../docs/adr/0007-artifact-delivery.md)),
> phases 1–2 (story #320, epic #332).

A **platform release** = one version (`platform-vX.Y.Z`) that pins a coherent set
of edition-agnostic service images + the editions Helm chart into a versioned,
digest-pinnable bundle that customer **SN** can seed into its Harbor and
`helm install` offline. This directory holds the release-cut tooling; it does
**not** push to any registry (OCI publish is gated off in this MVP).

## What's here

| File | Role |
|---|---|
| `platform-services.yaml` | Data-driven source list: each platform repo → its GHCR image (`ghcr.io/xenoisa/isa-<name>`), or `has_image: false` for libs-only repos. **Edit this** when the service set changes. |
| `generate-release-manifest.py` | Phase 1 — emits the release manifest JSON + the SN offline-bundle CSV for a version. |
| `package-charts.sh` | Phase 2 — `helm package` the `isa-service` chart + `isa-bigdata` umbrella at `version = platform version`; bundles the edition overlays. |
| `releases/` | Output dir (gitignored). Build artifacts: `platform-vX.Y.Z.json`, `platform-vX.Y.Z.offline-bundle.csv`, `charts/*.tgz`, `charts/editions/*.yaml`. |

## Services in a release (ADR 0007 §1, edition-boundary §A)

17 platform repos. 14 ship a runtime image and land in the manifest + bundle;
3 are libs/tooling with no container image (recorded in `platform-services.yaml`
with `has_image: false`, excluded from the manifest):

- **Image (14):** agent, agent_sdk, console, creative, data, docs, marketing,
  mate, mcp, model, os, training, user, admin.
  - `mcp` + `user` are the base-image outliers (ADR 0007 §1 / phase 5).
  - `admin` (17th mirror, #324) is a Next.js console; its Dockerfile is added
    under phase 5 — the image name is pinned now so manifests stay forward-compatible.
- **Libs-only, no image (3):** app_sdk (TS package monorepo), vibe (orchestrator
  CLI/tooling), cloud (this repo — infra + charts).

## Cutting a release

```bash
cd deployments/release
VERSION=1.0.0

# 1. Release manifest + SN offline-bundle CSV.
#    Timestamp is INJECTED (reproducible) — pass --generated-at or set
#    $RELEASE_GENERATED_AT. Add --resolve-digests on an internet-connected host
#    to pin @sha256 (falls back to :VERSION tags when the registry is unreachable).
python3 generate-release-manifest.py --version "$VERSION" \
    --generated-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --resolve-digests          # optional; omit offline

# 2. Package the charts at version = platform version, bundle edition overlays.
./package-charts.sh "$VERSION"
```

Outputs under `releases/`:

- `platform-vX.Y.Z.json` — the **release manifest** (single source of truth):
  ```json
  { "platform_version": "1.0.0",
    "generated_at": "2026-06-05T00:00:00Z",
    "services": { "isa-agent": "ghcr.io/xenoisa/isa-agent@sha256:…", … },
    "charts":   { "isa-service": "1.0.0", "isa-bigdata": "1.0.0" } }
  ```
- `platform-vX.Y.Z.offline-bundle.csv` — same column shape as SN's
  `offline-bundle-manifest.csv` (`category,component,source_ref,harbor_target,approx_size,action,notes`),
  every platform image as a `MIRROR` row → `harbor.prod.sn.local/isa/<image>:X.Y.Z`.
- `charts/isa-service-X.Y.Z.tgz`, `charts/isa-bigdata-X.Y.Z.tgz`,
  `charts/editions/*.yaml` (base + edition + `values-brand-sn` overlays).

> The on-disk `Chart.yaml` files stay at their placeholder `0.1.0`; the release
> version is stamped onto the **packaged** `.tgz` via `helm package --version`
> (additive — no chart mutation).

### OCI publish (gated off in MVP)

ADR 0007 §3 publishes charts as OCI artifacts. This MVP does **not** push.
To enable on a release runner (after `helm registry login ghcr.io`):

```bash
PUBLISH_OCI=1 OCI_REGISTRY=oci://ghcr.io/xenoisa/charts ./package-charts.sh "$VERSION"
```

## How SN consumes a release (ADR 0007 §4–5)

On an internet-connected host that can reach Harbor (SN side):

```bash
# 1. Seed Harbor from the offline-bundle CSV using SN's EXISTING mirror script.
export HARBOR=harbor.prod.sn.local
CSV=platform-vX.Y.Z.offline-bundle.csv ./mirror-to-harbor.sh images
#   true air-gap: MODE=archive ./mirror-to-harbor.sh images   (sneakernet tars)

# 2. Install the editions chart with edition + brand overlays (SN = on-prem-full + brand-sn).
helm install isa-on-prem-full ./isa-service-X.Y.Z.tgz \
    -f editions/values-base.yaml \
    -f editions/values-on-prem-full.yaml \
    -f editions/values-brand-sn.example.yaml
#   (or `oci://harbor.prod.sn.local/isa/charts/isa-service --version X.Y.Z` once OCI publish is on)
```

**Update** = new platform release → new manifest → mirror the **delta** images →
`helm upgrade` (or ArgoCD sync) → rollback via `helm rollback`.

## Tests

`../../tests/unit/test_generate_release_manifest.py` (L1/L2): manifest JSON shape,
injected timestamp, image-vs-libs filtering, digest-vs-tag refs, CSV columns match
SN's format, mocked/offline digest resolution.

```bash
python3 -m pytest tests/unit/test_generate_release_manifest.py -q
```

## Phases beyond this MVP (stories under #332)

3. **Platform-release workflow** — [`../../.github/workflows/platform-release.yml`](../../.github/workflows/platform-release.yml):
   on a `platform-v*` tag → resolve GHCR digests → emit manifest + offline bundle →
   package charts → publish a GitHub Release with the assets. **(done)**
4. **SN mirror integration / install runbook** — [`SN-DELIVERY.md`](SN-DELIVERY.md):
   seed Harbor from the offline-bundle CSV via `mirror-to-harbor.sh`, then
   `helm install/upgrade` with edition + brand overlays; update + rollback flows. **(done)**
5. Fix base-image outliers (isA_MCP / isA_user / isA_Admin → build base to GHCR).
6. ArgoCD image-tag sync from the manifest (`promote-to-production.yml`).
