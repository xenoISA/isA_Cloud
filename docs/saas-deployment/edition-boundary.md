# Edition & Sync Boundary — Repo Taxonomy

> **权威归类**:每个 repo 属于哪一类,决定它能不能被 isA→SN sanitizer 碰。
> 这是修复"用一套 sync 运作、但 sn 环境混了客户专属模块"这个设计缺陷的源头。
> 与 `.claude/rules/white-label.md` 的 16-repo map 对齐;后者只描述了平台镜像,
> 本文覆盖全部 40 个 `sn_*` + 7 个孤儿 `isA_*`。

> 数据来源:`~/Documents/Fun/isA/isA_*`(23 个上游)与
> `~/Documents/fun/sn/{sn_*,SN-*}`(40 个下游)实地核对,2026-06-04。

## 三类边界(一句话)

| 类别 | 有 isA 上游? | sanitizer 能碰? | 在哪演进 |
|---|:---:|:---:|---|
| **Platform 平台镜像** | ✅ | ✅ 应 sync | isA upstream,sync 到 sn |
| **Customer-specific 客户专属** | ❌ | ❌ **永不** | 仅 sn 环境,独立演进 |
| **Orphaned isA 孤儿** | ✅(无 sn 镜像) | 已定性(#324) | Admin→平台(第17镜像);IDE/Orch/Reading/Trade/Chain/Frame→isA-only |

> 第四类(规划中):**SaaS-only** —— 多租户/对外收费模块,活在 isA 但
> **不进白标 fork**(charging policy)。当前尚未拆出独立 repo,见下方「待办」。

---

## A. Platform 平台镜像(17 — 应 sync;含 #324 新增 isA_Admin)

`sn_X` ↔ `isA_X` 一一对应。sanitizer **只应**对这 16 个运行。

| sn repo | isA 上游 |
|---|---|
| sn_agent | isA_Agent |
| sn_agent_sdk | isA_Agent_SDK |
| sn_app_sdk | isA_App_SDK |
| sn_cloud | isA_Cloud |
| sn_console | isA_Console |
| sn_creative | isA_Creative |
| sn_data | isA_Data |
| sn_docs | isA_Docs |
| sn_marketing | isA_Marketing |
| sn_mate | isA_Mate |
| sn_mcp | isA_MCP |
| sn_model | isA_Model |
| sn_os | isA_OS |
| sn_training | isA_Training |
| sn_user | isA_user |
| sn_vibe | isA_Vibe |
| sn_admin | isA_Admin (#324, 新增) |

规范化的平台 key(供 sanitizer 白名单使用):
`agent agent_sdk app_sdk cloud console creative data docs marketing mate mcp model os training user vibe admin`

---

## B. Customer-specific 客户专属(24 — 永不 sync)

无 isA 上游。一旦被 sanitizer 碰到 → 被脱敏/历史重写/覆盖。**必须排除。**
这些是 SN 客户场景下的企业系统与业务塔,独立演进。

| sn repo | 性质(推测) |
|---|---|
| sn_aom | 运维/AOM |
| sn_arch | 架构/arch(discover 曾漏列,实地核对补回) |
| sn_commerce | 电商 |
| sn_commercial_tower | 商业塔 |
| sn_dtc | DTC |
| sn_erp | ERP |
| sn_feishu | 飞书集成 |
| sn_finance | 财务 |
| sn_gcp | GCP 相关 |
| sn_iam | IAM(另有独立项目 ~/Documents/Fun/Projects/IAM) |
| sn_ipd_tower | IPD 塔 |
| sn_maestro | Maestro 编排 |
| sn_mdm | 主数据 MDM |
| sn_mes | 制造执行 MES |
| sn_operation_tower | 运营塔 |
| sn_plan | 计划 |
| sn_plm | 产品生命周期 PLM |
| sn_pxm | PXM |
| sn_scm_tower | 供应链塔 |
| sn_seeyon | 致远 OA 集成 |
| sn_srm | 供应商关系 SRM |
| sn_tower_kit | 塔工具包 |
| SN-BI | BI/数仓 |
| SN-TROBS | TROBS |

> ⚠️ 这 24 个当前在 sync 体系里**裸奔**(既没排除也没纳入)。这是最高优先级
> 的护栏缺口。

---

## C. Orphaned isA 孤儿(7 — 已全部定性,#324 closed 2026-06-05)

原为"有上游、暂无 sn 镜像、决策待定"。现已全部定性:

| repo | 定性 | 处置 |
|---|---|---|
| **isA_Admin** | **平台**(白标交付) | **纳入 sync map(第 17 个)** — SN 运维需要管理后台。已加入 `sanitize.sh` PLATFORM_REPOS(sn-platform#27) |
| isA_IDE | **isA-only 产品** | 不 sync(独立产品,同 Reading/Trade/Chain) |
| isA_Orch | **isA-only 内部工具** | 不 sync(平台开发工具:code index / project registry,非客户交付物) |
| isA_Reading | isA-only 产品 | 不 sync(此前已定性) |
| isA_Trade | isA-only 产品 | 不 sync(此前已定性) |
| isA_Chain | isA-only 产品 | 不 sync(此前已定性) |
| isA_Frame | isA-only 产品(EmoFrame) | 不 sync(此前已定性) |

结果:**平台镜像 16 → 17**(+isA_Admin)。其余 6 个孤儿确认为 isA-only,永不进白标。

> 注:`isA_` 是一个空的残留目录,忽略(建议清理)。

---

## 护栏机制(本次落地)

1. **sanitizer 平台白名单守卫**:`scripts/sanitize.sh` 加 `PLATFORM_REPOS`
   数组 + 启动检查。规范化 repo basename(去 `isa_/isA_/sn_/ISA_` 前缀、转小写)
   后若不在白名单 → **拒绝运行**(除非显式 `SANITIZE_FORCE=1` 覆盖)。
   防止误把 `sn_erp` 等客户专属模块脱敏。
   > 注:权威脚本在 `xenoISA/sn-platform/scripts/sanitize.sh`(非本地)。
   > 本仓库 `.claude/skills/sync-diff/cache/sanitize.sh` 是缓存副本,已先行打补丁
   > 作为参考实现;真正生效需把同样改动 PR 到 sn-platform。

2. **本归类文档**:作为 sync 范围的 single source of truth。新增 repo 时先在
   此归类,再决定是否纳入 16-repo map(对应 white-label.md 的
   MIGRATION_CHECKLIST 流程)。

## 待办(后续 story)

- 把 white-label.md 的"16 repos"措辞补充指向本文档的全量归类。
- SaaS-only 模块(多租户/charging)拆出独立 repo 或加 sanitizer 排除规则。
- 7 个孤儿 isA repo 的 sync 决策(/design)。
- C 类 24 个客户专属模块在 sn 环境的分层/overlay 组织方式(Phase 2,Approach C)。
