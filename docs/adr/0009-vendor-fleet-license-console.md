# ADR 0009 — Vendor Fleet / License Console (cross-customer, vendor-side)

> Status: Proposed (2026-06-08)
> Story: TBD. Depends on ADR 0008 (license & entitlement). Sibling to ADR 0006
> (edition), ADR 0007 (artifact delivery). Resolves the "manage ALL my customers
> in one place, on-prem and SaaS" question that ADR 0008 §7 explicitly pushes out
> of isA_Admin's scope.

## Context

isA_Admin is a **single-deployment** operator console (ADR 0008 §7): it sees only
the data of the one deployment it is wired to. For SaaS that one deployment is
multi-tenant, so it covers all SaaS tenants; for on-prem (SN) it is deployed
per-customer, inside the customer's isolated/air-gapped environment, scoped to
that customer. **There is deliberately no isA_Admin that spans customers** — their
business data physically lives in their own environments, which is the isolation
they pay for.

But the **vendor** (isA) still needs one place to answer: *who are all my
customers, on what edition, with which modules entitled, expiring when, using how
much?* — across on-prem **and** SaaS. That is a different system with a different
data boundary:

- isA_Admin manages a deployment's **business data** (deep, one customer).
- This console manages the fleet's **metadata** (broad, all customers, no business
  data).

Crucially, the seed for this already exists: **issuing a license (ADR 0008 §1)
already produces the customer roster.** Every time isA signs a `license.json` it
knows `customer_id / edition / entitled_modules / expires_at`. The fleet console
is, at its floor, a durable ledger of those issuances — authoritative even if not
a single deployment ever reports back.

The air-gap constraint (FW-OUT-001) means the console **cannot pull** from customer
clusters. So its data is: (a) what isA itself issued (always available), plus
(b) what each deployment **chooses to push** back (variable).

## Decision

Build a **vendor-side Fleet / License Console** — a small isA-hosted app whose data
boundary is **fleet metadata only**, fed by two sources: the **license-issuance
ledger** (authoritative) and **opt-in telemetry** (best-effort). It never connects
to a customer database.

### 1. License-issuance ledger — the source of truth

A vendor-side datastore (Postgres) where **every license issuance is a row**.
Issuing a license = signing the artifact (ADR 0008 §1) **and** writing the ledger
in one workflow; the two cannot diverge.

```jsonc
// ledger row (one per issued license / renewal)
{
  "license_id": "sn-prod-2026",
  "customer_id": "SN",
  "edition": "on-prem-full",
  "entitled_modules": ["erp","mes","commercial_tower", ...],
  "quota_tier": "enterprise",
  "issued_at": "2026-06-08T00:00:00Z",
  "expires_at": "2027-06-08T00:00:00Z",
  "superseded_by": null,          // set when a renewal is issued
  "delivery": "offline-bundle",   // how it was shipped (ADR 0007)
  "deployment_secret_id": "dep-sn-7f3a"   // see §3, telemetry auth
}
```

This alone answers most fleet questions (roster, expiry calendar, who-has-what)
**with zero telemetry** — which is exactly what air-gapped customers will
contribute. It is the floor of truth; telemetry only enriches it.

### 2. Signing workflow wraps `isa-license-sign`

The offline signing tool from ADR 0008 §1 becomes a **console action** (still
offline-key-custodied): "Issue license for customer X" → produces the signed
`license.json` + the ledger row + a per-deployment telemetry credential (§3),
bundled for delivery (ADR 0007). Renewals supersede the prior row. Private key
custody stays offline (same custody as release signing); the console calls the
signer, it does not hold the key in a hot service.

### 3. Telemetry intake — opt-in, authenticated, three reachability tiers

At issuance, each deployment also gets a **per-deployment credential** (an HMAC
secret / API key, `deployment_secret_id` in the ledger) baked into its secret
bundle. Telemetry is authenticated with it and tied back to the ledger row. The
console exposes one internet-facing intake endpoint; how data reaches it depends
on the customer's network:

