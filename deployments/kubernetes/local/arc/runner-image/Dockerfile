# =============================================================================
# isA ARC runner image — pre-bakes toolchains so jobs do not depend on
# per-job downloads through the local-kind cluster's slow egress.
#
# Context: actions/setup-python@v5 aborts when pulling ~112 MB tarballs from
# release-assets.githubusercontent.com through the kind cluster (see #306 —
# observed bandwidth ~150 KB/s, action inactivity timeout ~17 s). Same risk
# applies to setup-node and any other download-and-extract toolchain action.
#
# Strategy: stage downloads on the BUILD host (Docker daemon network, fast),
# unpack into the layout that actions/setup-* read from RUNNER_TOOL_CACHE,
# drop a `<version>.complete` marker, and let setup-python / setup-node hit
# the cache and skip the download path entirely.
#
# Build + load into kind:
#   ./deployments/kubernetes/local/arc/scripts/build-runner-image.sh
#
# Refresh cadence: bump the version ARGs below and rebuild whenever any of
# the pilot repos pin a new Python / Node / pnpm / uv version. Stale tool
# cache entries are fine to leave behind; jobs that ask for a newer version
# will fall through to the download path (slow, but a clear signal to update
# the image).
# =============================================================================

# Pin the upstream runner base by digest in production; floating tag is OK on
# the local kind cluster where we control the rebuild cadence.
FROM ghcr.io/actions/actions-runner:2.330.0

USER root

# -----------------------------------------------------------------------------
# Versions — bump and rebuild together
# -----------------------------------------------------------------------------
# These match the GitHub-hosted-runner toolset closely so workflows that
# specify `python-version: '3.11'` or `node-version: '20'` hit the cache.
# Python release tags come from the actions/python-versions manifest:
#   https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json
# Bumping a version → look up the exact `<version>-<asset_id>` tag there.
ARG PYTHON_311=3.11.15
ARG PYTHON_312=3.12.13
ARG PYTHON_RELEASE_TAG_311=3.11.15-22631496413
ARG PYTHON_RELEASE_TAG_312=3.12.13-22652080177
# Must match the runner base image's Ubuntu version (currently 22.04 / GLIBC
# 2.35). When upgrading the FROM line, check `cat /etc/os-release` in a
# debug pod and bump this in lockstep — Python tarballs built for 24.04
# require GLIBC 2.38 and will not load against 22.04.
ARG PYTHON_OS=linux-22.04

ARG NODE_20=20.18.1
ARG NODE_22=22.18.0

ARG PNPM_VERSION=9.15.0
ARG UV_VERSION=0.5.11

# -----------------------------------------------------------------------------
# Base system packages — the official runner image is intentionally minimal.
# -----------------------------------------------------------------------------
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        file \
        git \
        gnupg \
        jq \
        libffi-dev \
        libssl-dev \
        make \
        pkg-config \
        python3-pip \
        unzip \
        xz-utils \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Tool cache root that actions/setup-* read.
# -----------------------------------------------------------------------------
ENV RUNNER_TOOL_CACHE=/opt/hostedtoolcache
RUN mkdir -p "${RUNNER_TOOL_CACHE}" && chown -R runner:runner "${RUNNER_TOOL_CACHE}"

# -----------------------------------------------------------------------------
# Python — pre-populate $RUNNER_TOOL_CACHE/Python/<version>/<arch>
#
# actions/setup-python looks for `<arch>.complete` adjacent to the version
# directory; without that marker the action treats the cache as empty and
# falls back to its (slow, abort-prone) download path.
# -----------------------------------------------------------------------------
RUN set -eux; \
    HOST_ARCH=$(uname -m); \
    case "${HOST_ARCH}" in \
        aarch64) ARCH=arm64 ;; \
        x86_64)  ARCH=x64   ;; \
        *) echo "unsupported arch: ${HOST_ARCH}" >&2; exit 1 ;; \
    esac; \
    for entry in "${PYTHON_311}:${PYTHON_RELEASE_TAG_311}" "${PYTHON_312}:${PYTHON_RELEASE_TAG_312}"; do \
        VERSION="${entry%%:*}"; \
        TAG="${entry#*:}"; \
        DEST="${RUNNER_TOOL_CACHE}/Python/${VERSION}/${ARCH}"; \
        mkdir -p "${DEST}"; \
        curl -fL --retry 5 --retry-delay 5 \
            "https://github.com/actions/python-versions/releases/download/${TAG}/python-${VERSION}-${PYTHON_OS}-${ARCH}.tar.gz" \
            | tar -xz -C "${DEST}"; \
        touch "${RUNNER_TOOL_CACHE}/Python/${VERSION}/${ARCH}.complete"; \
    done; \
    chown -R runner:runner "${RUNNER_TOOL_CACHE}/Python"

