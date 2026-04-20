# DEPRECATED — `deployments/kubernetes/local/scripts/`

These scripts are **deprecated** in favour of the canonical bootstrap path
in [`/.claude/skills/cluster_operations/`](../../../../.claude/skills/cluster_operations/).

## Use these instead

| Old script | Replacement |
|---|---|
| `kind-setup.sh` + `kind-deploy.sh` | `.claude/skills/cluster_operations/scripts/setup-local.sh` |
| `kind-teardown.sh` | `.claude/skills/cluster_operations/scripts/setup-local.sh --rebuild` (or `kind delete cluster --name isa-cloud-local`) |
| `kind-build-load.sh` | Still used for loading custom service images; not replaced |
| `check-services.sh` | `.claude/skills/cluster_operations/` health checks (or `kubectl get pods -n isa-cloud-local`) |
| `deploy.sh` | Generic env-aware deploy; superseded by the per-env scripts in `cluster_operations` |

## Why

The old `kind-deploy.sh` path used kustomize overlays from
`_legacy/base/infrastructure/` and assumed services were applied as raw
manifests. The actual cluster — and the documented operator workflow — uses
**Helm** for every infra service plus a small set of standalone manifests
(`local/manifests/falkordb.yaml`, `staging/manifests/etcd.yaml`, etc.).

The canonical `setup-local.sh`:

- Uses Helm (`bitnami/postgresql`, `minio/minio`, `neo4j/neo4j`,
  `qdrant/qdrant`, `nats/nats`, `hashicorp/consul`, `apisix/apisix`)
  with chart-correct values
- Includes **FalkorDB** (xenoISA/isA_MCP epic #525) which the legacy path
  doesn't know about
- Honours per-env values in `local/values/` with fallback to `staging/values/`
- Emits the host-port summary at the end so operators know exactly which
  ports map to which service

## Migration checklist

If you currently run `kind-deploy.sh` regularly:

1. `kind delete cluster --name isa-cloud-local`
2. `bash .claude/skills/cluster_operations/scripts/setup-local.sh --rebuild`
3. Restore data via `.claude/skills/backup_restore/scripts/restore-all.sh local <backup-dir>`

## When the old scripts will be removed

These files are kept for reference until the next isA_Cloud minor version
bump. After that, only the `cluster_operations` skill is supported.

Story: xenoISA/isA_MCP#525.
