#!/usr/bin/env bash
# =============================================================================
# setup-datalake.sh — bring up the isa-bigdata umbrella in correct order
# =============================================================================
# Tracking: xenoISA/isA_Cloud#234 (parent epic) + sn-commercial-tower
# ADR-0002 §12.3 (deploy.sh datalake subcommand). The cluster_operations
# skill scripts (setup-{local,staging,production}.sh) bring up the
# K8s + isA platform layer; this script layers the big-data foundation
# on top.
#
# Order (mirrors deployments/cluster-prereqs/README.md):
#   1. Pre-flight: kubectl context, helm version, target namespace
#   2. Cluster prereqs: PriorityClass platform-critical / infra-critical /
#      application
#   3. Strimzi Kafka Operator (cluster-scoped CRDs)
#   4. helm dependency update for the umbrella + each chart with file://
#      and remote deps
#   5. helm install/upgrade the umbrella with the chosen profile
#   6. (Optional) wait for readiness gates and run the chart smoke
#      test verify-bigdata-charts.sh
#
# Usage:
#   ./setup-datalake.sh [-p PROFILE] [-n NAMESPACE] [-r RELEASE]
#                       [--dry-run] [--skip-prereqs] [--skip-strimzi]
#                       [--values-extra FILE] [--smoke]
#
# Examples:
#   ./setup-datalake.sh -p kind-local                         # default
#   ./setup-datalake.sh -p customer-prod -n isa-bigdata
#   ./setup-datalake.sh --dry-run -p customer-prod
#   ./setup-datalake.sh --skip-strimzi -p kind-local          # operator already up
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENTS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${DEPLOYMENTS_DIR}/.." && pwd)"

# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------
PROFILE="${PROFILE:-kind-local}"
NAMESPACE="${NAMESPACE:-isa-bigdata}"
STRIMZI_NAMESPACE="${STRIMZI_NAMESPACE:-strimzi-system}"
RELEASE="${RELEASE:-bigdata}"
DRY_RUN=false
SKIP_PREREQS=false
SKIP_STRIMZI=false
EXTRA_VALUES=""
RUN_SMOKE=false

UMBRELLA_DIR="${DEPLOYMENTS_DIR}/umbrella/isa-bigdata"
PREREQS_FILE="${DEPLOYMENTS_DIR}/cluster-prereqs/priorityclasses.yaml"
STRIMZI_CHART_DIR="${DEPLOYMENTS_DIR}/charts/strimzi-operator"
VERIFY_SCRIPT="${SCRIPT_DIR}/verify/verify-bigdata-charts.sh"

# -----------------------------------------------------------------------------
# Output helpers
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { printf '%b[setup-datalake]%b %s\n'  "${BLUE}"   "${NC}" "$*"; }
ok()   { printf '%b[setup-datalake]%b %s\n'  "${GREEN}"  "${NC}" "$*"; }
warn() { printf '%b[setup-datalake]%b %s\n'  "${YELLOW}" "${NC}" "$*" >&2; }
die()  { printf '%b[setup-datalake]%b %s\n'  "${RED}"    "${NC}" "$*" >&2; exit 1; }

usage() {
  sed -n '1,40p' "${BASH_SOURCE[0]}" | grep -E '^#' | sed 's/^# \?//'
  exit 0
}

# -----------------------------------------------------------------------------
# Argument parsing
# -----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--profile)        PROFILE="$2"; shift 2 ;;
    -n|--namespace)      NAMESPACE="$2"; shift 2 ;;
    -r|--release)        RELEASE="$2"; shift 2 ;;
    --strimzi-namespace) STRIMZI_NAMESPACE="$2"; shift 2 ;;
    --dry-run)           DRY_RUN=true; shift ;;
    --skip-prereqs)      SKIP_PREREQS=true; shift ;;
    --skip-strimzi)      SKIP_STRIMZI=true; shift ;;
    --values-extra)      EXTRA_VALUES="$2"; shift 2 ;;
    --smoke)             RUN_SMOKE=true; shift ;;
    -h|--help)           usage ;;
    *) die "Unknown argument: $1 (try --help)" ;;
  esac
