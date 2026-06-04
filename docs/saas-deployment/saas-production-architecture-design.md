# isA SaaS Edition — Production Architecture Design

> Status: isA-owned design baseline. 这是 isA 产品 **SaaS edition** 的生产
> 架构基线。SaaS 是 isA 的一种部署形态(见 `README.md` 的 editions 矩阵),
> 与**企业版/on-prem**(其白标交付实例即 SN,见
> `sn_cloud/docs/implementation-delivery/`)同源同代码、不同 profile。

## Design Position

SaaS edition 由 isA 自营托管。它与企业版是**同一套代码、不同部署 profile**
的关系,而非两个产品。SaaS profile 的特征:

1. **多租户**:一套部署服务 N 个开发者,租户之间必须隔离。
   (企业版是单租户,不涉及。)
2. **关大数据模块**:`isa-bigdata`(Kafka/Flink/StarRocks/Iceberg/Dataphin)
   **永不安装**;只跑 isA_Data 的 PG / Redis / MinIO / DuckDB / Qdrant。
   (企业版可按客户需要开关此模块。)
3. **开多租户+计费模块**:注册/API key/计量/计费/限流。
   (企业版单租户不需要,且此模块不进白标 fork。)
4. **自营运维**:公网入口 + WAF + 自动证书 + 持续部署,无堡垒机 /
   离线包 / IDC 网络设备(那些是 on-prem 交付才有的)。
5. **不走白标脱敏**:SaaS 用 isA 品牌;只有 on-prem 交付才过
   `ISA_*→SN_*` sanitizer。

---

## Design Approaches Considered

### Approach A: 与 SN 同集群,仅 namespace 隔离

- **How**: isA 和 SN 跑在同一个 K8s 集群,用 `isa-saas` / `sn-cloud-*`
  两个 namespace + NetworkPolicy 区分。
- **Effort**: small. **Risk**: high.
- **Pros**: 成本最低,复用一套基础设施。
- **Cons**: SaaS 与 OP 混跑——大数据栈资源争抢、爆炸半径共享、一次集群
  事故同时打掉自营业务和客户交付物;计费/合规边界模糊。**不符合"SaaS vs
  OP 两条线"的定位。**

### Approach B: 独立集群,共享云账号与可观测

- **How**: isA 自己一个 K8s 集群(`isa-saas-prod`),SN 各客户各自集群;
  isA 集群内用 namespace 区分 `prod` / `staging`;Prometheus/Loki/Grafana
  可与内部工具共享。镜像走 isA 自己的 registry。
- **Effort**: medium. **Risk**: medium.
- **Pros**: SaaS 与 OP 物理隔离;爆炸半径独立;计费/限流/租户能力只活在
  isA 集群;复用云账号降低管理成本。匹配当前 repo 现状(服务多为
  ClusterIP,APISIX 为 API 控制点,bigdata 是独立 umbrella 可不装)。
- **Cons**: 需要维护两套部署配置与 CI/CD。

### Approach C: 独立云账号 + 独立一切(全零信任)

- **How**: isA 独立云账号 / 独立 VPC / 独立 registry / service mesh mTLS /
  per-tenant 集群,从第一天就全 default-deny。
- **Effort**: large. **Risk**: high(首发即引入过多活动面)。
- **Pros**: 最强隔离与安全姿态。
- **Cons**: SaaS 首发不需要 per-tenant 集群;service mesh 增加过多复杂度。
  可作为企业级租户的演进目标,不作为起步形态。

---

## Recommended Architecture

**首发用 Approach B。** SaaS 与 SN 物理隔离(独立集群 + 独立 registry +
独立 CI/CD + 独立数据),但复用云账号和可观测栈降低运营成本。租户隔离起步
用 row-level + API key,按付费档位演进到 schema/实例隔离(见
`tenant-isolation-design.md`)。

```
┌──────────────────────────────────────────────────────────────┐
│  isA SaaS 自营云(独立集群 isa-saas-prod)                       │
│                                                                │
│  公网 ──► WAF / DDoS ──► APISIX 北向网关(api.isa.xxx)          │
│                              │                                  │
│             ┌────────────────┼────────────────┐                │
│             ▼                ▼                ▼                 │
│        isA_Agent        isA_MCP          isA_Model              │
│        (8080)           (8081)           (8082)                 │
│             │                                                   │
│             ▼                                                   │
│        isA_Data (8084, FastAPI) ── 轻量数据层                    │
│             │                                                   │
│   ┌─────────┼─────────┬─────────┬─────────┐                    │
│   ▼         ▼         ▼         ▼         ▼                     │
│ Postgres  Redis     MinIO    DuckDB    Qdrant                   │
│ (租户schema/row-level + bucket + 命名空间隔离)                  │
│                                                                │
│  SaaS-only 控制面:注册登录 · API key · 用量计量 · 计费 · 限流   │
│  Consul 服务发现 · cert-manager 自动证书 · GitOps 持续部署        │
│                                                                │
│  ❌ 不部署:Kafka · Flink · StarRocks · Iceberg · Dataphin       │
└──────────────────────────────────────────────────────────────┘

         运行隔离 ▲▲▲ (自营云独立于任何客户环境)

┌──────────────────────────────────────────────────────────────┐
│  企业版 / On-Prem 交付(同源代码,不同 profile)                 │
│  装大数据 + 白标 → 即 SN(sn_cloud/docs/implementation-delivery)│
│  不装大数据 → 企业版·精简                                        │
└──────────────────────────────────────────────────────────────┘
```

