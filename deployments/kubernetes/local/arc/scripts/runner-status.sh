#!/usr/bin/env bash
# =============================================================================
# runner-status.sh — at-a-glance health of the local ARC self-hosted runner
#                    pool. Read-only; safe to run any time.
#
# Sections, in dependency order:
#   1. Cluster + namespace reachability
#   2. ARC controller + listener pod health
#   3. AutoScalingRunnerSet (scaling bounds + current state)
#   4. Ephemeral runner pods (image / phase / age)
#   5. Listener queue depth + last scaling decision
#   6. Recent job assignments + completion (last 5)
#
# Exit code mirrors health:
#   0  everything reachable, no CrashLoopBackOff
#   1  cluster unreachable / required pods unhealthy / chart not installed
#
# Intended as the lightweight scriptable counterpart to a Grafana board.
# Tracks xenoISA/isA_Cloud#292.
# =============================================================================

set -uo pipefail

CTX="${ISA_ARC_KUBE_CONTEXT:-kind-isa-cloud-local}"
CONTROLLER_NS="${ISA_ARC_CONTROLLER_NAMESPACE:-arc-systems}"
RUNNER_NS="${ISA_ARC_RUNNER_NAMESPACE:-arc-runners}"

# --- colors ------------------------------------------------------------------
if [ -t 1 ]; then
    BOLD=$'\033[1m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
    RED=$'\033[0;31m'; BLUE=$'\033[0;34m'; DIM=$'\033[2m'; NC=$'\033[0m'
else
    BOLD=; GREEN=; YELLOW=; RED=; BLUE=; DIM=; NC=
fi
hdr()  { echo; echo "${BOLD}${BLUE}== $* ==${NC}"; }
ok()   { echo "  ${GREEN}✓${NC} $*"; }
warn() { echo "  ${YELLOW}⚠${NC} $*"; }
bad()  { echo "  ${RED}✗${NC} $*"; }

HEALTH=0

# --- 1. cluster reachability -------------------------------------------------
hdr "Cluster"
if ! kubectl --context "$CTX" cluster-info >/dev/null 2>&1; then
    bad "context '$CTX' not reachable"
    exit 1
fi
ok "context '$CTX' reachable"

if ! kubectl --context "$CTX" get ns "$CONTROLLER_NS" >/dev/null 2>&1; then
    bad "namespace '$CONTROLLER_NS' missing — ARC not installed"
    exit 1
fi
if ! kubectl --context "$CTX" get ns "$RUNNER_NS" >/dev/null 2>&1; then
    bad "namespace '$RUNNER_NS' missing — runner scale set not installed"
    exit 1
fi
ok "namespaces $CONTROLLER_NS, $RUNNER_NS present"

# --- 2. controller + listener -----------------------------------------------
hdr "Control plane"
CTRL=$(kubectl --context "$CTX" -n "$CONTROLLER_NS" get pods \
    -l app.kubernetes.io/name=gha-rs-controller \
    -o jsonpath='{range .items[*]}{.metadata.name}|{.status.phase}|{.status.containerStatuses[0].ready}|{.status.containerStatuses[0].restartCount}{"\n"}{end}' 2>/dev/null)
if [ -z "$CTRL" ]; then
    bad "ARC controller pod not found"
    HEALTH=1
else
    while IFS='|' read -r name phase ready restarts; do
        [ -z "$name" ] && continue
        if [ "$ready" = "true" ] && [ "$phase" = "Running" ]; then
            ok "controller $name — Running (restarts: $restarts)"
        else
            bad "controller $name — phase=$phase ready=$ready restarts=$restarts"
            HEALTH=1
        fi
    done <<< "$CTRL"
fi

LIS=$(kubectl --context "$CTX" -n "$CONTROLLER_NS" get pods \
    -l app.kubernetes.io/component=runner-scale-set-listener \
    -o jsonpath='{range .items[*]}{.metadata.name}|{.status.phase}|{.status.containerStatuses[0].ready}|{.status.containerStatuses[0].restartCount}{"\n"}{end}' 2>/dev/null)
if [ -z "$LIS" ]; then
    bad "scale-set listener not found — runners won't pick up jobs"
    HEALTH=1
else
    while IFS='|' read -r name phase ready restarts; do
        [ -z "$name" ] && continue
        if [ "$ready" = "true" ] && [ "$phase" = "Running" ]; then
            ok "listener $name — Running (restarts: $restarts)"
        else
            bad "listener $name — phase=$phase ready=$ready restarts=$restarts"
            HEALTH=1
        fi
    done <<< "$LIS"
fi

# --- 3. scale set bounds + current state ------------------------------------
hdr "Scale set"
ASRS=$(kubectl --context "$CTX" -n "$RUNNER_NS" get autoscalingrunnerset \
    -o jsonpath='{range .items[*]}{.metadata.name}|{.spec.minRunners}|{.spec.maxRunners}|{.status.currentRunners}|{.status.pendingEphemeralRunners}|{.status.runningEphemeralRunners}|{.status.failedEphemeralRunners}{"\n"}{end}' 2>/dev/null)
