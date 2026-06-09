#!/usr/bin/env bash
set -euo pipefail

KUBECONFIG_ARG=()
if [[ -n "${KUBECONFIG:-}" ]]; then
  KUBECONFIG_ARG=(--kubeconfig "$KUBECONFIG")
fi
if [[ "${INSECURE_SKIP_TLS_VERIFY:-false}" == "true" ]]; then
  KUBECONFIG_ARG+=(--insecure-skip-tls-verify=true)
fi

NAMESPACES=("$@")
if [[ ${#NAMESPACES[@]} -eq 0 ]]; then
  NAMESPACES=(isa-cloud-production sn-cloud-production sn-bigdata dataphin)
fi

for namespace in "${NAMESPACES[@]}"; do
  kubectl "${KUBECONFIG_ARG[@]}" -n "$namespace" get pvc \
    -o jsonpath='{range .items[*]}{.spec.volumeName}{"\n"}{end}' |
    while IFS= read -r pv; do
      [[ -z "$pv" ]] && continue
      policy="$(kubectl "${KUBECONFIG_ARG[@]}" get pv "$pv" -o jsonpath='{.spec.persistentVolumeReclaimPolicy}')"
      if [[ "$policy" != "Retain" ]]; then
        kubectl "${KUBECONFIG_ARG[@]}" patch pv "$pv" \
          -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
      fi
    done
done
