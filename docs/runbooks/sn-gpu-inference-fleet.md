# Runbook — SN GPU Inference Fleet

> Deploy, verify and operate the on-prem local inference fleet.
> Capability/product view: [`../saas-deployment/sn-gpu-inference-fleet.md`](../saas-deployment/sn-gpu-inference-fleet.md).
> Allocation policy & rationale: [`../adr/0010-local-gpu-inference-allocation.md`](../adr/0010-local-gpu-inference-allocation.md).
> Context: `KUBECONFIG=~/.kube/sn-rancher.yaml`, namespace `sn-cloud-production`.

## Manifests

All under `deployments/kubernetes/production/manifests/gpu/`:

| File | Serves | `gpu_memory_utilization` |
|------|--------|--------------------------|
| `vllm-deployment.yaml` | chat — `qwen3.6-27b` FP8 | per ADR-0010 (LLM holds 1 card) |
| `qwen3-vl-deployment.yaml` | vision — Qwen3-VL-8B-FP8 | **0.25** (KV budget), `MAX_MODEL_LEN=32768` |
| `paddleocr-vl-deployment.yaml` | OCR — PaddleOCR-VL | **0.10**, `--no-enable-prefix-caching --mm-processor-cache-gb 0` |
| `perception-bundle-deployment.yaml` | Florence-2 + SAM + SigLIP | ~0.10 (FastAPI, not vLLM) |
| `qwen3-asr-deployment.yaml` | speech-to-text | **0.10** |
| `kokoro-gpu-deployment.yaml` | TTS — Kokoro-82M GPU | baked-deps image + ConfigMap `server.py` |
| `vllm-embedding-deployment.yaml` | embeddings (pooling) | **0.22** (no KV cache) |
| `local-inference-catalog.yaml` | catalog/policy ConfigMap | — |
| `gpu-node-labels.yaml`, `model-cache-pvc.yaml`, `model-prepull-job.yaml` | placement, cache, warm-pull | — |

### Sizing rules (from ADR-0010)

- **Cap every vLLM engine.** Default `0.9` hoards a whole 96 GB card for KV
  cache that generative models don't need at these sizes.
- **Pooling models carry no KV cache.** Embedding/rerank are sized to *weights +
  headroom* — never a generative budget. (Embedding was reserving ~48 GB at 0.50;
  fixed to 0.22, freeing ~27 GB. ASR 1.7B was reserving ~24 GB at 0.25; fixed to
  0.10.)
- **The chat LLM stays on one card** — no cross-card tensor parallel (no NVLink
  → all-reduce would crawl over PCIe Gen5).

> **Live note:** the running cluster currently uses **physical GPU** (time-slicing
> disabled per the SN service-deployment playbook): `nvidia.com/gpu=2` per node,
> `sharing-strategy=none`. ADR-0010 documents both the physical and the
> MPS/time-sliced states; if MPS is activated, the per-pod cap = 1 / slices.

## Blackwell (sm_120) build constraints

- **Build on a cu128 base** (`core.harbor.domain/isa/pytorch:2.8.0-cuda12.8-cudnn9-runtime`).
  Prebuilt images bundling CUDA < 12.8 fail with *"no kernel image"* on sm_120
  (this killed `kokoro-fastapi-gpu:v0.3.0` → rebuilt on cu128).
- **vLLM is fine** — it uses its own attention kernels (no flash-attn wheel
  needed). **Avoid HF `flash_attention_2`** — it hangs on sm_120.
- Set `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` so engines survive DNS flaps
  (a wedged HF file-list call once hung the qwen3-vl engine core).

## Pushing images to Harbor (the r17 fix)

Pushing to the `core.harbor.domain` **hostname** 500s on chunked blob upload
(redirect/proxy path). Push to the LB **IP** instead:

```sh
deployments/kubernetes/production/scripts/push-to-harbor.sh \
  core.harbor.domain/isa/<image>:<tag>     # → skopeo copy to 10.60.65.10, --dest-tls-verify=false
```

## Deploy order

