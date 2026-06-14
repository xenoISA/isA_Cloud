# Licensing & Authorization Model — how it fits together

> The single-page mental model for the platform license: the **key vs license**
> distinction, the **end-to-end flow** (issue → install → enforce → renew), and the
> **four authorization knobs** (edition + three license levers + enforcement policy).
> Updated 2026-06-09.
>
> Sits above the detailed docs — read this first, then drill in:
> - Design: ADR [`0008-license-entitlement`](../adr/0008-license-entitlement.md) (per-deployment),
>   [`0009-vendor-fleet-license-console`](../adr/0009-vendor-fleet-license-console.md) (vendor fleet).
> - Per-deployment ops: [`docs/runbooks/license-operator.md`](../runbooks/license-operator.md).
> - Key custody: [`license-key-custody.md`](./license-key-custody.md).
> - What each edition ships: [`edition-bom.md`](./edition-bom.md); repo taxonomy: [`edition-boundary.md`](./edition-boundary.md).
> - SN delivery (live example): `sn_cloud/docs/implementation-delivery/production/platform-services/license/README.md`.

---

## 1. Key vs license — the distinction that matters

These are two different objects. Conflating them is the #1 source of confusion.

| | Generated | Held by | Role |
|---|---|---|---|
| **Signing keypair** (ed25519) | **once, vendor-wide** (NOT per customer) | private key stays at isA forever (Vault / offline custody); public key is published | private key **signs**, public key **verifies** |
| **`license.json`** | **one per customer** (re-signed on renewal) | mounted in the customer's deployment | a signed "entitlement certificate": who / which edition / which modules / how much / until when |

The public key (`ISA_LICENSE_PUBKEY`) is the **same for every customer** and is baked
into images or shipped as the `isa-license-pubkey` ConfigMap. A customer environment
holding the public key can only **verify** — it can never forge a license, because the
private key never leaves isA. **The private key is the only secret that matters.**

---

## 2. End-to-end flow

### ① Vendor setup — once (reused for all customers)
```
isa-license-sign keygen                  # ed25519 keypair
  → private key  → Vault / offline custody (same custody as release signing, ADR 0007)
  → public key   → published; baked into images OR shipped as isa-license-pubkey ConfigMap
```

### ② Per-customer issuance — vendor side (business decision)
```
decide entitlement: edition / entitled_modules / quota_tier / seats / expiry
isa-license-sign sign --key <private> ... → license.json
  → record in the fleet issuance ledger (ADR 0009)
  → ship license.json + public key + telemetry secret in the offline delivery bundle (ADR 0007)
```

### ③ Per-deployment install — customer / operator side
```
kubectl apply isa-license + isa-license-pubkey ConfigMaps      # the "put it in" step
roll images built from licensing-aware isa_common              # mounts /etc/isa-license + injects pubkey (#370)
set ISA_LICENSE_ENFORCE=true (on-prem-full)                    # arm the gate
→ services verify the signature at startup → VALID → run; entitled modules render; quota applies
```

### ④ Renewal — before expiry
```
re-sign with the SAME private key, bump --expires-at → new license.json
swap the isa-license ConfigMap → rollout restart
```

> **Ordering safety:** `ISA_LICENSE_ENFORCE=true` + a missing/invalid license at startup
> → `setup_licensing` refuses to start (crash-loop). Always: **license present → roll
> enforced images → then arm enforce.** See the runbook for crash-loop recovery.

---

## 3. The four authorization knobs

Authorization is four orthogonal dials, set in two layers.

### Layer 1 — Edition (deployment-wide mode) — env `ISA_EDITION`
| edition | enforces license? | multi-tenant | charging | big-data |
|---|:---:|:---:|:---:|:---:|
| `saas` | ❌ default off | ✅ | ✅ | ❌ |
| `on-prem-full` (SN) | ✅ | ❌ | ❌ → showback | ✅ |
| `on-prem-lite` | ❌ | ❌ | ❌ | ❌ |

The license's `edition` field is **bound**: a license signed for `on-prem-full` is
`INVALID` on a `saas` runtime (verified behavior). That binding is the first restriction.

