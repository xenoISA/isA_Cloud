# SN Edition — Deep Functional Smoke Checklist (2026-06-08)

Per-service **functional** smoke (beyond health): for each backend service, pulled
`/openapi.json`, called every no-path-param GET endpoint (exercises the real
DB-read + serialization path), classified by status.

- **2xx** = functional (DB read + serialize OK)
- **401/403** = auth-gated (working as designed for an unauthenticated smoke)
- **422** = needs a query parameter (validation, working as designed)
- **5xx** = **REAL FAILURE** (root-caused below)

Run via an in-cluster Job (VPN-independent during execution), 12-way parallel,
≤10 GET endpoints/service.

## Result: 48/52 app services clean. 4 services with real 5xx (8 endpoints).

isa-mcp = MCP protocol (no OpenAPI; /health 200, /mcp live) — expected.
Frontends (isa-console/admin/docs) serve HTML, verified separately (routes 200).

## Real failures — root-caused

| Service | Endpoint(s) | Root cause | Fix |
|---------|-------------|-----------|-----|
| **isa-model** | `/api/v1/analytics/{overview,costs,models}` | `build_database_url()` builds a naive `postgresql://{user}:{password}@...` f-string; the platform password has URL-significant chars → `asyncpg.connect` fails → `get_db_connection` raises 500. **Same bug class as isa-agent PR#137 / isa_user quote_plus.** | URL-encode user+password (quote_plus). |
| **isa-os** | `/api/v1/web/providers` | `registry.get_all_info()` instantiates EVERY provider with `{}` just to read metadata; `BraveProvider.__init__` raises `ValueError: Brave API key is required`. Listing metadata must not require provider credentials. | Don't validate/raise at construction for a metadata listing (lazy key check, or read class metadata without instantiating). |
| **user-credit** | `/api/v1/credits/statistics` | `ResponseValidationError: 2 validation errors` — the statistics aggregation returns fields that don't match the response_model (None where non-null expected on empty data). Secondary: a misregistered handler → `TypeError: 'HTTPException' object is not callable`. | Coalesce empty aggregates (None→0) to satisfy the model; fix the exception-handler registration. |
| **user-training** | `/api/v1/training/courses`, `/api/v1/training/k12/contract` | `FileNotFoundError: '/isA_Training/_data/k12/seed.json'` — the K12 seed data file isn't shipped in the image. | Ship the seed data in the image (or tolerate missing → empty list). |

## To recheck
- **user-memory** `/api/v1/memories/health` returned a connection ERR during the
  smoke (likely a timeout, not a 5xx) — recheck in isolation.

## Method note
GH Actions is billing-blocked org-wide, so fixes ship via local build
(`buildx` docker-container driver → OCI archive → `skopeo` to Harbor) + a fresh
image tag + `pullPolicy: Always`.
