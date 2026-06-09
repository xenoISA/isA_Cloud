# New Model Runtimes — Serving Research (June 2026)

> Research scratchpad for four GPU models proposed for the SN production
> cluster (ADR 0010). AUTHORING + WEB RESEARCH ONLY — nothing here has been
> applied to a cluster, and the runtime claims below are from web sources as of
> June 2026, not from a live smoke test. Verify before relying on any of it.

Cards are NVIDIA RTX PRO 6000 Blackwell 96 GB, shared via MPS slices. Pods
request `nvidia.com/gpu: 1` (renameByDefault=false -> one slice).

Summary of where each model landed:

| Model | Turnkey serving image? | Outcome |
|-------|------------------------|---------|
| qwen3-asr-1.7b | YES — official vLLM (`vllm serve`), OpenAI `/v1/audio/transcriptions` | manifest drafted: `gpu/qwen3-asr-deployment.yaml` |
| qwen3-tts | NO — no OpenAI `/v1/audio/speech` server exists | research note below (no manifest) |
| flux-2-schnell | NO turnkey image; diffusers `Flux2Pipeline` path; **no "schnell" repo exists** | manifest drafted (Triton+diffusers): `gpu/triton-flux-2-schnell.yaml` |
| wan-2.2 | NO turnkey image; diffusers `WanPipeline` path | manifest drafted (Triton+diffusers): `gpu/triton-wan-2-2.yaml` |

---

## qwen3-tts — NO turnkey OpenAI-compatible server (build required)

**Decision: no manifest drafted.** As of June 2026 there is no off-the-shelf
container that exposes Qwen3-TTS over an OpenAI `/v1/audio/speech` endpoint, so
fabricating one would be guessing. Kokoro remains the `tts-1` default and
Qwen3-TTS is only needed for the multilingual HD `tts-1-hd` tier — there is no
urgency to ship an unverified runtime.

### What exists today

- **Open weights**, released 2026-01-22 (Qwen Collection, 0.6B + 1.7B):
  `Qwen/Qwen3-TTS-12Hz-1.7B-Base`, `...-1.7B-CustomVoice`,
  `...-1.7B-VoiceDesign`, `Qwen/Qwen3-TTS-12Hz-0.6B-Base`,
  `...-0.6B-CustomVoice`. (The catalog's `huggingface_id: Qwen/Qwen3-TTS` is a
  family alias — pick a concrete repo above; `1.7B-CustomVoice` is the likely
  default for HD multi-voice.)
- **Python package** `qwen-tts` (`pip install -U qwen-tts`) — load
  `Qwen3TTSModel` for custom-voice TTS, voice design, and voice cloning.
- **Local web UI demo only**:
  `qwen-tts-demo Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --ip 0.0.0.0 --port 8000`.
  This is a Gradio-style demo, NOT an OpenAI-shaped API.
- **vLLM-Omni**: day-0 support but **offline inference only** — "online serving
  will be supported later." So vLLM cannot serve a streaming HTTP TTS endpoint
  yet, unlike Qwen3-ASR.
- **DashScope** offers a hosted real-time API, but that is Alibaba's proprietary
  cloud service, not a self-hostable image.

### What it would take to build a server

1. **Base image**: `nvidia/cuda:12.x-cudnn-runtime` (or reuse the kokoro-fastapi
   build pattern). 1.7B at fp16 is ~4 GB VRAM — comfortably fits a 24 GB
   specialty MPS slice on k8s-03 alongside the rest of the audio pack.
2. **Deps**: `qwen-tts`, `torch`, `transformers`, plus an audio encode step
   (`soundfile`/`ffmpeg`) to emit mp3/opus/wav for the OpenAI response.
3. **Server framework**: a thin FastAPI wrapper exposing
   `POST /v1/audio/speech` (mirror kokoro-fastapi's surface so the model-service
   route is drop-in). Map the OpenAI body — `model`, `input`, `voice`,
   `response_format`, `speed` — onto `Qwen3TTSModel` synthesis; load the model
   once at startup; stream chunks if the package supports it (it advertises
   streaming generation).
4. **Model download**: lazy from HF into the `/root/.cache/huggingface` PVC
   (`HF_TOKEN` optional unless the repo is gated), exactly like kokoro-tts.
5. **Image hygiene**: bake a versioned image (e.g.
   `core.harbor.domain/isa/qwen3-tts-fastapi:<ver>`) and push to Harbor, same as
   the kokoro-fastapi-cpu image — do NOT pip-install at pod startup for a prod
   audio engine.

### Risks / unknowns

- No reference OpenAI adapter exists — the FastAPI shim is net-new code we own
  and must test against the model-service's `tts-1-hd` route.
- Streaming over HTTP from `qwen-tts` is advertised at the library level but the
  chunked-transfer behaviour for `/v1/audio/speech` is unproven.
- Voice naming: OpenAI `voice` values (alloy, etc.) must be mapped to Qwen3-TTS
  custom/design voices.

### Sources

- https://github.com/QwenLM/Qwen3-TTS
- https://huggingface.co/collections/Qwen/qwen3-tts
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base

