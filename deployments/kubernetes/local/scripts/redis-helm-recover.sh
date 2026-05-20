#!/usr/bin/env bash
# Recover a stuck local redis Helm release (#211).
#
# When values/redis.yaml changes an immutable StatefulSet field (e.g.
# architecture replication->standalone), `helm upgrade` fails with a
# "Forbidden: updates to statefulset spec ... are forbidden" error and the
# live release stays pinned to the old revision.
#
# This script does the only safe local fix: uninstall, drop the redis PVCs,
# and reinstall fresh from the current values file.
#
# DESTRUCTIVE — wipes local Redis data. Local/dev clusters only.
set -euo pipefail

NAMESPACE="${NAMESPACE:-isa-cloud-local}"
RELEASE="${RELEASE:-redis}"
VALUES="${VALUES:-deployments/kubernetes/local/values/redis.yaml}"
CHART="${CHART:-bitnami/redis}"

echo "==> redis Helm recovery — namespace=$NAMESPACE release=$RELEASE"

# Refuse to run against anything that doesn't look like a local kind cluster.
CURRENT_CTX="$(kubectl config current-context 2>/dev/null || echo '')"
case "$CURRENT_CTX" in
  kind-*|*local*) ;;
  *)
    echo "ERROR: current context '$CURRENT_CTX' is not a kind/local cluster."
    echo "       This script is destructive — aborting for safety."
    exit 1
    ;;
esac

echo "==> Current Helm history:"
helm history "$RELEASE" -n "$NAMESPACE" 2>/dev/null || echo "  (no release found)"

echo "==> Uninstalling release..."
helm uninstall "$RELEASE" -n "$NAMESPACE" 2>/dev/null || echo "  (already uninstalled)"

echo "==> Deleting redis PVCs (data wipe)..."
kubectl delete pvc -n "$NAMESPACE" \
  -l "app.kubernetes.io/instance=$RELEASE" --ignore-not-found

echo "==> Reinstalling from $VALUES ..."
helm install "$RELEASE" "$CHART" -n "$NAMESPACE" -f "$VALUES"

echo "==> Waiting for redis-master to become Ready..."
kubectl rollout status statefulset/redis-master -n "$NAMESPACE" --timeout=180s

echo "==> Done. Verify:"
echo "    kubectl -n $NAMESPACE get pods -l app.kubernetes.io/instance=$RELEASE"
echo "    helm get values $RELEASE -n $NAMESPACE"
