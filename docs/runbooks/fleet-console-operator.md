# Runbook: Fleet / License Console Operations (vendor-side)

> Operator runbook for the **vendor-side** Fleet / License Console — issue, renew,
> revoke licenses across **all** customers, ingest opt-in telemetry (including the
> air-gapped offline-upload loop), and read the fleet. Authoritative design:
> [`docs/adr/0009-vendor-fleet-license-console.md`](../adr/0009-vendor-fleet-license-console.md).
> This is the **cross-customer half** of licensing; the **per-deployment** half
> (install/swap inside one customer namespace) is
> [`docs/runbooks/license-operator.md`](./license-operator.md) — cross-reference it,
> don't duplicate it. Signing-key custody lives in
> [`docs/saas-deployment/license-key-custody.md`](../saas-deployment/license-key-custody.md)
> (ADR 0008 §1).

## Scope

The Fleet Console is the **inverse of isA_Admin** (ADR 0009 §5): broad-but-shallow
(metadata across every customer) where isA_Admin is deep-but-narrow (business data
for one). It is a **separate vendor-side deployment** — never under any `/admin`
path, never reaching a customer database.

This runbook covers the **vendor operator** workflow against the implemented
component in `fleet/` (`fleet_console/` package + `console-ui/` SPA):

- the **operator API** `fleet_console/api.py` (`create_fleet_api(...)`), served by
  `fleet/console-ui/server.py` — roster, customers, expiring, showback, issue,
  renew, revoke. Vendor-internal (behind VPN/SSO), **not** internet-facing.
- the **telemetry intake** `fleet_console/intake.py` (`create_intake_app(...)`) —
  the single internet-facing `POST /telemetry` + `POST /telemetry/upload`.

