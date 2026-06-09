# Runbook: On-Prem Full Layered Platform

This runbook defines the reusable product boundary for an on-prem-full
deployment that combines the cloud platform, the bigdata backbone, and
Dataphin as an attached data middle-platform.

Customer-specific IPs, VIPs, screenshots, license paths, kubeconfig names, and
incident timelines belong in the customer delivery repository. This document
keeps only the reusable isA_Cloud rules.

## Layer Model

| Layer | Product responsibility | Customer evidence responsibility |
|---|---|---|
| Cloud platform | Kubernetes/EonKube or compatible cluster, CSI storage classes, registry, ingress/LB, cert-manager, Vault/External Secrets, APISIX, platform infra services, user/application services | Actual nodes, storage array facts, VIPs, DNS, StorageClass names, Harbor address, access path, live pod/service state |
| Bigdata platform | `isa-bigdata` umbrella: Kafka, Apicurio, PostgreSQL, Hive Metastore, MinIO lake, Iceberg tooling, StarRocks, Flink, optional Flink CDC | Customer values, capacity, PVC/PV evidence, smoke output, storage expansion evidence |
| Data middle-platform | `isa-dataphin-infra` plus vendor Dataphin package/chart/bootloader attached to the bigdata backbone | License path, offline image intake, exact Dataphin values, UI/ingress/DNS evidence, functional smoke |

## Deployment Order

1. Bring up or verify the cloud platform substrate: Kubernetes, storage, registry,
   ingress/LB, cert-manager CRDs, Vault/External Secrets, and APISIX or a chosen
   north-south ingress path.
2. Deploy platform infra services and confirm they are internal by default.
3. Deploy `isa-bigdata` and verify Kafka, MinIO, PostgreSQL/HMS, Flink, and
   StarRocks in that order.
4. Deploy `isa-dataphin-infra` into the Dataphin namespace.
5. Install the vendor Dataphin package into the existing cluster; do not let a
   vendor bootstrapper create a second Kubernetes cluster unless the customer
   explicitly chooses an isolated Dataphin appliance model.
6. Attach Dataphin to MinIO/HMS/Iceberg/Kafka/Apicurio/Flink/StarRocks and
   record smoke evidence.

## Boundary Rules

| Rule | Reason |
|---|---|
| Keep platform MinIO and bigdata MinIO separate. | Platform object storage and lakehouse storage have different lifecycle, capacity, and blast radius. |
| Keep Dataphin PostgreSQL/Redis dedicated. | Dataphin bootloaders need installer-level privileges and should not mutate platform or bigdata databases. |
| Do not use CI as the production installer for stateful on-prem infra. | CI should lint/render; production state changes require controlled Helm/ArgoCD operations and evidence capture. |
| Do not treat Dataphin bootloader readiness as full business acceptance. | Business acceptance also needs UI login, tenant/bootstrap validation, licensed modules, and data-source smoke. |
| Validate real Dataphin UI accounts separately from bootstrap installer accounts. | Vendor bootstraps may create hidden owner/ops users; real customer admin/ops accounts still need tenant roles, current tenant context, and session/cache refresh. |
| VIPs must be inside the real LB/MetalLB pool. | Old design addresses outside the pool produce Pending services or unreachable DNS. |
| Patch critical PVs to `Retain` if the StorageClass defaults to `Delete`. | Prevent accidental data loss from PVC deletion. |

## Status Language

Use precise status terms:

| Term | Meaning |
|---|---|
| Substrate ready | Nodes, CSI, registry, ingress/LB, and cert-manager CRDs exist and are usable. |
| Platform services ready | Core infra and application services are Running and have health evidence; known degraded sidecars are explicitly listed. |
| Bigdata backbone ready | Kafka, MinIO, PostgreSQL/HMS, Flink, StarRocks, and Apicurio are Running and pass smoke. |
| Dataphin deployed | Bootloader and enabled runtime Deployments are Ready and the login page is reachable. |
| Dataphin business usable | Real admin and ops login, tenant/bootstrap settings, licensed modules, and dependency connections all pass. |
| Accepted | Customer owner signs off evidence and open risks. |

## Reusable Checks

Do not print decoded secrets.

```bash
kubectl get nodes -o wide
kubectl get sc
kubectl -n <platform-ns> get pods,svc,pvc
kubectl -n <bigdata-ns> get pods,svc,pvc
kubectl -n <dataphin-ns> get pods,svc,ingress,pvc
kubectl -n <bigdata-ns> get kafka,flinkdeployment,starrockscluster
```

Customer repos should keep one current-status page that maps these checks to
the three layers above and links to date-stamped evidence.