done

VALUES_FILE="${DEPLOYMENTS_DIR}/values/${PROFILE}.yaml"

# -----------------------------------------------------------------------------
# Step 1: Pre-flight
# -----------------------------------------------------------------------------
log "Pre-flight checks"

command -v kubectl >/dev/null 2>&1 || die "kubectl not on PATH"
command -v helm    >/dev/null 2>&1 || die "helm not on PATH"

if ! kubectl cluster-info >/dev/null 2>&1; then
  die "kubectl can't reach a cluster. Set KUBECONFIG or change context."
fi

ok "kubectl context: $(kubectl config current-context)"
ok "helm version:    $(helm version --short)"

# cert-manager CRDs are a hard prereq — the flink-operator sub-chart
# bundled inside the umbrella ships Certificate / Issuer CRs for its
# admission webhook. Without cert-manager installed the umbrella fails
# with the opaque `no matches for kind "Certificate" in version
# "cert-manager.io/v1"`. Use ./deploy.sh infrastructure to install
# cert-manager before this script.
if ! kubectl get crd certificates.cert-manager.io >/dev/null 2>&1; then
  warn "cert-manager CRDs not found. The flink-operator sub-chart needs them."
  warn "Run \`./deploy.sh infrastructure ${PROFILE}\` first, or install cert-manager"
  warn "manually with \`helm upgrade --install cert-manager"
  warn "  deployments/charts/cert-manager --namespace cert-manager --create-namespace\`."
  if [[ "${DRY_RUN}" != "true" ]]; then
    die "Aborting — cert-manager prereq missing"
  fi
fi

[[ -f "${VALUES_FILE}" ]]  || die "Profile values file not found: ${VALUES_FILE}"
[[ -f "${PREREQS_FILE}" ]] || die "Prereqs manifest not found: ${PREREQS_FILE}"
[[ -d "${UMBRELLA_DIR}" ]] || die "Umbrella chart dir not found: ${UMBRELLA_DIR}"

if [[ -n "${EXTRA_VALUES}" && ! -f "${EXTRA_VALUES}" ]]; then
  die "--values-extra file not found: ${EXTRA_VALUES}"
fi

ok "Profile: ${PROFILE}"
ok "Target namespace: ${NAMESPACE}"
ok "Release: ${RELEASE}"
[[ "${DRY_RUN}" == "true" ]] && warn "DRY-RUN — no cluster mutations will happen"

# -----------------------------------------------------------------------------
# Step 2: Cluster prereqs (PriorityClass)
# -----------------------------------------------------------------------------
if [[ "${SKIP_PREREQS}" == "true" ]]; then
  warn "Skipping cluster prereqs (--skip-prereqs)"
else
  log "Applying cluster prereqs (PriorityClass tiers)"
  if [[ "${DRY_RUN}" == "true" ]]; then
    kubectl apply --dry-run=client -f "${PREREQS_FILE}"
  else
    kubectl apply -f "${PREREQS_FILE}"
  fi
  ok "PriorityClass tiers: platform-critical / infra-critical / application"
fi

# -----------------------------------------------------------------------------
# Step 3: Strimzi Kafka Operator
# -----------------------------------------------------------------------------
if [[ "${SKIP_STRIMZI}" == "true" ]]; then
  warn "Skipping Strimzi Operator install (--skip-strimzi)"
else
  log "Installing Strimzi Kafka Operator into namespace ${STRIMZI_NAMESPACE}"

  if [[ "${DRY_RUN}" == "true" ]]; then
    helm template strimzi-operator "${STRIMZI_CHART_DIR}" \
      --namespace "${STRIMZI_NAMESPACE}" >/dev/null
    ok "Strimzi helm template OK (dry-run)"
  else
    # Pre-create both namespaces. The Strimzi chart projects RoleBindings
    # into the watched namespaces (e.g. isa-bigdata) at install time —
    # if the watched namespace doesn't exist yet helm fails immediately.
    if ! kubectl get namespace "${STRIMZI_NAMESPACE}" >/dev/null 2>&1; then
      kubectl create namespace "${STRIMZI_NAMESPACE}"
    fi
    if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
      kubectl create namespace "${NAMESPACE}"
    fi

    helm dependency update "${STRIMZI_CHART_DIR}" >/dev/null

    helm upgrade --install strimzi-operator "${STRIMZI_CHART_DIR}" \
      --namespace "${STRIMZI_NAMESPACE}" \
      --wait \
      --timeout 5m

    ok "Strimzi Operator ready in ${STRIMZI_NAMESPACE}"
  fi
