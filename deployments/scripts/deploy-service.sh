#!/bin/bash
# Compatibility wrapper used by GitHub Actions deployment workflows.
# Delegates service deploys to the maintained Helm deployment script.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_SCRIPT="${SCRIPT_DIR}/deploy.sh"

service="${1:-}"
environment="${2:-staging}"
action="${3:-deploy}"
version="${4:-${GITHUB_SHA:-latest}}"

usage() {
    echo "Usage: $0 <service> <staging|production> <deploy|rollback> [version]"
}

if [[ -z "$service" ]]; then
    usage
    exit 1
fi

case "$environment" in
    staging) namespace="isa-cloud-staging" ;;
    production) namespace="isa-cloud-production" ;;
    *) echo "Unknown environment: ${environment}"; usage; exit 1 ;;
esac

case "$action" in
    deploy) ;;
    rollback)
        exec "${DEPLOY_SCRIPT}" rollback "${service}-service" "${namespace}"
        ;;
    *) echo "Unknown action: ${action}"; usage; exit 1 ;;
esac

if [[ "$environment" == "production" && ( -z "$version" || "$version" == "latest" ) ]]; then
    echo "Production deploys require an immutable image tag or commit SHA; refusing version '${version}'."
    exit 1
fi

case "$service" in
    all)
        exec "${DEPLOY_SCRIPT}" all "${namespace}" "${version}"
        ;;
    gateway)
        echo "Gateway is managed by APISIX/Consul sync; deploy infrastructure instead."
        exit 0
        ;;
    mcp|model|agent|data)
        exec "${DEPLOY_SCRIPT}" "${service}" "${namespace}" "${version}"
        ;;
    user)
        exec "${DEPLOY_SCRIPT}" user all "${namespace}" "${version}"
        ;;
    blockchain)
        echo "Blockchain deploy is not wired in isA_Cloud/deployments/scripts/deploy.sh yet."
        exit 1
        ;;
    *)
        echo "Unknown service: ${service}"
        usage
        exit 1
        ;;
esac
