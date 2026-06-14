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

Two gate waves run (local clones + fresh clones of the never-cloned forks). Result is
**not** "archive all" — 6 of the "mirrors" carry real SweetNight product:

| sn repo | verdict | finding | status / action |
|---|---|---|---|
| **sn_app_sdk** | ✅ CLEAN | branding-only, behind upstream | **ARCHIVED 2026-06-11** (read-only + local clone removed) |
| **sn_docs** | ✅ CLEAN | branding-only | **ARCHIVED 2026-06-11** |
| **sn_marketing** | ✅ CLEAN | branding-only | **ARCHIVED 2026-06-11** |
| **sn_user** | ✅ CLEAN | migrations identical-modulo-renumber; behind upstream | **ARCHIVED 2026-06-11** |
| **sn_creative** | ✅ CLEAN | 1 branding-renamed test; not a deployed service | **ARCHIVED 2026-06-11** (no local clone) |
| **sn_agent** | 🟡 port done | 3 SN-only docs/ops | port → isA_Agent **#140**; **archive after merge** |
| **sn_console** | 🟡 port done | 7 SN-only tests (re-gated 06-02 push = sync-merge + 1-line sidebar overlay to keep) | port → isA_Console **#792**; **archive after merge** |
| **sn_mcp** | 🟡 small infra | 7 SN k8s/deploy scripts; legacy ArgoCD refs its values | port scripts / treat as infra → **archive (read-only safe)** |
| **sn_vibe** | 🟡 trivial | ABAP already in sync; 1 audit memo + deploy yaml | port memo (or drop) → **archive** |
| **sn_mate** | 🟡 stale | SN *behind* isA #590/#901 proxy refactor; test covers deleted behavior | **confirm proxy dead → archive** (pending) |
| **sn_data** | 🔴 RECLASSIFY | ~35k LOC SN data-infra + forecast/TROBS data products; `sn_model` depends on it | **→ §B customer-specific; ADR 0010 domain; do NOT archive** |
| **sn_os** | 🔴 RECLASSIFY | 141 SN-only files: personas / Amazon VC strategies / stealth / workers | **→ §B; do NOT archive** |
| **sn_agent_sdk** | 🔴 RECLASSIFY | net-new `sn_agent_sdk/` pkg: BatchSwarm / chain / Rufus·social adapters | **→ §B; do NOT archive** |
| **sn_model** | 🔴 RECLASSIFY | SweetNight SCM sales-forecast ML product, coupled to sn_data | **→ §B; do NOT archive** |
| **sn_training** | 🔴 RECLASSIFY | SweetNight business-ized training content / case libraries | **→ §B; do NOT archive** |
| **sn_cloud** | KEEP | SN delivery/ops content, no isA equivalent | **keep — §4** |

> **Deploy-safety check (2026-06-11):** production runs the **isA_Cloud editions path**
> (`isa-*` upstream images), not the forks. The only forks referenced in deploy are the
> **legacy** `sn_cloud` ArgoCD apps (`../../../sn_{model,mcp,os}/...` value files) — an
> explicitly-deprecated fallback, and ArgoCD isn't deployed. Archive = read-only (reads
> still resolve), so no deploy path breaks. model/os are kept anyway; mcp archive is safe.
>
> The 5 reclassified repos are moved to §B in `edition-boundary.md` — they are exactly the
> SN business logic ADR 0010 (`isa_data_product`) aims to give a platform home (esp. sn_data).

**Net:** 5 archived · 2 port-done→archive-on-merge (agent #140, console #792) · 2 small-fixup
(mcp, vibe) · 1 pending (mate) · 5 reclassify-keep (data, os, agent_sdk, model, training) ·
1 keep (sn_cloud). `sn_admin` never existed.

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
