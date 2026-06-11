# kokoro-gpu — baked image for fast restart recovery (issue #408)
#
# Replaces the startup-pip approach in kokoro-gpu-deployment.yaml: that installs
# kokoro + misaki[en] + deps at container start (~20min over the flaky SN->PyPI
# link), so a restart = ~20min TTS recovery. Baking the deps makes restart
# recovery ~30s (model still cached on the PVC).
#
# Build (in-cluster Kaniko recommended — avoids the laptop link; needs the
# harbor-isa dockerconfig + hostAliases core.harbor.domain->10.43.56.153 +
# --insecure/--skip-tls-verify). Local build alternative:
#   docker buildx build --platform linux/amd64 \
#     -t core.harbor.domain/isa/kokoro-gpu:cu128-v1 --push \
#     deployments/kubernetes/production/manifests/gpu/images/kokoro-gpu
#
# sm_120: built on the baked cu128 PyTorch base (sm_120-capable). Kokoro uses
# standard torch ops (no flash-attn), verified: 'torch 2.8.0+cu128 ... sm (12,0)'.
FROM core.harbor.domain/isa/pytorch:2.8.0-cuda12.8-cudnn9-runtime

# espeak-ng: misaki[en] G2P fallback for OOV words. git: some deps build from VCS.
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends espeak-ng git \
 && rm -rf /var/lib/apt/lists/*

# Deps only — torch is pre-baked (+cu128 sm_120). pip must NOT replace it; the
# guard fails the build if kokoro's resolver clobbers torch off the cu128 wheel.
RUN pip install --no-cache-dir --retries 10 --timeout 300 --prefer-binary \
        kokoro==0.9.4 "misaki[en]==0.9.4" soundfile==0.12.1 numpy==1.26.4 \
        fastapi==0.115.6 uvicorn==0.34.0 \
 && python -c "import torch,sys; v=torch.__version__; assert 'cu12' in v, 'torch clobbered: %s'%v; print('[build-guard] torch', v, 'cuda', torch.version.cuda)"

COPY server.py /opt/kokoro/server.py

ENV KOKORO_LANG=a \
    DEFAULT_VOICE=af_nicole \
    HF_HOME=/root/.cache/huggingface \
    HF_HUB_DISABLE_XET=1

EXPOSE 8880
CMD ["python", "/opt/kokoro/server.py"]