if [ -z "$ASRS" ]; then
    bad "no AutoScalingRunnerSet — runner scale set not deployed"
    exit 1
fi
while IFS='|' read -r name minR maxR cur pending running failed; do
    [ -z "$name" ] && continue
    printf "  %s scale set ${BOLD}%s${NC}\n" "$BLUE" "$name"
    printf "      bounds:   min=%s max=%s\n" "${minR:-0}" "${maxR:-?}"
    printf "      current:  %s\n" "${cur:-0}"
    printf "      pending:  %s   running: %s   failed: %s\n" \
        "${pending:-0}" "${running:-0}" "${failed:-0}"
    if [ -n "${failed:-}" ] && [ "${failed:-0}" -gt 0 ] 2>/dev/null; then
        warn "$failed ephemeral runners reported failed — inspect with: kubectl -n $RUNNER_NS get ephemeralrunner"
        HEALTH=1
    fi
done <<< "$ASRS"

# --- 4. runner pods ---------------------------------------------------------
hdr "Runner pods"
# Single-quote the jsonpath expression so the shell doesn't try to expand the
# `?(@.name=="runner")` filter; the kubectl custom-columns parser handles its
# own quoting once the whole flag value reaches it intact.
PODS=$(kubectl --context "$CTX" -n "$RUNNER_NS" get pods \
    -l app.kubernetes.io/component=runner \
    -o 'custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[*].ready,PHASE:.status.phase,IMAGE:.spec.containers[?(@.name=="runner")].image,RESTARTS:.status.containerStatuses[*].restartCount,AGE:.metadata.creationTimestamp' \
    --no-headers 2>/dev/null)
if [ -z "$PODS" ]; then
    echo "  (no active runner pods — pool scaled to 0)"
else
    printf "  %-32s %-6s %-12s %-30s %-8s %s\n" "NAME" "READY" "PHASE" "IMAGE" "RESTARTS" "AGE"
    while read -r line; do
        [ -z "$line" ] && continue
        echo "  $line"
    done <<< "$PODS"
fi

# --- 5. queue depth from listener log --------------------------------------
hdr "Queue (from listener)"
TAIL=$(kubectl --context "$CTX" -n "$CONTROLLER_NS" logs \
    -l app.kubernetes.io/component=runner-scale-set-listener \
    --tail=100 2>/dev/null | grep "Calculated target runner count" | tail -1)
if [ -z "$TAIL" ]; then
    warn "no scaling decisions in last 100 listener log lines — pool may be idle"
else
    # extract assigned/decision/min/max/current
    ASSIGNED=$(echo "$TAIL" | grep -oE '"assigned job"=[0-9]+' | grep -oE '[0-9]+')
    DECISION=$(echo "$TAIL" | grep -oE 'decision=[0-9]+' | cut -d= -f2)
    PMIN=$(echo "$TAIL" | grep -oE 'min=[0-9]+' | cut -d= -f2)
    PMAX=$(echo "$TAIL" | grep -oE 'max=[0-9]+' | cut -d= -f2)
    PCUR=$(echo "$TAIL" | grep -oE 'currentRunnerCount=[0-9]+' | cut -d= -f2)
    printf "  jobs assigned to scale set: %s\n" "${ASSIGNED:-?}"
    printf "  scaler decision:            %s   (bounds: %s..%s, current: %s)\n" \
        "${DECISION:-?}" "${PMIN:-?}" "${PMAX:-?}" "${PCUR:-?}"
    if [ -n "$ASSIGNED" ] && [ -n "$PMAX" ] && [ "$ASSIGNED" -gt "$PMAX" ] 2>/dev/null; then
        warn "queue depth ($ASSIGNED) exceeds maxRunners ($PMAX) — jobs will wait"
    fi
fi

# --- 6. recent ephemeral runner activity ------------------------------------
hdr "Recent job activity (latest 5 ephemeral runners)"
ER=$(kubectl --context "$CTX" -n "$RUNNER_NS" get ephemeralrunner \
    --sort-by=.metadata.creationTimestamp \
    -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,REPO:.status.jobRepositoryName,JOB:.status.jobDisplayName \
    --no-headers 2>/dev/null | tail -5)
if [ -z "$ER" ]; then
    echo "  (no EphemeralRunner CRs found)"
else
    printf "  %-38s %-10s %-22s %s\n" "NAME" "STATUS" "REPO" "JOB"
    while read -r line; do
        [ -z "$line" ] && continue
        echo "  $line"
    done <<< "$ER"
fi

echo
if [ "$HEALTH" -eq 0 ]; then
    echo "${GREEN}${BOLD}OK${NC} — ARC runner pool healthy."
else
    echo "${YELLOW}${BOLD}DEGRADED${NC} — see ${RED}✗${NC}/${YELLOW}⚠${NC} markers above."
fi
exit "$HEALTH"
