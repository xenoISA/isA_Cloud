# Runbook — Enable external LLM provider API mode (SN on-prem)

## Symptom
`/api/v1/invoke` with `provider=openai` (or anthropic/cerebras/openrouter) returns
**503**: `"All providers failed … Provider openai is not configured or enabled"`.

## Root cause
isa-model's `config_manager.py` enables a provider **only if its API-key env var is
present** (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CEREBRAS_API_KEY`,
`OPENROUTER_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`, `REPLICATE_API_TOKEN`):
`config.enabled = bool(config.api_key)`.

Those env vars come from the ESO-synced `isa-platform-secrets`, but its
ExternalSecret only maps **infra + brightdata** keys — **no LLM provider keys**,
and **no Vault path** for them existed. So external providers are never enabled.

```
Vault (no llm-providers path) → ExternalSecret (no OPENAI_API_KEY) →
  isa-platform-secrets (no provider keys) → isa-model env (none) → providers disabled → 503
```

## Prerequisite: egress
This is on-prem (IDC). External provider calls need **internet egress from the
cluster**. Issue isA_Model#549 ("NetworkPolicy blocks egress to external AI
providers") shows this has been a real gate. Confirm egress before wiring keys:
```bash
kubectl -n sn-cloud-production run egress-test --rm -it --image=curlimages/curl --restart=Never -- \
  curl -sS -m 10 -o /dev/null -w '%{http_code}\n' https://api.openai.com/v1/models
```
If the IDC is air-gapped, external API mode is intentionally unavailable — stay
local-first (the local GPU fleet already serves all modalities).

## Fix (strict order — ESO fails the whole sync if a Vault property is missing)

### 1. Seed the keys into Vault
```bash
vault kv put secret/isa-cloud/production/llm-providers \
  openai-api-key='sk-...' \
  anthropic-api-key='sk-ant-...'
  # add cerebras-api-key / openrouter-api-key only if you'll enable them
```

### 2. Apply the ExternalSecret + isa-model wiring
The provider keys live in a **separate** ExternalSecret (`isa-model-provider-keys`)
so a missing key can never break the infra secret. List ONLY properties seeded in
step 1 (uncomment the rest in the manifest as you seed them).
```bash
kubectl apply -f deployments/editions/sn/externalsecret-isa-model-providers.yaml
# isa-model already references it via extraSecretRefs (optional:true) — redeploy
# the chart so the new envFrom + r17 image land.
```

### 3. Verify the sync + restart
```bash
kubectl -n sn-cloud-production get externalsecret isa-model-provider-keys      # SecretSynced=True
kubectl -n sn-cloud-production get secret isa-model-provider-keys -o jsonpath='{.data}' | jq 'keys'
kubectl -n sn-cloud-production rollout restart deploy/isa-model
```

### 4. Test API mode
```bash
kubectl -n sn-cloud-production port-forward svc/isa-model 8082:8082 &
curl -s http://127.0.0.1:8082/api/v1/invoke -H 'Content-Type: application/json' \
  -d '{"service_type":"text","task":"chat","provider":"openai","model":"gpt-4o-mini","input_data":"Say hello","max_tokens":10}'
# expect success:true, runtime=openai (not 503)
```

## Related fix shipped in r17
`provider=isa` text *without* an explicit model used to resolve to `gpt-5-nano`
(an OpenAI name) and 404 on the local vLLM. Fixed in `model_router.py`: the
profile default model now applies whenever the effective provider is the profile
provider (`isa`) — text→`qwen3.6-27b` (`VLLM_DEFAULT_MODEL`), vision→
`qwen3-vl-8b` (`LOCAL_VLM_RUNTIME_MODEL`), audio→`LOCAL_STT_RUNTIME_MODEL`.
So local inference works without naming a model.
