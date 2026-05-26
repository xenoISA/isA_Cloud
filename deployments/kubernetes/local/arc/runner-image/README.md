# isA ARC runner image

Custom runner image for the local-kind ARC cluster. Pre-bakes the toolchains
that `actions/setup-*` actions would otherwise download per-job — the kind
cluster's egress is too slow (~150 KB/s observed in #306) for the actions'
inactivity timeout, so downloads abort and jobs fail.

## What's pre-installed

| Toolchain | Versions | Tool-cache layout |
|---|---|---|
| Python | `3.11.15`, `3.12.13` | `${RUNNER_TOOL_CACHE}/Python/<version>/<arch>/` with `<arch>.complete` |
| Node.js | `20.18.1`, `22.18.0` | `${RUNNER_TOOL_CACHE}/node/<version>/<arch>/` with `<arch>.complete` |
| pnpm | `9.15.0` | `/usr/local/bin/pnpm` (also reachable from Node 20 bin dir) |
| uv | `0.5.11` | `/usr/local/bin/uv`, `/usr/local/bin/uvx` |

System packages: `build-essential`, `git`, `jq`, `curl`, `file`, `unzip`,
`xz-utils`, `python3-pip`, plus the libs needed to compile native Python
wheels (`libssl-dev`, `libffi-dev`, `zlib1g-dev`).

The cache layout matches what `actions/setup-python@v5` and
`actions/setup-node@v4` look for, so workflows pinning
`python-version: '3.11'` or `node-version: '20'` hit the cache and skip
the download path.

## When to rebuild

Bump the version `ARG`s in [`Dockerfile`](Dockerfile) and re-run
[`../scripts/build-runner-image.sh`](../scripts/build-runner-image.sh) when:

- A pilot repo pins a new Python / Node minor that misses the cache.
- A security advisory affects `uv`, `pnpm`, or the actions/runner base.
- The actions/runner base image releases a new patch.

Workflows that ask for a version not in the cache still work — they fall
through to the slow download path, which is the signal to refresh.

## Build + load into kind

```bash
./deployments/kubernetes/local/arc/scripts/build-runner-image.sh
```

The script tags the image as `isa-arc-runner:<version>` (read from the
`ISA_RUNNER_IMAGE_TAG` env or `0.1.0`), builds for the host's architecture
only (kind is single-arch), and `kind load`s it into the cluster.
`imagePullPolicy: IfNotPresent` in `runner-scale-set.yaml` means kubelet
uses the loaded image without trying to pull from a registry.

## Not in scope here

- Multi-arch builds — kind runs one platform per cluster.
- Pushing to a registry — staging/prod will need this (#291). Local dev is
  build-and-load.
- Docker-in-docker tooling — provided by the chart's `dind` sidecar, not
  this image.
