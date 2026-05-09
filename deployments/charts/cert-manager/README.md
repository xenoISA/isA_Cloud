# cert-manager

cert-manager wrapper. Installs the upstream `jetstack/cert-manager`
(operator + CRDs) cluster-wide and renders one or more `ClusterIssuer`
CRs (selfsigned by default).

Tracking issue: [xenoISA/isA_Cloud#234](https://github.com/xenoISA/isA_Cloud/issues/234)
(closes the "🔴 cert-manager + ClusterIssuer" gap from the
deployment-readiness audit).

## ⚠️ Install order is strict

This chart is a **prerequisite** for any chart that issues `Certificate`
or `Issuer` CRs (or references a ClusterIssuer the chart created).
Install **before** the umbrella when HTTPS / mTLS / customer Ingresses
are in scope.

```bash
# Step 1: install cert-manager (CRDs + controller + ClusterIssuer)
kubectl create namespace cert-manager
helm dependency update deployments/charts/cert-manager
helm install cert-manager deployments/charts/cert-manager \
  --namespace cert-manager

# Step 2: install the big-data umbrella + any chart that issues Certs
deployments/scripts/setup-datalake.sh -p customer-prod
```

Reversing the order produces `no matches for kind "Certificate" in
version "cert-manager.io/v1"` if the umbrella issues Certs, or just
silent unenforced TLS if no charts depend on cert-manager today.

## What gets installed

The upstream chart ships:

- **6 cluster-scoped CRDs**: Certificate, CertificateRequest, ClusterIssuer, Issuer, Order, Challenge
- **`cert-manager` Deployment** — the main controller
- **`cert-manager-cainjector` Deployment** — the CA injector for webhooks
- **`cert-manager-webhook` Deployment** — the validating + mutating webhook
- **ServiceAccounts + ClusterRoles + ClusterRoleBindings** for each
- **MutatingWebhookConfiguration** + **ValidatingWebhookConfiguration**
- **Service** for the webhook endpoint

This chart additionally renders (gated by values):

- **`selfsigned-issuer`** ClusterIssuer (default ON) — selfSigned spec
- **`internal-ca-issuer`** ClusterIssuer (default OFF) — wraps a pre-provisioned root CA Secret
- **`letsencrypt-prod`** ClusterIssuer (default OFF) — ACME via Let's Encrypt

## ClusterIssuer types

Three independently-gated rendering paths:

### 1. `selfsigned-issuer` (default)

```yaml
clusterIssuers:
  selfsigned:
    enabled: true
    name: selfsigned-issuer
```

Suitable for kind / dev and any internal-only TLS where consumers
don't validate the cert chain. Renders a `selfSigned: {}` ClusterIssuer.

### 2. `internal-ca-issuer` (on-prem CA)

```yaml
clusterIssuers:
  internalCA:
    enabled: true
    name: internal-ca-issuer
    caSecretName: internal-ca   # pre-provision in cert-manager namespace
```

Wraps a pre-provisioned root CA (Secret with `tls.crt` + `tls.key`) so
all certificates issued through this ClusterIssuer chain back to the
customer's internal PKI. The Secret must exist before this chart is
applied (provision via vault / external-secrets).

### 3. `letsencrypt-prod` (ACME)

```yaml
clusterIssuers:
  acme:
    enabled: true
    name: letsencrypt-prod
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@example.com         # required
    solver:
      http01:
        ingressClass: nginx
```

Suitable for customer-facing Ingress endpoints with public DNS. Renders
an ACME ClusterIssuer with HTTP-01 challenge using the ingress class.
DNS-01 challenge config is out of scope for this initial chart shell —
extend the template if needed.

## Profile differential

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| selfsigned-issuer | ✅ on | ✅ on | ✅ on |
| internal-ca-issuer | off | off | ✅ on (vault-provisioned root CA) |
| letsencrypt-prod | off | off | ✅ on (for Grafana / customer Ingress) |
| Replica count | 1 | 1 | 1 (HA-by-restart; controllers leader-elect) |
| `installCRDs` | true | true | true |
| PriorityClass | (none) | (none) | `infra-critical` |

(Profile-specific overlay files are out of scope for this initial chart
PR; the umbrella values default works for staging.)

## Why this chart's CRDs are NOT in the umbrella

Same reasoning as Strimzi Operator (#259) and Prometheus Operator
(#234's prometheus-operator chart): cert-manager CRDs are cluster-scoped
and must exist before any consumer of `Certificate` / `Issuer` /
`ClusterIssuer` CRs applies. Putting them in the umbrella would force
every `helm upgrade isa-bigdata` to grapple with CRD ordering. Keeping
them in their own chart lets cert-manager's release cadence run
independently of the application umbrella.

## Bumping cert-manager

1. Pick a new version from <https://cert-manager.io/docs/release-notes/>.
2. Update `dependencies.version` in `Chart.yaml` and re-run
   `helm dependency update`.
3. Re-vendor the `.tgz` for air-gap.
4. Confirm CRD migrations — cert-manager occasionally bumps API
   versions (`v1alpha2` → `v1alpha3` → `v1beta1` → `v1`); ensure
   downstream charts use the current version.

## Uninstall (cleanup)

```bash
# 1. Delete any Certificate / Issuer / ClusterIssuer CRs first
#    (they may have finalizers).
kubectl get certificates -A
kubectl get issuers -A
kubectl get clusterissuers
# delete them as appropriate

# 2. Uninstall the operator stack.
helm uninstall cert-manager -n cert-manager

# 3. Manually clean up the CRDs.
kubectl delete crd \
  certificaterequests.cert-manager.io \
  certificates.cert-manager.io \
  challenges.acme.cert-manager.io \
  clusterissuers.cert-manager.io \
  issuers.cert-manager.io \
  orders.acme.cert-manager.io
```

## Out of scope (separate stories)

- **Profile-specific overlay files** under `deployments/values/` for cert-manager
- **DNS-01 challenge** config for ACME ClusterIssuers (per-provider)
- **Vault PKI ClusterIssuer** — `cert-manager` supports it; needs vault
  config which is customer-prod specific
- **Pre-loaded `Certificate` CRs** for the big-data services (Apicurio
  HTTPS, Flink JM web UI, StarRocks FE) — those land in the consumer
  charts when TLS is opted in
- **Wiring `setup-datalake.sh`** to optionally install cert-manager
  pre-umbrella

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#259 — Strimzi Operator chart (sibling cluster-wide prereq)
- xenoISA/isA_Cloud#266 — PriorityClass + ArgoCD `isa-bigdata.yaml` (sibling)
- xenoISA/isA_Cloud#268 — Prometheus Operator chart (sibling cluster-wide prereq)
- xenoISA/sn-commercial-tower `docs/design/00-infra-architecture-overview.md` §5.2 — security/TLS architecture
