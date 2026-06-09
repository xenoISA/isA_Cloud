# fleet — Vendor Fleet / License Console (ADR 0009)

This is the **vendor-side** Fleet / License Console: a small, isA-hosted component
whose data boundary is **fleet metadata only**. It is the cross-customer half of the
licensing system.

- **ADR 0008** issues + enforces a license *inside one deployment* (offline signed
  `license.json`, startup hard-check). That is the per-customer half.
- **ADR 0009** (this component) aggregates issuance — and later opt-in telemetry —
  on the vendor side into one fleet view across **all** customers (on-prem + SaaS).

It is a **separate deployment** from isA_Admin and the inverse of it (ADR 0009 §5):

| | isA_Admin (ADR 0008) | Fleet Console (this) |
|---|---|---|
| Lives | inside each deployment | vendor side, one instance |
| Sees | one customer's **business data** | **all** customers' **metadata** |
| Customer business data | yes | **never** |
| Reaches into customer DB | n/a | **never** (push-only intake) |

**Hard rule:** this component is **metadata-only**. It NEVER connects to a customer
database and NEVER stores customer business data or PII. The ledger holds only what
isA itself signed: `license_id / customer_id / edition / entitled_modules /
quota_tier / dates / delivery`.

## What's here

The **license-issuance ledger** + the **issuance workflow** + a **library-level
query API** (#373), plus the **telemetry intake endpoint** (#375).

```
fleet/
├── README.md                         # this file
├── fleet_console/                    # the Python package
│   ├── __init__.py                   # public surface (re-exports)
│   ├── models.py                     # SQLAlchemy: Base + IssuanceLedger (#373)
│   ├── issuance.py                   # IssuanceService / issue_license / renew_license (#373)
│   ├── queries.py                    # roster / by_customer / expiring_soon (#373)
│   ├── telemetry_credential.py       # #374: mint/verify per-deployment HMAC credential
│   ├── intake.py                     # telemetry intake: POST + file-upload, HMAC, strict schema (#375)
│   ├── api.py                        # #377: operator-facing fleet API (roster/expiry/entitlement/showback/issue/renew/revoke)
│   ├── telemetry_models.py           # SQLAlchemy: TelemetryRecord store (#375)
│   └── telemetry_queries.py          # honest-silence / last_seen_per_deployment (#375)
├── console-ui/                       # #377: the Fleet UI — a SEPARATE deployable SPA
│   ├── server.py                     # mounts create_fleet_api(...) + serves the SPA
│   ├── index.html / app.js / app.css # zero-build single-page console
├── migrations/
│   ├── 0001_issuance_ledger.sql      # CREATE TABLE issuance_ledger (Postgres DDL)
│   ├── 0002_deployment_secret.sql    # CREATE TABLE deployment_secret (#374, sensitive)
│   ├── 0003_telemetry_record.sql     # CREATE TABLE telemetry_record (Postgres DDL, #375)
│   └── 0004_issuance_revocation.sql  # ALTER issuance_ledger ADD revoked_at/revoked_reason (#377)
└── tests/
    ├── test_issuance.py              # sign->ledger round-trip, renewal, query filters (#373)
    ├── test_telemetry_credential.py  # #374: mint, verify, rotation, migration DDL
    ├── test_intake.py                # HMAC/401, strict-schema/422, file-upload, silence query (#375)
    └── test_api.py                   # #377: roster/expiry/issue/renew/revoke/showback + metadata-only
```

## Telemetry intake (ADR 0009 §3, #375)

`fleet_console/intake.py` is the single internet-facing intake for opt-in fleet
telemetry. All three ADR 0009 §3 reachability tiers land in ONE store
(`telemetry_record`):

| Tier | Endpoint | `source` |
|---|---|---|
| realtime (SaaS) / periodic (connected on-prem) | `POST /telemetry` (JSON body) | `realtime` |
| offline (air-gapped) | `POST /telemetry/upload` (multipart file) | `offline-upload` |

Both entrypoints consume the SAME signed **envelope** the deployment-side
producer (#376) emits — `{payload, deployment_secret_id, signature}` — and share
ONE parse→auth→validate→persist pipeline:

1. **Parse the envelope (422).** The request body (`POST /telemetry`) or the
   uploaded file bytes (`POST /telemetry/upload`) is the envelope JSON; malformed
   JSON or a missing `payload`/`deployment_secret_id`/`signature` key → 422.
2. **Auth first (401).** The `signature` is HMAC-SHA256 (the #374 contract) over
   the CANONICAL payload bytes, re-derived EXACTLY as the producer did:
   `json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":")).encode()`.
   It is verified via `verify_telemetry_hmac` against the secret for the envelope's
   `deployment_secret_id` BEFORE the payload schema is validated or persisted. The
   credential + signature ride INSIDE the envelope (no transport headers), so the
   air-gapped file upload works with the file alone.
3. **Metadata only (422).** The `payload` sub-dict is validated against
   `TelemetryPayload`, a strict Pydantic model with
   `model_config = ConfigDict(extra="forbid")` — any unknown field (smuggled
   business data / PII) is rejected. Fields: `license_id`, `last_seen`,
   `active_edition`, `active_modules`, `module_usage`, `showback_totals`,
   `over_license` (ADR 0008 §3).
4. **Tied to the ledger.** `license_id` must exist in `issuance_ledger`; when the
   ledger row pins a `deployment_secret_id` it must match the envelope's credential.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fleet_console import Base, create_intake_app

engine = create_engine("postgresql+psycopg://.../fleet")
Base.metadata.create_all(engine)  # builds issuance_ledger AND telemetry_record
app = create_intake_app(sessionmaker(bind=engine, class_=Session))  # FastAPI app
# or: build_intake_router(session_factory) to mount into a larger app.
```

**Honest silence (ADR 0009 §4).** `last_seen_per_deployment(session, ...)` returns
one row per current license joined to its newest telemetry — never-reported
deployments come back with `last_seen=None`/`silent=True` (the explicit "no
telemetry since X" the UI #377 must show for silent/air-gapped customers).

> **#374 credential (now merged).** Intake authenticates via
> `telemetry_credential.verify_telemetry_hmac(session, deployment_secret_id,
> payload_bytes, signature)` — the #374 contract, now backed by its real
> per-deployment secret store (the isolated `deployment_secret` table), not an env
> stub. The session in the request path (from `session_factory`) is threaded into
> the verify call so the secret is looked up from the DB before any parsing.

### Package layout convention (for #374 / #375 / #377)

`fleet_console/` is the package root. New vendor-side pieces go here:

- **#374 telemetry credential** — DONE. `fleet_console/telemetry_credential.py`
  mints a per-deployment HMAC secret at issuance, writes its `deployment_secret_id`
  onto the ledger row, and stores the secret in an isolated `deployment_secret`
  table. See "Telemetry credential" below.
- **#375 intake endpoint** — the internet-facing, HMAC-authenticated, metadata-only
  telemetry intake. Suggested: `fleet_console/intake.py` (+ an `app.py` / ASGI
  entry). **Call `fleet_console.verify_telemetry_hmac(session,
  deployment_secret_id, payload_bytes, signature)` to authenticate** — do not
  re-implement the HMAC; the scheme is defined once in #374 (below).
- **#377 fleet API + UI** — DONE. `fleet_console/api.py` is the HTTP layer over the
  `queries.py` / `issuance.py` / `telemetry_queries.py` library functions
  (`create_fleet_api(session_factory, signing_key_pem=...)`), and `console-ui/` is the
  separate-deployable SPA over it. See "Fleet console API + UI" above.

## Fleet console API + UI (ADR 0009 §2/§4, #377)

The query / issuance / telemetry helpers above are a Python **library**. The Fleet
UI (#377) needs them over HTTP, so this issue adds an **operator-facing API** and a
**UI** — a coherent vertical slice. (This is distinct from `intake.py`, which is the
internet-facing telemetry *push* from deployments, not the operator read/issue API.)

### `fleet_console/api.py` — the operator API (FastAPI, `create_*` factory)

```python
from sqlalchemy.orm import Session, sessionmaker
from fleet_console import Base, create_fleet_api
app = create_fleet_api(sessionmaker(bind=engine, class_=Session))  # FastAPI app
# or build_fleet_router(session_factory, signing_key_pem=...) to mount elsewhere.
```

| Endpoint | Wraps (#373/#375 library fn) | Notes |
|---|---|---|
| `GET /fleet/roster` | `queries.roster()` + `telemetry_queries.last_seen_per_deployment()` | each row gets a derived `status` (current / expiring / expired / perpetual / revoked) + honest `last_seen`/`silent` |
| `GET /fleet/customers/{id}` | `queries.by_customer()` | + entitlement view (union of `entitled_modules`) |
| `GET /fleet/expiring?within_days=N` | `queries.expiring_soon()` | expiry calendar / renewal alerts |
| `GET /fleet/showback` | `telemetry_queries.last_seen_per_deployment()` + `latest_record()` | per-customer rollup; `telemetry_state` = `realtime` (SaaS) / `last-upload` (connected/offline) / `none` (silent → honest "no telemetry since X") |
| `POST /fleet/issue` | `IssuanceService.issue()` | signs + writes ledger; returns the signed license + non-secret `deployment_secret_id` |
| `POST /fleet/renew` | `IssuanceService.renew()` | supersedes the prior row |
| `POST /fleet/revoke` | `IssuanceService.revoke()` | ledger flag (see below) |

**Metadata-only (ADR 0009 §5).** Every response model is built ONLY from ledger
columns + telemetry *metadata* (last_seen, active edition/modules, usage **counters**,
showback totals, `over_license`). The API has no path to a customer DB at all. The
issue/renew/revoke request bodies set `extra="forbid"`, so smuggled business data /
PII is rejected (422) — the same guard intake uses.

**Signing-key custody (ADR 0009 §2).** `issue`/`renew` need the offline ed25519
private key. The API never holds it hot: `create_fleet_api(..., signing_key_pem=...)`
is the dev/test pin, but in real ops the operator supplies `signing_key_pem` (PEM)
**in the request body**, sourced from the offline keystore/HSM at issuance time, and
it is dropped after the call. `revoke` needs no key (it does not sign).

### Revoke model (ADR 0009: online revocation is a FUTURE extension)

An offline-signed `license.json` **cannot be remotely killed** once shipped (least of
all to an air-gapped deployment); ADR 0009 scopes online revocation / CRL as a future
online extension. So at this layer **revoke is a vendor-side ledger flag**:
`IssuanceService.revoke(license_id, reason=...)` stamps `revoked_at` (+ `revoked_reason`)
on the ledger row (migration `0004_issuance_revocation.sql`). A revoked row is
**retained for audit** but, like a superseded row, drops out of the active roster /
expiry / showback (the queries now filter `revoked_at IS NULL` alongside
`superseded_by IS NULL`). Revoking a superseded or already-revoked row is rejected.
True kill-on-the-deployment is the future CRL/online extension.

### UI — `fleet/console-ui/` (a SEPARATE deployable, NOT under `/admin`)

A lean **single-page app** (static `index.html` + `app.js` + `app.css`, no build
step) served by `console-ui/server.py`, which mounts `create_fleet_api(...)` and the
static SPA into one **separate** vendor-side FastAPI app.

**Why a FastAPI-served SPA instead of a full Next.js app?** ADR 0009 §4 allows reusing
the isA_Admin Next.js stack, and #377 explicitly permits "a minimal Next app (or even
a single-page app served by the FastAPI) … AS LONG AS it calls the real endpoints and
is clearly a separate deployable." A full Next scaffold + build is heavy to provision
and verify in this environment for what is a thin operator console; a zero-build SPA
over the real API is faster to ship and trivially verifiable (booted in-process
against the live endpoints). It remains a **distinct deployable** — its own
`server.py`, its own trust zone, never co-hosted on the public intake and never under
any `/admin` path (it is the inverse of isA_Admin, ADR 0009 §5). Swapping in a Next
app later is purely a frontend change; the API contract is the boundary.

Views: **Roster** (customer × edition × status + last-seen/silence), **Expiry /
renewal alerts**, **Entitlements** (per customer), **Showback** (honest "no telemetry
since X" for silent/air-gapped), and **Issue / Renew / Revoke** controls wired to the
API. Run:

```bash
export FLEET_API_TOKEN="...operator bearer token..."   # REQUIRED — see auth note below
PYTHONPATH="$PWD/isA_common:$PWD/fleet:$PWD/fleet/console-ui" \
    uvicorn server:app --app-dir fleet/console-ui --port 8077
# or: python fleet/console-ui/server.py
# FLEET_DATABASE_URL=postgresql+psycopg://.../fleet  (defaults to a local sqlite file)
# FLEET_SIGNING_KEY_FILE=...  (optional dev pin; unset => operator pastes key per request)
```

### Operator auth — required, fail-closed (B2, #377)

Every `/fleet/*` route is gated by an operator bearer token. The whole API router
carries a `require_operator` dependency (`create_fleet_api(..., operator_token=...)`,
defaulting to **`FLEET_API_TOKEN`** in the environment), so all current and future
routes are covered — there is no open route.

- **Configure `FLEET_API_TOKEN`** before running the console. If it is **unset**, the
  API **fails closed**: every route returns **503 `fleet auth not configured`** (it
  never serves open). A signing key pinned (`FLEET_SIGNING_KEY_FILE`) without a token
  set is **refused at startup** — a hot key behind no auth is an open license-minting
  oracle.
- The operator / SPA must send the token on **every** call as
  **`Authorization: Bearer <FLEET_API_TOKEN>`** (or, equivalently, `X-Fleet-Token:
  <token>`). A missing/mismatched token → **401**. The token is compared
  constant-time (`hmac.compare_digest`) and is never logged.
- The SPA-serving `console-ui/server.py` mounts the static SPA over this same API; it
  does **not** bypass auth — the operator supplies the token from the browser. (No
  login UI is built here; behind VPN/SSO the token is the operator credential.)
- Only `/healthz` is unauthenticated (liveness).

## The issuance workflow (ADR 0009 §1–2)

Issuing a license is **one workflow** that signs the artifact **and** writes the
ledger row — "the two cannot diverge" (ADR 0009 §1). It wraps the existing offline
signer `isa_common.license_sign` (issue #366); it does **not** reimplement signing.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fleet_console import Base, IssuanceRequest, IssuanceService

engine = create_engine("postgresql+psycopg://.../fleet")  # or sqlite for tests
Base.metadata.create_all(engine)  # or run migrations/0001_issuance_ledger.sql

with Session(engine) as session:
    svc = IssuanceService(session, signing_key_pem=PRIVATE_KEY_PEM_BYTES)
    result = svc.issue(IssuanceRequest(
        customer_id="SN",
        edition="on-prem-full",
        entitled_modules=["erp", "mes", "commercial_tower"],
        quota_tier="enterprise",
        expires_at="2027-06-08T00:00:00Z",
        grace_days=30,
        seats=-1,
        delivery="offline-bundle",
    ))
    result.license      # the signed license.json body (dict, with base64 signature)
    result.ledger_row   # the persisted IssuanceLedger row
```

**Atomicity / ordering** (documented in `issuance.py`): sign first (in memory, pure,
can't half-fail), then write the ledger row in a single DB transaction; the signed
artifact is **returned only after commit**. If signing raises, nothing is written;
if the commit fails, it rolls back and raises — so the caller gets **both or
neither**. The private key (PEM bytes) is passed into the call; custody stays
offline (ADR 0009 §2) — the console calls the signer, it does not run a hot key
service.

**Renewals** (`IssuanceService.renew(prior_license_id, req)`): sign + write the new
row **and** set `superseded_by` on the prior row, all in one transaction. The new
row is the current one (`superseded_by IS NULL`); the prior is excluded from the
roster.

## Query API (backs #377)

```python
from fleet_console import roster, by_customer, expiring_soon

roster(session)                          # all current (non-superseded) licenses
roster(session, include_superseded=True) # full historical ledger
by_customer(session, "SN")               # one customer's current license(s)
expiring_soon(session, within_days=30)   # current licenses expiring within N days
```

## Telemetry credential (ADR 0009 §3, #374)

Issuing a license also **mints a per-deployment telemetry credential** in the same
transaction (`fleet_console/telemetry_credential.py`). `IssuanceResult` now carries
it:

```python
result = svc.issue(IssuanceRequest(customer_id="SN", edition="on-prem-full", ...))
result.credential.deployment_secret_id   # e.g. "dep-sn-7f3a1c0b" — NON-secret pointer
result.credential.secret                 # the HMAC secret — SENSITIVE, bake into bundle
result.ledger_row.deployment_secret_id   # == credential.deployment_secret_id
```

**Where the secret lives (security rationale).** HMAC is *symmetric*: intake (#375)
must recompute the HMAC, so it needs the *same* secret the deployment signed with —
unlike the *license* ed25519 key there is no public/private split. So the secret is
retained vendor-side, but **isolated**:

- `deployment_secret_id` → the **ledger** row (non-secret pointer).
- the secret value → a **separate `deployment_secret` table** keyed by
  `deployment_secret_id` (`migrations/0002_deployment_secret.sql`). Marked SENSITIVE:
  the broad roster query never loads it, and it can be GRANT-restricted / encrypted
  at-rest independently of the metadata ledger. We store the secret (not a hash)
  because a hash cannot recompute an HMAC.

**Blast radius.** A leaked deployment secret only forges *that one customer's*
telemetry (metadata-only, §5) — **never a license**. Licenses need the offline
ed25519 *private* key, which never enters this system
([`docs/saas-deployment/license-key-custody.md`](../docs/saas-deployment/license-key-custody.md)).

**The HMAC scheme (defined once here; #375/#376 use it verbatim).**

| Aspect | Value |
|---|---|
| Algorithm | **HMAC-SHA256** |
| Key | the per-deployment `secret` (UTF-8 bytes of the `token_urlsafe` string) |
| Message | the **raw telemetry payload bytes**, signed exactly as transmitted (no imposed canonicalisation) |
| Encoding | signature is **lowercase hex** (`hmac.hexdigest()`, 64 chars) |
| Compare | constant-time (`hmac.compare_digest`) |

```python
from fleet_console import verify_telemetry_hmac, sign_telemetry

# deployment side (#376) — sign the usage bundle bytes:
sig = sign_telemetry(secret, payload_bytes)            # -> hex str

# intake side (#375) — authenticate before accepting:
ok = verify_telemetry_hmac(session, deployment_secret_id, payload_bytes, sig)  # -> bool
```

`verify_telemetry_hmac(session, deployment_secret_id, payload_bytes, signature) ->
bool` returns True iff the signature is valid; unknown id → False.

**Delivery to the deployment.** The `secret` rides the **same offline/secret bundle
path as the rest of the deployment's secrets** — it is NOT committed to this repo.
For the SN on-prem edition it is delivered as a Vault-backed k8s Secret
(`ISA_TELEMETRY_SECRET` / `ISA_DEPLOYMENT_SECRET_ID`); see
[`deployments/editions/sn/README.md`](../deployments/editions/sn/README.md)
"Telemetry credential (#374)". The deployment uses it to sign usage bundles (#376);
intake validates them here.

**Rotation.**
- *Implicit* — `IssuanceService.renew` mints a **fresh** credential for the new
  lineage row, so a renewed deployment gets a new secret in its refreshed bundle and
  the old secret retires at the renewal boundary.
- *Explicit (leak)* — `rotate_credential(session, customer_id=..., license_id=...,
  old_deployment_secret_id=...)` mints + persists a new secret, deletes the old, and
  you repoint the active ledger row's `deployment_secret_id`. Rotation **never
  touches the license** (no ed25519 key involved) — its blast radius is telemetry
  only.

## Schema / migrations

The ledger schema is defined twice, kept in lock-step:

- **`fleet_console/models.py`** — the SQLAlchemy `IssuanceLedger` model (runtime ORM,
  and `Base.metadata.create_all()` for tests).
- **`migrations/0001_issuance_ledger.sql`** — the Postgres `CREATE TABLE` DDL for
  production.

**There is no migration runner in this repo yet** (no alembic — consistent with the
repo's current minimalism). `0001_issuance_ledger.sql` is a plain forward-only DDL
file; apply it with `psql "$FLEET_DATABASE_URL" -f fleet/migrations/0001_issuance_ledger.sql`.
Wiring a lightweight migration runner (alembic or a simple numbered-SQL applier) is a
follow-up; until then, new migrations are added as `000N_*.sql` and applied in order.

## Tests

```
python3 -m pytest fleet/tests/ -v
```

Tests use an in-memory **sqlite** SQLAlchemy engine (no live Postgres needed) and a
real ed25519 keypair. They cover: issue → ledger row + a **VALID** signed license
(round-tripped through `isa_common.license`), renewal sets `superseded_by`, roster
excludes superseded rows, and the expiring-soon filter. The SQL migration is also
parsed/applied against in-memory sqlite to confirm it is valid DDL.