```sh
export KUBECONFIG=~/.kube/sn-rancher.yaml
N=sn-cloud-production
# 1. placement + cache
kubectl -n $N apply -f manifests/gpu/gpu-node-labels.yaml -f manifests/gpu/model-cache-pvc.yaml
kubectl -n $N apply -f manifests/gpu/local-inference-catalog.yaml
# 2. engines
kubectl -n $N apply -f manifests/gpu/vllm-deployment.yaml          # chat
kubectl -n $N apply -f manifests/gpu/qwen3-vl-deployment.yaml      # vision
kubectl -n $N apply -f manifests/gpu/paddleocr-vl-deployment.yaml  # OCR
kubectl -n $N apply -f manifests/gpu/perception-bundle-deployment.yaml
kubectl -n $N apply -f manifests/gpu/qwen3-asr-deployment.yaml     # STT
kubectl -n $N apply -f manifests/gpu/kokoro-gpu-deployment.yaml    # TTS
kubectl -n $N apply -f manifests/gpu/vllm-embedding-deployment.yaml
# 3. point isa-model at the local endpoints (LOCAL_*_BASE_URL)
kubectl -n $N apply -f deployments/editions/sn/configmap-isa-platform-env.yaml
```

## External providers (seed → sync → restart)

External API mode (`provider=openai|anthropic|cerebras|openrouter`) needs the
keys in Vault, synced to a secret, and isa-model **restarted** (config_manager
caches provider enablement at init — see below).

```sh
# 1. seed Vault (KV v2 mount `secret`, path isa-cloud/production/llm-providers)
#    properties: openai-api-key, anthropic-api-key, cerebras-api-key, openrouter-api-key
#    → see docs/runbooks/sn-external-llm-providers.md for the exact vault kv put
# 2. sync the ExternalSecret (maps all 4 → isa-model-provider-keys secret)
kubectl -n $N apply -f deployments/editions/sn/externalsecret-isa-model-providers.yaml
kubectl -n $N get externalsecret isa-model-provider-keys      # want SecretSynced / Ready=True
# 3. isa-model consumes it via extraSecretRefs (already in services/isa-model.yaml), then RESTART
kubectl -n $N rollout restart deploy/isa-model
```

> ⚠️ **The 503-with-keys-present trap.** `config_manager.py` evaluates
> `enabled = bool(api_key)` **once at process init**. If isa-model started before
> the keys were in env, it stays cached with providers **disabled** and returns
> *"Provider openai is not configured or enabled"* even though the key is in the
> pod env. A clean `rollout restart` is the fix — not a Vault/secret change.
> Vault has **manual Shamir unseal** (no auto-unseal) → a Vault restart re-seals
> and ExternalSecrets go `Ready=False`; unseal with 3-of-5 keys to recover.

## Verification — local vs API parity

```sh
kubectl -n $N port-forward svc/isa-model 18082:8082 &
INV=http://127.0.0.1:18082/api/v1/invoke
# text: local (provider=isa → qwen3.6-27b) vs cloud (provider=openai → gpt-4o-mini)
curl -s $INV -H 'Content-Type: application/json' \
  -d '{"service_type":"text","task":"chat","provider":"isa","input_data":"A bat and ball cost $1.10; the bat is $1 more than the ball. How much is the ball?","max_tokens":40}'
curl -s $INV -H 'Content-Type: application/json' \
  -d '{"service_type":"text","task":"chat","provider":"openai","model":"gpt-4o-mini","input_data":"<same prompt>","max_tokens":40}'
# vision: provider=isa (qwen3-vl) vs provider=openai (gpt-4o-mini), same data-URL image
```

Expected (2026-06-11): both return **$0.05**; vision both read the ground-truth
image identically (`provider_used=openai, backend_used=cloud` on the cloud leg;
`provider_used=isa` on the local leg).

## Common failures

| Symptom | Cause → fix |
|---------|-------------|
| vLLM OOM on KV cache | `gpu_memory_utilization` too high → cap it; raise `MAX_MODEL_LEN` budget |
| *"no kernel image"* | image bundles CUDA < 12.8 → rebuild on cu128 base |
| engine core hangs at load | HF DNS file-list flap → `HF_HUB_OFFLINE=1` |
| Harbor push 500 (EOF) | pushing to hostname → use `push-to-harbor.sh` (IP) |
| *"Provider X not configured"* with key present | config cached at init → `rollout restart deploy/isa-model` |
| ExternalSecret `Ready=False` | Vault sealed → unseal 3-of-5 |
