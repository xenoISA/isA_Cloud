# Runbook — Vault Transit Auto-Unseal (SN production)

> Durable fix for #426: `vault-0` re-seals on every restart (manual Shamir), which
> silently broke ESO sync for ~2 days. This migrates the main Vault from Shamir to
> **transit auto-unseal** backed by a dedicated on-prem **unseal Vault** — no cloud
> dependency (SN is on-prem / data-sovereign).
>
> Context: `KUBECONFIG=~/.kube/sn-rancher.yaml`, namespace `sn-cloud-production`.
>
> ⚠️ **This migrates the seal of a production secrets store. A botched
> `operator unseal -migrate` can leave Vault unable to unseal → every secret
> inaccessible.** Do it in a maintenance window, with the current Shamir unseal
> keys + root token on hand, and follow the rollback section if anything diverges.

## ✅ Status: DONE — migrated & verified 2026-06-13

Live in `sn-cloud-production`: `vault-0` is transit-sealed and auto-unseals on
restart (verified: pod delete → self-unseal, 0 manual steps); the dedicated
`vault-unseal` is auto-unsealed by a `vault-unseal-unsealer` Deployment
(verified: pod delete → auto-recovered); all 7 ExternalSecrets `SecretSynced`.
Helm releases (`vault` rev 8, `vault-unseal` rev 2) store the final config.

## ⚠️⚠️ CRITICAL GOTCHA — bind listeners to `0.0.0.0`, NOT `[::]`

**This caused hours of CrashLoopBackOff during the migration.** The SN nodes run
with IPv6 `bindv6only`, so a listener on `[::]:8200` (IPv6 wildcard) **refuses
all IPv4 connections** to the pod IP. Pod IPs here are IPv4 (`10.42.x.x`), so
that single misconfig broke everything:

- **vault-unseal** on `[::]` → the **transit seal was unreachable cross-node**
  (vault-0 on k8s-02 → vault-unseal on k8s-01 = `connection refused`), so
  `vault-0` couldn't auto-unseal at boot and **crash-looped** (Vault hard-exits
  if its seal backend is unreachable at startup). Same-node traffic happened to
  work, which made it look intermittent.
- **vault-0** on `[::]` → the **kubelet liveness/readiness probes** (which hit
  the IPv4 pod IP) got `connection refused`; with `failureThreshold: 2` the
  probe killed a fully-unsealed, healthy Vault ~74s after every boot.

**Fix:** set the listener `address`/`cluster_address` to `0.0.0.0:8200`/`:8201`
on **both** Vaults. This is baked into the values below. If you ever see Vault
crash-looping with `connection refused` to its own pod IP or to the unseal Vault,
check the listener bind first.

> A second gotcha: the `vault-unseal-unsealer` needs **≥256Mi memory** — at 64Mi
> the `vault` CLI it shells out to gets OOM-killed (`Killed` in its log) and never
> completes the unseal.

## Current state (verified 2026-06-12)

| Fact | Value |
|------|-------|
| Chart / image | HashiCorp Vault Helm, `core.harbor.domain/hashicorp/vault:1.21.2` |
| Topology | `ha.enabled=true`, `replicas: 1` (single `vault-0`), `raft.enabled=false` |
| Storage | **Consul** (`consul-server.sn-cloud-production:8500`, path `vault/`) |
| Seal | **Shamir** (no `seal` stanza) → manual unseal on every restart |
| TLS | enabled (`vault-server-tls` secret, CA at `/vault/userconfig/vault-server-tls/ca.crt`) |
| Readiness probe | `…&sealedcode=204…` → **sealed reads as "ready"** (why the outage was silent) |

## Architecture

```
┌─────────────────────┐   transit unseal (encrypt/decrypt master key)   ┌──────────────────┐
│  vault-unseal        │ <─────────────────────────────────────────────  │  vault-0 (main)  │
│  (new, dedicated)    │                                                  │  seal "transit"  │
│  - Shamir (1 small   │   token w/ policy: transit/{en,de}crypt/keys/    │  storage: consul │
│    key set, stable)  │   autounseal                                     │  holds all secrets│
│  - transit: key      │                                                  │  + the 6 ESO     │
│    "autounseal"      │                                                  │  ExternalSecrets │
└─────────────────────┘                                                  └──────────────────┘
```

The main Vault (which restarts on node drains/upgrades and gates ESO) becomes
**hands-off**. The only remaining manual-unseal surface is the small, rarely
restarted `vault-unseal`. That is the accepted trade-off of on-prem transit
(no cloud KMS / HSM to break the chicken-and-egg entirely).

## Prerequisites

