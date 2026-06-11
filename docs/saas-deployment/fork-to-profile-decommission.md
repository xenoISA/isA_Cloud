# Fork → Profile — repo decommission plan

> The actionable companion to [`edition-boundary.md`](./edition-boundary.md) (the
> taxonomy authority). Under the **profile/edition model**, SN deploys the
> edition-agnostic `isa/*` images by config (ADR 0006, `editions/sn/`), so the
> **platform-mirror `sn_*` forks are deployment-redundant** and become archive
> candidates. Customer-specific forks have **no isA upstream** and stay.
> Survey date 2026-06-11 (`~/Documents/fun/sn`, org `org-sweet-night`).
>
> ⚠️ Archiving is a GitHub state change (reversible) — **never delete**. Each
> platform mirror passes a **sync-diff gate** (no un-merged SN delta) before archive.

---

## 1. Principle

| Class | isA upstream? | Under profile model | Action |
|---|:---:|---|---|
| **Platform mirror** (edition-boundary §A, 17) | ✅ `sn_X ↔ isA_X` | deployment uses isA images by config — the branded fork is **not deployed** | **archive** (after sync-diff gate) |
| **Customer-specific** (§B, 24) | ❌ no upstream | SN business systems, independent | **keep** |
| **Stub** (non-git dir) | — | placeholder | decide create-or-drop (separate from fork cleanup) |

The forks were the *old* white-label model (sanitizer `ISA_*→SN_*`). Profile replaces
them for **deployment**; the only reason to keep a mirror is genuine, un-merged
SN-specific source divergence — which the gate measures.

---

## 2. Platform mirrors — VERIFIED 2026-06-11 (divergence gate run)

Each local mirror was diffed against its isA upstream (commit history + tree diff +
content spot-check). Result is **not** "archive all" — 2 are real customer logic:

| sn repo | verdict | finding | action |
|---|---|---|---|
| **sn_app_sdk** | ✅ CLEAN | branding-only, behind upstream | **archive now** |
| **sn_docs** | ✅ CLEAN | branding-only, 0 SN-only files | **archive now** |
| **sn_marketing** | ✅ CLEAN | branding-only, 0 SN-only files | **archive now** |
| **sn_user** | ✅ CLEAN | "SN-only" migrations are identical-modulo-renumber; behind upstream | **archive now** |
| **sn_agent** | 🟡 small delta | 3 SN-only docs/ops: `docs/scheduler.md`, `docs/deployment/multi-tenant-playbook.md`, `deployment/local-dev-crud.sh` (document features already in isA) | **port up → isA_Agent, then archive** |
| **sn_console** | 🟡 small delta | 7 SN-only test files (tenant/schedule/billing — source is upstream, tests weren't); CI workflows + `.d.ts` shims are white-label scaffolding | **port 7 tests → isA_Console; reclassify scaffolding; then archive** |
| **sn_mate** | 🟡 stale | only code delta is SN *behind* isA's #590/#901 proxy-ownership refactor; 1 SN-only test covers deleted behavior | **confirm nobody wants self-hosted proxy → archive (nothing to preserve)** |
| **sn_model** | 🔴 RECLASSIFY | full SweetNight **SCM sales-forecast ML product** (LightGBM/backtest/eval-gate/MLflow/notebooks/25+ tests), coupled to `sn_data` forecast product | **NOT a mirror → customer-specific (§3); do NOT archive** |
| **sn_training** | 🔴 RECLASSIFY | divergent sibling: SweetNight business-ized training content / case libraries / PRD / decks; drops the isA training-service half entirely | **NOT a mirror → customer-specific (§3); do NOT archive** |
| **sn_cloud** | KEEP | carries SN delivery/ops content with no isA equivalent | **keep — see §4** |
| *(not cloned locally)* sn_agent_sdk, sn_creative, sn_data, sn_mcp, sn_os, sn_vibe, sn_admin | ⬜ ungated | can't verify locally | **run the gate at the source repo before archiving** |

> sn_model + sn_training are moved to §3/§B in `edition-boundary.md`. They are exactly
> the SN business logic that ADR 0010 (`isa_data_product`) aims to give a platform home.

**Net:** 4 archive-clean today · 3 archive after a small fixup · 2 reclassify-and-keep ·
1 keep (sn_cloud) · 7 ungated (verify at source).

The heuristic gate above is strong; for the final archive, a `/sync-diff` (or sanitizer
dry-run) per repo is the authoritative confirmation. Archive = GitHub Settings → Archive
(read-only, reversible), drop from the sanitizer `PLATFORM_REPOS`, remove the local clone.

---

## 3. Customer-specific — KEEP (no isA upstream)

`sn_aom · sn_arch · sn_commerce · sn_commercial_tower · sn_dtc · sn_erp · sn_feishu ·
sn_finance · sn_iam · sn_ipd_tower · sn_maestro · sn_mdm · sn_mes · sn_operation_tower ·
sn_plan · sn_plm · sn_pxm · sn_scm_tower · sn_seeyon · sn_srm · sn_tower_kit`

Never touched by the sanitizer; these are SN business systems. No action — they
consume the platform via SDK/API, not by forking it (edition-bom).

**Stubs (non-git placeholders)** — decide create-or-drop, *separate* from fork cleanup:
`sn_gcp · SN-BI · SN-TROBS` (known) and **new: `sn_feilian` · `sn_fine_bi`** (appeared
since the 2026-06-04 survey — confirm what they are and whether they belong in §B).

---

## 4. sn_cloud — special case, KEEP

`sn_cloud ↔ isA_Cloud` is nominally a platform mirror, but it is **not a pure mirror**:
it carries SN-only delivery content with no isA equivalent —
`docs/implementation-delivery/` (the production playbook, evidence, the license
ConfigMaps we just staged), customer ArgoCD apps, `operations/`. The *deployment*
role (charts/editions) is superseded by isA_Cloud `editions/sn`, but the **delivery /
operations role stays in sn_cloud**. Keep it; do not archive. (Its legacy
`customer-prod` profile / `setup-datalake.sh` are already marked for retirement, #322.)

---

## 5. sn_commercial_tower — profile-ization adjustments

Not a fork (customer-specific, keep), but it still assumes the old monorepo/sibling
layout. To consume the platform as a namespace-isolated profile instead of by-sibling:

1. **Drop `sys.path` parent traversal** — `scripts/smoke/w7_p0_smoke.py`,
   `amazon_sc_e2e_smoke.py`, `tests/conftest.py` inject `~/Documents/fun/sn` to import
   `sn_data` (88 sites). Install `sn_data` as a package **or** consume its API
   (`SN_DATA_API_ENDPOINT` via APISIX). *(critical blocker)*
2. **Parameterize the K8s namespace** — `deployment/services/namespace.yaml` hard-wires
   `commercial-tower`; should fold into `sn-cloud-production` / be templated.
3. **Prefix Kafka topics** — `deployment/kafka/topics/_generated/*.kafkatopic.yaml`
   (47) are global names → collide across profiles; add a profile prefix / Helm template.
4. **Service discovery via DNS** — `docker-compose.yml`, `frontend/next.config.ts`
   (`FRAPPE_URL`), notebook `SN_DATA_BASE_URL` default to `localhost` → use
   `<svc>.sn-cloud-production.svc.cluster.local` or injected env.

~87% of the repo is genuine commerce-domain code (collectors, BFF, UI) — no rewrite,
only the platform-access seam changes. (File this as its own issue.)

---

## 6. Execution order

1. **Verify** — run the sync-diff gate on each §2 mirror (read-only; no risk).
2. **Land deltas** — for any mirror with SN-only delta, push it to the isA upstream
   (or reclassify). Nothing archived until its delta is preserved.
3. **Archive** — GitHub-archive the clean mirrors (reversible), remove from the
   sanitizer's PLATFORM_REPOS set, delete local clones. **Requires sign-off** (it's an
   org-visible state change).
4. **sn_commercial_tower** — separate issue for the §5 adjustments.
5. **Stubs** — separate triage for §3 placeholders.

> Confirm the §2 archive list before step 3 — that step is the only outward-facing,
> sign-off-gated action here. Steps 1–2 are safe to run now.
