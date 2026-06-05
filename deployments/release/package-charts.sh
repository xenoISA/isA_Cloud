#!/usr/bin/env bash
# package-charts.sh — package the platform Helm charts for a release (ADR 0007 §3, phase 2).
#
# Packages the base service chart (isa-service) and the big-data umbrella
# (isa-bigdata) with version = app-version = the platform release version, and
# drops the .tgz artifacts + the edition value overlays into releases/charts/.
#
# WHY version = platform version: ADR 0007 §3 — "chart version = platform version
# at release". The on-disk Chart.yaml stays at its placeholder 0.1.0 (additive,
# no chart mutation); `helm package --version` stamps the release version onto the
# packaged artifact only.
#
# OCI publish (ADR 0007 §3) is intentionally GATED OFF in this MVP. To publish:
#   helm push releases/charts/isa-service-X.Y.Z.tgz  oci://ghcr.io/xenoisa/charts
#   helm push releases/charts/isa-bigdata-X.Y.Z.tgz  oci://ghcr.io/xenoisa/charts
# Enable with PUBLISH_OCI=1 (requires `helm registry login ghcr.io`). MVP default: off.
#
# Usage:
#   ./package-charts.sh X.Y.Z
#   PUBLISH_OCI=1 OCI_REGISTRY=oci://ghcr.io/xenoisa/charts ./package-charts.sh X.Y.Z
#
# Reads nothing from the network unless PUBLISH_OCI=1.
set -euo pipefail

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "usage: $0 X.Y.Z" >&2
  exit 2
fi
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+].+)?$ ]]; then
  echo "error: '$VERSION' is not a semver X.Y.Z" >&2
  exit 2
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENTS="$(cd "$HERE/.." && pwd)"
SERVICE_CHART="$DEPLOYMENTS/charts/isa-service"
UMBRELLA_CHART="$DEPLOYMENTS/umbrella/isa-bigdata"
EDITIONS_DIR="$DEPLOYMENTS/editions"
OUT_DIR="${OUT_DIR:-$HERE/releases/charts}"

PUBLISH_OCI="${PUBLISH_OCI:-0}"
OCI_REGISTRY="${OCI_REGISTRY:-oci://ghcr.io/xenoisa/charts}"

command -v helm >/dev/null 2>&1 || { echo "error: helm not found on PATH" >&2; exit 3; }

mkdir -p "$OUT_DIR"

echo ">> helm lint isa-service"
helm lint "$SERVICE_CHART"

echo ">> package isa-service @ $VERSION"
helm package "$SERVICE_CHART" \
  --version "$VERSION" --app-version "$VERSION" \
  --destination "$OUT_DIR"

# Umbrella: resolve file:// deps first so it packages cleanly (ADR 0007 §3).
# `dependency build` uses the committed Chart.lock; if absent, fall back to update.
echo ">> resolve isa-bigdata file:// dependencies"
if [[ -f "$UMBRELLA_CHART/Chart.lock" ]]; then
  helm dependency build "$UMBRELLA_CHART"
else
  helm dependency update "$UMBRELLA_CHART"
fi

echo ">> helm lint isa-bigdata"
helm lint "$UMBRELLA_CHART"

echo ">> package isa-bigdata @ $VERSION"
helm package "$UMBRELLA_CHART" \
  --version "$VERSION" --app-version "$VERSION" \
  --destination "$OUT_DIR"

# Bundle the edition + brand value overlays alongside the charts so SN installs
# with `-f values-base -f values-<edition> -f values-brand-sn` (ADR 0007 §5).
echo ">> bundle edition overlays"
mkdir -p "$OUT_DIR/editions"
cp "$EDITIONS_DIR"/*.yaml "$OUT_DIR/editions/" 2>/dev/null || true

echo ">> packaged artifacts:"
ls -1 "$OUT_DIR"/*.tgz

if [[ "$PUBLISH_OCI" == "1" ]]; then
  echo ">> PUBLISH_OCI=1 — pushing charts to $OCI_REGISTRY"
  for tgz in "$OUT_DIR"/*.tgz; do
    echo "   helm push $tgz $OCI_REGISTRY"
    helm push "$tgz" "$OCI_REGISTRY"
  done
else
  echo ">> OCI publish gated off (MVP). Set PUBLISH_OCI=1 to push to $OCI_REGISTRY"
fi

echo "DONE: charts in $OUT_DIR"
