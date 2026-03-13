# Runbook: TLS Certificate Rotation

## Symptoms

- `SSL: CERTIFICATE_VERIFY_FAILED` or `certificate has expired` errors
- Services failing to connect to each other
- Browser showing certificate warnings for web endpoints
- APISIX returning 502 with SSL errors in logs

## Quick Health Check

```bash
# Check certificate expiry for all TLS secrets
kubectl get secrets -n isa-cloud-local -o json | \
  jq -r '.items[] | select(.type=="kubernetes.io/tls") | .metadata.name' | \
  while read secret; do
    EXPIRY=$(kubectl get secret "$secret" -n isa-cloud-local -o jsonpath='{.data.tls\.crt}' | \
      base64 -d | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
    echo "$secret: expires $EXPIRY"
  done

# Check APISIX SSL certificates
curl -s http://localhost:9180/apisix/admin/ssls -H "X-API-KEY: ${APISIX_ADMIN_KEY}" | \
  jq '.list[].value | {sni: .snis, expiry: .validity_end}'

# Check cert-manager certificates (if installed)
kubectl get certificates -n isa-cloud-local -o wide 2>/dev/null
```

## Certificate Types in isA Platform

| Certificate | Location | Used By | Rotation Method |
|-------------|----------|---------|-----------------|
| APISIX gateway TLS | K8s secret `apisix-tls` | APISIX ingress | Manual or cert-manager |
| Service-to-service mTLS | K8s secrets per service | Inter-service comms | Manual |
| PostgreSQL TLS | PG config / K8s secret | DB connections | Manual |
| Redis TLS | Redis config / K8s secret | Cache connections | Manual |
| NATS TLS | NATS config / K8s secret | Message bus | Manual |

## Rotation Procedures

### 1. APISIX Gateway Certificate

```bash
# Generate new certificate (or use cert-manager / ACME)
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout tls.key -out tls.crt \
  -days 365 -subj "/CN=*.isa.cloud"

# Update Kubernetes secret
kubectl create secret tls apisix-tls \
  -n isa-cloud-local \
  --cert=tls.crt --key=tls.key \
  --dry-run=client -o yaml | kubectl apply -f -

# Reload APISIX (picks up new certs without restart)
kubectl rollout restart deploy/apisix -n isa-cloud-local

# Verify
curl -vk https://localhost:9443 2>&1 | grep "expire date"
```

### 2. Service-to-Service mTLS

```bash
# Generate CA (if not using existing)
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout ca.key -out ca.crt \
  -days 3650 -subj "/CN=isA Internal CA"

# Generate service cert signed by CA
SERVICE_NAME="mcp-service"
openssl req -newkey rsa:2048 -nodes \
  -keyout "${SERVICE_NAME}.key" -out "${SERVICE_NAME}.csr" \
  -subj "/CN=${SERVICE_NAME}.isa-cloud-local.svc.cluster.local"

openssl x509 -req -in "${SERVICE_NAME}.csr" \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out "${SERVICE_NAME}.crt" -days 365

# Update secret
kubectl create secret tls "${SERVICE_NAME}-tls" \
  -n isa-cloud-local \
  --cert="${SERVICE_NAME}.crt" --key="${SERVICE_NAME}.key" \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart service to pick up new cert
kubectl rollout restart deploy/"${SERVICE_NAME}" -n isa-cloud-local
```

### 3. PostgreSQL TLS

```bash
# Generate server cert
openssl req -newkey rsa:2048 -nodes \
  -keyout pg-server.key -out pg-server.csr \
  -subj "/CN=postgresql.isa-cloud-local.svc.cluster.local"

openssl x509 -req -in pg-server.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out pg-server.crt -days 365

# Update secret
kubectl create secret generic postgresql-tls \
  -n isa-cloud-local \
  --from-file=tls.crt=pg-server.crt \
  --from-file=tls.key=pg-server.key \
  --from-file=ca.crt=ca.crt \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart PostgreSQL
kubectl rollout restart deploy/postgresql -n isa-cloud-local

# Verify TLS connection
kubectl exec -n isa-cloud-local deploy/postgresql -- \
  psql "host=localhost user=postgres sslmode=verify-full sslrootcert=/tls/ca.crt" \
  -c "SHOW ssl;"
```

### 4. Redis TLS

```bash
# Generate Redis cert
openssl req -newkey rsa:2048 -nodes \
  -keyout redis.key -out redis.csr \
  -subj "/CN=redis-master.isa-cloud-local.svc.cluster.local"

openssl x509 -req -in redis.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out redis.crt -days 365

# Update secret
kubectl create secret generic redis-tls \
  -n isa-cloud-local \
  --from-file=tls.crt=redis.crt \
  --from-file=tls.key=redis.key \
  --from-file=ca.crt=ca.crt \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart Redis
kubectl rollout restart deploy/redis-master -n isa-cloud-local
```

## Automated Rotation with cert-manager

If cert-manager is installed, certificates auto-renew. Verify setup:

```bash
# Check cert-manager is running
kubectl get pods -n cert-manager

# Check certificate status
kubectl get certificates -n isa-cloud-local

# Check certificate renewal events
kubectl describe certificate -n isa-cloud-local | grep -A 3 "Events:"
```

## Emergency: Expired Certificate

If a certificate has already expired and services are down:

1. **Immediate**: Generate a self-signed cert to restore connectivity
   ```bash
   openssl req -x509 -newkey rsa:2048 -nodes \
     -keyout emergency.key -out emergency.crt \
     -days 30 -subj "/CN=emergency"
   ```
2. **Apply** to the affected secret and restart the service
3. **Follow up** with proper certificate rotation within the 30-day window

## Preventive Monitoring

### Alerts to set up
- Certificate expiry < 30 days: warning
- Certificate expiry < 7 days: critical
- cert-manager renewal failures

### Periodic checks
- Monthly: run the health check script above to audit all cert expiry dates
- After cluster upgrades: verify all TLS secrets are intact
