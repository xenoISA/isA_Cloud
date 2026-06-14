# SN GPU Inference Fleet — Capability Surface

> Product view of the on-prem local inference fleet for the SN edition.
> Operations & deploy order: [`../runbooks/sn-gpu-inference-fleet.md`](../runbooks/sn-gpu-inference-fleet.md).
> Allocation policy: [`../adr/0010-local-gpu-inference-allocation.md`](../adr/0010-local-gpu-inference-allocation.md).
> Model-side API: isA_Model `docs/overview/local-gpu-inference.md`.

## Why it exists

SN is an **on-prem-full** edition: the customer's data must not leave their IDC.
The GPU inference fleet provides the **same modality surface as the external AI
APIs** (chat, vision, OCR, perception, speech, embeddings, image, video) running
entirely on SN's own GPUs. Applications call isa-model with `provider=isa` and
get cloud-equivalent results without egress. The external providers remain wired
as an optional fallback / quality baseline (see "External provider fallback").

## The hardware

3 nodes × 2 GPUs = **6 × NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation
Edition** (sm_120), ~96 GB VRAM each, ~576 GB total. No MIG, no NVLink (PCIe
Gen5 only). GPUs are grouped by Kubernetes node label into three roles:

| Role | Nodes | Serves |
|------|-------|--------|
| **llm** (always-on) | k8s-01, k8s-02 | primary text/chat inference |
| **specialty** (staged/elastic) | k8s-03 | embedding, rerank, STT, TTS, OCR, vision, image |
| **elastic** (preemptible) | k8s-03 | batch, training, video, overflow |

## Capability tiers

| Capability | Model (image/runtime) | License | Replaces |
|------------|-----------------------|---------|----------|
| Chat / reasoning | `qwen3.6-27b` FP8 (vLLM) | Apache-2.0 | GPT-4o-mini / Claude chat |
| Vision / VQA | Qwen3-VL-8B-Instruct-FP8 (vLLM) | Apache-2.0 | GPT-4o vision |
| Document OCR | PaddleOCR-VL (vLLM) | Apache-2.0 | cloud OCR / doc AI |
| Detection / caption / grounding | Florence-2-large | MIT | enterprise CV |
| Segmentation | SAM (`sam-vit-base`) | Apache-2.0 | segmentation APIs |
| Zero-shot classify | SigLIP-2 → SigLIP-1 fallback | Apache-2.0 | classification APIs |
| Speech-to-text | Qwen3-ASR / faster-whisper-large-v3-turbo | Apache/MIT | Whisper API |
| Text-to-speech | Kokoro-82M on GPU (`kokoro-gpu`, ~12× realtime) | Apache-2.0 | TTS APIs |
| Embeddings | `qwen3-embedding-8b` (vLLM pooling) | Apache-2.0 | text-embedding-3 |
| Rerank | `bge-reranker-v2-m3` | Apache-2.0 | Cohere rerank |
| Image generation | `qwen-image-2.0`, `flux-2-schnell` (Triton) | — | DALL·E / Flux |
| Video | `wan-2.2` (Triton, elastic) | — | — |

All models are **permissively licensed** for commercial on-prem use (a key
reason fish-speech and other non-commercial options were rejected — see
ADR-0010 and the runbook).

The detection/segmentation/classification trio ship as one **perception bundle**
service (FastAPI) so the specialty node hosts CV with a single endpoint.

## Capacity rationale (the "why it fits")

The full catalog of weights sums to **~145 GB** — about 1.5 cards — yet the
bootstrap "1 model = 1 card" rule demanded 8 cards for 6. Cards *looked* full
only because vLLM reserves ~90 % VRAM for KV cache by default. The fleet instead
**budgets by actual VRAM** and caps `gpu_memory_utilization` per engine; pooling
models (embedding/rerank) carry **no KV cache** and are sized to weights only
(embedding dropped from a 48 GB reservation to ~0.22 utilization). This is what
lets the whole menu fit on 6 cards. Full policy: ADR-0010.

## Quality parity (verified 2026-06-11, real data)

| Test | Local | Cloud baseline | Result |
|------|-------|----------------|--------|
| Reasoning (bat & ball) | `qwen3.6-27b` → $0.05 | `gpt-4o-mini` → 0.05 | match |
| Vision (ground-truth image) | `qwen3-vl` reads text + shapes | `gpt-4o-mini` same | match |
| OCR / STT / embeddings | verbatim / clean separation | — | pass |

## External provider fallback

External LLM keys (openai, anthropic, cerebras, openrouter) are seeded in Vault
and synced to isa-model, so a request can target a cloud provider for burst
capacity or comparison. This is **off the data-residency path** — only use it
when local cannot serve the request. Wiring: runbook §"External providers".

## See also

- Operations runbook: [`../runbooks/sn-gpu-inference-fleet.md`](../runbooks/sn-gpu-inference-fleet.md)
- Allocation ADR: [`../adr/0010-local-gpu-inference-allocation.md`](../adr/0010-local-gpu-inference-allocation.md)
- External providers runbook: [`../runbooks/sn-external-llm-providers.md`](../runbooks/sn-external-llm-providers.md)
- Deployment status: [`./SN-DEPLOYMENT-STATUS.md`](./SN-DEPLOYMENT-STATUS.md)
