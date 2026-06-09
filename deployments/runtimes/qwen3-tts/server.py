"""
Minimal OpenAI-compatible TTS server for Qwen3-TTS (Qwen/Qwen3-TTS).

Exposes:
  POST /v1/audio/speech   - OpenAI Audio Speech contract (model, input, voice,
                            response_format, speed). Returns raw audio bytes.
  GET  /health            - liveness/readiness; reports model-loaded + device.
  GET  /v1/voices         - convenience list of mapped + native voices.

Why this exists: as of mid-2026 there is no first-party Qwen3-TTS image that
speaks the OpenAI /v1/audio/speech contract. vLLM-Omni added Qwen3-TTS day-0 but
is still OFFLINE-INFERENCE-ONLY ("online serving will be supported later"), so it
cannot back an HTTP endpoint. This is a thin FastAPI shim over the `qwen-tts`
package's `Qwen3TTSModel`, mirroring the kokoro-fastapi surface so the isA_Model
model-service `tts-1-hd` route is drop-in.

Audio is synthesized as a float32/int16 waveform by qwen-tts, then encoded to the
requested container (wav/mp3/opus/flac/aac/pcm) with soundfile (+ ffmpeg for the
lossy formats). Streaming is NOT implemented here (see README risks): the OpenAI
client treats the body as a complete file, and qwen-tts chunked-HTTP behaviour is
unproven — we return the full buffer.
"""

from __future__ import annotations

import io
import logging
import os
import subprocess
import time
from typing import Literal, Optional

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("qwen3-tts")

# --- Configuration (all overridable via env / ConfigMap) --------------------
# Pick a concrete repo: `Qwen/Qwen3-TTS` is a family alias, not a loadable repo.
# 1.7B-CustomVoice is the multi-voice HD default for the tts-1-hd tier.
MODEL_ID = os.getenv("TTS_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
DEVICE = os.getenv("DEVICE", "cuda:0")
DTYPE = os.getenv("TTS_DTYPE", "bfloat16")  # bfloat16 is safe on Blackwell
# qwen-tts returns (wavs, sr); we trust the returned sr but allow an override
# if a model variant reports an unexpected rate.
SAMPLE_RATE_OVERRIDE = os.getenv("TTS_SAMPLE_RATE")  # e.g. "24000"; empty = use model sr
DEFAULT_LANGUAGE = os.getenv("TTS_DEFAULT_LANGUAGE", "Auto")
DEFAULT_SPEAKER = os.getenv("TTS_DEFAULT_SPEAKER", "Ryan")
# flash_attention_2 needs a built flash-attn wheel; default to PyTorch SDPA which
# is always present on the cu128 base. Set to "flash_attention_2" if baked in.
ATTN_IMPL = os.getenv("TTS_ATTN_IMPL", "sdpa")

# Map OpenAI's fixed voice vocabulary onto Qwen3-TTS preset speakers so existing
# OpenAI clients (which send alloy/echo/...) keep working. Unknown voices are
# passed through verbatim so callers can request native speakers directly.
OPENAI_VOICE_MAP = {
    "alloy": "Ryan",
    "echo": "Eric",
    "fable": "Dylan",
    "onyx": "Uncle_Fu",
    "nova": "Serena",
    "shimmer": "Vivian",
    "ash": "Aiden",
    "ballad": "Sohee",
    "coral": "Ono_Anna",
    "sage": "Vivian",
    "verse": "Ryan",
}

# response_format -> (soundfile subtype/format) or ffmpeg target.
# soundfile handles wav/flac/pcm natively; mp3/opus/aac go through ffmpeg.
SF_FORMATS = {
    "wav": ("WAV", "PCM_16"),
    "flac": ("FLAC", None),
    "pcm": ("RAW", "PCM_16"),
}
FFMPEG_FORMATS = {
    "mp3": ("mp3", "audio/mpeg"),
    "opus": ("opus", "audio/ogg"),
    "aac": ("adts", "audio/aac"),
}
CONTENT_TYPES = {
    "wav": "audio/wav",
    "flac": "audio/flac",
    "pcm": "audio/pcm",
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
}

app = FastAPI(title="qwen3-tts", version="0.1.0")

# Loaded once at startup; kept resident for the pod lifetime.
_model = None
_model_loaded = False


class SpeechRequest(BaseModel):
    """OpenAI POST /v1/audio/speech body. `model` is accepted for contract
    compatibility (we always serve the loaded MODEL_ID)."""

    model: str = Field(default="tts-1-hd")
    input: str = Field(..., description="Text to synthesize")
    voice: str = Field(default="alloy")
    response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "mp3"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    # Non-OpenAI extras (optional): let advanced callers steer Qwen3-TTS directly.
    language: Optional[str] = None
    instruct: Optional[str] = None


@app.on_event("startup")
def _load_model() -> None:
    global _model, _model_loaded
    dtype = getattr(torch, DTYPE)
    log.info("Loading %s on %s (dtype=%s, attn=%s)", MODEL_ID, DEVICE, DTYPE, ATTN_IMPL)
    from qwen_tts import Qwen3TTSModel  # imported here so /health can answer pre-load

    _model = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        device_map=DEVICE,
        dtype=dtype,
        attn_implementation=ATTN_IMPL,
    )
    _model_loaded = True
    log.info("Model loaded.")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if _model_loaded else "loading",
        "model": MODEL_ID,
        "device": DEVICE,
        "cuda_available": torch.cuda.is_available(),
        "model_loaded": _model_loaded,
    }


