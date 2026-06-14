#!/bin/bash
# Verify public service health endpoints for staging/production workflows.

set -euo pipefail

environment="${1:-}"
service="${2:-all}"
expected_ref="${3:-}"

usage() {
    echo "Usage: $0 <staging|production> <service|all> [expected-ref]"
}

if [[ -z "$environment" ]]; then
    usage
    exit 1
fi

case "$environment" in
    staging)
        base_url="${STAGING_HEALTH_BASE_URL:-}"
        ;;
    production)
        base_url="${PRODUCTION_HEALTH_BASE_URL:-}"
        ;;
    *)
        echo "Unknown environment: ${environment}"
        usage
        exit 1
        ;;
esac

if [[ -z "$base_url" ]]; then
    echo "Missing ${environment} health base URL."
    echo "Set STAGING_HEALTH_BASE_URL or PRODUCTION_HEALTH_BASE_URL in workflow secrets/variables."
    exit 1
fi

base_url="${base_url%/}"

case "$service" in
    all)
        services="gateway mcp model agent user"
        ;;
    gateway|mcp|model|agent|user|data|blockchain)
        services="$service"
        ;;
    *)
        echo "Unknown service for health check: ${service}"
        usage
        exit 1
        ;;
esac

for svc in $services; do
    if [[ "$svc" == "gateway" ]]; then
        url="${base_url}/health"
    else
        url="${base_url}/${svc}/health"
    fi

    echo "Checking ${svc}: ${url}"
    body="$(curl -fsS --retry 3 --retry-delay 2 --max-time 20 "$url")"
    echo "$body" | python3 - "$svc" "$expected_ref" <<'PY'
import json
import sys

service = sys.argv[1]
expected_ref = sys.argv[2]
raw = sys.stdin.read()

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    if raw.strip():
        print(f"{service}: non-JSON health response accepted")
        sys.exit(0)
    print(f"{service}: empty health response", file=sys.stderr)
    sys.exit(1)

status = str(data.get("status") or data.get("health") or data.get("state") or "").lower()
if status and status not in {"ok", "healthy", "ready", "up"}:
    print(f"{service}: unhealthy status {status!r}", file=sys.stderr)
    sys.exit(1)

if expected_ref:
    version = str(data.get("version") or data.get("sha") or data.get("commit") or "")
    if version and expected_ref not in version and version not in expected_ref:
        print(
            f"{service}: deployed version {version!r} does not match expected ref {expected_ref!r}",
            file=sys.stderr,
        )
        sys.exit(1)

print(f"{service}: healthy")
PY
done
