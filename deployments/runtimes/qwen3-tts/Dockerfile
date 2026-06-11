# Qwen3-TTS OpenAI-compatible TTS server.
#
# HARD CONSTRAINT: target GPUs are RTX PRO 6000 Blackwell (compute capability
# sm_120). PyTorch MUST be a CUDA 12.8+ / sm_120 build or every CUDA kernel
# launch fails with "no kernel image is available for execution on the device".
# We therefore install torch from the cu128 wheel index. The base image only
# needs to provide a recent CUDA *runtime* + cuDNN; the torch wheels bundle their
# own CUDA libs, so 12.8.1 base + cu128 torch is consistent.
#
# Alternative Blackwell-ready base: nvcr.io/nvidia/pytorch:25.xx-py3 (ships a
# Blackwell-enabled torch already). We use the slimmer nvidia/cuda runtime + pip
# torch==2.7.x+cu128 to keep the image small and the torch version explicit.

FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/root/.cache/huggingface \
    HOST=0.0.0.0 \
    PORT=8000

# System deps: python 3.11, ffmpeg (mp3/opus/aac encode), libsndfile (soundfile).
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip \
        ffmpeg libsndfile1 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# 1) Blackwell-correct PyTorch FIRST, pinned, from the cu128 index. Doing this
#    before requirements.txt guarantees no transitive dep silently downgrades
#    torch to a non-sm_120 wheel.
RUN python -m pip install --upgrade pip \
    && python -m pip install \
        --index-url https://download.pytorch.org/whl/cu128 \
        torch==2.7.1 torchaudio==2.7.1

# 2) Model + server deps (torch already satisfied, so pip won't refetch it).
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install -r /app/requirements.txt

COPY server.py /app/server.py

EXPOSE 8000

# Single worker: the model is large and held in VRAM; one process per GPU slice.
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
