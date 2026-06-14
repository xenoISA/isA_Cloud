#!/usr/bin/env bash
#
# Build + push the Qwen3-TTS OpenAI-compatible server image to Harbor.
#
# DO NOT run this from the authoring agent — it is for the operator. It performs
# a network build (pulls the cu128 CUDA base + torch wheels) and pushes to the
# production registry. Run it on a machine that can reach core.harbor.domain and
# is `docker login`-ed to it.
#
# Why buildx + --platform linux/amd64: the SN cluster nodes are amd64; building on
# an arm64 workstation (Apple Silicon) without this flag produces an unrunnable
# arm64 image. buildx cross-builds the amd64 image regardless of build host.
#
# Usage:
#   ./build.sh            # build + push 0.1.0
#   VERSION=0.1.1 ./build.sh
#   PUSH=false ./build.sh # build only, no push (local smoke test)
set -euo pipefail

REGISTRY="${REGISTRY:-core.harbor.domain}"
PROJECT="${PROJECT:-isa}"
IMAGE="${IMAGE:-qwen3-tts}"
VERSION="${VERSION:-0.1.0}"
PLATFORM="${PLATFORM:-linux/amd64}"
PUSH="${PUSH:-true}"

TAG="${REGISTRY}/${PROJECT}/${IMAGE}:${VERSION}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ">> Building ${TAG} for ${PLATFORM}"
echo ">> Build context: ${SCRIPT_DIR}"

# Ensure a buildx builder exists (idempotent).
docker buildx inspect isa-builder >/dev/null 2>&1 || \
    docker buildx create --name isa-builder --use

PUSH_FLAG="--load"          # default: load amd64 image into local docker
if [[ "${PUSH}" == "true" ]]; then
    PUSH_FLAG="--push"      # build + push in one shot (required for multi-arch)
fi

docker buildx build \
    --builder isa-builder \
    --platform "${PLATFORM}" \
    --tag "${TAG}" \
    ${PUSH_FLAG} \
    "${SCRIPT_DIR}"

echo ">> Done: ${TAG}"
if [[ "${PUSH}" == "true" ]]; then
    echo ">> Pushed to ${REGISTRY}/${PROJECT}/${IMAGE}"
else
    echo ">> Local-only build (PUSH=false). To push: PUSH=true ./build.sh"
fi
