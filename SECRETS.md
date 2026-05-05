# isA Cloud Secrets

## MLflow APISIX JWT Auth

`/mlflow` is protected by APISIX `jwt-auth` in local deployments. The APISIX
consumer validates JWTs issued by `isA_user/auth_service`, which currently signs
local tokens with `HS256` and `JWT_SECRET`.

Create the APISIX validation secret with the same value used by auth_service:

```bash
kubectl create secret generic auth-service-jwt \
  -n isa-cloud-local \
  --from-literal=jwt-secret="${JWT_SECRET}"
```

Issue a client-credentials token through auth_service:

```bash
curl -X POST http://localhost:8201/oauth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "grant_type=client_credentials&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&scope=mlflow.read mlflow.write"
```

Use the returned token when calling MLflow through APISIX:

```bash
curl http://127.0.0.1:9080/mlflow/api/2.0/mlflow/experiments/search \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

For Python MLflow clients, export:

```bash
export MLFLOW_TRACKING_URI=http://127.0.0.1:9080/mlflow
export MLFLOW_TRACKING_TOKEN="${ACCESS_TOKEN}"
```
