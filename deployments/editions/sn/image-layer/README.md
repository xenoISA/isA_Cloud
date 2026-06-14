# SN image-layer — escape hatch (Model (a)), OFF BY DEFAULT

> Prep for the editions cutover (#462→#322). **Do not use this unless the cutover
> Decision-1 classifies a service as needing it.** The default and recommended path
> is **Model (c)** — the pod runs the edition-agnostic upstream `isa/<svc>` image and
> SN-ness comes from the `editions/sn` config overlays. See the decision record:
> `sn_cloud/docs/implementation-delivery/production/platform-services/sn-package-delivery-decision.md`.

## What this is

A single **parametrized** Dockerfile (`Dockerfile`) that layers an SN pip package
(`sn-<svc>`) on top of a **digest-pinned upstream platform image**:

```
FROM ghcr.io/xenoisa/isa-<svc>@sha256:<digest>
RUN pip install --no-deps --index-url <sn-internal-index> sn-<svc>==<ver>
```

Entrypoint / CMD / USER / ports are inherited from the upstream image unchanged — the
layer adds code, not wiring. Same base digest both editions; SN delta added on top, so
there is still **no per-edition rebuild of the platform image itself**.

## When (and only when) to use it

Per-service, after running the `/sync-diff` dry-run (isA→SN sanitizer) for that
service, you find the fork carries **runtime code that is NOT a sanitizer rewrite and
NOT expressible as `editions/sn` config**. Preferred remediation is still to
**upstream that delta** (which lets the service cut over to Model (c) and lets #322
close). Use this layer only as an interim, and record it as tech-debt against #322.

## Build

Local (connected or SN-internal host):

```bash
docker build \
  -f deployments/editions/sn/image-layer/Dockerfile \
  --build-arg BASE_IMAGE=ghcr.io/xenoisa/isa-model@sha256:<digest-from-platform-manifest> \
  --build-arg SN_PACKAGE="sn-model==0.6.0" \
  --build-arg PIP_INDEX="https://pypi.sn.internal/simple" \
  -t ghcr.io/xenoisa/sn-model-layer:<platform-version> .
```

CI (manual dispatch only — `.github/workflows/sn-image-layer.yml`):

```bash
gh workflow run sn-image-layer.yml \
  -f service=model \
  -f base_image=ghcr.io/xenoisa/isa-model@sha256:<digest> \
  -f sn_package="sn-model==0.6.0" \
  -f pip_index="https://pypi.sn.internal/simple" \
  -f platform_version=1.0.0
```

The workflow guards that `base_image` is `@sha256`-pinned and refuses otherwise.

## Mirror + wire (ops)

GitHub runners cannot reach SN Harbor (`10.60.65.10`, VPN-only). Mirror the built
layer with `skopeo` (same bootstrap method as every other image, SN-DELIVERY.md):

```bash
skopeo copy --dest-tls-verify=false --dest-creds admin:<HARBOR_PWD> \
  docker://ghcr.io/xenoisa/sn-model-layer:<platform-version> \
  docker://10.60.65.10/isa/sn-model-layer:<platform-version>
```

Then point that one service's editions override at the layer image:

```yaml
# deployments/editions/sn/services/isa-model.yaml (only if opted in)
image:
  repository: isa/sn-model-layer   # was: isa/isa-model
  tag: "<platform-version>"
```

Everything else (chart, base, brand/edition config) is unchanged. Revert = point the
override back at `isa/isa-model` and re-sync.