---

## Network Design

| 项 | isA SaaS | 对比 SN OP |
|---|---|---|
| 入口 | 公网 LB → WAF/DDoS → APISIX | IDC VIP → FortiGate → APISIX |
| 证书 | cert-manager 自动签发/续期(Let's Encrypt 或云托管) | BYO PKI / 客户 CA |
| 域名 | isA 自有(`api.isa.xxx`、`app.isa.xxx`) | 客户内网 FQDN |
| 管理面访问 | 云 IAM + OIDC,无堡垒机 | JumpServer 堡垒机 |
| 数据面暴露 | 全部 ClusterIP,仅 APISIX 对外 | 同左,额外私有路由给企业系统 |
| Egress | 按需放行(模型 API / 计费 / 邮件) | 受限,多为离线 |

NetworkPolicy:default-deny,仅放行 APISIX → 服务、服务 → 数据存储、
服务 → Consul。SaaS-only 控制面(计费/计量)单独打 label,可独立限流。

---

## Multi-Tenancy(SN 没有的核心)

SN 是单租户,不涉及。isA SaaS 必须在一套部署内隔离 N 个开发者:

| 粒度 | 隔离强度 | 成本 | 适用档位 |
|---|---|---|---|
| **row-level**(`tenant_id` 列 + RLS) | 低 | 最低 | free / 标准开发者(起步默认) |
| **schema-per-tenant** | 中 | 中 | 付费团队 |
| **实例 / namespace-per-tenant** | 高 | 高 | 企业租户(接近 OP) |

- **MinIO**:bucket 前缀或 policy 按 `tenant_id` 隔离(`tenant-<id>/...`)。
- **Qdrant**:collection 按租户命名或 payload 过滤。
- **Redis**:key 前缀 + 逻辑 DB 隔离;限流计数器按 API key。
- **入口**:每个租户一把 API key,APISIX 做 key 认证 + per-key 限流。

详见 `tenant-isolation-design.md`(待写)。

---

## Data Layer(轻量,确认无大数据依赖)

证据:`isA_Data/config/dependencies.yaml` 仅声明 PG/Redis/MinIO/DuckDB/Qdrant;
`isA_Data/src/main.py` 的 async client 只有这几个,**无 Kafka 消费者、无 Flink
CDC**。因此 SaaS 部署**直接不安装** `isa-bigdata` umbrella chart。

| 存储 | 用途 | 备份 |
|---|---|---|
| PostgreSQL | 业务数据 + 租户元数据 + 计费账目 | 云托管自动快照 / WAL |
| Redis | 会话 / 缓存 / 限流计数 | RDB/AOF |
| MinIO | 对象 / 数据集 / 向量原文 | 跨区复制 |
| DuckDB | 内嵌分析(开发者本地分析) | 随对象存储 |
| Qdrant | 向量检索 / RAG | 快照 |

---

## SaaS-only 控制面(不可 sync 进 SN)

isA SaaS 需要、但 SN OP **不需要**的能力:

- 开发者注册 / 登录 / 组织管理
- API key 签发与轮换
- 用量计量(按调用 / token / 存储)
- 计费与订阅档位
- per-key / per-tenant 限流

**白标风险**:这些代码若被 isA→SN sanitizer 同步过去,会给单租户客户引入
无用且增加安全面/license 风险的模块。处置:

- 放进独立 repo(如 `isA_Billing` / `isA_Tenant`)且**不纳入 16-repo 同步 map**;或
- 在 `scripts/sanitize.sh` 加 SaaS-only 模块的排除规则。

(对应 `.claude/rules/white-label.md` 的"Customer-specific code does NOT
belong in isA"的反向约束:SaaS-only code does NOT belong in SN。)

---

## CI/CD & Observability

| 项 | isA SaaS | SN OP |
|---|---|---|
| 流水线 | 持续部署(GitOps,push 即发) | sync → sanitize → 打包离线交付 |
| Registry | isA 自有 `registry/isa-*` | 客户 Harbor `sn-*`(离线灌入) |
| 发布节奏 | 持续 / 灰度 | 跟随月度 sync |
| 可观测 | Prometheus + Loki + Grafana(label `tenant=<id>`) | 同栈,客户侧独立 |
| 告警 | isA on-call | 客户 / hypercare |

---

## Isolation Boundary(SaaS 运行面 vs on-prem 交付,检查清单)

虽是同源代码,但 SaaS 自营环境与任何客户 on-prem 部署在**运行时必须完全
独立**,不共享:

- [ ] K8s 集群(SaaS `isa-saas-prod` vs 客户 IDC 集群)
- [ ] 镜像仓库(isA registry vs 客户 Harbor)
- [ ] CI/CD 流水线(持续部署 vs 打包离线交付)
- [ ] 数据存储实例(PG/Redis/MinIO/Qdrant 各自独立,无共享 schema/bucket)
- [ ] 域名 / 证书 / DNS
- [ ] SaaS-only 控制面代码不流入白标 fork(sanitizer 排除)
- [ ] 监控/日志租户标签互不串台

---

## Open Items

1. `tenant-isolation-design.md`:租户隔离粒度的 A/B/C 取舍与落地。
2. `saas-values/`:裁掉 bigdata 的 isA 开发者环境 Helm values。
3. sanitizer 排除规则:确认 SaaS-only 模块不进 SN。
4. 计量/计费的数据模型(PostgreSQL schema)。