fi

# -----------------------------------------------------------------------------
# Step 4: Refresh helm dependencies
# -----------------------------------------------------------------------------
log "Refreshing helm dependencies for big-data charts"

# Charts with remote (Bitnami / Apache / Strimzi / MinIO / StarRocks /
# Flink Operator) deps need `helm dependency update` before the umbrella
# can pick them up. Skip charts that are pure file:// deps.
CHARTS_WITH_REMOTE_DEPS=(
  "${DEPLOYMENTS_DIR}/charts/postgres-bigdata"   # bitnami/postgresql
  "${DEPLOYMENTS_DIR}/charts/minio"              # minio/minio
  "${DEPLOYMENTS_DIR}/charts/starrocks"          # starrocks/kube-starrocks
  "${DEPLOYMENTS_DIR}/charts/flink"              # flink-operator/flink-kubernetes-operator
)

for chart in "${CHARTS_WITH_REMOTE_DEPS[@]}"; do
  if [[ -f "${chart}/Chart.yaml" ]]; then
    log "  helm dep update ${chart#${REPO_ROOT}/}"
    helm dependency update "${chart}" >/dev/null
  fi
done

# Umbrella aggregates 10 file:// deps; refresh after subcharts are
# updated so the umbrella's Chart.lock reflects the latest.
log "  helm dep update umbrella"
helm dependency update "${UMBRELLA_DIR}" >/dev/null

ok "Dependencies up to date"

# -----------------------------------------------------------------------------
# Step 5: Install / upgrade the umbrella
# -----------------------------------------------------------------------------
log "Installing isa-bigdata umbrella (release=${RELEASE}, namespace=${NAMESPACE})"

HELM_ARGS=(
  upgrade --install "${RELEASE}" "${UMBRELLA_DIR}"
  --namespace "${NAMESPACE}"
  --create-namespace
  --values "${VALUES_FILE}"
)

if [[ -n "${EXTRA_VALUES}" ]]; then
  HELM_ARGS+=(--values "${EXTRA_VALUES}")
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  HELM_ARGS+=(--dry-run --debug)
else
  HELM_ARGS+=(--wait --timeout 15m)
fi

helm "${HELM_ARGS[@]}"

if [[ "${DRY_RUN}" == "true" ]]; then
  ok "Umbrella dry-run OK"
else
  ok "Umbrella deployed"

  log "Cluster status snapshot:"
  kubectl -n "${NAMESPACE}" get \
    statefulset,deployment,kafka,kafkanodepool,starrockscluster,flinkdeployment 2>/dev/null \
    || true
fi

# -----------------------------------------------------------------------------
# Step 6: Optional smoke test
# -----------------------------------------------------------------------------
if [[ "${RUN_SMOKE}" == "true" ]]; then
  if [[ -x "${VERIFY_SCRIPT}" ]]; then
    log "Running chart smoke test (verify-bigdata-charts.sh)"
    bash "${VERIFY_SCRIPT}"
    ok "Smoke test passed"
  else
    warn "Smoke script not found / not executable: ${VERIFY_SCRIPT}"
  fi
fi

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
ok "setup-datalake.sh complete"
log "Next steps:"
log "  - Wait for hive-metastore-init-schema Job to complete (kind/dev profiles)"
log "  - Wait for Apicurio Registry Pods to become Ready (V-5 prereq)"
log "  - Run V-1..V-9 verification (xenoISA/isA_Cloud#257) once that script lands"
log "  - dataphin chart will install separately when vendor delivers (xenoISA/isA_Cloud#263)"
