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

## 2. Platform mirrors — archive candidates (sync-diff gate first)

Commit counts are shallow and frozen at the 2026-05-25 bulk sanitizer sync → pure
mirrors. `model`/`training`/`cloud` diverge later → verify before archiving.

| sn repo | isA upstream | local activity | divergence risk | action |
|---|---|---|:---:|---|
| sn_agent | isA_Agent | 16 commits, all 05-25 | low | gate → archive |
| sn_app_sdk | isA_App_SDK | 2 commits, ≤05-25 | low | gate → archive |
| sn_console | isA_Console | 10 commits, all 05-25 | low | gate → archive |
| sn_docs | isA_Docs | 4 commits, all 05-25 | low | gate → archive |
| sn_marketing | isA_Marketing | 3 commits, ≤05-25 | low | gate → archive |
| sn_mate | isA_Mate | 5 commits, all 05-25 | low | gate → archive |
| sn_user | isA_user | 2 commits, ≤05-25 | low | gate → archive |
| sn_model | isA_Model | 14 commits, →06-03 | **medium** | gate → archive **or** push delta upstream |
| sn_training | isA_Training | 2 commits, →06-08 | **medium** | gate → decide |
| **sn_cloud** | isA_Cloud | active (06-11) | **KEEP** | **not a pure mirror — see §4** |
| *(not cloned locally)* sn_agent_sdk, sn_creative, sn_data, sn_mcp, sn_os, sn_vibe, sn_admin | isA_* | — | — | gate at source repo → archive |

**Sync-diff gate (per repo):**
```
# dry-run the isA upstream → sn fork sanitize; reports add/delete/modify, touches nothing
/sync-diff <repo>           # or xenoISA/sn-platform sanitizer dry-run
```
- **No SN-only delta** (everything would come from isA) → archive the GitHub repo
  (Settings → Archive: read-only), drop it from the sanitizer set, remove the local clone.
- **SN-only delta exists** → that code must land somewhere first: push it back to the
  isA upstream as an optional/edition feature, *then* archive; or, if truly SN-only,
  reclassify it out of "platform mirror" and keep.

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
