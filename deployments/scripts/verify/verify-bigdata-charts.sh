#!/usr/bin/env bash
# verify-bigdata-charts.sh — helm lint + template smoke for the isa-bigdata
# umbrella across the kind-local and customer-prod profiles. Tracking issue:
# xenoISA/isA_Cloud#234.
#
# Usage:
#   deployments/scripts/verify/verify-bigdata-charts.sh
#
# Exits non-zero on any helm error or missing manifest.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEPLOYMENTS="${REPO_ROOT}/deployments"
UMBRELLA="${DEPLOYMENTS}/umbrella/isa-bigdata"
KAFKA_CHART="${DEPLOYMENTS}/charts/kafka"
APICURIO_CHART="${DEPLOYMENTS}/charts/apicurio-registry"
POSTGRES_CHART="${DEPLOYMENTS}/charts/postgres-bigdata"
HMS_CHART="${DEPLOYMENTS}/charts/hive-metastore"
MINIO_CHART="${DEPLOYMENTS}/charts/minio"
ICEBERG_CHART="${DEPLOYMENTS}/charts/iceberg-tools"
STARROCKS_CHART="${DEPLOYMENTS}/charts/starrocks"
FLINK_CHART="${DEPLOYMENTS}/charts/flink"
FLINK_CDC_CHART="${DEPLOYMENTS}/charts/flink-cdc-jobs"
FLUSS_CHART="${DEPLOYMENTS}/charts/fluss"
STRIMZI_CHART="${DEPLOYMENTS}/charts/strimzi-operator"
PROMETHEUS_CHART="${DEPLOYMENTS}/charts/prometheus-operator"
CERT_MANAGER_CHART="${DEPLOYMENTS}/charts/cert-manager"

PROFILES=("kind-local" "dev-shared" "customer-prod")

step() {
  printf '\n=== %s ===\n' "$1"
}

require_helm() {
  command -v helm >/dev/null 2>&1 || {
    echo "helm not found on PATH" >&2
    exit 2
  }
}

lint_chart() {
  local chart="$1"
  step "helm lint ${chart}"
  helm lint "${chart}"
}

template_chart() {
  local chart="$1"
  local extra_args=("$@")
  step "helm template ${chart} ${extra_args[*]:1}"
  helm template smoke "${chart}" "${extra_args[@]:1}" >/dev/null
}

template_umbrella_with_profile() {
  local profile="$1"
  local values_file="${DEPLOYMENTS}/values/${profile}.yaml"
  step "helm template umbrella -f values/${profile}.yaml"
  if [[ ! -f "${values_file}" ]]; then
    echo "missing values file: ${values_file}" >&2
    exit 3
  fi
  local out
  out=$(helm template "isa-bigdata-${profile}" "${UMBRELLA}" --values "${values_file}")
  # Sanity checks — make sure both subcharts actually rendered something.
  if ! grep -q "kind: Kafka" <<<"${out}"; then
    echo "[fail] no Kafka resource in ${profile} render" >&2
    exit 4
  fi
  if ! grep -q "kind: KafkaNodePool" <<<"${out}"; then
    echo "[fail] no KafkaNodePool resource in ${profile} render" >&2
    exit 4
  fi
  if ! grep -q "apicurio-registry" <<<"${out}"; then
    echo "[fail] no apicurio-registry rendering in ${profile}" >&2
    exit 4
  fi
  if ! grep -q "postgresql" <<<"${out}"; then
    echo "[fail] no postgresql (postgres-bigdata) rendering in ${profile}" >&2
    exit 4
  fi
  if ! grep -q "hive-metastore" <<<"${out}"; then
    echo "[fail] no hive-metastore rendering in ${profile}" >&2
    exit 4
  fi
  if ! grep -q "minio" <<<"${out}"; then
    echo "[fail] no minio rendering in ${profile}" >&2
    exit 4
  fi
  if ! grep -q "iceberg-catalog" <<<"${out}"; then
    echo "[fail] no iceberg-tools rendering in ${profile}" >&2
    exit 4
  fi
  if ! grep -q "kind: StarRocksCluster" <<<"${out}"; then
    echo "[fail] no StarRocksCluster CR in ${profile}" >&2
    exit 4
  fi
  if ! grep -q "kind: FlinkDeployment" <<<"${out}"; then
    echo "[fail] no FlinkDeployment CR in ${profile}" >&2
    exit 4
  fi
  # FlinkSessionJob CRs only render when at least one source is enabled.
  # kind-local + dev-shared have 3 P0 sources enabled; customer-prod has
  # all 22 sources but disabled-by-default — treat its absence as OK.
  if [[ "${profile}" != "customer-prod" ]]; then
    if ! grep -q "kind: FlinkSessionJob" <<<"${out}"; then
      echo "[fail] no FlinkSessionJob CR in ${profile}" >&2
      exit 4
    fi
  fi
}