| Tier | Customer | Mechanism |
|---|---|---|
| **Realtime** | SaaS (isA's own cloud) | direct internal push; full, continuous |
| **Periodic** | Connected on-prem (SN over VPN) | deployment POSTs a signed heartbeat/showback when the VPN is up; gaps tolerated |
| **Offline** | Fully air-gapped | operator **exports** a signed usage bundle from their isA_Admin and **uploads** it to the console manually; cadence = whenever |

Payload is **metadata only**: `license_id`, `last_seen`, edition flags actually
active, module usage counters, showback totals (ADR 0008 §3's `over_license`
flag). **No business records, no PII, no tenant content.** The intake validates
the HMAC against the ledger's `deployment_secret_id` before accepting.

### 4. Fleet UI

A thin operator UI (can reuse the isA_Admin Next.js stack, but a **separate
deployment** on the vendor side — it is not "isA_Admin with cross-customer mode",
which ADR 0008 §7 forbids):

- **Roster**: all customers × edition × status (issued / last-seen / expired).
- **Expiry calendar + renewal alerts** (drives ADR 0008's contractual lever).
- **Entitlement view**: which modules each customer is licensed for.
- **Showback rollup**: usage per customer (realtime for SaaS, last-uploaded for
  on-prem, "no telemetry" for silent air-gapped — shown honestly as such).
- **Issue / renew / revoke** actions → §2 signing workflow.

### 5. Data boundary (the inverse of isA_Admin)

| | isA_Admin (ADR 0008 §7) | Fleet Console (this ADR) |
|---|---|---|
| Lives | inside each deployment | vendor side, one instance |
| Sees | one customer's **business data** | **all** customers' **metadata** |
| Customer business data | yes | **never** |
| License | read-only display | **issues / renews / revokes** |
| Reaches into customer DB | n/a (it is the DB's UI) | **never** (push-only intake) |

This boundary is the whole point: the console is broad-but-shallow (metadata
across everyone) exactly because isA_Admin is deep-but-narrow (business data for
one). Neither crosses into the other's lane.

## Consequences

**Positive**
- One vendor-side answer to "all my customers, op + saas" without violating
  per-customer isolation or the air-gap.
- The ledger is authoritative with zero telemetry, so it works even for the
  hardest (fully air-gapped) customers — they just contribute less *usage* data.
- Reuses ADR 0008's signing as the single issuance path; license sprawl
  (untracked `license.json` files in chats/emails) is eliminated.

**Negative / risks**
- **New internet-facing intake endpoint** = a security surface; mitigated by
  per-deployment HMAC tied to the ledger, metadata-only payloads, and the option
  to run intake offline-upload-only for the most sensitive customers.
- **Air-gapped usage visibility is inherently partial** — honest "no telemetry
  since X" states, not fabricated dashboards. Accept and surface it.
- **Private-key custody** for signing is now a standing vendor responsibility
  (shared with release signing per ADR 0007).
- Clock/identity integrity of uploaded offline bundles depends on the
  per-deployment HMAC; a leaked deployment secret only forges *that* customer's
  telemetry, not a license (licenses need the offline private key).

## Alternatives considered

- **Extend isA_Admin to a cross-customer mode** — rejected: breaks per-customer
  isolation (ADR 0008 §7) and is physically impossible for air-gapped on-prem
  (can't reach in). The console must be a separate vendor-side system fed by
  push/issuance, not pull.
- **Phone-home license validation** (deployments call vendor to validate) —
  rejected: incompatible with the air-gap (ADR 0008 Context); also makes customer
  uptime depend on vendor reachability.
- **No console; track licenses in a spreadsheet** — rejected: license sprawl, no
  renewal alerting, no usage rollup, error-prone issuance.

## Relationship to ADR 0008

- **ADR 0008** issues + enforces a license **inside one deployment** (offline
  signed file, startup hard-check, runtime fail-open, per-profile config).
- **ADR 0009** aggregates **issuance + optional telemetry on the vendor side**
  into one fleet view. 0008 is the per-customer half; 0009 is the cross-customer
  half. They share exactly one thing — the signing step — which 0009 turns into
  the issuance ledger.

## Implementation sketch (follow-up, after ADR 0008 lands)

1. Ledger schema + the issuance workflow (sign → ledger row → bundle).
2. Per-deployment telemetry credential, minted at issuance, into the secret bundle.
3. Intake endpoint (HMAC-authenticated, metadata-only schema, offline-upload path).
4. isA_user "export signed usage bundle" action (the air-gapped upload source).
5. Fleet UI (roster, expiry calendar, entitlement, showback, issue/renew/revoke).
6. Runbook: issuance, renewal, revocation, offline-upload procedure for air-gapped
   customers.