---

## qwen3-asr-1.7b — turnkey via official vLLM (manifest drafted)

Recorded here for completeness; the manifest is
`gpu/qwen3-asr-deployment.yaml`.

- vLLM ships first-party Qwen3-ASR support: `vllm serve Qwen/Qwen3-ASR-1.7B`
  exposes the OpenAI Audio Transcriptions API at `/v1/audio/transcriptions` on
  `:8000` — same `vllm/vllm-openai` image + contract the chat LLM already uses.
- Requires the `vllm[audio]` decode extra (baked into the vllm-openai image on
  the cu130 line).
- A community wrapper image also exists if a thinner runtime is wanted:
  `ghcr.io/malaiwah/qwen3-asr-server:latest` (port 8000, `/v1/audio/transcriptions`,
  ~6 GB VRAM min, `QWEN3_ASR_MODEL_ID`/`HF_TOKEN`/`QWEN_API_KEY` env). We chose
  the official vLLM image instead for supply-chain hygiene.
- Risk: vLLM's transcription endpoint maturity for Qwen3-ASR (streaming + the
  OpenAI `verbose_json` word/segment timestamp fields) should be smoke-tested
  before routing traffic off faster-whisper.

### Sources

- https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-ASR.html
- https://docs.vllm.ai/en/latest/contributing/model/transcription/
- https://huggingface.co/Qwen/Qwen3-ASR-1.7B
- https://github.com/QwenLM/Qwen3-ASR
- https://github.com/malaiwah/qwen3-asr-server

---

## flux-2-schnell — no turnkey image; diffusers path (manifest drafted, naming caveat)

Manifest is `gpu/triton-flux-2-schnell.yaml` (Triton Python backend +
`diffusers.Flux2Pipeline`, same pattern as triton-qwen-image-2-0).

**Important naming correction:** there is **no `FLUX.2-schnell` repo** as of
June 2026. The FLUX.2 line is `FLUX.2-dev` (32B), and the fast/distilled family
is **`FLUX.2-klein`** — `FLUX.2-klein-9B` (~29 GB VRAM) and `FLUX.2-klein-4B`
(~13 GB VRAM), released 2026-01-15 as "the fastest models yet." The manifest
serves `black-forest-labs/FLUX.2-klein-9B` while keeping the
`triton-flux-2-schnell` service name to honour the existing catalog/route
contract. Confirm the intended variant (klein-9B vs klein-4B) with the ADR
owner.

### Build / verification notes

- Base + strategy reused from Qwen-Image: `nvcr.io/nvidia/tritonserver:24.01-py3`
  + startup pip install (`diffusers`, `transformers`, `accelerate`, `Pillow`,
  `sentencepiece`). Production should bake a versioned image.
- FLUX.2 needs a diffusers release that ships `Flux2Pipeline` (>= the FLUX.2
  line; the `>=0.36` pin in the manifest is a guess — verify).
- FLUX.2-klein is **gated** on HF — `HF_TOKEN` is effectively required.
- klein is distilled for few-step generation (defaults: ~4 steps, guidance 0).
- VRAM on a 48 GB slice for klein-9B + the (large) text encoder at bf16 is
  tight; fp8 or group offloading may be needed.

### Sources

- https://huggingface.co/blog/flux-2
- https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
- https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
- https://github.com/black-forest-labs/flux2

---

## wan-2.2 — no turnkey image; diffusers path (manifest drafted)

Manifest is `gpu/triton-wan-2-2.yaml` (Triton Python backend +
`diffusers.WanPipeline`, MP4 returned base64). No OpenAI/Triton off-the-shelf
image exists, but Wan2.2 has an officially-supported diffusers integration
(landed 2025-07-28).

### Build / verification notes

- Defaults to `Wan-AI/Wan2.2-TI2V-5B-Diffusers` (~24 GB VRAM, 720p, does T2V +
  I2V). The A14B MoE (`Wan2.2-T2V-A14B-Diffusers` / `Wan2.2-I2V-A14B-Diffusers`)
  is higher quality but needs 40-80 GB depending on resolution/precision and
  will not fit a 24 GB slice.
- Placed in the **elastic** group (preemptible) — video is batch/overflow, must
  not keep a specialty card resident.
- Video gen is slow (~4 min per 5s 480p clip on H100). Synchronous Triton
  `infer` is a poor fit; prefer an async job/queue in front. The drafted
  wrapper is synchronous and will need long client/server timeouts.
- `export_to_video` needs ffmpeg — the manifest adds `imageio-ffmpeg` to the
  startup pip install; verify it resolves a working binary in the Triton image.
- Pin the diffusers Wan pipeline signature (`num_frames`, `fps`, guidance)
  against the diffusers release in use before baking an image.

### Sources

- https://github.com/Wan-Video/Wan2.2
- https://huggingface.co/docs/diffusers/api/pipelines/wan
- https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B-Diffusers
- https://huggingface.co/Wan-AI/Wan2.2-T2V-A14B-Diffusers
