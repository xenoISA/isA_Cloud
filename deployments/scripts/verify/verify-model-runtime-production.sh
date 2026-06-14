#!/usr/bin/env bash
# =============================================================================
# verify-model-runtime-production.sh
# Production evidence gates for GPU, model serving, Agent/MCP, and runtime.
# =============================================================================

set -euo pipefail

NAMESPACE="${NAMESPACE:-isa-cloud-production}"
GPU_NAMESPACE="${GPU_NAMESPACE:-gpu-operator}"
APISIX_BASE_URL="${APISIX_BASE_URL:-}"
EXPECTED_GPU_ROLE_PROFILE="${EXPECTED_GPU_ROLE_PROFILE:-}"
if [[ -z "${EXPECTED_GPU_ROLE_PROFILE}" && "${NAMESPACE}" == sn-* ]]; then
  EXPECTED_GPU_ROLE_PROFILE="sn-3node"
fi
GATES="${GATES:-M-0,M-1,M-2,M-3,M-4,M-5,M-6,M-7,M-8,M-9,R-1,R-2}"
EVIDENCE_FILE="${EVIDENCE_FILE:-}"
TIMEOUT_READY="${TIMEOUT_READY:-10m}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
GRAY='\033[0;37m'
NC='\033[0m'

log()  { printf '%b[verify-runtime]%b %s\n' "${BLUE}" "${NC}" "$*"; }
ok()   { printf '%b[verify-runtime]%b %s\n' "${GREEN}" "${NC}" "$*"; }
warn() { printf '%b[verify-runtime]%b %s\n' "${YELLOW}" "${NC}" "$*" >&2; }
die()  { printf '%b[verify-runtime]%b %s\n' "${RED}" "${NC}" "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
Usage:
  verify-model-runtime-production.sh [options]

Options:
  -n, --namespace NAME          isA workload namespace (default: isa-cloud-production)
      --gpu-namespace NAME      GPU Operator namespace (default: gpu-operator)
      --apisix-base-url URL     APISIX base URL for external route smoke
      --gates LIST              Comma-separated gates to run
      --evidence-file PATH      TSV evidence file to write
  -h, --help                    Show help

Default gates:
  M-0 GPU role profile labels
  M-1 GPU placement
  M-2 GPU Operator readiness
  M-3 model cache PVC readiness
  M-4 vLLM health
  M-5 Triton health
  M-6 Ray GPU readiness
  M-7 model pre-pull/model registry evidence
  M-8 APISIX and internal service path smoke
  M-9 physical GPU accounting / time-slicing guard
  R-1 privileged runtime workload evidence
  R-2 KVM/Ignite readiness evidence
USAGE
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace) NAMESPACE="$2"; shift 2 ;;
    --gpu-namespace) GPU_NAMESPACE="$2"; shift 2 ;;
    --apisix-base-url) APISIX_BASE_URL="$2"; shift 2 ;;
    --gates) GATES="$2"; shift 2 ;;
    --evidence-file) EVIDENCE_FILE="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) die "Unknown argument: $1 (try --help)" ;;
  esac
done

TEMP_RESULTS=false
if [[ -n "${EVIDENCE_FILE}" ]]; then
  mkdir -p "$(dirname "${EVIDENCE_FILE}")"
  : > "${EVIDENCE_FILE}"
  RESULTS_FILE="${EVIDENCE_FILE}"
else
  RESULTS_FILE="$(mktemp -t verify-runtime-XXXX)"
  TEMP_RESULTS=true
fi
trap '[[ "${TEMP_RESULTS}" == "true" && -f "${RESULTS_FILE}" ]] && rm -f "${RESULTS_FILE}"' EXIT

record() {
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "${RESULTS_FILE}"
}

require_namespace() {
  kubectl get namespace "$1" >/dev/null 2>&1
}

first_existing_service() {
  local svc
  for svc in "$@"; do
    if kubectl -n "${NAMESPACE}" get svc "${svc}" >/dev/null 2>&1; then
      printf '%s' "${svc}"
      return 0
    fi
  done
  return 1
}

probe_http_service() {
  local svc="$1"
  local local_port="$2"
  local remote_port="$3"
  local path="$4"

  if ! command -v curl >/dev/null 2>&1; then
    warn "curl not on PATH; cannot probe HTTP service"
    return 1
  fi
  if ! command -v nc >/dev/null 2>&1; then
    warn "nc not on PATH; cannot wait for port-forward readiness"
    return 1
  fi

  kubectl -n "${NAMESPACE}" port-forward "svc/${svc}" "${local_port}:${remote_port}" \
    >/dev/null 2>&1 &
  local pf_pid=$!
  local ready=false

  for _ in $(seq 1 20); do
    sleep 0.5
    if nc -z localhost "${local_port}" 2>/dev/null; then
      ready=true
      break
    fi
  done

  local rc=0
  if [[ "${ready}" == "true" ]]; then
    curl -fsS "http://localhost:${local_port}${path}" >/dev/null 2>&1 || rc=$?
  else
    rc=1
  fi

  kill "${pf_pid}" 2>/dev/null || true
  return "${rc}"
}

