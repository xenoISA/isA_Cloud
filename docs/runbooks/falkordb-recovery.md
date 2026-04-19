# Runbook: FalkorDB Recovery

FalkorDB is the graph database (Redis module) that powers the MCP hierarchical
resource discovery backend (epic xenoISA/isA_MCP#525). Unlike pure Redis, the
data here is the source-of-truth read projection of MCP tools/prompts/resources
joined to skills.

## Symptoms

- Application errors from `isa_common.AsyncFalkorClient`: `ConnectionError`,
  `Authentication required`, or `module falkordb not loaded`
- isA_MCP `HierarchicalSearchService` returns empty results or falls back to
  the legacy Qdrant + Postgres path (look for `mcp_search_backend_used{backend="qdrant"}`
  metric spike in Grafana)
- Slow query latency on graph hot path (`discovery.tool_traverse` span p95 > 200ms)

## Quick Health Check

```bash
NS=isa-cloud-staging  # or isa-cloud-production

# Pod status
kubectl get pods -n $NS -l app=falkordb

# Module loaded?
PASS=$(kubectl get secret falkordb-secret -n $NS -o jsonpath='{.data.falkordb-password}' | base64 -d)
kubectl exec -n $NS svc/falkordb-master -- redis-cli -a "$PASS" MODULE LIST

# Graph(s) present?
kubectl exec -n $NS svc/falkordb-master -- redis-cli -a "$PASS" GRAPH.LIST

# Memory + persistence
kubectl exec -n $NS svc/falkordb-master -- redis-cli -a "$PASS" INFO memory | grep -E "used_memory_human|maxmemory_human"
kubectl exec -n $NS svc/falkordb-master -- redis-cli -a "$PASS" INFO persistence | grep -E "rdb_last_save_time|aof_enabled"

# Sample query against the discovery graph
kubectl exec -n $NS svc/falkordb-master -- redis-cli -a "$PASS" \
  GRAPH.QUERY mcp_discovery "MATCH (s:Skill) RETURN count(s) AS n"
```

## Common Failure Modes

### 1. Module not loaded

**Symptom**: `MODULE LIST` returns empty; `GRAPH.QUERY` returns
`(error) ERR unknown command 'GRAPH.QUERY'`.

**Cause**: Pod restarted but `--loadmodule` flag missing, or Bitnami chart
upgrade dropped the `master.extraFlags` block.

**Resolution**:
```bash
# Verify values file still has the loadmodule extraFlags
helm get values falkordb -n $NS | grep -A 3 extraFlags

# Re-apply with the values file
helm upgrade falkordb bitnami/redis -n $NS \
  -f deployments/kubernetes/staging/values/falkordb.yaml \
  --wait
```

### 2. Pod crash / OOMKilled

**Symptom**: Pod in `CrashLoopBackOff`; events show `OOMKilled`.

**Cause**: Graph grew past `maxmemory`; common when bulk migration runs without
the noeviction policy being respected by the workload.

**Resolution**:
1. Bump memory in the values file under `master.resources.limits.memory` and
   `master.configuration.maxmemory`, then `helm upgrade`.
2. If the workload should not have grown that much, check for runaway writes:
   ```bash
   kubectl exec -n $NS svc/falkordb-master -- redis-cli -a "$PASS" \
     GRAPH.QUERY mcp_discovery "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS c"
   ```

### 3. PVC corruption / data loss

**Symptom**: Pod restarts but `GRAPH.LIST` is empty; RDB file present but won't
load (`Bad file format` in logs).

**Resolution — restore from MinIO backup**:

```bash
# 1. List available backups
aws --endpoint-url http://minio.$NS.svc.cluster.local:9000 \
  s3 ls s3://falkordb-backups/

# 2. Pick the latest good one and copy locally
aws --endpoint-url http://minio.$NS.svc.cluster.local:9000 \
  s3 cp s3://falkordb-backups/falkordb-20260419-031500.rdb /tmp/restore.rdb

# 3. Scale FalkorDB master to 0 (master statefulset has only one replica)
kubectl scale statefulset falkordb-master -n $NS --replicas=0

# 4. Get the PVC name
PVC=$(kubectl get pvc -n $NS -l app.kubernetes.io/name=redis,app.kubernetes.io/component=master -o jsonpath='{.items[0].metadata.name}')

# 5. Mount the PVC in a temporary pod and copy the RDB into place
kubectl run -n $NS rdb-restore --rm -it --restart=Never \
  --image=busybox \
  --overrides='{"spec":{"containers":[{"name":"rdb-restore","image":"busybox","stdin":true,"tty":true,"volumeMounts":[{"name":"data","mountPath":"/data"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"'$PVC'"}}]}}' \
  -- sh

# Inside the pod:
#   cp /tmp/restore.rdb /data/dump.rdb
#   chown 1001:1001 /data/dump.rdb
#   exit

# 6. Scale master back up
kubectl scale statefulset falkordb-master -n $NS --replicas=1

# 7. Verify
kubectl exec -n $NS svc/falkordb-master -- redis-cli -a "$PASS" GRAPH.LIST
```

### 4. Auth failures

**Symptom**: `Authentication required` from clients; `WRONGPASS` in logs.

**Cause**: `falkordb-secret` rotated but pods not restarted, or client config
points at the wrong secret.

**Resolution**:
```bash
# Roll the master to pick up the new secret
kubectl rollout restart statefulset/falkordb-master -n $NS

# Verify the consumers (mcp-service) have the matching env var
kubectl get pod -n $NS -l app=mcp-service -o jsonpath='{.items[0].spec.containers[0].env}' | jq '.[] | select(.name=="FALKOR_PASSWORD")'
```

## Recovery from Empty Graph (No Backup)

If the graph is gone and there's no backup, rebuild from PostgreSQL — it stays
the source of truth.

```bash
# Trigger the migration job from xenoISA/isA_MCP (story #528)
kubectl -n $NS create job --from=cronjob/mcp-falkor-migration mcp-falkor-rebuild-$(date +%s)
kubectl -n $NS logs -f job/mcp-falkor-rebuild-<timestamp>
```

While the rebuild runs, the MCP service should auto-fall-back to the Qdrant
path (story #529 circuit breaker); confirm by checking
`mcp_search_backend_used{backend="qdrant"}` in Grafana.

## Cutover Back to Qdrant Fallback

If FalkorDB is impaired and we want to flip MCP off it temporarily:

```bash
kubectl -n $NS set env deployment/mcp-service MCP_SEARCH_BACKEND=qdrant
kubectl rollout status deployment/mcp-service -n $NS
```

When restored, flip back to `falkor` (or `dual` to verify diffs first).

## Escalation

- On-call rotation: `#mcp-platform`
- Owner: ISA MCP Team
- Related: `docs/runbooks/redis-recovery.md` (FalkorDB shares Bitnami Redis chart mechanics)
