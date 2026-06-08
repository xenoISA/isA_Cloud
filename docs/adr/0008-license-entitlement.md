# ADR 0008 — License & Entitlement Layer (offline, air-gapped, per-profile)

> Status: Proposed (2026-06-08)
> Story: TBD. Follows the editions/profile model (#328, ADR 0006) and artifact
> delivery (ADR 0007). Grounded in the current state of `isa_common/edition.py`,
> `isa_common/quota_enforcer.py`, and `docs/saas-deployment/SN-DEPLOYMENT-STATUS.md`.
> Sibling: ADR 0006 (edition runtime contract), `isa_common/brand.py`
> (brand-as-config), `deployments/editions/`.

## Context

The profile/edition model is live: one edition-agnostic `isa/*` image set is
deployed by config (ConfigMap swap), brand + edition as runtime env, per
namespace (SN runs in `sn-cloud-production`). The runtime half is `isa_common`:
`get_edition()` reads `ISA_EDITION` + `ISA_*_ENABLED` flags; `get_brand()` reads
`BRAND_*`. Both are frozen-dataclass singletons loaded once at import.

What is **missing** is the "who is allowed to run this, which modules, and until
when" layer. There is **no** license / entitlement / activation / expiry
mechanism anywhere in the codebase today (verified by grep across `isa_common`:
`license / entitlement / activation / ISA_LICENSE` all absent). The fork→profile
move makes this gap worth closing now: under the old white-label fork, "what SN
got" was decided by which repos were forked; under profiles, **every edition runs
the same images**, so the only thing distinguishing a licensed SN install from an
unlicensed copy of the same images is configuration. A signed license is what
makes that configuration tamper-evident.

### Hard constraint: SN is air-gapped

Per `SN-DEPLOYMENT-STATUS.md`, SN runs in a customer air-gapped IDC
(EonKube/Rancher RKE, over a flapping FortiGate VPN, no public egress —
firewall FW-OUT-001 forbids post-deploy registry pulls). Therefore:

- **No online activation, no phone-home, no license server.** The platform
  cannot reach an Anthropic/isA-hosted endpoint to validate.
- License must be an **offline, locally-verifiable signed artifact**: a
  `license.json` signed with isA's **private** key; images embed only the
  **public** key and verify the signature + expiry locally.
- License is **per-profile / per-namespace**, exactly like brand and edition:
  the `sn-cloud-production` namespace mounts SN's license; a GCP SaaS namespace
  mounts its own (or none). It travels with the profile, not the image.

## Decision

Add a third config contract alongside edition and brand: **`isa_common.license`**,
backed by an **offline ed25519-signed license file**, gating three things —
**expiry (kill-switch)**, **module entitlement**, and **usage quota** — with a
**fail-open-at-runtime / hard-check-at-startup** enforcement policy.

### 1. License artifact — signed `license.json`

isA signs (offline, with a private key never shipped) a JSON document:

```jsonc
{
  "license_id": "sn-prod-2026",
  "customer_id": "SN",
  "edition": "on-prem-full",          // must match ISA_EDITION or refuse
  "issued_at": "2026-06-08T00:00:00Z",
  "not_before": "2026-06-08T00:00:00Z",
  "expires_at": "2027-06-08T00:00:00Z",
  "grace_days": 30,                    // soft window after expiry (warn, not block)
  "entitled_modules": [               // see edition-boundary.md §B (24 customer modules)
    "erp", "mes", "plm", "srm", "scm_tower", "finance", "commerce",
    "commercial_tower", "mdm", "maestro", "feishu", "seeyon"
  ],
  "quota_tier": "enterprise",         // → TierQuota (see §4)
  "seats": -1,                         // -1 = unlimited
  "signature": "<ed25519 sig over the canonicalized body, base64>"
}
```

- **Algorithm: ed25519** (small, fast, no parameter choices to get wrong; pure-
  Python verify via `cryptography`, already a transitive dep). RSA acceptable but
  no reason to prefer it.
- **Signed payload** = the JSON object with the `signature` field removed,
  serialized canonically (sorted keys, no whitespace). The verifier reproduces
  this canonical form before checking.
- **Public key is baked into the image** (or mounted as a non-secret ConfigMap);
  the private key lives only in isA's signing tooling. A leaked public key cannot
  forge a license.

### 2. `isa_common/license.py` — runtime contract (mirrors `edition.py`)

A new module following the exact `edition.py` shape: a `LicenseStatus` enum, a
frozen `LicenseConfig` dataclass, a `from_env()` classmethod, and a process-wide
`get_license()` singleton. Exported from `isa_common/__init__.py` next to
`get_edition` / `get_brand`.

```python
class LicenseStatus(str, Enum):
    VALID       = "valid"        # signed, in-window
    GRACE       = "grace"        # expired but within grace_days → warn, allow
    EXPIRED     = "expired"      # past expiry + grace
    INVALID     = "invalid"      # bad signature / edition mismatch / malformed
    UNLICENSED  = "unlicensed"   # no license file present

@dataclass(frozen=True)
class LicenseConfig:
    status: LicenseStatus
    customer_id: str
    edition: str
    expires_at: Optional[datetime]
    grace_days: int
    entitled_modules: frozenset[str]
    quota_tier: Optional[str]
    seats: int

    @classmethod
    def from_env(cls) -> "LicenseConfig": ...
    #   ISA_LICENSE_FILE   path to license.json (unset → UNLICENSED)
    #   ISA_LICENSE_PUBKEY ed25519 public key (PEM) for verification
    #   verify signature → check not_before/expires_at+grace → check edition
    #     matches get_edition().edition → derive status

    def is_entitled(self, module_key: str) -> bool:
        return module_key in self.entitled_modules

# module-level singleton, read once at import (same as _edition)
def get_license() -> LicenseConfig: ...
```

Defaults are conservative and **decoupled from enforcement**: with no
`ISA_LICENSE_FILE` set, status is `UNLICENSED` — which on a dev/lite install is
fine (enforcement is opt-in per §3), so this module is a safe addition that
changes no behavior until wired up.

> Note on time: ed25519 verify is deterministic, but expiry needs "now". Read it
> once at startup for the hard check (§3); the per-request path (§3) re-reads the
> cached status from Redis with a TTL, so a long-running pod re-evaluates expiry
> hourly without re-verifying the signature on every request.

### 3. Enforcement policy — hard at startup, fail-open at runtime

Per the air-gapped operational risk (a license file not swapped in time must not
take the whole customer site down):

- **Startup (hard check).** A shared `setup_licensing(app)` helper (called next to
  the existing observability setup) runs at service start. If
  `ISA_LICENSE_ENFORCE=true` (set only in on-prem-full / SN values) and status is
  `EXPIRED` or `INVALID` → **refuse to start** (raise, pod crash-loops, visible in
  cluster). `VALID` / `GRACE` start normally; `GRACE` logs a loud warning.
  `UNLICENSED` starts only when enforcement is off.
- **Runtime (fail-open).** An optional FastAPI middleware checks the **cached**
  license status (Redis, 1h TTL). On `EXPIRED` it **warns + emits a metering
  event but does NOT 403** — fail-open. It only hard-blocks on explicit
  `revoked` state (a future online/CRL extension, out of scope here). Rationale:
  the startup gate already prevents an expired install from *restarting*; blocking
  live traffic mid-shift on a clock-edge is a worse failure than a few hours of
  over-run that showback will record anyway.
- **Showback ties it off.** Metering is always-on (edition-bom). An
  `over_license` flag on usage events during `GRACE`/`EXPIRED` gives a defensible
  paper trail without a technical kill-switch — turning expiry into a
  **contractual** lever, which is what an air-gapped enterprise deal actually
  wants.

### 4. Quota — feed the existing enforcer, don't rebuild it

`quota_enforcer.py` already gates per-org `tokens_per_hour / gpu_minutes_per_day /
ray_workers / mcp_calls_per_day` via a `TierQuota` dataclass with
`TierQuota.from_product_spec_tier(orm_tier)`. Add a sibling constructor:

```python
@classmethod
def from_license(cls, lic: "LicenseConfig") -> "TierQuota":
    # map lic.quota_tier → concrete limits; "enterprise" → -1 (unlimited)
```

On-prem-full (single-tenant) typically maps to an unlimited/enterprise tier — so
in practice the license's quota role on SN is mostly a documented ceiling, not a
hot path. The machinery is reused, not duplicated; the enforcement call sites are
unchanged.

### 5. Module entitlement — drive deployment, not just runtime

The 24 customer-specific modules (edition-boundary.md §B) are delivered/operated
separately and consume the platform via API/SDK. Entitlement is enforced **at the
deployment boundary**, which is cheaper and stronger than per-request code gates:

- The license's `entitled_modules` is the source of truth for **which ArgoCD
  module Applications get instantiated** in the SN namespace. A module not in the
  list is simply not deployed.
- For defense-in-depth, a platform module's own startup can call
  `get_license().is_entitled("commercial_tower")` and refuse to start if absent —
  but the primary control is "don't render the app".

> **Implementation (#369).** ArgoCD cannot read the signed `license.json`, so the
> entitled list is projected into the GitOps layer at deploy time:
> `deployments/editions/sn/values-entitled-modules.yaml` holds `sn.entitledModules`
> — the single ops edit point, transcribed verbatim from the license's
> `entitled_modules`. A customer-modules ApplicationSet
> (`deployments/argocd/apps/production/sn-customer-modules-appset.yaml`, modeled on
> `user-services-appset.yaml`) enumerates all 24 §B modules in its `list` generator,
> each element carrying an `entitled: "true"|"false"` flag, and gates rendering with
> `spec.selector.matchLabels: { entitled: "true" }`. Non-entitled modules produce no
> Application and are never deployed. On renewal: re-issue the signed license, then
> update the values file and flip the matching appset flags in lock-step.

### 6. Helm / deployment wiring (per-profile)

Add to `deployments/editions/sn/` (and the `isa-*-env` overlay), alongside the
existing `ISA_EDITION` / `BRAND_*`:

```yaml
env:
  - name: ISA_LICENSE_ENFORCE
    value: "true"                         # off in saas/lite by default
  - name: ISA_LICENSE_FILE
    value: /etc/isa-license/license.json  # mounted from a ConfigMap
  - name: ISA_LICENSE_PUBKEY
    valueFrom:
      configMapKeyRef: { name: isa-license-pubkey, key: ed25519.pub }
# license.json itself: a ConfigMap (it's signed → integrity doesn't need Secret,
# but mount read-only). Delivered in the offline bundle (ADR 0007), swapped on renewal.
```

SaaS/lite ship with `ISA_LICENSE_ENFORCE` unset → today's behavior, unchanged.

### 7. Admin surfaces — scope, and license is READ-ONLY in isA_Admin

isA_Admin is a **single-deployment operator console**: a Next.js frontend with no
database that proxies to the backend services of **one** deployment. Its scope is
therefore exactly the data of the namespace it is wired to — there is no
cross-deployment view, by design. The same code ships in two forms, switched by
edition:

- **SaaS edition** (`multi_tenant=true`): one isA_Admin instance in
  `isa-cloud-production` administers **all SaaS tenants** — that is what
  multi-tenancy means.
- **On-prem edition** (`multi_tenant=false`, e.g. SN): isA_Admin is deployed
  **per customer, inside that customer's namespace/cluster**, scoped to that one
  customer's data. Operators reach it locally or over the customer VPN (SN:
  FortiGate). There is **no** central isA_Admin that spans on-prem customers —
  their data physically lives in their isolated (often air-gapped) environments,
  which is the isolation the customer is paying for.

**Hard rule for this ADR: the license is NEVER editable from isA_Admin.** The
signature model (§1) exists precisely so the running environment cannot alter its
own entitlements; an admin form that uploads/edits `license.json` would defeat it.
isA_Admin MAY render license/edition state **read-only** — a
`/admin/platform/license` panel showing `edition`, `customer_id`, `status`
(VALID/GRACE/EXPIRED), `expires_at`, and `entitled_modules` — which is genuinely
useful for ops (renewal warnings, "is this module entitled?"). License
**authoring** lives only in the isA-side offline signing tool (`isa-license-sign`,
§1), never in a customer-reachable surface.

What isA_Admin *does* write is the orthogonal, per-org runtime layer it already
owns: products, pricing, subscriptions, credits, and per-org quota values **within
the ceiling** the license's `quota_tier` sets (§4). Deployment-identity config
(edition / brand / license) is profile-layer config (GitOps + signed file);
per-org operational config is isA_Admin's job. Keep that line.

> Cross-customer "all my deployments in one screen" is a **separate** vendor-side
> system, not isA_Admin — see ADR 0009 (Vendor Fleet / License Console). Its data
> source is the license-issuance ledger plus opt-in telemetry, never a direct
> connection into customer databases.

## Consequences

**Positive**
- Reuses three existing layers (edition singleton pattern, quota enforcer,
  metering); the genuinely new surface is one ~150-line module + a verify helper +
  a startup hook. Small, testable, isolated.
- Works fully offline; nothing depends on the flapping VPN.
- License is per-namespace config that rides the profile — consistent with brand
  and edition, so operators already understand the shape.
- Expiry is a contractual lever (showback evidence) rather than a brittle
  kill-switch — matches enterprise air-gapped reality.

**Negative / risks**
- **Clock dependence.** Expiry needs a trustworthy local clock; an air-gapped
  cluster with skewed/rolled-back time could mis-evaluate. Mitigation: rely on
  `not_before` too, and treat large backward jumps as suspect (log, don't block).
- **Fail-open means expiry is not a hard technical stop** while pods keep running.
  Accepted deliberately; the startup gate + showback are the teeth.
- **Public-key rotation** is a future chore (image rebuild or ConfigMap swap);
  acceptable at enterprise renewal cadence.
- Signing tooling + private-key custody is a new operational responsibility on the
  isA side (keep the private key offline, e.g. in the same custody as release
  signing).

## Alternatives considered

- **Online activation / license server** — rejected: incompatible with FW-OUT-001
  air-gap.
- **Per-request fail-closed 403 on expiry** — rejected per user decision: too
  brittle for an air-gapped site; a late license swap would black out production.
- **Encrypt images / per-customer image builds** — rejected: throws away the
  edition-agnostic single-image-set property that the whole profile model is
  built on (ADR 0006/0007).
- **JWT (RS256)** instead of a signed JSON doc — viable, but a bare ed25519
  signature over canonical JSON is simpler to reason about and avoids dragging in
  JWT validation footguns (alg confusion, etc.).

## Implementation sketch (follow-up story)

1. `isa_common/license.py` + export from `__init__.py` (mirror `edition.py`).
2. ed25519 verify helper + a tiny `isa-license-sign` CLI in release tooling.
3. `setup_licensing(app)` startup hook; opt-in via `ISA_LICENSE_ENFORCE`.
4. `TierQuota.from_license()` in `quota_enforcer.py`.
5. `entitled_modules` → ArgoCD ApplicationSet generator filter for SN modules.
6. `deployments/editions/sn/` license env + ConfigMaps; bundle the file into the
   offline delivery (ADR 0007).
7. Runbook: license issuance, renewal/swap, grace behavior, clock guidance.