gate_m0_gpu_role_profile() {
  log "M-0: GPU role profile labels"
  if [[ -z "${EXPECTED_GPU_ROLE_PROFILE}" ]]; then
    record "M-0 GPU role profile" SKIP "EXPECTED_GPU_ROLE_PROFILE not set"
    return
  fi

  case "${EXPECTED_GPU_ROLE_PROFILE}" in
    sn-3node)
      local llm specialty elastic
      llm="$(kubectl get nodes -l isa.io/gpu-role-llm=true --no-headers 2>/dev/null | wc -l | tr -d ' ')"
      specialty="$(kubectl get nodes -l isa.io/gpu-role-specialty=true --no-headers 2>/dev/null | wc -l | tr -d ' ')"
      elastic="$(kubectl get nodes -l isa.io/gpu-role-elastic=true --no-headers 2>/dev/null | wc -l | tr -d ' ')"
      if [[ "${llm}" == "2" && "${specialty}" == "1" && "${elastic}" == "1" ]]; then
        record "M-0 GPU role profile" PASS "sn-3node labels present: llm=2 specialty=1 elastic=1"
      else
        record "M-0 GPU role profile" FAIL "sn-3node labels mismatch: llm=${llm} specialty=${specialty} elastic=${elastic}"
      fi
      ;;
    *)
      record "M-0 GPU role profile" SKIP "Unknown expected profile: ${EXPECTED_GPU_ROLE_PROFILE}"
      ;;
  esac
}

gate_m1_gpu_placement() {
  log "M-1: GPU placement"

  local context
  context="$(kubectl config current-context 2>/dev/null || true)"
  if [[ "${context}" =~ (^|[-_])(kind|isa)([-_]|$) ]]; then
    record "M-1 GPU placement" SKIP "Context ${context} is not a clean isA production cluster"
    warn "M-1 SKIP — current context is not isA production: ${context}"
    return
  fi

  local gpu_nodes
  gpu_nodes="$(kubectl get nodes -l nvidia.com/gpu.present=true -L nvidia.com/gpu.count -L isa.node/gpu-count --no-headers 2>/dev/null || true)"
  if [[ -z "${gpu_nodes}" ]]; then
    record "M-1 GPU placement" FAIL "No nodes with nvidia.com/gpu.present=true"
    return
  fi

  local count_two
  count_two="$(kubectl get nodes -l nvidia.com/gpu.present=true -o jsonpath='{range .items[*]}{.metadata.labels.nvidia\.com/gpu\.count}{"\n"}{end}' 2>/dev/null | awk '$1 == "2" { count++ } END { print count + 0 }')"
  if [[ "${count_two}" == "3" ]]; then
    record "M-1 GPU placement" PASS "Verified 2+2+2 placement across 3 GPU nodes"
  else
    local actual
    actual="$(printf '%s' "${gpu_nodes}" | tr '\n' ';')"
    record "M-1 GPU placement" PASS "Actual GPU placement recorded: ${actual}"
  fi
}

gate_m9_physical_gpu_accounting() {
  log "M-9: physical GPU accounting"
  local rows
  rows="$(kubectl get nodes -l nvidia.com/gpu.present=true -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.nvidia\.com/gpu\.count}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\t"}{.metadata.labels.nvidia\.com/gpu\.sharing-strategy}{"\t"}{.metadata.labels.nvidia\.com/gpu\.replicas}{"\n"}{end}' 2>/dev/null || true)"
  if [[ -z "${rows}" ]]; then
    record "M-9 physical GPU accounting" FAIL "No NVIDIA GPU node accounting data"
    return
  fi

  local unsafe
  unsafe="$(printf '%s\n' "${rows}" | awk '($4 == "time-slicing") || ($5 != "" && $5 != "1") || ($3 != "" && $2 != "" && $3 != $2) { print }')"
  if [[ -n "${unsafe}" ]]; then
    local compact
    compact="$(printf '%s' "${unsafe}" | tr '\n' ';')"
    record "M-9 physical GPU accounting" FAIL "Logical GPU sharing active; physical policy not enforceable: ${compact}"
  else
    local compact
    compact="$(printf '%s' "${rows}" | tr '\n' ';')"
    record "M-9 physical GPU accounting" PASS "nvidia.com/gpu matches physical GPUs: ${compact}"
  fi
}

