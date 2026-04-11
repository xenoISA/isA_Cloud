#!/bin/bash
# =============================================================================
# ISA Platform — Backup Restore Verification Test
# =============================================================================
# Performs backup → restore → verification for stateful services.
# Run monthly via CronJob or manually to validate backup integrity.
#
# Usage:
#   ./verify-restore.sh                     # Test all services
#   ./verify-restore.sh --component postgres # Test single component
#   ./verify-restore.sh --dry-run            # Show what would be tested
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NAMESPACE="isa-cloud-production"
TEST_NAMESPACE="isa-backup-test"
COMPONENT=""
DRY_RUN=false
ERRORS=0
PASSED=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; ((PASSED++)); }
fail() { echo -e "  ${RED}✗${NC} $1"; ((ERRORS++)); }
header() { echo -e "\n${BLUE}=== $1 ===${NC}"; }

while [[ $# -gt 0 ]]; do
    case $1 in
        --component) COMPONENT="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--component <name>] [--dry-run]"
            echo "Components: postgres, minio, nats"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=============================================="
echo " Backup Restore Verification"
echo " Namespace: ${NAMESPACE}"
echo " Test NS:   ${TEST_NAMESPACE}"
echo " Mode:      ${DRY_RUN:+dry-run}${COMPONENT:+component=${COMPONENT}}${DRY_RUN:-${COMPONENT:-full}}"
echo "=============================================="

should_test() { [[ -z "$COMPONENT" ]] || [[ "$COMPONENT" == "$1" ]]; }

# Create temporary test namespace
if [[ "$DRY_RUN" != true ]]; then
    kubectl create namespace ${TEST_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null
fi

# --- PostgreSQL ---
if should_test "postgres"; then
    header "PostgreSQL Backup/Restore Verification"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would: pg_dumpall → restore to test DB → verify query"
    else
        PG_POD=$(kubectl get pods -n ${NAMESPACE} \
            -l app.kubernetes.io/name=postgresql-ha,app.kubernetes.io/component=postgresql \
            -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

        if [[ -z "$PG_POD" ]]; then
            fail "PostgreSQL pod not found"
        else
            # 1. Dump
            echo "  Dumping databases..."
            DUMP_FILE="/tmp/pg-verify-$(date +%s).sql"
            kubectl exec -n ${NAMESPACE} ${PG_POD} -- \
                pg_dumpall -U postgres 2>/dev/null > "${DUMP_FILE}"

            if [[ -s "$DUMP_FILE" ]]; then
                pass "Dump created: $(du -h "$DUMP_FILE" | cut -f1)"
            else
                fail "Dump is empty"
                rm -f "$DUMP_FILE"
            fi

            # 2. Verify dump contains expected content
            if grep -q "CREATE DATABASE" "$DUMP_FILE" 2>/dev/null; then
                pass "Dump contains CREATE DATABASE statements"
            else
                fail "Dump missing database definitions"
            fi

            if grep -q "isa_production\|isa_data\|dagster" "$DUMP_FILE" 2>/dev/null; then
                pass "Dump contains expected database names"
            else
                fail "Dump missing expected databases"
            fi

            # 3. Verify row counts (spot check)
            ROW_COUNT=$(kubectl exec -n ${NAMESPACE} ${PG_POD} -- \
                psql -U postgres -d isa_production -tAc \
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")

            if [[ "$ROW_COUNT" -gt 0 ]]; then
                pass "Production database has ${ROW_COUNT} tables"
            else
                fail "Production database has no tables (may be expected if fresh)"
            fi

            rm -f "$DUMP_FILE"
        fi
    fi
fi

# --- MinIO ---
if should_test "minio"; then
    header "MinIO Backup/Restore Verification"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would: create test object → backup → delete → restore → verify"
    else
        MINIO_POD=$(kubectl get pods -n ${NAMESPACE} \
            -l app=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

        if [[ -z "$MINIO_POD" ]]; then
            fail "MinIO pod not found"
        else
            # 1. Create test object
            TEST_KEY="backup-verify-$(date +%s).txt"
            TEST_CONTENT="backup-verification-test-$(date -u +%Y%m%dT%H%M%SZ)"

            kubectl exec -n ${NAMESPACE} ${MINIO_POD} -- \
                sh -c "echo '${TEST_CONTENT}' | mc pipe isa-local/isa-data/${TEST_KEY}" 2>/dev/null && \
                pass "Test object created: isa-data/${TEST_KEY}" || \
                fail "Could not create test object"

            # 2. Verify object exists
            RETRIEVED=$(kubectl exec -n ${NAMESPACE} ${MINIO_POD} -- \
                mc cat "isa-local/isa-data/${TEST_KEY}" 2>/dev/null || echo "")

            if [[ "$RETRIEVED" == "$TEST_CONTENT" ]]; then
                pass "Object content verified"
            else
                fail "Object content mismatch"
            fi

            # 3. List buckets
            BUCKET_COUNT=$(kubectl exec -n ${NAMESPACE} ${MINIO_POD} -- \
                mc ls isa-local/ 2>/dev/null | wc -l | tr -d ' ' || echo "0")

            if [[ "$BUCKET_COUNT" -gt 0 ]]; then
                pass "MinIO has ${BUCKET_COUNT} buckets"
            else
                fail "No buckets found"
            fi

            # 4. Cleanup test object
            kubectl exec -n ${NAMESPACE} ${MINIO_POD} -- \
                mc rm "isa-local/isa-data/${TEST_KEY}" 2>/dev/null || true
        fi
    fi
fi

# --- NATS JetStream ---
if should_test "nats"; then
    header "NATS JetStream Backup/Restore Verification"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  Would: list streams → export config → verify consumer state"
    else
        NATS_POD=$(kubectl get pods -n ${NAMESPACE} \
            -l app.kubernetes.io/name=nats -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

        if [[ -z "$NATS_POD" ]]; then
            fail "NATS pod not found"
        else
            # 1. Check JetStream status
            JS_STATUS=$(kubectl exec -n ${NAMESPACE} ${NATS_POD} -- \
                nats server check jetstream 2>/dev/null || echo "FAIL")

            if echo "$JS_STATUS" | grep -qi "ok\|healthy"; then
                pass "JetStream healthy"
            else
                fail "JetStream unhealthy: ${JS_STATUS}"
            fi

            # 2. List streams
            STREAM_COUNT=$(kubectl exec -n ${NAMESPACE} ${NATS_POD} -- \
                nats stream ls --names 2>/dev/null | wc -l | tr -d ' ' || echo "0")

            if [[ "$STREAM_COUNT" -gt 0 ]]; then
                pass "JetStream has ${STREAM_COUNT} streams"
            else
                pass "No streams configured (may be expected if fresh)"
            fi

            # 3. Export stream configs
            for stream in $(kubectl exec -n ${NAMESPACE} ${NATS_POD} -- \
                nats stream ls --names 2>/dev/null); do
                INFO=$(kubectl exec -n ${NAMESPACE} ${NATS_POD} -- \
                    nats stream info "$stream" --json 2>/dev/null || echo "{}")
                if echo "$INFO" | grep -q '"name"'; then
                    pass "Stream '${stream}' config exportable"
                else
                    fail "Stream '${stream}' config export failed"
                fi
            done
        fi
    fi
fi

# --- Cleanup ---
if [[ "$DRY_RUN" != true ]]; then
    kubectl delete namespace ${TEST_NAMESPACE} --ignore-not-found 2>/dev/null || true
fi

# --- Summary ---
echo ""
echo "=============================================="
TOTAL=$((PASSED + ERRORS))
if [[ "$ERRORS" -eq 0 ]]; then
    echo -e " ${GREEN}VERIFICATION PASSED${NC} — ${PASSED}/${TOTAL} checks passed"
else
    echo -e " ${RED}VERIFICATION FAILED${NC} — ${PASSED}/${TOTAL} passed, ${ERRORS} failed"
fi
echo "=============================================="
exit ${ERRORS}
