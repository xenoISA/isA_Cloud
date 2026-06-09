# Cloud-Native Parity Test Suite

ONE functional test suite that runs against **any** environment by config — proving
every isA service is cloud-native: same images + config, runnable in **local dev**
and deployable to **any K8s** (own IDC / SN, and GCP / GKE).

It exists to catch the "works-in-local-dev / breaks-in-prod" bug class surfaced by
the SN parity audit (`../../docs/saas-deployment/SN-PARITY-AUDIT.md`): hardcoded
`localhost`, non-URL-encoded DB DSNs, missing-env defaults, unmounted content,
response-models that 500 on empty data, gateway/host-header rejection, etc.

## What it checks

- `test_00_read_parity.py` — every service reachable + **no GET endpoint 5xxs**
  (5xx == real bug; 401/403/422 are expected). No auth needed; runs everywhere.
- `test_01_auth_flow.py` — register → verify → login → authed call (the core
  cross-service journey + the JWT bootstrap self-test).
- `test_<service>.py` — per-service real CRUD (create → verify → **delete cleanup**),
  generated from the audit test-specs. Cleanup makes it safe against prod.

## Targets (the cloud-native point)

Set `PARITY_TARGET`:

| Target | Base URL shape | Use |
|--------|----------------|-----|
| `local` | `http://localhost:<port>` (or `PARITY_HOST`) | local dev / kind port-forward |
| `incluster` | `http://<svc>.<ns>.svc.cluster.local:<port>` | **SN-IDC and GCP-GKE** (same shape) |

`PARITY_NAMESPACE` selects the namespace (default `sn-cloud-production`).
SN and GCP are both `incluster` — that identity is the whole proof of portability.

## Run locally

```bash
# services on localhost (or PARITY_HOST), e.g. via kubectl port-forward
PARITY_TARGET=local pip install pytest redis && python -m pytest tests/parity -q
```

## Run in any K8s (SN now, GCP next)

```bash
kubectl create configmap parity-suite --from-file=tests/parity -n <namespace>
kubectl apply -f tests/parity/run-parity-job.yaml      # edit PARITY_NAMESPACE for GCP
kubectl logs job/parity -n <namespace> -f
```

The JWT bootstrap retrieves the registration code env-aware: the auth dev endpoint
in local dev, else the Redis store in-cluster (`REDIS_*` from the platform secret).

## CI gate

Run `PARITY_TARGET=incluster` as a post-deploy gate in every environment's pipeline
(IDC + GCP). A 5xx / failed CRUD = a parity regression; fix in code (env-first,
never break local-dev) before promoting.
