# ADR 0010 — Local GPU Inference Allocation Policy (SN 3-node Blackwell)

> Status: Proposed (2026-06-09)
> Supersedes the bootstrap GPU policy in
> `deployments/kubernetes/production/profiles/3-node/nvidia-device-plugin-physical-gpu.yaml`
> ("1 physical GPU = 1 model, no sharing"). Scoped to the SN production cluster
> (`sn-cloud-production`) but written against the unified isA_Cloud profile.

## Context

The SN production cluster is **3 nodes × 2 GPUs = 6× NVIDIA RTX PRO 6000
Blackwell Max-Q Workstation Edition**. Verified from GPU Feature Discovery:

| Fact | Value | Source |
|------|-------|--------|
| VRAM per GPU | 97 887 MB (~96 GB) | `nvidia.com/gpu.memory` |
| Total VRAM | ~576 GB | 6 × 96 GB |
| Compute capability | 12.0 (Blackwell) | `nvidia.com/gpu.compute.{major,minor}` |
| MIG capable | **false** | `nvidia.com/mig.capable` (workstation card) |
| NVLink | **absent** — PCIe Gen5 only | Max-Q workstation cards ship without NVLink |
| Current sharing | none, replicas=1 | `nvidia.com/gpu.sharing-strategy` |

The bootstrap policy gave **one whole 96 GB card to each model**. The catalog's
real VRAM footprints expose how wasteful this is:

| Model | ~VRAM | role |
|-------|-------|------|
| qwen3.6-27b (FP8) | ~30 GB | llm |
| qwen3-embedding-8b | ~16 GB | specialty |
| qwen-image-2.0 | ~40 GB | specialty |
| flux-2-schnell | ~24 GB | specialty |
| wan-2.2 | ~28 GB | elastic |
| whisper-large-v3-turbo | ~3 GB | specialty |
| bge-reranker-v2-m3 | ~2 GB | specialty |
| kokoro-82M | ~0.5 GB | specialty |

The **entire catalog sums to ~145 GB** — ~1.5 cards of VRAM — yet the
1-model-per-card rule demands 8 cards and we have 6. Cards *look* full mostly
because **vLLM reserves 90 % of VRAM for KV cache by default**
(`gpu_memory_utilization=0.9`), not because weights need it. The bottleneck is
the policy, not the hardware.

## Decision

Replace "1 GPU = 1 model" with a **VRAM-budgeted allocation policy**:

### 1. Budget by VRAM, cap vLLM

Place engines by actual VRAM need, not card count. Cap
`gpu_memory_utilization` on every vLLM engine (e.g. ~0.4–0.5 for the 27B) so it
stops hoarding whole cards.

### 2. Latency-critical engines stay dedicated; small engines co-locate

- The **chat LLM runs on a single dedicated card** — **no cross-card tensor
  parallel** (no NVLink → TP all-reduce would crawl over PCIe Gen5). A 27B
  (~30 GB) fits one 96 GB card with ample KV headroom.
- **Small, bursty, latency-tolerant specialty engines** (STT, TTS, rerank)
  **share one card** via **single-container co-location**: one container runs
  several model servers (supervisord), requests `nvidia.com/gpu: 1`, and the
  processes share the GPU through the driver's default multi-process context.
  This is the only clean way to share a card across engines **without** a sharing
  plugin — a multi-container pod cannot share one GPU because the
  `nvidia.com/gpu` request and `NVIDIA_VISIBLE_DEVICES` injection are per
  container.

### 3. GPU sharing plugin (MPS) is deferred, not adopted

MPS *is* supported at the driver level (CC 12.0). It is **not** adopted now
because:

- the NVIDIA k8s device-plugin MPS mode is **NVIDIA-labeled experimental**;
- it flips a **cluster-wide** plugin config (affects all GPU scheduling) and
  needs a maintenance window;
- it only partitions a card into **equal** slices, and isolation on workstation
  cards is **soft** (an OOM in one client can disturb neighbours).

> A vendor test deploying a 120B model does **not** validate MPS — that exercises
> single large-process serving (and, if TP, PCIe), not concurrent multi-process
> GPU sharing. MPS will be adopted only after a **single-card micro-benchmark**
> (e.g. kokoro + whisper concurrent) shows acceptable interference. Until then,
> single-container co-location covers the same need with no cluster surgery.

HAMi (arbitrary per-pod VRAM) is the fallback if independent pod lifecycles +
hard per-engine memory caps become a hard requirement.

### 4. Placement (6 × 96 GB)

| Card | Tenant(s) | ~VRAM |
|------|-----------|-------|
| k8s-01 GPU0 | qwen3.6-27b (dedicated, capped util, no TP) | ~30–50 |
| k8s-01 GPU1 | free → 2nd LLM / overflow | — |
| k8s-02 GPU0 | qwen-image-2.0 (dedicated) | ~40 |
| k8s-02 GPU1 | flux-2-schnell + wan-2.2 (async generative) | ~52 |
| k8s-03 GPU0 | qwen3-embedding-8b (vLLM, capped) | ~16–40 |
| k8s-03 GPU1 | **specialty-audio bundle**: whisper · qwen3-asr · kokoro · qwen3-tts · rerank | ~13 |

Everything resident on 6 cards, two cards free for headroom.

### 5. SOTA model refresh

Keep the current catalog (already current as of 2026-06) and add two:

- **Qwen3-ASR-1.7B** (Jan 2026, SOTA open ASR — beats Whisper on
  accuracy/speed/streaming; tiny). Whisper retained for 99-language coverage.
- **Qwen3-TTS** (multilingual, Qwen-stack) to fill the `tts-1-hd` slot;
  Kokoro stays the fast/cheap `tts-1` default.

Deferred (not selected this round): Qwen3.6-35B-A3B LLM swap, Z-Image-Turbo,
LTXVideo.

## Consequences

- **Positive:** all 10 engines fit on 6 cards (today only 3 do); no experimental
  cluster-wide infra; no maintenance window; the chat LLM keeps predictable
  latency; trivially reversible (per-Deployment edits).
- **Negative / cost:** the specialty-audio bundle needs a **combined
  supervisord image** (build effort) before GPU co-location is real; bundled
  engines share a pod lifecycle (restart together); repurposing k8s-02 to a
  `generative` role drops resident chat-LLM capacity from 4 cards to 2 (still
  ~3× a 27B's need).
- **Interim:** until the combined specialty-audio image exists, **Kokoro runs on
  CPU** (82M model — viable, zero GPU contention). This unblocks TTS immediately
  and is swapped to GPU co-location when the image lands.

## Rollout (sequenced, prod changes gated)

1. Land this ADR + the `local-inference-catalog.yaml` policy/model updates (repo).
2. Deploy Kokoro CPU interim → working `tts-1`.
3. Build the combined specialty-audio image (whisper + qwen3-asr + kokoro +
   qwen3-tts + rerank via supervisord); mirror to Harbor.
4. Cut whisper over to the bundle on k8s-03 GPU1; free its dedicated card.
5. Repurpose k8s-02 → `generative`; deploy qwen-image / flux / wan capped.
6. (Later, optional) MPS micro-benchmark → adopt if it wins.
