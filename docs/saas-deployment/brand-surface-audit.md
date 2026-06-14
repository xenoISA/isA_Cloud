# Brand-Surface Audit + Brand-Config Contract

> Deliverable for isA_Cloud#314 (brand audit) + #315 (brand config contract).
> Source: parallel per-repo audits across 22 isA repos, 2026-06-04.
> Classification rubric: **Bucket A** = customer-visible brand (→ config) ·
> **Bucket B** = internal `isa_` identifiers (stay, never config).

## Headline

Brand surface is **small and highly repetitive**. Across 22 repos there are
~**250 Bucket A findings**, but they collapse into **~15 recurring config keys**.
Internal `isa_` identifiers number in the thousands — **none** become config
(they just stay `isa_` forever; nothing rewrites them under the profile model).

**Two config layers are needed** (not one):
1. **Python backends** → a `BrandConfig` in `isa_common`, read from env/ConfigMap.
   Every service already imports `isa_common`, so one definition covers
   Cloud, MCP, Model, Agent, Data, user, Creative, Marketing, Orch, Training, Mate.
2. **JS/TS frontends** → a `brand` config read from `NEXT_PUBLIC_*` build env /
   runtime config, for Console, Frame, IDE, Admin, Reading, Docs, App_SDK(ui-web).

> Precedent already exists: **isA_MCP has `core/branding.py` (`DISPLAY_NAME`)** —
> but several endpoints bypass it with hardcoded `"Smart MCP Server"`/`"isA MCP
> Server"`. The pattern is right; it just needs to be centralized in `isa_common`
> and used consistently.

---

## The Brand-Config Contract (#315)

Canonical keys, derived from what actually recurs across repos.

### Python — `isa_common.brand.BrandConfig` (env-driven)

| Key | Env var | Default | Used by (examples) |
|-----|---------|---------|--------------------|
| `name` | `BRAND_NAME` | `isA` | logos, prose, A2A short |
| `display_name` | `BRAND_DISPLAY_NAME` | `isA Platform` | titles, headers |
| `org_name` | `BRAND_ORG_NAME` | `isA` | **A2A `provider_org`** (Creative ×7, Marketing, Trade, Vibe) |
| `service_name` | `BRAND_SERVICE_NAME` | per-svc (`isA_Model`…) | **observability/OTEL/logger/health `service`** (Model, Data, Creative, Marketing, Vibe…) |
| `openapi_title` | `BRAND_OPENAPI_TITLE` | per-svc | **FastAPI `title`** (every backend) |
| `openapi_description` | `BRAND_OPENAPI_DESCRIPTION` | per-svc | FastAPI `description` |
| `support_email` | `BRAND_SUPPORT_EMAIL` | `dev@iapro.ai` | emails, errors |
| `cookie_domain` | `AUTH_COOKIE_DOMAIN` | `.iapro.ai` | **auth cookie** (user, Cloud) — note real prod domain is `.iapro.ai` |
| `primary_host` / `docs_url` | `BRAND_PRIMARY_HOST` / `BRAND_DOCS_URL` | `isa.dev`/`docs.isa.dev` | public URLs, CORS |
| `email_*` (welcome subject/body) | template files | — | isA_user notification_service |
| `agent_persona_name` | `BRAND_AGENT_NAME` | `Mate`/none | **agent system-prompt persona** (Mate config.yaml) |
| `cli_name` | `BRAND_CLI_NAME` | `isa-vibe`/`isa-orch`/`isa-mate` | CLI banners/help (Vibe, Orch, Mate) |

### TS/JS — `brand` config (`NEXT_PUBLIC_*` build env)

| Key | Env var | Used by |
|-----|---------|---------|
| `name` / `shortName` | `NEXT_PUBLIC_BRAND_NAME` / `_SHORT` | logo text, nav, titles (Console, Admin, Docs, IDE, App_SDK) |
| `displayName` / `description` | `NEXT_PUBLIC_BRAND_DISPLAY_NAME` / `_DESCRIPTION` | `<title>`, meta, OG tags |
| `logoUrl` / `faviconUrl` / `faviconGlyph` | `NEXT_PUBLIC_BRAND_LOGO_URL` … | logo/favicon assets |
| `docsUrl` / `apiUrl` / `discordUrl` / `twitterUrl` / `githubOrg` | `NEXT_PUBLIC_*` | footer/nav links (Docs surfaces.ts already env-driven) |
| `colors.*` (primary/secondary/accent) | `NEXT_PUBLIC_BRAND_COLOR_*` | theme (Frame, mobile apps) |
| i18n `app_title`/`auth.title` | locale files keyed to `brand.*` | Console, Admin (en/zh/ru) |
| app name / permission prompts | `app.json` + build substitution | Frame mobile (EmoFrame — see scope note) |

> **Docs prose** (~363 mentions in isA_Docs) is NOT per-string config — use a
> single build-time `{{brand.name}}` token + MDX preprocessor. Chrome (title/logo/
> footer, ~18 strings) is normal config.

---

## Per-repo summary (Bucket A volume + dominant surface)