# -----------------------------------------------------------------------------
# Node.js — same tool-cache pattern.
# -----------------------------------------------------------------------------
RUN set -eux; \
    HOST_ARCH=$(uname -m); \
    case "${HOST_ARCH}" in \
        aarch64) ARCH=arm64 ;; \
        x86_64)  ARCH=x64   ;; \
        *) echo "unsupported arch: ${HOST_ARCH}" >&2; exit 1 ;; \
    esac; \
    for VERSION in "${NODE_20}" "${NODE_22}"; do \
        DEST="${RUNNER_TOOL_CACHE}/node/${VERSION}/${ARCH}"; \
        mkdir -p "${DEST}"; \
        curl -fL --retry 5 --retry-delay 5 \
            "https://nodejs.org/dist/v${VERSION}/node-v${VERSION}-linux-${ARCH}.tar.xz" \
            | tar -xJ --strip-components=1 -C "${DEST}"; \
        touch "${RUNNER_TOOL_CACHE}/node/${VERSION}/${ARCH}.complete"; \
    done; \
    chown -R runner:runner "${RUNNER_TOOL_CACHE}/node"

# -----------------------------------------------------------------------------
# pnpm — install into the Node 20 toolchain so the binary travels with the
# default Node version most workflows pick. Workflows that activate a
# different Node still resolve pnpm via PATH because we also symlink it into
# /usr/local/bin.
# -----------------------------------------------------------------------------
RUN set -eux; \
    HOST_ARCH=$(uname -m); \
    case "${HOST_ARCH}" in \
        aarch64) ARCH=arm64 ;; \
        x86_64)  ARCH=x64   ;; \
    esac; \
    NODE_BIN="${RUNNER_TOOL_CACHE}/node/${NODE_20}/${ARCH}/bin"; \
    # npm resolves `node` via `/usr/bin/env node`. The tool-cache bin dir
    # is not on PATH outside an active setup-node session, so we symlink
    # node + pnpm + pnpx into /usr/local/bin and run the install with
    # NODE_BIN prepended.
    ln -sf "${NODE_BIN}/node" /usr/local/bin/node; \
    PATH="${NODE_BIN}:${PATH}" "${NODE_BIN}/npm" install -g "pnpm@${PNPM_VERSION}"; \
    ln -sf "${NODE_BIN}/pnpm" /usr/local/bin/pnpm; \
    ln -sf "${NODE_BIN}/pnpx" /usr/local/bin/pnpx

# -----------------------------------------------------------------------------
# uv — Astral's installer drops a single binary; we pin a version and place
# it on PATH for both root and runner.
# -----------------------------------------------------------------------------
RUN set -eux; \
    HOST_ARCH=$(uname -m); \
    case "${HOST_ARCH}" in \
        aarch64) ARCH=aarch64 ;; \
        x86_64)  ARCH=x86_64  ;; \
    esac; \
    curl -fL --retry 5 --retry-delay 5 \
        "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${ARCH}-unknown-linux-gnu.tar.gz" \
        | tar -xz -C /tmp; \
    mv "/tmp/uv-${ARCH}-unknown-linux-gnu/uv"   /usr/local/bin/uv; \
    mv "/tmp/uv-${ARCH}-unknown-linux-gnu/uvx"  /usr/local/bin/uvx; \
    chmod +x /usr/local/bin/uv /usr/local/bin/uvx; \
    rm -rf "/tmp/uv-${ARCH}-unknown-linux-gnu"

# -----------------------------------------------------------------------------
# Drop privileges. ARC runs `/home/runner/run.sh` as the runner user.
# -----------------------------------------------------------------------------
USER runner
WORKDIR /home/runner
