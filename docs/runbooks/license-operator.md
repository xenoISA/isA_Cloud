# Runbook: License & Entitlement Operations (per-deployment)

> Operator runbook for the per-deployment license lifecycle — issue, deliver,
> install, renew, and expiry behavior. Authoritative design:
> [`docs/adr/0008-license-entitlement.md`](../adr/0008-license-entitlement.md).
> Cross-customer / vendor-fleet view is a **separate** system — see
> [`docs/adr/0009-vendor-fleet-license-console.md`](../adr/0009-vendor-fleet-license-console.md).
> Pairs with [`saas-deployment/SN-DEPLOYMENT-STATUS.md`](../saas-deployment/SN-DEPLOYMENT-STATUS.md)
> and the editions overlays in `deployments/editions/`.

## Scope

The license is a **per-profile / per-namespace** config contract that rides the
profile exactly like `ISA_EDITION` and `BRAND_*` (ADR 0008 §0, §6). One
edition-agnostic `isa/*` image set runs everywhere; the signed `license.json`
mounted into a namespace is what distinguishes a licensed install (e.g. SN in
`sn-cloud-production`) from an unlicensed copy of the same images.

This runbook covers **one deployment's** license. It does NOT cover the
vendor-side roster across all customers (ADR 0009) and it does NOT cover editing
a license from inside a running deployment — **the license is never editable from
isA_Admin** (ADR 0008 §7). isA_Admin may only render `/admin/platform/license`
read-only (`status`, `customer_id`, `expires_at`, `entitled_modules`).

## Mental model (read first)

- **Offline, locally-verifiable.** No online activation, no phone-home, no license
  server (SN air-gap, FW-OUT-001). The image embeds only the **ed25519 public
  key** and verifies the signature + window locally. The private key never ships.
- **Expiry is a CONTRACTUAL lever, not a kill-switch.** Enforcement is hard at
  startup but **fail-open at runtime** (ADR 0008 §3). A license not swapped in
  time must not black out a live customer site.
- **No online revocation.** Revocation is by expiry only (see below).

---

## 1. Issue a license (vendor / isA side)

Done **offline** with the `isa-license-sign` CLI (#366), which holds the ed25519
private key. Never run on or reachable from a customer cluster.

1. Confirm the deployment's runtime `ISA_EDITION` (check the target namespace's
   `isa-*-env` ConfigMap). The license `edition` field **MUST match** `ISA_EDITION`
   or the runtime derives status `INVALID` and (under enforcement) refuses to start.
2. Fill the `license.json` body (ADR 0008 §1):

   | Field | Notes |
   |---|---|
   | `license_id` | e.g. `sn-prod-2026`; renewals get a new id |
   | `customer_id` | e.g. `SN` |
   | `edition` | **must equal** the target `ISA_EDITION` (e.g. `on-prem-full`) |
   | `issued_at` / `not_before` | issuance + earliest-valid instant (UTC) |
   | `expires_at` | hard expiry (UTC) |
   | `grace_days` | soft window after expiry — warn, do not block (e.g. `30`) |
   | `entitled_modules` | source of truth for which modules deploy (ADR 0008 §5) |
   | `quota_tier` | maps to `TierQuota` (ADR 0008 §4); `enterprise` → unlimited |
   | `seats` | `-1` = unlimited |
   | `signature` | ed25519 sig over the canonicalized body (sorted keys, no whitespace) |

3. Sign. The CLI canonicalizes the body (signature field removed), produces the
   ed25519 signature, and emits the complete `license.json`.