| Repo | Type | Bucket A | Dominant surface |
|------|------|:---:|---|
| isA_Console | FE | ~35 | titles, sidebar, login, i18n, feature-matrix labels, docs.isa.dev |
| isA_Frame | FE (RN/Expo) | ~55 | **app name "EmoFrame"**, permission prompts, theme colors, device names |
| isA_IDE | Desktop (Tauri) | ~18 | productName, window title, bundle id `com.isa.ide`, logo, generated-code header |
| isA_Admin | FE | ~15 | title, login, sidebar, i18n ×3, `admin@isa.ai`, audit metadata |
| isA_Docs | Docs | ~18 chrome + ~363 prose | site title/logo/footer + prose token |
| isA_App_SDK | SDK/FE | ~6 | PlatformNav logo, package descriptions; **NO plugin API yet (see #319)** |
| isA_Cloud | Backend | ~6 cats | CORS origins, cookie domain, package metadata, README |
| isA_MCP | Backend | ~13 | server card/`.well-known`, CLI help; **branding.py exists but bypassed** |
| isA_Model | Backend | ~7 | FastAPI title, OTEL service_name, Postman collection |
| isA_Agent | Backend | ~5 | FastAPI title/desc, README, pyproject |
| isA_Data | Backend | ~8 | FastAPI title, health/root `service`, log service, MinIO bucket prefix |
| isA_user | Backend (auth) | ~7 | **welcome email template**, cookie domain `.iapro.ai`, service titles |
| isA_Creative | Backend | ~16 | **A2A `provider_org="isA"` ×7**, OTEL, FastAPI, k8s ns |
| isA_Marketing | Backend | ~8 | A2A provider_org, service_name, notification source |
| isA_Mate | Backend+CLI | ~18 | **agent system-prompt persona**, OpenAPI title, CLI banner, TLS cert CN |
| isA_Vibe | CLI+API | ~11 | CLI banner/help, `isa-vibe` cmd, OpenAPI, A2A provider_org |
| isA_Orch | CLI/lib | 2 | module docstring, `isa-orch --help` — essentially all-internal |
| isA_Training | Backend | ~14 | FastAPI title, seed-data `platform` field, Docker/pyproject |
| isA_Reading | FE (standalone) | ~6 | **own brand "isA Reading"** — scope ? |
| isA_Trade | Backend (domain) | ~11 | **own brand "isA_Trade"** — scope ? |
| isA_Chain | Blockchain | ~200 | **own brand "isA_Chain"/isa-chain.io**, on-chain contract strings — scope ? |
| isA_Agent_SDK | SDK | ~7 | **A2A card defaults `provider_org="isA"` / `description="isA agent"`** (a2a.py:78-79, service_builder.py:87-89), User-Agent `ISAAgent-Python`, pyproject, docstrings |

---

## Decisions this audit surfaces (need user input)

1. **Orphaned domain apps brand as their OWN product names**, not "isA platform":
   `isA_Reading` ("isA Reading"), `isA_Trade` ("isA_Trade"), `isA_Chain`
   ("isA_Chain", isa-chain.io). They have **no sn mirror**. Decision: are these
   **white-labeled to SN at all, or isA-only products**? If isA-only → out of
   brand-config scope (skip them).
2. **isA_Frame ships as "EmoFrame"** — a separate consumer product brand, not
   "isA". Is EmoFrame white-labeled, isA-owned-but-separate, or out of scope?
3. **isA_Chain smart contracts**: on-chain error strings are immutable post-deploy;
   sanitizer/config can't touch bytecode. If Chain is white-labeled, contracts
   must be redeployed. (Likely moot if Chain is isA-only.)
4. **isA_Marketing / isA_Docs**: are these isA's own marketing/docs (isA-only) or
   shipped per-customer? If isA-only, only the shippable product chrome matters.

## Special cases / notes

- **`provider_org="isA"`** in A2A agent cards is the single highest-leverage shared
  fix — recurs across Creative(×7)/Marketing/Trade/Vibe, customer-visible in agent
  discovery. **The DEFAULT lives in `isA_Agent_SDK` (a2a.py `A2AAgentCard`,
  service_builder.py `AgentServiceExecutionProfile`)** — so wiring the SDK default
  to `BrandConfig.org_name` fixes the root, and the per-service explicit
  `provider_org="isA"` overrides just need to drop the override (inherit) or read
  the same config. Fix the SDK first.
- **OTEL/observability `service_name`** recurs (Model/Data/Creative/Marketing/Vibe)
  — customer-visible in dashboards. One `BrandConfig.service_name`.
- **Real production domain is `.iapro.ai`** (not the `.example.com` placeholders in
  k8s manifests). Confirm canonical host before defaulting.
- **Bucket B is enormous but zero-work**: under the profile model nothing renames
  `isa_` internally. (Contrast with the old sanitizer that rewrote everything.)

## Recommended implementation order (feeds #315 → fix fan-out)

1. Land `isa_common.brand.BrandConfig` (Python) — unblocks all 11 backends at once.
2. Land the TS `brand` config helper — unblocks the FE apps.
3. Resolve the 4 scope decisions above (drops Reading/Trade/Chain/EmoFrame if isA-only).
4. THEN fan out `/fix` per repo against the locked contract (one PR per repo).