### Layer 2 — the three license levers (set at signing; decide *what* is restricted)
| Lever | Field / CLI flag | Restricts | Mechanism |
|---|---|---|---|
| **Expiry / kill-switch** | `--expires-at` + `--grace-days` | **time** | past expiry+grace → `EXPIRED`. Runtime is **fail-open** → startup gate + showback, not a hard mid-run kill |
| **Module entitlement** | `--entitled-modules` | **which modules** | a module not listed → its customer-module ArgoCD Application doesn't render (#369); optional per-module startup guard via `is_entitled()` |
| **Usage quota** | `--quota-tier` + `--seats` | **how much** | feeds `TierQuota.from_license` (#368) → per-org token/gpu/ray/mcp caps; `enterprise` = unlimited (-1), lower tiers = finite |

### Layer 3 — Enforcement policy (how hard) — env `ISA_LICENSE_ENFORCE`
- `false` / unset → gate not armed (license is advisory). *SN is here today.*
- `true` → **startup hard-check** (EXPIRED/INVALID → refuse to start, visible crash-loop)
  **+ runtime fail-open** (expiry mid-run → warn + showback `over_license`, never 403).
  "Hard at startup, soft at runtime" is fixed by design (ADR 0008 §3), not per-license.

---

## 4. Key-management strategy — WORKING DECISION: A (one vendor key)

How many signing keypairs?

- **A — one vendor-wide private key (ADOPTED).** All customers' licenses signed with it;
  one public key everywhere. Simplest. The single key is the one thing to guard. A leak
  compromises *all* customers' enforcement until images ship a new public key.
- **B — one keypair per customer.** ×N custody cost. **Adds no anti-forgery strength**
  (the private key is the only secret; public keys are public anyway). Only benefit: a key
  leak's blast radius is one customer. Reasonable only with very few on-prem customers.

> **Decided 2026-06-10:** model **A**. The keypair first generated for SN now serves as the
> **vendor-wide signing key**, held in **isA-side custody outside any repo** (per
> [`license-key-custody.md`](./license-key-custody.md)) — not in SN's cluster Vault, not in
> git. Future customers are signed with this same key; revisit only if per-customer blast-
> radius isolation becomes a requirement.

---

## 5. How to tighten — worked examples

| Goal | How |
|---|---|
| Sell only ERP + MDM | `--entitled-modules erp,mdm` |
| 90-day trial | `--expires-at <now+90d>` |
| Capacity-limited tier | `--quota-tier pro` (finite token/gpu vs `enterprise` unlimited) |
| Seat cap | `--seats 50` |
| Stop a customer | let the license lapse (no renewal). **No online revocation** in air-gapped — ADR 0009 |

---

## 6. Known limits (air-gapped reality)
- **No phone-home / no online revocation.** Enforcement is an offline signed file +
  expiry; "stopping" a customer = not renewing. A fleet-side revoke flag exists (ADR 0009)
  but cannot kill an already-deployed air-gapped license.
- **Runtime fail-open.** Expiry mid-run does not block traffic; the teeth are the startup
  gate + showback evidence (a contractual lever, not a hard switch).
- **Clock trust.** Expiry needs a sane local clock; a rolled-back clock on an air-gapped
  node can re-validate an expired license. Mitigation tracked as a follow-up.

---

## 7. Current SN instance (live example)
```
license_id=sn-prod-2026   customer=SN   edition=on-prem-full
entitled_modules=24 (erp..trobs — DEFAULT, confirm actual commercial scope)
quota_tier=enterprise   seats=-1   expires_at=2027-06-09 (+30d grace)
state: isa-license + isa-license-pubkey ConfigMaps APPLIED (staged) in sn-cloud-production;
       ISA_LICENSE_ENFORCE unset (gate NOT armed); running images pre-licensing.
private key: in isA-side custody, outside any repo (model A vendor key — §4); not in /tmp, not in git.
```
Arming path: confirm scope → roll #370 values + licensing images → set `ISA_LICENSE_ENFORCE=true`.
