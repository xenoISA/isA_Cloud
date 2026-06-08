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

## Result

Closure status (2026-06-08): **52/52 app services clean** for this
unauthenticated no-path-param GET smoke. The 4 services that initially returned
real 5xx responses are now fixed and redeployed; the 8 failed endpoints all
return 200 from inside `sn-cloud-production`.

Initial result before fixes: 48/52 app services clean. 4 services with real 5xx
(8 endpoints).

isa-mcp = MCP protocol (no OpenAPI; /health 200, /mcp live) — expected.
Frontends (isa-console/admin/docs) serve HTML, verified separately (routes 200).

## Real failures — root-caused

| Service | Endpoint(s) | Root cause | Fix |
|---------|-------------|-----------|-----|
| **isa-model** | `/api/v1/analytics/{overview,costs,models}` | `build_database_url()` builds a naive `postgresql://{user}:{password}@...` f-string; the platform password has URL-significant chars → `asyncpg.connect` fails → `get_db_connection` raises 500. **Same bug class as isa-agent PR#137 / isa_user quote_plus.** | URL-encode user+password (quote_plus). |
| **isa-os** | `/api/v1/web/providers` | `registry.get_all_info()` instantiates EVERY provider with `{}` just to read metadata; `BraveProvider.__init__` raises `ValueError: Brave API key is required`. Listing metadata must not require provider credentials. | Don't validate/raise at construction for a metadata listing (lazy key check, or read class metadata without instantiating). |
| **user-credit** | `/api/v1/credits/statistics` | `ResponseValidationError: 2 validation errors` — the statistics aggregation returns fields that don't match the response_model (None where non-null expected on empty data). Secondary: a misregistered handler → `TypeError: 'HTTPException' object is not callable`. | Coalesce empty aggregates (None→0) to satisfy the model; fix the exception-handler registration. |
| **user-training** | `/api/v1/training/courses`, `/api/v1/training/k12/contract` | `FileNotFoundError: '/isA_Training/_data/k12/seed.json'` — the K12 seed data file isn't shipped in the image. | Ship the seed data in the image (or tolerate missing → empty list). |

## Recheck
- **user-memory** `/api/v1/memories/health` rechecked in isolation with a longer
  timeout: **200**.

## Method note
GH Actions is billing-blocked org-wide, so fixes ship via local build
(`buildx` docker-container driver → OCI archive → `skopeo` to Harbor) + a fresh
image tag + `pullPolicy: Always`.

## Fix status (2026-06-08)

| Service | PR | Image | Verified |
|---------|----|----|----------|
| **isa-model** `/analytics/*` | isA_Model `fb3cda1f` / #989 (`quote_plus` DSN) | `core.harbor.domain/isa/isa-model:gpu-vllm-stt-20260608-r10` | **200** — overview/costs/models |
| **isa-os** `/web/providers` | #425 + #426 (skip unreadable providers, not fabricate ProviderInfo) | `core.harbor.domain/isa/isa-os:0.1.3` | **200** — lists configured providers, Brave skipped when unconfigured |
| **user-credit** `/credits/statistics` | isA_user #520 | user-credit:0.1.1 (local thin build) | **200** — full stats structure |
| **user-training** `/courses`, `/k12/contract` | isA_user #520 | user-training:0.1.1 (local thin build) | **200** — graceful empty (seedAvailable:false) |

Local-build notes: isa_user thin services = skopeo-pull base→daemon, `docker build` thin layer (FROM amd64 base → amd64 output, COPY-only), skopeo→Harbor. isa-os 0.1.3 was rebuilt from the web service Dockerfile using the local amd64 `isa-python-base` cache because GHCR metadata returned 403. `isa-model` r10 was verified by a temporary image-check pod before removing the temporary ConfigMap mount. Final live deployments use pure Harbor images; no hotfix mounts remain.
