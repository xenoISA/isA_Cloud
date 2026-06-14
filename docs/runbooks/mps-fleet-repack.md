# MPS Fleet Repack — Engine Manifest Readiness & LLM Consolidation

> Operational companion to ADR 0010 (`docs/adr/0010-local-gpu-inference-allocation.md`).
> Covers the repack step (Kokoro CPU→GPU, co-tenancy on k8s-03/k8s-02) and the
> chat-LLM consolidation onto k8s-01 that frees k8s-02.
>
> **Authoring + read-only only.** Every mutating command below is given as an
> exact, *un-run* command. Do NOT apply/scale/relabel as part of authoring.

## Background (verified read-only, 2026-06-09)

- 3 nodes × 2×96 GB Blackwell. `nvidia.com/gpu` allocatable = **2 per node**
  (physical cards; MPS not yet active — `nvidia.com/mps.capable=false` on all 3).
- Node roles today: `sn-prod-k8s-01` and `sn-prod-k8s-02` both
  `sn.io/gpu-role=llm` + `isa.io/gpu-role-llm=true`; `sn-prod-k8s-03`
  `sn.io/gpu-role=specialty` + `isa.io/gpu-role-specialty=true`. No node carries
  a `generative` role yet — **k8s-02 must be relabeled** generative as part of
  the repack.
- Under MPS with `renameByDefault=false`, a pod keeps requesting
  `nvidia.com/gpu: 1` and receives **one slice** (96 GB ÷ replicas-per-card).
  So a manifest that already requests `nvidia.com/gpu: 1` and targets the right
  node needs **no resource-shape change** — only the node's MPS config/label
  flip changes the slice size it lands in.

## Per-engine MPS readiness