4. **Key custody (#366 / ADR 0008, ADR 0009).** The signing private key is a
   standing vendor responsibility — keep it **offline, in the same custody as
   release signing**. A leaked *public* key cannot forge a license; a leaked
   *private* key can — treat it like the release-signing key.

> `entitled_modules` is also the source of truth for **which ArgoCD module
> Applications get instantiated** in the namespace (ADR 0008 §5). Modules not in
> the list are simply not rendered, so get this list right at issuance.

---

## 2. Deliver & install (operator side)

The license rides the **profile / namespace**, delivered in the offline bundle
(ADR 0007) and swapped on renewal. It is **signed**, so integrity does not need a
Secret — mount it as a **read-only ConfigMap**.

```bash
# license.json itself → ConfigMap in the customer namespace
kubectl create configmap isa-license \
  -n sn-cloud-production \
  --from-file=license.json=./license.json \
  --dry-run=client -o yaml | kubectl apply -f -

# the ed25519 PUBLIC key → non-secret ConfigMap (for signature verification)
kubectl create configmap isa-license-pubkey \
  -n sn-cloud-production \
  --from-file=ed25519.pub=./ed25519.pub \
  --dry-run=client -o yaml | kubectl apply -f -
```

Env contract — set in `deployments/editions/sn/` (the `isa-*-env` overlay),
alongside `ISA_EDITION` / `BRAND_*` (ADR 0008 §6):

| Env var | Value | Meaning |
|---|---|---|
| `ISA_LICENSE_ENFORCE` | `"true"` (on-prem-full / SN only) | turns on the startup hard-check; **unset** in saas/lite → today's behavior, unchanged |
| `ISA_LICENSE_FILE` | `/etc/isa-license/license.json` | path to the mounted `license.json`; **unset → `UNLICENSED`** |
| `ISA_LICENSE_PUBKEY` | `configMapKeyRef: isa-license-pubkey / ed25519.pub` | ed25519 public key (PEM) used to verify the signature |

Mount the `isa-license` ConfigMap read-only at `/etc/isa-license/` so
`ISA_LICENSE_FILE` resolves. SaaS/lite ship with `ISA_LICENSE_ENFORCE` unset and
behave exactly as before.

### Verify install

```bash
# Confirm the env + mount landed
kubectl get cm isa-license isa-license-pubkey -n sn-cloud-production
kubectl exec -n sn-cloud-production deploy/isa-admin -- cat /etc/isa-license/license.json | head

# Read-only operator view (does NOT permit editing — ADR 0008 §7)
#   /admin/platform/license → status / customer_id / expires_at / entitled_modules
```

A healthy install with `ISA_LICENSE_ENFORCE=true` shows status `VALID` and pods
`Running`. See §4 for what other states look like.

---

## 3. Renew / swap

Renewal = **swap the ConfigMap + roll the workloads**. There is no in-place edit.

```bash
# 1. Receive the new signed license.json (new license_id, later expires_at)
# 2. Replace the ConfigMap (same name → mounts pick it up on restart)
kubectl create configmap isa-license \
  -n sn-cloud-production \
  --from-file=license.json=./license-2027.json \
  --dry-run=client -o yaml | kubectl apply -f -

# 3. Roll the workloads so they re-read the file at startup
kubectl rollout restart deploy -n sn-cloud-production    # or the licensed subset
```

What to watch during a swap:

- The startup hard-check re-runs on each restarting pod — a **bad/mismatched**
  license surfaces immediately as a **crash-loop** (see §4). Roll one workload
  first to catch this before fleet-wide restart.
- The runtime path caches license status in Redis with a **1h TTL** (ADR 0008
  §3); a long-running pod that you did *not* restart re-evaluates within the hour.
  For a deterministic cutover, restart rather than wait out the TTL.
- Confirm `edition` in the new file still matches the namespace's `ISA_EDITION`.
- Confirm the new `entitled_modules` matches intended deployed modules (ADR 0008
  §5) — a dropped module will stop being rendered by ArgoCD.

---

## 4. Grace & expiry behavior

Enforcement is **hard at startup, fail-open at runtime** (ADR 0008 §3). Status is
one of `VALID` / `GRACE` / `EXPIRED` / `INVALID` / `UNLICENSED`.

| Status | Startup (`ISA_LICENSE_ENFORCE=true`) | Runtime | What ops sees |
|---|---|---|---|
| `VALID` | starts normally | normal | nothing |
| `GRACE` (expired, within `grace_days`) | starts, **loud warning** logged | normal | renewal warnings; usage events flagged `over_license` |
| `EXPIRED` (past expiry + grace) | **refuses to start → crash-loop** | **fail-open**: warns + emits metering event, does **NOT** 403 | crash-loop on restart; `over_license` on live usage |
| `INVALID` (bad sig / edition mismatch / malformed) | **refuses to start → crash-loop** | fail-open | crash-loop on restart |
| `UNLICENSED` (no `ISA_LICENSE_FILE`) | starts only if enforcement is **off** | n/a | refuses to start if enforce=true |

Key consequences:

- **Startup is the gate.** With `ISA_LICENSE_ENFORCE=true`, an `EXPIRED`/`INVALID`
  license means pods **crash-loop on (re)start** — visible in the cluster. This is
  the teeth: an expired install cannot *restart* into service.
- **Runtime is fail-open.** A pod already running when the license expires keeps
  serving traffic — it logs warnings and emits metering events with the
  **`over_license`** flag, but does **not** 403. Blocking live traffic mid-shift
  on a clock-edge is a worse failure than a few hours of recorded over-run.
- **Showback is the paper trail.** Metering is always-on (`edition-bom.md`); the
  `over_license` flag on `GRACE`/`EXPIRED` usage events is the defensible record
  that turns expiry into a **contractual** lever, not a technical kill-switch.

```bash
# Diagnose a crash-looping licensed pod
kubectl get pods -n sn-cloud-production | grep -v Running
kubectl logs -n sn-cloud-production deploy/<svc> --previous | grep -i licens
#   → "EXPIRED", "INVALID", "edition mismatch", or "signature" tells you which
```

Remediation for an expiry/invalid crash-loop: install a valid renewed license
(§3). As a deliberate emergency lever you *may* unset `ISA_LICENSE_ENFORCE` to let
pods start while a renewal is in flight — this is a contractual override, log it.

---

## 5. Revoke-by-expiry (the revocation model)

**There is no online revocation, no CRL, no kill command.** The platform cannot
reach a vendor endpoint (air-gap), so revocation is modeled entirely through the
license window:

- To "revoke," **let the current license expire** (and do not renew), or issue a
  short-lived replacement with a near `expires_at`. Past expiry + `grace_days`,
  status is `EXPIRED`: the startup gate stops restarts and showback flags all
  usage `over_license`.
- A live pod is **not** killed mid-run by a revocation (fail-open). Practical
  enforcement of a revocation = a **rollout** (which then hits the startup gate)
  plus the contractual lever of the showback record.
- The runtime middleware only hard-blocks on an explicit `revoked` state, which is
  a **future** online/CRL extension and is **out of scope** today (ADR 0008 §3).
  Do not assume an online revoke exists.

Plan revocations as contract events with lead time, not as an instant remote
switch.

---

## 6. Clock guidance (air-gapped clusters)

Expiry needs a trustworthy local clock, and an air-gapped cluster may have skewed
or rolled-back time (ADR 0008 §3, Consequences).

- The license carries **both `not_before` and `expires_at`** — the runtime checks
  both, so a clock rolled *back* before `not_before` reads as not-yet-valid, not
  as "valid forever."
- **Large backward clock jumps are treated as suspect**: logged, **not** used to
  silently extend a license, and **not** treated as a hard block either (don't
  trust a rolled-back clock in either direction).
- Keep the cluster's clock disciplined (an internal NTP/PTP source inside the
  air-gap). A drifting clock will mis-evaluate `GRACE`/`EXPIRED` boundaries and
  produce confusing showback timestamps.
- ed25519 signature verification is **clock-independent** — only the window check
  depends on time. A signature failure (`INVALID`) is never a clock problem;
  investigate the file/pubkey instead.

---

## Cross-references

- [`docs/adr/0008-license-entitlement.md`](../adr/0008-license-entitlement.md) —
  authoritative design (§1 schema, §3 enforcement, §6 Helm wiring, §7 scope).
- [`docs/adr/0009-vendor-fleet-license-console.md`](../adr/0009-vendor-fleet-license-console.md) —
  vendor-side cross-customer fleet/roster (separate system, not isA_Admin).
- `isa-license-sign` CLI + **private-key custody** — #366 (keep the key offline,
  same custody as release signing).
- [`docs/saas-deployment/edition-bom.md`](../saas-deployment/edition-bom.md) —
  what each edition ships (metering always-on; `entitled_modules` context).
- [`docs/saas-deployment/SN-DEPLOYMENT-STATUS.md`](../saas-deployment/SN-DEPLOYMENT-STATUS.md) —
  the SN air-gapped target (`sn-cloud-production`, FortiGate VPN, FW-OUT-001).