- VPN up; `KUBECONFIG=~/.kube/sn-rancher.yaml` reaches the cluster.
- The **current main-vault Shamir unseal keys (3) + root token** (from
  `vault-init-keys.json`) — needed for the `-migrate` step.
- A maintenance window: `vault-0` restarts twice (seal-stanza apply, and again to
  verify auto-unseal); ESO is degraded only between the restart and the migrate.
- `helm` and a `vault` CLI (or `kubectl exec` into a vault pod) available.

## Step 1 — Deploy the dedicated unseal Vault

Reuse the same chart/image; minimal, isolated release `vault-unseal`. Save as
`values/vault-unseal.yaml`:

```yaml
global: { enabled: true, tlsDisable: false, imagePullSecrets: [{ name: harbor-isa }] }
injector: { enabled: false }
server:
  image: { repository: core.harbor.domain/hashicorp/vault, tag: 1.21.2 }
  imagePullSecrets: [{ name: harbor-isa }]
  dataStorage: { enabled: true, size: 2Gi, storageClass: local-replica2-delay-bind }  # its own raft; tiny
  extraEnvironmentVars:
    VAULT_ADDR: https://127.0.0.1:8200
    VAULT_CACERT: /vault/userconfig/vault-server-tls/ca.crt
  extraVolumes: [{ name: vault-server-tls, type: secret }]
  standalone:
    enabled: true            # single-node raft is fine for an unseal vault
    config: |
      ui = false
      listener "tcp" {
        address = "0.0.0.0:8200"        # IPv4 — NOT [::] (see Critical Gotcha)
        cluster_address = "0.0.0.0:8201"
        tls_cert_file = "/vault/userconfig/vault-server-tls/tls.crt"
        tls_key_file  = "/vault/userconfig/vault-server-tls/tls.key"
      }
      storage "raft" { path = "/vault/data" }
  ha: { enabled: false }
ui: { enabled: false }
```

```sh
helm upgrade --install vault-unseal hashicorp/vault \
  -n sn-cloud-production -f values/vault-unseal.yaml
```

> Reuse the existing `vault-server-tls` secret (SANs must already cover the
> service name `vault-unseal`; if not, reissue the cert with the added SAN first).

## Step 2 — Initialize + unseal the unseal Vault

```sh
kubectl -n sn-cloud-production exec -it vault-unseal-0 -- \
  vault operator init -key-shares=1 -key-threshold=1 -format=json > vault-unseal-init.json
# UNSEAL key + root token are in that file — NEW custody item (see Security hygiene).
UNSEAL=$(jq -r '.unseal_keys_b64[0]' vault-unseal-init.json)
kubectl -n sn-cloud-production exec vault-unseal-0 -- vault operator unseal "$UNSEAL"
```

## Step 3 — Transit engine, key, policy, token (on the unseal Vault)

```sh
ROOT=$(jq -r '.root_token' vault-unseal-init.json)
X(){ kubectl -n sn-cloud-production exec vault-unseal-0 -- env VAULT_TOKEN="$ROOT" vault "$@"; }
X secrets enable transit
X write -f transit/keys/autounseal
# least-privilege policy
kubectl -n sn-cloud-production exec -i vault-unseal-0 -- env VAULT_TOKEN="$ROOT" \
  vault policy write autounseal - <<'POLICY'
path "transit/encrypt/autounseal" { capabilities = ["update"] }
path "transit/decrypt/autounseal" { capabilities = ["update"] }
path "transit/keys/autounseal"    { capabilities = ["read"] }
POLICY
# periodic, renewable token for the main vault
AUTOUNSEAL_TOKEN=$(X token create -policy=autounseal -period=24h -orphan -field=token)
```

## Step 4 — Hand the token to the main Vault

```sh
kubectl -n sn-cloud-production create secret generic vault-transit-token \
  --from-literal=token="$AUTOUNSEAL_TOKEN"
```

## Step 5 — Add the `seal "transit"` stanza to the main Vault

Edit the main Vault helm values (`server.ha.config` HCL) and `server.extraEnvironmentVars`.
**Add** (do not remove storage/listener):

```hcl
# NOTE: point at the POD's headless DNS (publishNotReadyAddresses=true), NOT the
# ready-gated `vault-unseal` ClusterIP service — the service won't route to a
# sealed (=not-ready) unseal Vault, deadlocking auto-unseal.
seal "transit" {
  address            = "https://vault-unseal-0.vault-unseal-internal.sn-cloud-production.svc.cluster.local:8200"
  disable_renewal    = "false"
  key_name           = "autounseal"
  mount_path         = "transit/"
  tls_skip_verify    = "true"   # cert lacks a vault-unseal SAN; in-cluster hop
  # token comes from VAULT_TOKEN env (Step 4 secret), NOT inlined here
}
```