main() {
  require_helm

  step "helm dependency update ${POSTGRES_CHART}"
  helm dependency update "${POSTGRES_CHART}"

  step "helm dependency update ${MINIO_CHART}"
  helm dependency update "${MINIO_CHART}"

  step "helm dependency update ${STARROCKS_CHART}"
  helm dependency update "${STARROCKS_CHART}"

  step "helm dependency update ${FLINK_CHART}"
  helm dependency update "${FLINK_CHART}"

  step "helm dependency update ${STRIMZI_CHART}"
  helm dependency update "${STRIMZI_CHART}"

  step "helm dependency update ${PROMETHEUS_CHART}"
  helm dependency update "${PROMETHEUS_CHART}"

  step "helm dependency update ${CERT_MANAGER_CHART}"
  helm dependency update "${CERT_MANAGER_CHART}"

  lint_chart "${KAFKA_CHART}"
  lint_chart "${APICURIO_CHART}"
  lint_chart "${POSTGRES_CHART}"
  lint_chart "${HMS_CHART}"
  lint_chart "${MINIO_CHART}"
  lint_chart "${ICEBERG_CHART}"
  lint_chart "${STARROCKS_CHART}"
  lint_chart "${FLINK_CHART}"
  lint_chart "${FLINK_CDC_CHART}"
  lint_chart "${FLUSS_CHART}"
  lint_chart "${STRIMZI_CHART}"
  lint_chart "${PROMETHEUS_CHART}"
  lint_chart "${CERT_MANAGER_CHART}"

  template_chart "${KAFKA_CHART}"
  template_chart "${APICURIO_CHART}" --set db.auth.create=true --set db.auth.password=test
  template_chart "${POSTGRES_CHART}"
  template_chart "${HMS_CHART}" \
    --set db.auth.create=true --set db.auth.password=test \
    --set s3a.auth.create=true --set s3a.auth.accessKey=test --set s3a.auth.secretKey=test
  template_chart "${MINIO_CHART}" \
    --set auth.create=true --set auth.rootUser=test --set auth.rootPassword=testtesttest
  template_chart "${ICEBERG_CHART}"
  template_chart "${STARROCKS_CHART}" \
    --set rootPassword.create=true --set rootPassword.password=test
  template_chart "${FLINK_CHART}"
  # flink-cdc-jobs renders nothing when sources is empty; pass a smoke source.
  template_chart "${FLINK_CDC_CHART}" \
    --set 'sources[0].name=smoke' \
    --set 'sources[0].enabled=true' \
    --set 'sources[0].sql=SELECT 1;'
  # fluss is a shell — default disabled at all profiles. Standalone
  # template with --set enabled=true exercises the placeholder render
  # path so helper / labels / ConfigMap regressions are caught here.
  template_chart "${FLUSS_CHART}" --set enabled=true
  # strimzi-operator is a STRICT prerequisite for the umbrella's kafka
  # chart — installed separately before the umbrella. Verified standalone
  # (NOT included in any umbrella render).
  template_chart "${STRIMZI_CHART}"
  # prometheus-operator is a STRICT prerequisite when customer-prod
  # ServiceMonitors are enabled — installed separately before the
  # umbrella. Verified standalone (NOT included in any umbrella render).
  template_chart "${PROMETHEUS_CHART}"
  # cert-manager is a STRICT prerequisite when any chart issues
  # Certificate / Issuer / ClusterIssuer CRs — installed separately
  # before the umbrella. Verified standalone (NOT included in any
  # umbrella render).
  template_chart "${CERT_MANAGER_CHART}"

  step "helm dependency update ${UMBRELLA}"
  helm dependency update "${UMBRELLA}"

  for profile in "${PROFILES[@]}"; do
    template_umbrella_with_profile "${profile}"
  done

  step "all checks passed"
}

main "$@"
