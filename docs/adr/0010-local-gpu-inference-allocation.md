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

## Activation status (2026-06-09) — BLOCKED on a device-plugin bug

Canary attempted on **k8s-03** (helm upgrade adding mps-r1/r2/r4 configs +
labeling k8s-03 `mps.capable=true`, `device-plugin.config=mps-r4`). Result:

- The **main device plugin applied mps-r4 correctly** — k8s-03 advertised
  `nvidia.com/gpu: 8`, and the MPS daemon (`-ctr`) started with **per-device
  pinned mem limit 24471 MB and active-thread 25%** (so this plugin *does*
  enforce per-slice VRAM — the earlier "soft isolation" worry is moot here).
- **BUT** the `mps-control-daemon`'s **config-manager `-sidecar` crashloops
  deterministically**: it reads `nvidia.com/device-plugin.config` as *empty*,
  falls back to the non-MPS `config`, then panics
  `index out of range [0] with length 0` (cmd/config-manager/main.go:456) because
  that config has no `sharing.mps.resources`. Fresh pod → same panic. The DS
  never reaches Ready (1/2).
- Running workloads (embedding, whisper) were **never disrupted** throughout.
- **Rolled back** (removed both labels) → k8s-03 back to `allocatable=2`,
  mps-control-daemon de-scheduled, fleet healthy. The mps-r* configs remain in
  the configmap (inert without node labels) ready for a retry.

