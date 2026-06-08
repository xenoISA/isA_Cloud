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

## What's here (this story, #373)

The **license-issuance ledger** + the **issuance workflow** + a **library-level
query API**. No HTTP endpoint and no UI yet — those are later stories.

```
fleet/
├── README.md                         # this file
├── fleet_console/                    # the Python package
│   ├── __init__.py                   # public surface (re-exports)
│   ├── models.py                     # SQLAlchemy: Base + IssuanceLedger
│   ├── issuance.py                   # IssuanceService / issue_license / renew_license
│   └── queries.py                    # roster / by_customer / expiring_soon
├── migrations/
│   └── 0001_issuance_ledger.sql      # CREATE TABLE issuance_ledger (Postgres DDL)
└── tests/
    └── test_issuance.py              # sign->ledger round-trip, renewal, query filters
```

### Package layout convention (for #374 / #375 / #377)

`fleet_console/` is the package root. New vendor-side pieces go here:

- **#374 telemetry credential** — mint a per-deployment HMAC secret at issuance and
  write its id onto the ledger row. The column already exists:
  `IssuanceLedger.deployment_secret_id` (nullable `TEXT`). Populate it inside the
  issuance transaction (extend `IssuanceService.issue` / `.renew`) or via an
  `UPDATE issuance_ledger SET deployment_secret_id = ... WHERE license_id = ...`.
  Suggested new module: `fleet_console/telemetry_credential.py`.
- **#375 intake endpoint** — the internet-facing, HMAC-authenticated, metadata-only
  telemetry intake. Validates the HMAC against the ledger's `deployment_secret_id`.
  Suggested: `fleet_console/intake.py` (+ an `app.py` / ASGI entry).
- **#377 fleet UI** — calls the query API in `fleet_console/queries.py` (`roster`,
  `by_customer`, `expiring_soon`). A separate Next.js deployment (ADR 0009 §4); it
  reads through these functions (or an HTTP layer wrapping them).

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
