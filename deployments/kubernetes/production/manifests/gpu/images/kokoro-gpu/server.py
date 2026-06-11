import io, os, threading, time, traceback
import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import uvicorn

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
LANG = os.getenv("KOKORO_LANG", "a")
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "af_nicole")
SR = 24000
STATE = {"ready": False, "error": None}
P = {}

def _load():
    # Retry across the flaky SN->HF link: a transient DNS/connection error
    # during the Kokoro-82M download must NOT permanently fail the engine
    # (the download resumes from the PVC HF cache on each attempt).
    from kokoro import KPipeline
    for attempt in range(1, 13):
        try:
            t0 = time.time()
            print(f"[load] attempt {attempt}: KPipeline lang={LANG} device={DEVICE} ...", flush=True)
            P["pipe"] = KPipeline(lang_code=LANG, device=DEVICE)
            for _g, _p, _a in P["pipe"]("warm up.", voice=DEFAULT_VOICE):
                break
            STATE["ready"] = True
            STATE["error"] = None
            print(f"[load] kokoro ready on {DEVICE} in {time.time()-t0:.0f}s", flush=True)
            return
        except Exception as e:
            # keep /health at 503 (loading) during retries, not 500
            print(f"[load] attempt {attempt} failed ({e}); retry in 20s", flush=True)
            time.sleep(20)
    STATE["error"] = "kokoro load failed after retries (see logs)"
    print(f"[load] giving up: {STATE['error']}", flush=True)

app = FastAPI(title="kokoro-gpu")

@app.get("/health")
def health():
    if STATE["error"]: raise HTTPException(500, STATE["error"][:400])
    if not STATE["ready"]: raise HTTPException(503, "loading")
    return {"status": "ok", "device": DEVICE}

class SpeechReq(BaseModel):
    model: str = "kokoro"
    input: str
    voice: str = DEFAULT_VOICE
    response_format: str = "wav"
    speed: float = 1.0

def _synth(text, voice, speed):
    chunks = []
    for _gs, _ps, audio in P["pipe"](text, voice=voice or DEFAULT_VOICE, speed=speed):
        a = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
        chunks.append(a.astype("float32"))
    return np.concatenate(chunks) if chunks else np.zeros(1, dtype="float32")

@app.post("/v1/audio/speech")
def speech(r: SpeechReq):
    if not STATE["ready"]: raise HTTPException(503, "not ready")
    try:
        audio = _synth(r.input, r.voice, r.speed)
    except Exception as e:
        raise HTTPException(500, f"synthesis failed: {e}")
    fmt = (r.response_format or "wav").lower()
    buf = io.BytesIO()
    if fmt in ("wav", "pcm"):
        sf.write(buf, audio, SR, format="WAV"); mt = "audio/wav"
    elif fmt == "flac":
        sf.write(buf, audio, SR, format="FLAC"); mt = "audio/flac"
    else:
        sf.write(buf, audio, SR, format="WAV"); mt = "audio/wav"
    return Response(content=buf.getvalue(), media_type=mt)

@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "kokoro", "object": "model", "owned_by": "isa"}]}

if __name__ == "__main__":
    threading.Thread(target=_load, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8880, log_level="info")