It does NOT cover installing/swapping a `license.json` inside a customer namespace
(that is the #372 [`license-operator.md`](./license-operator.md) runbook) and it
NEVER touches customer business data (ADR 0009 §5 — every response is built only
from ledger columns + telemetry metadata).

## Mental model (read first)

- **The issuance ledger is the floor of truth.** Issuing a license = signing the
  artifact **and** writing one ledger row, in one transaction that "cannot diverge"
  (ADR 0009 §1). The roster works with **zero telemetry** — which is exactly what a
  fully air-gapped customer contributes.
- **The signing key is never hot.** `issue`/`renew` need the offline ed25519
  *private* key; the operator supplies it **per request**, sourced from the offline
  keystore/HSM, and it is dropped after the call (ADR 0009 §2). `revoke` needs no
  key.
- **Telemetry is opt-in, authenticated, metadata-only.** Three reachability tiers
  (realtime / periodic / offline) land in ONE store; each request carries a
  per-deployment HMAC tied to the ledger. No business records, no PII (ADR 0009
  §3/§5).
- **Revoke here is a vendor-side ledger flag, not a remote kill.** An offline-signed
  `license.json` cannot be killed remotely once shipped (§3 below).
- **Silence is shown honestly.** Silent/air-gapped deployments surface as "no
  telemetry since X", never a fabricated dashboard (ADR 0009 §4).

---

## 0. Reach the console

```bash
export FLEET_DATABASE_URL="postgresql+psycopg://.../fleet"
# Optional dev/test pin ONLY; leave unset in prod so the operator pastes the
# offline signing key per issue/renew request (ADR 0009 §2):
# export FLEET_SIGNING_KEY_FILE="/path/to/offline-ed25519.pem"
PYTHONPATH="$PWD/isA_common:$PWD/fleet" \
  uvicorn console_ui.server:app --port 8077     # or: python fleet/console-ui/server.py
```

This serves the **operator API** (`/fleet/*`) + the SPA. The first time, apply the
DDL (no migration runner yet — plain forward-only SQL, ADR 0009 implementation
sketch):

```bash
psql "$FLEET_DATABASE_URL" -f fleet/migrations/0001_issuance_ledger.sql
psql "$FLEET_DATABASE_URL" -f fleet/migrations/0002_deployment_secret.sql
psql "$FLEET_DATABASE_URL" -f fleet/migrations/0003_telemetry_record.sql
psql "$FLEET_DATABASE_URL" -f fleet/migrations/0004_issuance_revocation.sql
```

The internet-facing **intake** (`POST /telemetry*`) is a **separate deployable**
(`fleet_console.create_intake_app`) in its own trust zone — do not co-host it on the
operator console (ADR 0009 §3/§5).

---

## 1. Issue a license

`POST /fleet/issue` runs the ADR 0009 §2 issuance workflow: it **signs** the
`license.json` (wrapping the offline `isa_common.license_sign`) **and** writes the
ledger row **and** mints a per-deployment telemetry credential — all atomically
("both or neither"; the signed artifact is returned only after the DB commit).

Inputs (request body — `extra="forbid"`, so business data is rejected 422):

| Field | Notes |
|---|---|
| `customer_id` | e.g. `SN` |
| `edition` | **must match** the target deployment's runtime `ISA_EDITION` (e.g. `on-prem-full`) — see #372 runbook |
| `entitled_modules` | source of truth for which modules deploy (ADR 0008 §5) |
| `quota_tier` | maps to `TierQuota` (ADR 0008 §4); `enterprise` → unlimited |
| `expires_at` | hard expiry (UTC, ISO-8601); omit for a perpetual license |
| `not_before` | earliest-valid instant (optional) |
| `grace_days` | soft window after expiry (e.g. `30`) |
| `seats` | `-1` = unlimited |
| `license_id` | optional; auto-derived if omitted; renewals get a fresh id |
| `delivery` | ledger-only delivery note (e.g. `offline-bundle`, ADR 0007) |
| `signing_key_pem` | **the offline ed25519 private key, PEM text** — supplied per request, dropped after the call |

> **Key custody (ADR 0009 §2, ADR 0008 §1).** The private key is an *issuance
> secret* kept offline in the **same custody as release signing** — never in a repo,
> image, CI secret, or any customer-reachable surface. See
> [`docs/saas-deployment/license-key-custody.md`](../saas-deployment/license-key-custody.md).
> In prod, leave `FLEET_SIGNING_KEY_FILE` unset and paste the PEM into the request;
> the console "calls the signer, it does not run a hot key service." A leaked
> *public* key cannot forge a license; treat the *private* key like the
> release-signing key.

```bash
curl -sS -X POST http://localhost:8077/fleet/issue \
  -H 'Content-Type: application/json' \
  -d '{
        "customer_id": "SN",
        "edition": "on-prem-full",
        "entitled_modules": ["erp","mes","commercial_tower"],
        "quota_tier": "enterprise",
        "expires_at": "2027-06-08T00:00:00Z",
        "grace_days": 30,
        "seats": -1,
        "delivery": "offline-bundle",
        "signing_key_pem": "'"$(cat /path/to/offline-ed25519.pem)"'"
      }'
```

The response (`201`) carries:

- `license` — the signed `license.json` body (dict, with base64 `signature`).
  **Deliver it offline** in the bundle (ADR 0007) and install it per the #372
  runbook (`isa-license` ConfigMap + roll).
- `deployment_secret_id` — the **non-secret** pointer to the minted telemetry
  credential. The **secret value itself is NOT returned over this API** (it must not
  ride an HTTP response). It is stored isolated in the `deployment_secret` table and
  delivered to the deployment via the **same offline/secret bundle** as the rest of
  its secrets (for SN: `ISA_TELEMETRY_SECRET` / `ISA_DEPLOYMENT_SECRET_ID`). The
  deployment uses it to HMAC-sign its usage bundles (§4).
- `ledger_row` — the persisted metadata row (now visible in the roster).

So one issue produces three coupled outputs: **signed `license.json` + a minted
per-deployment telemetry credential (`deployment_secret_id` + secret) + a ledger
row**.

---

## 2. Renew

`POST /fleet/renew` issues a **new** license that **supersedes** the prior ledger
row and mints a **fresh** telemetry credential — all in one transaction. The new row
becomes current (`superseded_by IS NULL`); the prior drops out of the roster but is
retained for audit.

Body = the same fields as issue (§1), plus `prior_license_id` (the license being
superseded) and a distinct `license_id`:

```bash
curl -sS -X POST http://localhost:8077/fleet/renew \
  -H 'Content-Type: application/json' \
  -d '{
        "prior_license_id": "sn-prod-2026",
        "license_id": "sn-prod-2027",
        "customer_id": "SN",
        "edition": "on-prem-full",
        "entitled_modules": ["erp","mes","commercial_tower"],
        "quota_tier": "enterprise",
        "expires_at": "2028-06-08T00:00:00Z",
        "grace_days": 30,
        "delivery": "offline-bundle",
        "signing_key_pem": "'"$(cat /path/to/offline-ed25519.pem)"'"
      }'
```

Renewing an already-superseded (or non-existent) `prior_license_id`, or reusing the
prior id as the new one, is rejected (`400`).

**Delivery on the deployment side.** The response again carries the signed
`license.json` + a **new** `deployment_secret_id`. Hand both to the operator:

- swap the new `license.json` on the deployment — ConfigMap replace + `rollout
  restart` — per [`license-operator.md`](./license-operator.md) §3 (there is no
  in-place edit; the startup hard-check re-runs on each restarting pod).
- refresh the deployment's secret bundle with the new telemetry secret. The old
  secret retires at the renewal boundary (**implicit rotation**, ADR 0009 §3) — the
  renewed deployment signs telemetry with the new credential.

---

## 3. Revoke

`POST /fleet/revoke` flags the ledger row: `IssuanceService.revoke(license_id,
reason=...)` stamps `revoked_at` (server clock) + optional `revoked_reason`
(migration `0004_issuance_revocation.sql`). **No signing key is needed.**

```bash
curl -sS -X POST http://localhost:8077/fleet/revoke \
  -H 'Content-Type: application/json' \
  -d '{"license_id":"sn-prod-2026","reason":"contract terminated"}'
```

**What revoke DOES:**

- the row's derived `status` becomes `revoked`; it drops out of the active roster /
  expiry / showback (queries filter `revoked_at IS NULL` alongside `superseded_by IS
  NULL`).
- the row is **retained for audit** (recoverable history, not deleted).

**What revoke does NOT do (be honest — ADR 0009, see [`license-operator.md`](./license-operator.md) §5):**

- it does **NOT** remotely kill an already-deployed license. An offline-signed
  `license.json` cannot be killed once shipped — least of all to an air-gapped
  deployment (no egress, no CRL, no phone-home). A pod already running keeps serving
  (runtime fail-open, ADR 0008 §3).
- True kill-on-the-deployment (online revocation / CRL) is a **future** extension,
  explicitly **out of scope** today.

Practical enforcement of a revocation is the **per-deployment** path: let the
license expire (or issue a short-lived replacement), then a rollout hits the startup
gate, plus the `over_license` showback record as the contractual lever. Plan
revocations as contract events with lead time, not an instant remote switch.
Revoking a superseded or already-revoked row is rejected (`400`).

---

## 4. Offline-upload procedure (air-gapped customers)

For a fully air-gapped customer the console **cannot pull** (FW-OUT-001) and the
deployment **cannot push** over a VPN. Telemetry travels as a **hand-carried, signed
usage bundle** (ADR 0009 §3 offline tier). The full loop:

1. **Customer operator exports a signed usage bundle** from their isA_Admin /
   telemetry service (#376). The exporter serialises a **metadata-only** payload
   (`license_id`, `last_seen`, `active_edition`, `active_modules`, `module_usage`
   counters, `showback_totals`, `over_license` — ADR 0008 §3) and HMAC-signs the raw
   bytes with the deployment's telemetry secret using the #374 scheme
   (`sign_telemetry(secret, payload_bytes)` → lowercase hex HMAC-SHA256):

   ```bash
   # On the air-gapped deployment (the #376 exporter):
   python -m microservices.telemetry_service.usage_bundle \
     --out usage_bundle.json
   #   → writes the metadata-only bundle + prints the X-Deployment-Secret-Id and
   #     X-Telemetry-Signature (HMAC-SHA256, lowercase hex over the raw bytes)
   ```

   The signature is over the **raw bytes exactly as written** — the file the vendor
   uploads must be byte-identical to what was signed.

2. **Hand-carry** the `usage_bundle.json` (+ its `deployment_secret_id` and
   signature) out of the air-gap by whatever approved offline path is used for that
   customer. Cadence = whenever (no schedule).

3. **Vendor uploads it** to the internet-facing intake via `POST /telemetry/upload`
   (multipart file). Same auth + same strict schema as the realtime path — only the
   transport and the recorded `source` (`offline-upload`) differ:

   ```bash
   curl -sS -X POST https://intake.example.com/telemetry/upload \
     -H "X-Deployment-Secret-Id: dep-sn-7f3a1c0b" \
     -H "X-Telemetry-Signature: <hex-hmac-sha256-over-raw-bytes>" \
     -F "file=@usage_bundle.json"
   ```

4. **Intake validates and stores it** (the single `auth → validate → persist`
   pipeline in `intake.py`):
   - **HMAC first (401).** `verify_telemetry_hmac(session, deployment_secret_id,
     raw, signature)` recomputes the HMAC over the raw bytes against the secret in
     the isolated `deployment_secret` table, **before any parsing**. Missing/bad →
     `401`.
   - **Metadata only (422).** Validated against `TelemetryPayload`
     (`extra="forbid"`) — any unknown field (smuggled business data / PII) → `422`.
   - **Tied to the ledger.** `license_id` must exist in `issuance_ledger`; if the
     ledger row pins a `deployment_secret_id` it must match the caller's (`404`
     unknown license / `403` mismatch).
   - On success → one metadata-only `telemetry_record` row (`201 accepted`).

**The three reachability tiers** (ADR 0009 §3) all land in the same store:

| Tier | Customer | Endpoint | `source` |
|---|---|---|---|
| **realtime** | SaaS (isA's own cloud) | `POST /telemetry` | `realtime` |
| **periodic** | connected on-prem (SN over VPN) | `POST /telemetry` | `realtime` |
| **offline** | fully air-gapped | `POST /telemetry/upload` | `offline-upload` |

A leaked deployment secret only forges **that** customer's telemetry (metadata-only)
— **never a license** (licenses need the offline ed25519 private key, which never
enters this system). On a leak, rotate the credential (`rotate_credential(...)`,
ADR 0009 §3) and re-bundle — it never touches the license.

Silent deployments (never reported, or stale past threshold) are surfaced **honestly**
as "no telemetry since X" in the roster/showback — never fabricated (§5).

---

## 5. Reading the fleet

The operator API (and the `console-ui` SPA over it) gives four read views. All are
**metadata only** — built from ledger columns + telemetry metadata, with no path to
a customer DB.

```bash
# Roster — every CURRENT license × edition × derived status + honest last-seen/silence
curl -sS http://localhost:8077/fleet/roster
curl -sS 'http://localhost:8077/fleet/roster?include_superseded=true'   # full history

# One customer + entitlement view (union of entitled_modules)
curl -sS http://localhost:8077/fleet/customers/SN

# Expiry calendar / renewal alerts — current licenses expiring within N days
curl -sS 'http://localhost:8077/fleet/expiring?within_days=30'

# Showback rollup per customer — honest about telemetry state
curl -sS http://localhost:8077/fleet/showback
```

**Derived roster status** (`derive_status`, metadata-layer mirror of the
in-deployment `isa_common.license` semantics — the fleet layer never loads the
signed artifact):

| Status | Meaning |
|---|---|
| `current` | in-window, beyond the expiring threshold |
| `expiring` | within `expiring_within_days` (default 30) of `expires_at` |
| `expired` | past `expires_at` (the deployment's own grace handling is local) |
| `perpetual` | no `expires_at` |
| `revoked` | the ledger row is flagged (§3) |

**Showback `telemetry_state`** (and what "silent" means):

| State | Meaning |
|---|---|
| `realtime` | newest record came from a SaaS direct push (`source=realtime`) |
| `last-upload` | newest record came from a connected/offline upload — last known values |
| `none` | **silent** — never reported, or stale past the silence threshold → explicit `note` "no telemetry since X" (or "no telemetry on record"). Never fabricated. |

Superseded and revoked rows are excluded from the active views (filtered
`superseded_by IS NULL` AND `revoked_at IS NULL`); `?include_superseded=true` and the
retained revoked rows are available for audit.

---

## 6. Key custody (cross-reference)

Signing-key custody is a **standing vendor responsibility**, the same custody as
release signing:

- [`docs/saas-deployment/license-key-custody.md`](../saas-deployment/license-key-custody.md)
  (#366) — the ed25519 keypair, `keygen`, offline private-key storage, public-key
  distribution (image bake / ConfigMap), and rotation at the renewal boundary.
- ADR 0008 §1 — the license schema + signing the canonical body; the license is
  **never editable from isA_Admin** (ADR 0008 §7), authoring lives only in the
  offline tool that the issuance workflow (§1) wraps.

The **telemetry** HMAC secret (§1/§4) is a *separate, symmetric, lower-stakes*
credential, isolated in the `deployment_secret` table — its blast radius is
telemetry only, never a license.

---

## Cross-references

- [`docs/adr/0009-vendor-fleet-license-console.md`](../adr/0009-vendor-fleet-license-console.md)
  — authoritative design (§1 ledger, §2 issuance, §3 telemetry/tiers/offline-upload,
  §4 UI, §5 data boundary).
- [`docs/adr/0008-license-entitlement.md`](../adr/0008-license-entitlement.md) — the
  per-deployment license & entitlement layer (the half this console aggregates).
- [`docs/runbooks/license-operator.md`](./license-operator.md) (#372) — the
  **per-deployment** operator runbook: install/swap the `license.json` on a
  namespace, grace/expiry behavior, revoke-by-expiry. The deployment-side
  counterpart to this runbook.
- [`docs/saas-deployment/license-key-custody.md`](../saas-deployment/license-key-custody.md)
  (#366) — signing-key custody.
- [`fleet/README.md`](../../fleet/README.md) — the implemented component (ledger,
  issuance, telemetry credential, intake, API, console-ui).
