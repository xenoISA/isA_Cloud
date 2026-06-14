# SN APISIX north-south ingress

MetalLB (apisix-gateway LoadBalancer, ext IP 10.60.65.210) -> APISIX -> Consul discovery -> service.

## Required for the chain to work (all verified 2026-06-09)
1. **Services register their pod IP**: every backend deployment sets
   `SERVICE_HOST` via downward API `fieldRef: status.podIP` (isa_common consul_client
   otherwise registers the pod hostname -> APISIX 502). Apply to all user-* + isa-* backends.
2. **Routes provisioned**: the consul-apisix-sync CronJob (this dir) creates consul-discovery
   routes from the Consul catalog. Build/push the image from ./Dockerfile + ./sync_routes.sh.
3. **APISIX worker_processes pinned**: set `worker_processes: "4"` in the apisix configmap
   (data."config.yaml"). `auto` on a many-core node spawns dozens of workers and the consul
   discovery broadcast saturates the worker_events socket -> broad 502/503. THIS was the
   root cause of gateway instability.

## sync_routes.sh fixes vs staging
- limit-count plugin: pass redis_password (Redis is password-protected).
- removed active health checks (redundant with consul discovery; they saturated worker_events).

## Verify (IN-CLUSTER, not external — VPN gives false timeouts)
kubectl run t --rm -it --image=curlimages/curl -- \
  curl http://apisix-gateway.sn-cloud-production.svc.cluster.local/api/v1/<svc>/health
Route URIs are derived per service (some singular, some plural) — check the actual URI.
