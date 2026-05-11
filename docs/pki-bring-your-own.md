# PKI — Bring-Your-Own Root CA

> Status: documentation for the W2.10 acceptance gate (W3 hardware
> deployment uses this path). Tracked in
> [xenoISA/isA_Cloud#276](https://github.com/xenoISA/isA_Cloud/issues/276).

## What this document covers

The `deployments/charts/cert-manager` chart ships with three independently
gated `ClusterIssuer` paths: `selfsigned-issuer` (default), `internal-ca-issuer`
(BYO root CA), and `letsencrypt-prod` (ACME). This document is the customer
playbook for the **`internal-ca-issuer` / bring-your-own** path — the
expected production posture for the customer's on-prem cluster where their
existing PKI must be the chain anchor.

The mechanical install steps are in `deployments/charts/cert-manager/README.md`
sections "ClusterIssuer types → internal-ca-issuer" and "Profile differential".
This document explains the **what / why** that sits outside the chart README:

1. Which CA artefact the customer provides
2. How that artefact lands in the cluster as a Secret
3. Which downstream services consume the chain
4. Rotation, expiry, and audit posture
5. What survives a chart re-install

## 1. The artefact the customer provides

A **single PEM-encoded intermediate CA bundle** with the corresponding
private key. Exactly one Secret in the `cert-manager` namespace, type
`kubernetes.io/tls`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: internal-ca
  namespace: cert-manager
type: kubernetes.io/tls
data:
  tls.crt: <base64 PEM — intermediate cert chained to the customer's root>
  tls.key: <base64 PEM — corresponding private key>
```

Requirements:

- The cert MUST have `CA:TRUE` in its Basic Constraints extension.
  cert-manager refuses to chain certificates from a non-CA leaf.
- The private key MUST match (`openssl x509 -modulus` ==
  `openssl rsa -modulus`). Mismatch fails the ClusterIssuer Ready condition.
- Validity SHOULD be ≥ 5 years from issuance. cert-manager re-signs
  leaf certificates near their expiry, but it cannot re-sign with an
  expired intermediate.
- The CN / SAN list is not consumed by cert-manager — it issues new
  certificates with whatever SANs the downstream `Certificate` CR
  declares.

The **root CA above the intermediate stays in the customer's PKI
infrastructure** (typically an HSM or air-gapped CA host) and never
lands in the cluster. Only the signing-tier intermediate is on cluster.

## 2. Provisioning the Secret

Two supported paths:

### 2.1. Vault path (recommended for customer-prod)

The customer's Vault holds the intermediate at a known KV-v2 path, e.g.
`secret/data/isa-platform/pki/intermediate`. The `external-secrets-operator`
chart (`deployments/charts/external-secrets-operator`) provides a
`ClusterSecretStore` pointing at that Vault. Then add an `ExternalSecret`:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: internal-ca
  namespace: cert-manager
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-cluster
    kind: ClusterSecretStore
  target:
    name: internal-ca
    creationPolicy: Owner
    template:
      type: kubernetes.io/tls
      data:
        tls.crt: "{{ .crt }}"
        tls.key: "{{ .key }}"
  data:
    - secretKey: crt
      remoteRef:
        key: isa-platform/pki/intermediate
        property: crt
    - secretKey: key
      remoteRef:
        key: isa-platform/pki/intermediate
        property: key
```

This is the expected production path because:

- Vault keeps the authoritative copy, encrypted at rest.
- Rotation is one Vault write — ESO syncs the cluster Secret automatically.
- All access is audited in Vault, not in `kubectl describe`.
- Disaster recovery: re-create the cluster, re-install ESO + the
  ExternalSecret, and the intermediate flows back without re-uploading PEMs.

### 2.2. Direct kubectl path (kind / dev / first-time install)

```bash
kubectl create secret tls internal-ca \
  --namespace cert-manager \
  --cert=./intermediate.crt \
  --key=./intermediate.key
```

Use this only when Vault is not in scope. The PEM files MUST be deleted
from the operator's workstation after creating the Secret. There is no
cluster-side audit trail for direct `kubectl create secret` — assume
the operator's shell history is the only record.

## 3. Enabling the ClusterIssuer

In the `cert-manager` chart values (per profile under
`deployments/values/`):

```yaml
cert-manager:
  clusterIssuers:
    selfsigned:
      enabled: true        # leave on — used by smoke tests
      name: selfsigned-issuer
    internalCA:
      enabled: true
      name: internal-ca-issuer
      caSecretName: internal-ca   # matches the Secret name from step 2
    acme:
      enabled: false
```

After install:

```bash
kubectl get clusterissuer internal-ca-issuer -o yaml | yq '.status.conditions'
# Expected: type=Ready, status=True, reason=KeyPairVerified
```

If `Ready=False`:

- `reason: ErrGetKeyPair` → the Secret is missing or named wrong.
- `reason: ErrInitIssuer` → the cert/key pair don't match or the cert
  is not a CA.

## 4. Which services consume the chain

W3 hardware bringup wires the following downstream `Certificate` CRs to
`internal-ca-issuer` (gated by per-chart values):

| Chart | Cert subject | DNS SAN | Notes |
|---|---|---|---|
| `apicurio-registry` | `apicurio-registry.isa-bigdata` | `apicurio-registry.isa-bigdata.svc.cluster.local` | HTTPS REST API |
| `flink` (JM web UI) | `flink-session-rest.isa-bigdata` | `flink-session-rest.isa-bigdata.svc.cluster.local` | Web UI + REST |
| `starrocks` (FE) | `bigdata-starrocks-fe-service.isa-bigdata` | FE Service DNS | mysql-protocol + HTTP query API |
| `hive-metastore` | `hive-metastore.isa-bigdata` | HMS Service DNS | Thrift TLS (W3 opt-in) |
| `apisix` | customer-facing FQDN | per-Ingress | Gateway-tier HTTPS |

Each chart's values file has a `tls.issuer.kind: ClusterIssuer` /
`tls.issuer.name: internal-ca-issuer` knob. Leaving the knob unset
falls back to `selfsigned-issuer` (W2 kind behavior).

## 5. Rotation cadence

- **Leaf certs** (per service): cert-manager renews 30 days before expiry,
  by default with 90-day lifetimes. No operator action.
- **Intermediate CA**: customer-driven. Rotate when:
  - Approaching the intermediate's `notAfter` minus 6 months.
  - A key compromise is suspected.
  - Customer's security policy mandates a calendar rotation.

  Rotation procedure:
  1. Customer issues a new intermediate from their root.
  2. Update Vault `secret/data/isa-platform/pki/intermediate` (path
     2.1) or recreate the `internal-ca` Secret (path 2.2).
  3. ESO syncs (within `refreshInterval`); cert-manager re-issues
     all downstream Certificates within 1 hour (cert-manager's
     re-sync interval on a Secret update).
  4. Pods consuming the new cert via `Secret`-mounted volumes may
     need a roll. The downstream charts set `secretChecksum`
     annotations so a Secret hash change triggers a Deployment roll
     automatically.
- **Root CA**: out of scope for this cluster. Customer's PKI ops own
  the root rotation, which produces a new intermediate that flows
  through steps 1-4 above.

## 6. What survives a chart re-install

A `helm uninstall cert-manager` followed by `helm install cert-manager`
preserves:

- The `internal-ca` Secret (managed by ESO, not the chart).
- Any existing leaf Certificate CRs (cluster-scoped CRDs, not Helm-owned).

It does NOT preserve:

- The `internal-ca-issuer` ClusterIssuer object (chart-templated;
  re-rendered fresh). Downstream Certificates briefly drift to
  `Ready=False` until the new ClusterIssuer reaches `Ready=True`,
  typically < 30s.

A `kubectl delete secret internal-ca` cascades:
`internal-ca-issuer` flips to `Ready=False`, every Certificate flips
to `Ready=False`, and no new leaf certs can be issued. ESO restores the
Secret on its next sync (~hourly), at which point everything heals
without operator action. To force immediate recovery:
`kubectl annotate externalsecret internal-ca force-sync=$(date +%s)`.

## 7. Audit posture

The customer can answer "who issued cert X" with:

```bash
# Show every cert in the cluster + which ClusterIssuer signed it
kubectl get certificates -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{"\t"}{.spec.issuerRef.name}{"\n"}{end}'

# For a given Certificate, dump the issuance trail
kubectl describe certificate -n <ns> <name>
# → "Renewed" / "Issued" / "RequestApproved" events with timestamps
```

Combined with Vault's audit log for intermediate rotations, this gives
the customer end-to-end chain-of-custody: Vault audit → ESO sync event
→ cert-manager Certificate event → Pod restart event.

## 8. Out of scope here

- **DNS-01 ACME challenge** — see the chart README for the ACME path
  (only used for customer-facing public FQDNs that bypass internal CA).
- **HSM-backed intermediate** — cert-manager talks PKCS#11 via the
  `cert-manager-csi-driver`. Out of scope for W3; document if customer
  asks.
- **Wildcard intermediates** — supported by cert-manager but the
  customer's PKI policy is the authority. If the customer's intermediate
  is constrained to specific name spaces, the SAN list on the leaf
  Certificate CRs must comply or issuance fails.

## References

- Chart: `deployments/charts/cert-manager/README.md`
- External-Secrets-Operator chart: `deployments/charts/external-secrets-operator/`
- Architecture: `docs/design/00-infra-architecture-overview.md` §7 (security tier)
- W2.10 issue: <https://github.com/xenoISA/isA_Cloud/issues/276>
