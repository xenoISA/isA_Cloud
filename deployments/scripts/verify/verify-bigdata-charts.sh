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
PAIMON_CHART="${DEPLOYMENTS}/charts/paimon-tools"

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
  if ! grep -q "paimon-catalog" <<<"${out}"; then
    echo "[fail] no paimon-tools rendering in ${profile}" >&2
    exit 4
  fi
}

main() {
  require_helm

  step "helm dependency update ${POSTGRES_CHART}"
  helm dependency update "${POSTGRES_CHART}"

  step "helm dependency update ${MINIO_CHART}"
  helm dependency update "${MINIO_CHART}"

  lint_chart "${KAFKA_CHART}"
  lint_chart "${APICURIO_CHART}"
  lint_chart "${POSTGRES_CHART}"
  lint_chart "${HMS_CHART}"
  lint_chart "${MINIO_CHART}"
  lint_chart "${PAIMON_CHART}"

  template_chart "${KAFKA_CHART}"
  template_chart "${APICURIO_CHART}" --set db.auth.create=true --set db.auth.password=test
  template_chart "${POSTGRES_CHART}"
  template_chart "${HMS_CHART}" \
    --set db.auth.create=true --set db.auth.password=test \
    --set s3a.auth.create=true --set s3a.auth.accessKey=test --set s3a.auth.secretKey=test
  template_chart "${MINIO_CHART}" \
    --set auth.create=true --set auth.rootUser=test --set auth.rootPassword=testtesttest
  template_chart "${PAIMON_CHART}"

  step "helm dependency update ${UMBRELLA}"
  helm dependency update "${UMBRELLA}"

  for profile in "${PROFILES[@]}"; do
    template_umbrella_with_profile "${profile}"
  done

  step "all checks passed"
}

main "$@"