| Engine | Manifest | Target node (ADR) | Requests `nvidia.com/gpu:1`? | Specialty/generative affinity? | MPS-ready as-is? | Change needed |
|--------|----------|-------------------|------------------------------|-------------------------------|------------------|---------------|
| kokoro | `gpu/kokoro-tts-deployment.yaml` (CPU interim) → **`gpu/kokoro-tts-deployment.gpu.yaml`** (new) | k8s-03 (24 GB) | CPU interim: **no GPU**. GPU variant: **yes** | CPU interim: none. GPU variant: specialty (restored) | **Not as-is** | Apply the new GPU variant: `USE_GPU=true`, `DEVICE_TYPE=cuda`, image `kokoro-fastapi-gpu:v0.3.0`, `nvidia.com/gpu:1`, specialty affinity + toleration. Replaces the CPU interim. |
| whisper-large-v3-turbo | `gpu/faster-whisper-v3-turbo-deployment.yaml` | k8s-03 (24 GB) | **yes** (req+lim) | **yes** — specialty (isa.io/gpu-role-specialty In[true] OR sn.io/gpu-role In[specialty]) | **Yes** | None |
| qwen3-embedding-8b | `gpu/vllm-embedding-deployment.yaml` | k8s-03 (24 GB) | **yes** (req+lim) | **yes** — specialty | **Yes** | None. (GPU_MEMORY_UTILIZATION already capped at 0.50; under a 24 GB slice that's ~12 GB and the 8B needs ~16 GB — see note below.) |
| qwen-image-2.0 | `gpu/qwen-image-deployment.yaml` | k8s-02 (48 GB) | **yes** (req+lim) | partial — has **specialty** affinity, but ADR places it on the **generative** node (k8s-02) | **Resource shape yes; placement no** | No resource-shape change. Re-point node affinity to the generative node once k8s-02 is relabeled (`sn.io/gpu-role In[generative]` / `isa.io/gpu-role-generative In[true]`), or relabel k8s-02 `specialty` to match the existing manifest. Header comment still says "no MIG/MPS / GPU 4" — refresh wording. |
| qwen3-asr-1.7b | *none* (catalog-only: `local-inference-catalog.yaml`) | k8s-03 (24 GB) | n/a | n/a | **No manifest yet** | Author a new Deployment (ADR rollout step 6): request `nvidia.com/gpu:1`, specialty affinity + `nvidia.com/gpu` toleration, runtime image to be built/mirrored. |
| qwen3-tts | *none* (catalog-only) | k8s-03 (24 GB) | n/a | n/a | **No manifest yet** | Same as qwen3-asr — author Deployment with `nvidia.com/gpu:1` + specialty affinity once the runtime image exists. |
| flux-2-schnell | *none* (catalog-only; referenced in qwen-image header) | k8s-02 (48 GB) | n/a | n/a | **No manifest yet** | Author a Triton/diffusers Deployment: `nvidia.com/gpu:1` + generative-node affinity. |
| wan-2.2 | *none* (catalog-only) | k8s-02 (48 GB) | n/a | n/a | **No manifest yet** | Author a Deployment: `nvidia.com/gpu:1` + generative-node affinity. |

**Summary:** of the engines that have manifests today, **whisper** and
**embedding** are MPS-ready with no change; **kokoro** needs the new GPU variant
(authored here); **qwen-image** needs no resource-shape change but its node
placement must be reconciled with the generative relabel of k8s-02. ASR, TTS,
flux, and wan have no manifests yet and are authored later (ADR step 6).

> **Slice-size caveat (embedding):** a 24 GB MPS slice on k8s-03 (replicas=4)
> caps per-client memory; `Qwen3-Embedding-8B` (~16 GB) plus vLLM overhead can
> exceed `0.50 × 24 GB`. If it OOMs on the slice, either bump
> `GPU_MEMORY_UTILIZATION` toward the slice ceiling or give it a larger slice
> node. No manifest *shape* change — a config value, validated by the post-MPS
> micro-benchmark (ADR step 7).

## LLM consolidation — free k8s-02, keep chat serving

The chat LLM is fronted by Service **`vllm-qwen36-27b-pool`** (selector
`engine=vllm`, `isa-model/model-id=qwen3.6-27b`). Read-only inspection found the
pool currently has **four** backends behind it, not three:

| Deployment | Node | Model | In pool? |
|------------|------|-------|----------|
| `vllm-qwen36-27b-node01-a` | k8s-01 | qwen3.6-27b | yes |
| `vllm-qwen36-27b-node01-b` | k8s-01 | qwen3.6-27b | yes |
| `vllm-qwen36-27b-node02-b` | k8s-02 | qwen3.6-27b | yes |
| **`vllm`** (the "mystery" deploy) | **k8s-02** | qwen3.6-27b | **yes** |

### Identity of the mystery `vllm` deployment

It is **not** an unknown model. `kubectl get deploy vllm -o yaml` +
`cm/vllm-runtime-config` show:

- Labels `app=vllm`, **`engine=vllm`**, **`isa-model/model-id=qwen3.6-27b`**,
  `isa-model/instance-group=primary`.
- Config: `MODEL_ID=Qwen/Qwen3.6-27B-FP8`, `SERVED_MODEL_NAME=qwen3.6-27b`,
  `TENSOR_PARALLEL_SIZE=1`, `GPU_MEMORY_UTILIZATION=0.85`, image
  `vllm/vllm-openai:cu130-nightly`, args `vllm serve … --reasoning-parser qwen3
  --language-model-only`.
- Node affinity: `isa.io/gpu-role-llm In[true]` OR `sn.io/gpu-role In[llm]`;
  pod currently on **sn-prod-k8s-02**.

Because its labels match the pool selector exactly, **it is a chat backend** —
the original single-Deployment chat server, now co-existing with the newer
`node01-a/-b` / `node02-b` pool members. **Freeing k8s-02 therefore means
removing BOTH k8s-02 backends: `vllm-qwen36-27b-node02-b` AND `vllm`.** Dropping
only `node02-b` would leave the `vllm` pod still holding a card on k8s-02.

After removing both, the pool drops from 4 → 2 backends, both on k8s-01 (matches
the ADR "pool drops 3→2 on k8s-01" intent; the ADR's "3" omitted the legacy
`vllm` deploy that this inspection surfaced).

### Exact commands to free k8s-02 (DO NOT RUN — authoring only)

Run with the SN prod kubeconfig and read/skip-tls flags:

```bash
export KUBECONFIG=/Users/xenodennis/.kube/sn-prod.conf
KF="--insecure-skip-tls-verify=true --request-timeout=15s"
NS=sn-cloud-production

# 0. Pre-check: confirm the two surviving k8s-01 backends are Ready BEFORE removing
#    anything (the pool must keep serving throughout).
kubectl $KF -n $NS get pods -l isa-model/model-id=qwen3.6-27b -o wide
kubectl $KF -n $NS get endpoints vllm-qwen36-27b-pool

# 1. Scale the k8s-02 pool member to 0 (graceful; keeps the manifest for rollback).
kubectl $KF -n $NS scale deployment vllm-qwen36-27b-node02-b --replicas=0

# 2. Scale the legacy 'vllm' chat backend (also on k8s-02) to 0.
kubectl $KF -n $NS scale deployment vllm --replicas=0

# 3. Verify the pool now has exactly the two k8s-01 backends and k8s-02 holds no
#    LLM pods, then confirm k8s-02 GPUs are free before relabeling it generative.
kubectl $KF -n $NS get endpoints vllm-qwen36-27b-pool
kubectl $KF -n $NS get pods -l isa-model/model-id=qwen3.6-27b -o wide
kubectl $KF get node sn-prod-k8s-02 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}{"\n"}'
```

Notes:
- Use `scale --replicas=0` (not `delete`) so the Deployments/Services remain for
  rollback; deleting is only appropriate once the generative repack on k8s-02 is
  proven. If full removal is later desired:
  `kubectl $KF -n $NS delete deployment vllm-qwen36-27b-node02-b vllm`.
- Scale **one at a time** and re-check endpoints between steps so the pool never
  drops below the two k8s-01 backends — that is what keeps chat serving.
- These commands free k8s-02 of LLM workloads only. Relabeling k8s-02 to the
  generative role and rolling the MPS device-plugin config are separate ADR
  steps (3 and 5) and are also out of scope for this authoring task.