@app.get("/v1/voices")
def voices() -> dict:
    native = ["Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric",
              "Ryan", "Aiden", "Ono_Anna", "Sohee"]
    return {"openai_aliases": sorted(OPENAI_VOICE_MAP), "native_speakers": native}


def _encode(wav: np.ndarray, sr: int, fmt: str) -> tuple[bytes, str]:
    """Encode a float waveform into the requested container, returning
    (bytes, content_type)."""
    # qwen-tts may hand back float32 in [-1, 1]; soundfile needs that for PCM_16.
    wav = np.asarray(wav, dtype=np.float32).squeeze()

    if fmt in SF_FORMATS:
        sf_format, subtype = SF_FORMATS[fmt]
        buf = io.BytesIO()
        if fmt == "pcm":
            # Raw headerless little-endian 16-bit PCM (OpenAI's "pcm").
            pcm16 = np.clip(wav, -1.0, 1.0)
            pcm16 = (pcm16 * 32767.0).astype("<i2")
            return pcm16.tobytes(), CONTENT_TYPES[fmt]
        sf.write(buf, wav, sr, format=sf_format, subtype=subtype)
        return buf.getvalue(), CONTENT_TYPES[fmt]

    if fmt in FFMPEG_FORMATS:
        # Pipe WAV into ffmpeg and read the lossy container back from stdout.
        wav_buf = io.BytesIO()
        sf.write(wav_buf, wav, sr, format="WAV", subtype="PCM_16")
        ffmpeg_fmt, ctype = FFMPEG_FORMATS[fmt]
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-f", ffmpeg_fmt, "pipe:1"],
            input=wav_buf.getvalue(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            raise HTTPException(500, f"ffmpeg {fmt} encode failed: "
                                     f"{proc.stderr.decode(errors='ignore')[:500]}")
        return proc.stdout, ctype

    raise HTTPException(400, f"unsupported response_format: {fmt}")


@app.post("/v1/audio/speech")
def speech(req: SpeechRequest) -> Response:
    if not _model_loaded:
        raise HTTPException(503, "model still loading")
    if not req.input.strip():
        raise HTTPException(400, "input is empty")

    speaker = OPENAI_VOICE_MAP.get(req.voice.lower(), req.voice)
    language = req.language or DEFAULT_LANGUAGE
    t0 = time.time()

    try:
        # generate_custom_voice returns (wavs, sr); wavs is a list of np arrays.
        wavs, sr = _model.generate_custom_voice(
            text=req.input,
            language=language,
            speaker=speaker,
            instruct=req.instruct,
        )
    except Exception as exc:  # surface model errors as 500 with context
        log.exception("synthesis failed")
        raise HTTPException(500, f"synthesis failed: {exc}") from exc

    wav = wavs[0] if isinstance(wavs, (list, tuple)) else wavs
    if SAMPLE_RATE_OVERRIDE:
        sr = int(SAMPLE_RATE_OVERRIDE)

    # NOTE: OpenAI `speed` is not natively honored by generate_custom_voice. We
    # apply it as a cheap sample-rate resample-by-playback-rate only if != 1.0,
    # which changes pitch slightly; for true time-stretch swap in an SoX/rubberband
    # filter via ffmpeg. Kept simple here per the "minimal" brief.
    if abs(req.speed - 1.0) > 1e-3:
        sr = int(sr * req.speed)

    audio_bytes, content_type = _encode(wav, sr, req.response_format)
    log.info("synth voice=%s lang=%s chars=%d -> %s %dB in %.2fs",
             speaker, language, len(req.input), req.response_format,
             len(audio_bytes), time.time() - t0)
    return Response(content=audio_bytes, media_type=content_type)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"),
                port=int(os.getenv("PORT", "8000")))