**Fix paths to investigate (do in a window, off-prod first if possible):**
1. Bump `nvidia-device-plugin` past v0.18.2 (the config-manager MPS path has a
   history of bugs across v0.15–v0.18; see upstream issue #1094) and re-canary.
2. Work around the empty-label read: try a config-map key literally named
   `default` that *is* a valid MPS config for mps-capable nodes (so the
   sidecar's empty-label fallback lands on an MPS config, not the non-MPS one) —
   while keeping llm nodes unlabeled/unshared.
3. If neither resolves it, fall back to one-pod (supervisord) co-location for the
   small specialty engines (the pre-MPS plan), which needs no device-plugin MPS.

Until resolved, the fleet stays on the current dedicated-card layout; Kokoro
remains the CPU interim (live, serving tts-1).

## Update (2026-06-09) — time-slicing adopted; Kokoro stays CPU (Blackwell)

1. **Sharing mechanism → time-slicing, not MPS.** Since the MPS control daemon
   crashes on v0.18.2, we use the device-plugin's **time-slicing** — it needs
   **no control daemon**, sidestepping that bug. Added `ts-r2`/`ts-r4` configs.
   Canary on k8s-03 (`device-plugin.config=ts-r4`, no `mps.capable`):
   **allocatable→8, no crashing daemon, embedding/whisper undisturbed, plugin
   2/2.** Time-slicing has no hard VRAM isolation, so co-tenant vLLM engines MUST
   cap `gpu_memory_utilization`; small fixed-footprint engines are safe. This is
   now the working sharing path.

2. **Kokoro GPU image is not Blackwell-compatible.** Onto a slice it scheduled
   fine (time-slicing works) but crashed at CUDA init: `no kernel image is
   available for execution on the device` — `kokoro-fastapi-gpu:v0.3.0` torch has
   no **sm_120 (Blackwell)** kernels. The running engines (vLLM LLM/embedding,
   faster-whisper) *are* Blackwell-OK, so this is image-specific. **Kokoro stays
   CPU** (82M, fine). **Implication:** every *new* GPU engine must be verified
   Blackwell-compatible (cu128+ torch) before taking a slice.

Remaining to fully pack: build Blackwell-compatible images for
qwen3-asr/qwen-image/qwen3-tts/flux/wan, consolidate the LLM to free cards, then
schedule them onto slices with VRAM caps.

## Update (2026-06-11) — understanding + perception tier (close the modality matrix)

Audit vs the platform's own API/Modal capability surface (isa_model `types.py`
ServiceType/TaskType + the Modal `isa_vision_*` services) found the local fleet
had **generation only** — the **understanding side (image/video -> text) and the
enterprise perception layer were Modal-only**, not local. The 4×4 modality
matrix (text/image/video/audio in × out): generation cells covered (T->T LLM,
T->I qwen-image/flux, T->V wan, T->A TTS); the gaps were **I->T and V->T (no
VLM)** plus OCR / detection / segmentation / table extraction.

Added to the catalog (specialty node k8s-03, 24 GB time-slices — all verified to
run on sm_120 **without a hard flash-attn dependency**, the qwen-tts trap):

- **Understanding — VLM**: `Qwen/Qwen3-VL-8B-Instruct-FP8` (Apache-2.0),
  **vLLM-served** (vLLM uses its own attention kernels — no flash-attn wheel
  needed; categorically different from qwen-tts/HF `flash_attention_2`). Image +
  video over OpenAI `/v1/chat/completions`. Localizes the Qwen2.5-VL the platform
  ran on Modal. 48 GB-slice upgrade: `Qwen3-VL-30B-A3B-Instruct-FP8` (MoE).
- **Perception — PaddleOCR-VL 1.5** (Apache-2.0, own slice): OCR + layout +
  tables in one 0.9 B model — retires the Modal OCR service **and** both
  Table-Transformers.
- **Perception bundle** (one 24 GB slice, FastAPI multi-model, ~4-6 GB, all
  SDPA/ONNX): Florence-2 (MIT, grounding/region — 1:1 with the Modal service),
  Grounding-DINO (Apache), SAM 3.1 (segmentation), YOLO26 (detection),
  SigLIP-2 (image embeddings).

**⚠️ License flags for commercial/customer (SN) traffic — clear with legal
before production use:** YOLO26 = **AGPL-3.0** (needs Ultralytics Enterprise
license, or swap to Apache RT-DETR); SAM 3.1 = **gated Meta SAM license**;
Fish-Speech S2-Pro = **non-commercial**. The Apache/MIT picks (Qwen3-VL,
PaddleOCR-VL, Florence-2, Grounding-DINO, SigLIP-2) are commercially clean.

Placement: VLM-8B + PaddleOCR-VL + perception-bundle = 3 new slices on k8s-03
(→ ~7/8 specialty slices used). Implementation order: VLM first (closes the
biggest gap, cleanest vLLM path), then PaddleOCR-VL, then the bundle.

**As-built note (perception bundle):** the bundle shipped as **Florence-2-large
(MIT) + SAM (`facebook/sam-vit-base`, Apache, ungated) + SigLIP-2→SigLIP-1
fallback (Apache)** — the license-clean, ungated subset. AGPL YOLO26 and
Meta-gated SAM 3.1 were deliberately dropped (see license flags above); Florence-2
covers detection/grounding and SAM covers promptable segmentation. SigLIP-2 has a
processor bug in transformers 4.49.0, so the loader falls back to SigLIP-1; the
loader marks the bundle ready on Florence-2+SAM alone and treats SigLIP as
best-effort.

## Update (2026-06-11b) — VRAM memory-budget policy (per-pod caps, enforceable)

A fish-speech **CUDA OOM** ("card has 7.62 MiB free") exposed the gap between the
*intent* above ("cap `gpu_memory_utilization`") and an *enforceable rule*. Root
cause: `vllm-qwen3-embedding-8b` ran at `gpu_memory_utilization=0.50` → it
reserved **~48 GB** (16 GB weights + **31.63 GiB KV cache**, 230 320 tokens) on a
k8s-03 card whose **time-slice budget is 24 GB**. An **embedding model is a
pooling runner** — one forward pass, *no* autoregressive KV growth — so that
31.63 GiB of KV cache is pure waste. It occupied one *scheduler slice* while
eating *two slices' worth of memory*, starving co-tenants.

### The invariant (why this happens)

Time-slicing has **no memory isolation** and the scheduler counts **slices, not
bytes**. `nvidia.com/gpu: 1` reserves a *time slot*, not VRAM. So nothing stops
the sum of co-tenant reservations on one physical card from exceeding 96 GB — and
when it does, whichever pod loads last OOMs. The only defense is to **bound each
pod's VRAM to the slice granularity** so that a full card (all slices occupied)
still fits:

> **Per-pod VRAM cap = (card VRAM ÷ slices-per-card) × ~0.95 headroom.**
> For vLLM this is exactly `gpu_memory_utilization` (a fraction of the *whole*
> card), so on a node with N slices/card the cap is **≤ 1/N**.

| Node | Role | Slices/card | Slice budget | **Per-pod cap** |
|------|------|------------|-------------|-----------------|
| k8s-01 | llm (dedicated, no TS) | 1 | 96 GB | `gpu_mem_util ≤ 0.85` |
| k8s-02 | generative (ts-r2) | 2 | 48 GB | `≤ 0.50` |
| k8s-03 | specialty (ts-r4) | 4 | 24 GB | **`≤ 0.25`** |

### Per-model-type sizing rules (size to *need*, not to the cap)

The cap is a **ceiling**; size each engine to its actual footprint:

- **Generative (LLM, VLM)** — weights + KV cache; KV fills the remaining budget →
  more concurrency/context. *Use the slice cap.* qwen3-vl-8B-FP8 = 0.25 (10 GB
  weights + ~14 GB KV → 2.4× concurrency @ 32k); qwen36-27B = 0.85 on its
  dedicated card.
- **Pooling (embedding, rerank)** — weights + small activation, **no KV cache**.
  *Size to weights + ~30 %, well under the cap.* 8B embedder ≈ 16 GB weights →
  **0.22 (~21 GB)**, never 0.50.
- **ASR/STT** — weights + audio activation; modest. qwen3-asr 0.25; faster-whisper
  ~3 GB (fixed, non-vLLM).
- **Diffusion (Triton/diffusers)** — weights + latent/VAE buffers, can spike
  during denoising; not `gpu_mem_util`-governed, so verify peak ≤ slice budget.
- **Fixed-footprint (FastAPI/transformers: perception, fish)** — load what they
  need (~6 GB, ~16 GB); count them against the card budget like any co-tenant.

### k8s-03 allocation — current vs corrected

| Pod | Type | was | **now** | VRAM | within 24 GB slice? |
|-----|------|-----|---------|------|---------------------|
| vllm-qwen3-embedding-8b | pooling | 0.50 | **0.22** | ~21 GB | ✓ (was ✗ @ 48 GB) |
| qwen3-vl-8b | generative | 0.25 | 0.25 | ~24 GB | ✓ |
| qwen3-asr | asr | 0.25 | 0.25 | ~24 GB | ✓ |
| paddleocr-vl | generative (0.9B) | 0.10 | 0.10 | ~10 GB | ✓ |
| faster-whisper-v3-turbo | asr (fixed) | — | — | ~3 GB | ✓ |
| perception-bundle | fixed | — | — | ~6 GB | ✓ |
| fish-speech-tts | fixed | — | — | ~16 GB | ✓ |

**Worst-case placement check** (the 4 heaviest pods on one physical card, since
ts-r4 = 4 slices/card): qwen3-vl 24 + embedding 21 + qwen3-asr 24 + fish 16 =
**85 GB < 96 GB ✓**. Total node demand ~104 GB across 192 GB (2 cards) = 54 %
util — comfortable, with fish now fitting.

### Dynamic allocation — why static caps (for now)

True *dynamic* per-process memory limits need either **MPS**
(`CUDA_MPS_PINNED_DEVICE_MEM_LIMIT` per client) — **blocked**, the MPS control
daemon crashloops on device-plugin v0.18.2 (see 2026-06-09 update) — or **MIG**,
which gives *hardware* memory isolation but only in fixed profiles (e.g. 1g/2g/4g)
and reduces packing flexibility. Until MPS is fixed or MIG profiles are planned,
**static per-pod caps at slice granularity** are the correct, predictable policy.
Revisit MIG if hard isolation becomes a multi-tenant requirement.

### Checklist when adding a model to a time-sliced node

1. Classify it (generative / pooling / asr / diffusion / fixed).
2. Set `gpu_memory_utilization` ≤ the node's per-pod cap (1/slices-per-card),
   and **lower** for pooling/small models.
3. Re-run the worst-case check: sum the *N* heaviest pods (N = slices/card) ≤
   ~0.95 × card VRAM.
4. Pooling/embedding/rerank models **never** get a generative-sized budget.