```yaml
# server.extraEnvironmentVars: add
  VAULT_TOKEN:
    valueFrom: { secretKeyRef: { name: vault-transit-token, key: token } }
```
*(The chart renders `extraEnvironmentVars` as plain env; if it can't take a
`valueFrom`, use `server.extraSecretEnvironmentVars` instead to inject
`VAULT_TOKEN` from `vault-transit-token`.)*

While here, fix the silent-seal probe so a future seal is visible:
`server.readinessProbe.path` → drop `sealedcode=204` (let sealed read as not-ready).

## Step 6 — Apply + migrate Shamir → transit

```sh
helm upgrade vault hashicorp/vault -n sn-cloud-production -f values/vault.yaml
# vault-0 restarts and comes up SEALED (still Shamir until migrated).
# Migrate with the 3 CURRENT Shamir keys:
kubectl -n sn-cloud-production exec -it vault-0 -- vault operator unseal -migrate <key1>
kubectl -n sn-cloud-production exec -it vault-0 -- vault operator unseal -migrate <key2>
kubectl -n sn-cloud-production exec -it vault-0 -- vault operator unseal -migrate <key3>
# After the threshold, Vault rewraps the master key via transit and unseals.
kubectl -n sn-cloud-production exec vault-0 -- vault status   # Sealed=false, Seal Type=transit
```

> After migration the 3 Shamir keys become **recovery keys** (for
> `operator generate-root` / rekey), no longer day-to-day unseal keys.

## Step 7 — Verify auto-unseal

```sh
kubectl -n sn-cloud-production delete pod vault-0
kubectl -n sn-cloud-production exec vault-0 -- vault status   # expect Sealed=false WITHOUT manual unseal
kubectl -n sn-cloud-production get externalsecret             # all 6 stay SecretSynced/Ready=True
```

## Step 8 — Seal-status alert (so a future seal pages, never silent)

Enable Vault telemetry (one more `helm upgrade` → restart, now safe because it
auto-unseals). Add to the main listener + top level:

```hcl
listener "tcp" { telemetry { unauthenticated_metrics_access = true } }   # within the existing listener
telemetry { prometheus_retention_time = "24h" disable_hostname = true }
```

ServiceMonitor + PrometheusRule (`cattle-monitoring-system`):

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata: { name: vault, namespace: sn-cloud-production, labels: { release: rancher-monitoring } }
spec:
  selector: { matchLabels: { app.kubernetes.io/name: vault } }
  endpoints:
    - port: https, scheme: https, path: /v1/sys/metrics, params: { format: ["prometheus"] }
      tlsConfig: { insecureSkipVerify: true }
---
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata: { name: vault-seal, namespace: cattle-monitoring-system, labels: { release: rancher-monitoring } }
spec:
  groups:
    - name: vault.seal
      rules:
        - alert: VaultSealed
          expr: vault_core_unsealed == 0
          for: 1m
          labels: { severity: critical }
          annotations: { summary: "Vault {{ $labels.instance }} is SEALED — ESO sync is broken" }
        - alert: VaultDown
          expr: up{job=~".*vault.*"} == 0
          for: 2m
          labels: { severity: critical }
          annotations: { summary: "Vault target {{ $labels.instance }} is down" }
```

## Rollback (if `-migrate` fails or Vault won't unseal)

1. Vault still has the Shamir key material until migration completes — re-run
   `operator unseal` (no `-migrate`) with the 3 keys to bring it up under Shamir.
2. If already partway: remove the `seal "transit"` stanza, `helm upgrade` back,
   restart `vault-0`, unseal with the 3 Shamir keys. Storage (Consul) is
   untouched — no secret data is lost by a seal rollback.
3. Keep `vault-unseal` running until the main Vault is confirmed stable; only
   then decommission if rolling back.

## Security hygiene (#426 §6.3)

- Move **both** key sets off the laptop to offline/Vault custody and delete the
  local copies: the main-vault recovery keys + root token (`vault-init-keys.json`)
  and the new `vault-unseal-init.json`.
- Rotate the root token after setup (`vault token revoke` the init root once an
  admin auth method is in place).

## Why transit (not cloud KMS / in-cluster keys)

- **Cloud KMS** would be simpler/hands-off and the cluster has egress, but it
  makes unsealing a production secrets store depend on an external cloud — counter
  to SN's on-prem isolation. Rejected for SN.
- **In-cluster auto-unseal** (keys in a Secret) avoids the migration but stores
  unseal authority in-cluster (weaker). Acceptable only as a stopgap.
- **Transit** keeps everything on-prem and reduces the manual-unseal surface to one
  small, stable Vault. Chosen.
