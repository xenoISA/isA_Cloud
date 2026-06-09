# isA 部署形态(Deployment Editions)

isA 是**一个产品**,通过模块化部署支持多种形态。**不是多个产品**——
同一套 `xenoISA/isA_*` 代码,按 profile(Helm values / feature flags)
裁剪出不同 edition:

| 形态 | 部署位置 | 租户 | 大数据模块 | 多租户+计费 | 品牌 | 实例 |
|---|---|---|---|:---:|---|---|
| **企业版·全量**(on-prem) | 客户 IDC / VPC | 单租户 | ✅ 装 | ❌ | 白标 | **SN** |
| **企业版·精简**(on-prem) | 客户 IDC / VPC | 单租户 | ❌ 不装 | ❌ | 白标 | 中小客户 |
| **SaaS** | isA 自营云 | 多租户 | ❌ 不装 | ✅ | isA | api.isa.xxx |

两条正交的模块开关:

1. **大数据模块**(`isa-bigdata` umbrella:Kafka/Flink/StarRocks/Iceberg/Dataphin)
   —— 企业版按客户需要装或不装;**SaaS 永远不装**。
2. **多租户 + 计费模块**(注册/API key/计量/计费/限流)
   —— **仅 SaaS**;on-prem 单租户不需要,且**不应** sync 进白标 fork。

## 形态关系图

```
                    isA 产品(单一代码源 xenoISA/isA_*)
                              │
            ┌─────────────────┴─────────────────┐
            ▼                                     ▼
   ┌──────────────────┐                  ┌──────────────────┐
   │ 企业版 / On-Prem  │                  │ SaaS / 自营托管    │
   │ 单租户·模块化     │                  │ 多租户·托管        │
   ├──────────────────┤                  ├──────────────────┤
   │ + 大数据(可选)   │                  │ - 无大数据         │
   │ - 无计费          │                  │ + 多租户/计费/限流 │
   │ 白标脱敏 → sn_*   │                  │ isA 品牌           │
   └──────────────────┘                  └──────────────────┘
            │                                     │
            ▼                                     ▼
   交付给客户(如 SN)                      api.isa.xxx 对外开放
   sn_cloud/docs/implementation-delivery   (本目录)
```

> **白标 `sn_*` fork** 只是企业版之上的品牌脱敏层(`ISA_*→SN_*`),
> 不是另一个产品。SN = 企业版·全量(含大数据)的一个白标交付实例。

## 本目录范围

本目录聚焦 **SaaS edition** 的部署设计。企业版/on-prem 的交付细节(IDC、
网络设备、堡垒机、离线包、Dataphin、cutover/rollback)见
`sn_cloud/docs/implementation-delivery/`——那是企业版的一个具体白标交付。

| Document | Purpose |
|---|---|
| `licensing-model.md` | **授权模型总纲**:密钥 vs license、端到端流程、四个授权旋钮(edition + 三把锁 + enforce)、密钥策略 A/B。跨 edition,先读这页 |
| `edition-bom.md` / `edition-boundary.md` | 每个 edition 装什么 / repo 归类(平台镜像 vs 客户专属) |
| `saas-production-architecture-design.md` | SaaS 形态生产架构:集群、网络、多租户、轻量数据、网关、计费、与企业版/白标的模块边界 |
| `tenant-isolation-design.md` | (待写)SaaS 多租户隔离粒度 + API key + 计量计费 |
| `saas-values/` | (待写)SaaS profile 的 Helm values(关大数据、开多租户) |

## 模块边界(防串台)

| 模块 | 企业版·全量 | 企业版·精简 | SaaS | 实现要点 |
|---|:---:|:---:|:---:|---|
| 核心服务(Agent/MCP/Model/Data) | ✅ | ✅ | ✅ | 始终在 upstream |
| 轻量数据(PG/Redis/MinIO/DuckDB/Qdrant) | ✅ | ✅ | ✅ | isA_Data 默认依赖 |
| 大数据(`isa-bigdata`) | ✅ | ❌ | ❌ | 独立 umbrella chart,profile 控制 |
| 多租户/计费/限流 | ❌ | ❌ | ✅ | SaaS-only,独立 repo 或 sanitizer 排除 |
| 白标脱敏 | ✅(→sn_*) | ✅(→sn_*) | ❌ | 仅 on-prem 走 sanitizer |