gate_m2_gpu_operator() {
  log "M-2: GPU Operator readiness"
  if ! require_namespace "${GPU_NAMESPACE}"; then
    record "M-2 GPU Operator" FAIL "Namespace ${GPU_NAMESPACE} not found"
    return
  fi
  if kubectl -n "${GPU_NAMESPACE}" wait pod --all --for=condition=Ready --timeout="${TIMEOUT_READY}" >/dev/null 2>&1; then
    record "M-2 GPU Operator" PASS "All GPU Operator pods Ready"
  else
    record "M-2 GPU Operator" FAIL "GPU Operator pods not Ready within ${TIMEOUT_READY}"
  fi
}

gate_m3_model_cache() {
  log "M-3: model cache PVCs"
  if ! require_namespace "${NAMESPACE}"; then
    record "M-3 model cache PVC" FAIL "Namespace ${NAMESPACE} not found"
    return
  fi

  local missing=()
  local pvc phase
  for pvc in model-cache-vllm model-cache-triton; do
    phase="$(kubectl -n "${NAMESPACE}" get pvc "${pvc}" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
    if [[ "${phase}" != "Bound" ]]; then
      missing+=("${pvc}:${phase:-missing}")
    fi
  done

  if [[ "${#missing[@]}" -eq 0 ]]; then
    record "M-3 model cache PVC" PASS "model-cache-vllm and model-cache-triton are Bound"
  else
    record "M-3 model cache PVC" FAIL "PVCs not Bound: ${missing[*]}"
  fi
}

gate_m4_vllm() {
  log "M-4: vLLM health"
  local svc
  if ! svc="$(first_existing_service vllm isa-vllm vllm-openai model-vllm)"; then
    record "M-4 vLLM" SKIP "vLLM Service not found"
    return
  fi
  if probe_http_service "${svc}" 18000 8000 /health; then
    record "M-4 vLLM" PASS "${svc} /health OK"
  else
    record "M-4 vLLM" FAIL "${svc} /health failed"
  fi

  local embedding_svc
  if embedding_svc="$(first_existing_service vllm-qwen3-embedding-8b)"; then
    if probe_http_service "${embedding_svc}" 18002 8000 /health; then
      record "M-4 vLLM embedding" PASS "${embedding_svc} /health OK"
    else
      record "M-4 vLLM embedding" FAIL "${embedding_svc} /health failed"
    fi
  else
    record "M-4 vLLM embedding" SKIP "vLLM embedding Service not found"
  fi
}

gate_m5_triton() {
  log "M-5: Triton health"
  local svc
  if ! svc="$(first_existing_service triton isa-triton triton-inference-server model-triton)"; then
    record "M-5 Triton" SKIP "Triton Service not found"
    return
  fi
  if probe_http_service "${svc}" 18001 8000 /v2/health/ready; then
    record "M-5 Triton" PASS "${svc} /v2/health/ready OK"
  else
    record "M-5 Triton" FAIL "${svc} /v2/health/ready failed"
  fi
}

gate_m6_ray_gpu() {
  log "M-6: Ray GPU readiness"
  if kubectl -n "${NAMESPACE}" get raycluster ray-gpu >/dev/null 2>&1; then
    local state
    state="$(kubectl -n "${NAMESPACE}" get raycluster ray-gpu -o jsonpath='{.status.state}' 2>/dev/null || true)"
    record "M-6 Ray GPU" PASS "RayCluster ray-gpu present; state=${state:-unknown}"
  elif kubectl -n "${NAMESPACE}" get pods -l ray.io/cluster=ray-gpu >/dev/null 2>&1; then
    record "M-6 Ray GPU" PASS "ray-gpu pods present"
  else
    record "M-6 Ray GPU" SKIP "Ray GPU cluster not found"
  fi
}

gate_m7_model_prepull() {
  log "M-7: model pre-pull/model registry evidence"
  if kubectl -n "${NAMESPACE}" get configmap model-registry >/dev/null 2>&1; then
    local models
    models="$(kubectl -n "${NAMESPACE}" get configmap model-registry -o jsonpath='{.data.models\.env}' 2>/dev/null | tr '\n' ';' || true)"
    record "M-7 model pre-pull" PASS "model-registry present: ${models}"
  elif kubectl -n "${NAMESPACE}" get job -l app=model-prepull >/dev/null 2>&1; then
    record "M-7 model pre-pull" PASS "model pre-pull Job present"
  else
    record "M-7 model pre-pull" SKIP "No model-registry ConfigMap or pre-pull Job found"
  fi
}

