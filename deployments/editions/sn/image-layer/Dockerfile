# =============================================================================
# SN thin image-layer — ESCAPE HATCH (Model (a)), OFF BY DEFAULT.
# =============================================================================
# The cutover target is Model (c): the deployed pod runs the edition-agnostic
# upstream `isa/<svc>` image unchanged, SN-ness via config overlays (see
# sn_cloud docs/.../platform-services/sn-package-delivery-decision.md).
#
# This Dockerfile exists ONLY for a service that Decision-1 classifies as
# carrying SN runtime code that is not yet upstreamed and not expressible as
# config. It layers the SN pip package onto the pinned upstream image WITHOUT a
# per-edition rebuild of the platform itself — same base image digest both
# editions, SN delta added on top.
#
# It is referenced by NO ArgoCD app unless ops explicitly opt a service in.
# Prefer upstreaming the delta (closes #322 cleanly) over shipping this layer.
#
# -----------------------------------------------------------------------------
# Build args (all required; no defaults so a mis-wired build fails loudly):
#   BASE_IMAGE   full digest-pinned upstream ref from the platform release
#                manifest, e.g. ghcr.io/xenoisa/isa-model@sha256:...
#                (or core.harbor.domain/isa/isa-model@sha256:... post-mirror)
#   SN_PACKAGE   the SN pip package + pin, e.g. "sn-model==0.6.0"
#   PIP_INDEX    index URL reachable from the build host. In the air-gapped SN
#                build this is the SN-internal PyPI/devpi mirror — NEVER the
#                public index post-deploy (FW-OUT-001). The package install
#                happens at BUILD time on a connected/seeded host, not at deploy.
# -----------------------------------------------------------------------------
# Example:
#   docker build \
#     -f deployments/editions/sn/image-layer/Dockerfile \
#     --build-arg BASE_IMAGE=ghcr.io/xenoisa/isa-model@sha256:<digest> \
#     --build-arg SN_PACKAGE="sn-model==0.6.0" \
#     --build-arg PIP_INDEX="https://pypi.sn.internal/simple" \
#     -t ghcr.io/xenoisa/sn-model-layer:<platform-version> .
# =============================================================================

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG SN_PACKAGE
ARG PIP_INDEX

# Re-declare after FROM so they are in scope for RUN (Docker ARG scoping rule).
# Fail the build if any required arg is empty rather than producing a silently
# wrong image.
RUN test -n "${SN_PACKAGE}" || (echo "ERROR: SN_PACKAGE build-arg is required" && exit 1) && \
    test -n "${PIP_INDEX}"  || (echo "ERROR: PIP_INDEX build-arg is required"  && exit 1)

# Install the SN package on top of the upstream image. --no-deps by default:
# the upstream image already carries the platform runtime + the SN package's
# transitive deps should already be present (the SN package is a thin consumer
# of the platform SDK). Drop --no-deps only if Decision-1 shows the package
# pulls runtime deps the base lacks (record that as a finding — it weakens the
# "thin layer" claim and argues for upstreaming instead).
RUN pip install --no-cache-dir --no-deps --index-url "${PIP_INDEX}" "${SN_PACKAGE}"

# Provenance: record what was layered so `docker inspect` / SBOM shows the SN
# delta and the base it was built on.
LABEL sn.image-layer.base="${BASE_IMAGE}" \
      sn.image-layer.package="${SN_PACKAGE}" \
      sn.image-layer.model="a-escape-hatch" \
      org.opencontainers.image.description="SN thin layer over edition-agnostic upstream image (cutover escape hatch)"

# Entrypoint/CMD/USER/EXPOSE are INHERITED from the upstream image unchanged —
# do not override them here. The layer adds code, not behaviour wiring; the pod
# still starts exactly as the upstream image does, picking up SN config via the
# editions/sn env + ConfigMaps/Secrets at runtime.
