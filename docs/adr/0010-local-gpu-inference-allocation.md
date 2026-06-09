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

### 2. Share cards by VRAM via MPS; the LLM does not span cards

- The **chat LLM runs on a single card** — **no cross-card tensor parallel**
  (no NVLink → TP all-reduce would crawl over PCIe Gen5). A 27B (~30 GB) fits one
  96 GB card with ample KV headroom; extra cards are a *throughput* choice, not a
  VRAM need.
- **Every other engine shares a card via MPS slices.** A 16 GB embedding or a
  0.5 GB TTS must never own a 96 GB card. MPS partitions a card into equal
  slices (`replicas` per card → memory = 96 GB ÷ replicas, with per-client mem +
  compute caps), and pods keep requesting `nvidia.com/gpu: 1` — each gets one
  slice (`renameByDefault: false`), so engine manifests need no resource-shape
  change.

### 3. Activate the pre-staged MPS (cluster's intended path)

MPS is **already installed on this cluster, dormant**: the NVIDIA device-plugin
ships a `nvidia-device-plugin-mps-control-daemon` DaemonSet gated on the node
label `nvidia.com/mps.capable=true` (currently 0 nodes). The operators staged
MPS as the intended sharing mechanism — activating it is **labeling nodes +
adding per-node MPS configs + flipping `sharing-strategy=mps`**, not introducing
new infra. (MIG is unavailable on workstation cards; HAMi is not installed —
Volcano is present only as a scheduler.)

Residual caveats (managed, not blocking): MPS slices are **equal-size** so
`replicas` is **uniform per node** → group similar-VRAM engines per node;
isolation on workstation cards is **soft**. Rolling the device-plugin config
re-registers GPUs, so do it in a brief window.

> A vendor test deploying a 120B model does **not** validate MPS — that exercises
> single large-process serving (and, if TP, PCIe), not concurrent multi-process
> GPU sharing. A single-card micro-benchmark (kokoro + whisper concurrent) is
> still worth running post-activation to tune `replicas` and confirm interference
> is acceptable.

### 4. Placement (6 × 96 GB, MPS by node)

| Node | MPS replicas/card | Slice | Tenants |
|------|-------------------|-------|---------|
| k8s-01 | 1 (dedicated) — 2 only if chat throughput needs it | 96 / 48 GB | qwen3.6-27b (capped util, no TP) |
| k8s-02 | 2 | 48 GB | qwen-image-2.0 (40) · flux-2-schnell (24) · wan-2.2 (28) |
| k8s-03 | 4 | 24 GB | qwen3-embedding-8b (16) · whisper (3) · qwen3-asr (2) · kokoro (0.5) · qwen3-tts (5) · bge-reranker (2) |

8 slices on k8s-03 hold all six small engines with spares; the LLM frees 1–3
cards vs today's 4. Per-node config is selected by node label
(`nvidia.com/device-plugin.config`).

### 5. SOTA model refresh

Keep the current catalog (already current as of 2026-06) and add two:

- **Qwen3-ASR-1.7B** (Jan 2026, SOTA open ASR — beats Whisper on
  accuracy/speed/streaming; tiny). Whisper retained for 99-language coverage.
- **Qwen3-TTS** (multilingual, Qwen-stack) to fill the `tts-1-hd` slot;
  Kokoro stays the fast/cheap `tts-1` default.

Deferred (not selected this round): Qwen3.6-35B-A3B LLM swap, Z-Image-Turbo,
LTXVideo.

## Consequences

- **Positive:** all engines fit on 6 cards (today only 3 do) with cards to
  spare; small engines stop wasting 96 GB cards; uses the cluster's pre-staged
  MPS rather than new infra or a supervisord-image hack; engine manifests keep
  `nvidia.com/gpu: 1` (no resource-shape churn); the chat LLM frees 1–3 cards.
- **Negative / cost:** MPS slices are equal-size (group by VRAM per node);
  isolation is soft on workstation cards; activating MPS re-registers GPUs
  cluster-wide (brief window); the LLM consolidation reschedules its pods
  (mitigated by scaling the pool down by replica, keeping it serving).
- **Superseded interim:** Kokoro's CPU interim (already deployed) is replaced by
  a GPU MPS slice on k8s-03 once MPS is active.

## Rollout (sequenced; MPS activation is the gate)

1. Land this ADR + `local-inference-catalog.yaml` updates (repo). ✅
2. Author MPS device-plugin per-node configs (r1/r2/r4) + node labels (repo).
3. **Activate MPS** (brief window): label nodes `nvidia.com/mps.capable=true` +
   `nvidia.com/device-plugin.config=<mps-rN>`, apply the MPS configmap, roll the
   device plugin; verify `nvidia.com/gpu` allocatable rises per node.
4. Consolidate the chat LLM to k8s-01 (scale the pool down by replica — stays
   serving); free k8s-02's cards.
5. Repack: Kokoro CPU→GPU slice; co-tenant whisper/embedding/asr/tts/rerank on
   k8s-03; deploy qwen-image / flux / wan on k8s-02 (48 GB slices).
6. Build/mirror runtime images that don't exist yet (qwen3-asr, qwen3-tts, and
   any triton model repos) as their deploys come up.
7. Run the single-card MPS micro-benchmark; tune `replicas` if needed.