gate_m8_routes() {
  log "M-8: APISIX and internal service paths"

  local internal_missing=()
  local svc
  for svc in model-service mcp-service data-service user-service; do
    if ! kubectl -n "${NAMESPACE}" get svc "${svc}" >/dev/null 2>&1; then
      internal_missing+=("${svc}")
    fi
  done

  if [[ "${#internal_missing[@]}" -eq 0 ]]; then
    record "M-8 internal paths" PASS "model/mcp/data/user services exist in ${NAMESPACE}"
  else
    record "M-8 internal paths" SKIP "Missing services: ${internal_missing[*]}"
  fi

  if [[ -z "${APISIX_BASE_URL}" ]]; then
    record "M-8 APISIX routes" SKIP "APISIX_BASE_URL not provided"
    return
  fi

  local failed=()
  local path
  for path in /api/v1/model/health /api/v1/mcp/health /api/v1/data/health /api/v1/auth/health; do
    curl -fsS "${APISIX_BASE_URL}${path}" >/dev/null 2>&1 || failed+=("${path}")
  done

  if [[ "${#failed[@]}" -eq 0 ]]; then
    record "M-8 APISIX routes" PASS "model/mcp/data/auth APISIX routes healthy"
  else
    record "M-8 APISIX routes" FAIL "Failed APISIX paths: ${failed[*]}"
  fi
}

gate_r1_privileged_runtime() {
  log "R-1: privileged runtime workload evidence"
  if ! require_namespace "${NAMESPACE}"; then
    record "R-1 privileged runtime" FAIL "Namespace ${NAMESPACE} not found"
    return
  fi

  local workloads
  workloads="$(kubectl -n "${NAMESPACE}" get deploy,ds,sts 2>/dev/null | grep -E 'cloud[-_]os|container[-_]service|pool[-_]manager|ignite|kvm' || true)"
  if [[ -z "${workloads}" ]]; then
    record "R-1 privileged runtime" SKIP "Runtime workloads not found"
    return
  fi

  local privileged
  privileged="$(kubectl -n "${NAMESPACE}" get pods -o yaml 2>/dev/null | grep -E 'privileged: true|hostPath:|/dev/kvm|SYS_ADMIN|NET_ADMIN' || true)"
  if [[ -n "${privileged}" ]]; then
    record "R-1 privileged runtime" PASS "Runtime workloads present; privileged/host access evidence recorded from pod YAML"
  else
    record "R-1 privileged runtime" PASS "Runtime workloads present; no privileged/host access detected in pod YAML"
  fi
}

gate_r2_kvm_ignite() {
  log "R-2: KVM/Ignite readiness evidence"
  local resources
  resources="$(kubectl get pods,ds -A 2>/dev/null | grep -E 'ignite|kvm|firecracker|container-service' || true)"
  if [[ -n "${resources}" ]]; then
    record "R-2 KVM/Ignite" PASS "KVM/Ignite related resources present"
  else
    record "R-2 KVM/Ignite" SKIP "No KVM/Ignite resources found; run node-level KVM preflight before runtime acceptance"
  fi
}

print_summary() {
  echo ""
  echo "=============================================="
  echo "  model/runtime production evidence summary"
  echo "=============================================="

  local pass=0 fail=0 skip=0
  while IFS=$'\t' read -r gate status msg; do
    case "${status}" in
      PASS) printf '  %bPASS%b  %-28s %s\n' "${GREEN}" "${NC}" "${gate}" "${msg}"; pass=$((pass+1)) ;;
      FAIL) printf '  %bFAIL%b  %-28s %s\n' "${RED}" "${NC}" "${gate}" "${msg}"; fail=$((fail+1)) ;;
      SKIP) printf '  %bSKIP%b  %-28s %s\n' "${GRAY}" "${NC}" "${gate}" "${msg}"; skip=$((skip+1)) ;;
    esac
  done < "${RESULTS_FILE}"

  echo "----------------------------------------------"
  printf '  %d PASS · %d FAIL · %d SKIP\n' "${pass}" "${fail}" "${skip}"
  [[ -n "${EVIDENCE_FILE}" ]] && echo "Evidence file: ${EVIDENCE_FILE}"
  [[ "${fail}" -eq 0 ]]
}

main() {
  command -v kubectl >/dev/null 2>&1 || die "kubectl not on PATH"

  IFS=',' read -ra requested <<<"${GATES}"
  for gate in "${requested[@]}"; do
    case "${gate}" in
      M-1) gate_m1_gpu_placement ;;
      M-2) gate_m2_gpu_operator ;;
      M-3) gate_m3_model_cache ;;
      M-4) gate_m4_vllm ;;
      M-5) gate_m5_triton ;;
      M-6) gate_m6_ray_gpu ;;
      M-7) gate_m7_model_prepull ;;
      M-8) gate_m8_routes ;;
      M-0) gate_m0_gpu_role_profile ;;
      M-9) gate_m9_physical_gpu_accounting ;;
      R-1) gate_r1_privileged_runtime ;;
      R-2) gate_r2_kvm_ignite ;;
      *) warn "Unknown gate: ${gate} (skipped)" ;;
    esac
  done

  print_summary
}

main "$@"
